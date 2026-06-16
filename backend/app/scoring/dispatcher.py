"""RuleDispatcher — plugin-aware scoring rule dispatcher."""

from __future__ import annotations

import importlib
import importlib.metadata
from pathlib import Path
from typing import Any

from app.scoring.base import BaseScorer
from app.scoring.builtins import (
    ExactMatchScorer,
    KeywordScorer,
    RegexScorer,
    DurationScorer,
    LengthScorer,
)
from app.scoring import ScoringContext, ScoreResult


class RuleDispatcher:
    """Registry + dispatcher for scorer plugins."""

    def __init__(self):
        self._scorers: dict[str, BaseScorer] = {}

    def register(self, scorer: BaseScorer):
        self._scorers[scorer.rule_type] = scorer

    def discover_plugins(self, plugin_dirs: list[Path] | None = None):
        """Discover via entry_points."""
        try:
            for entry in importlib.metadata.entry_points(group="agentmate.scorers"):
                try:
                    cls = entry.load()
                    self.register(cls())
                except Exception:
                    pass
        except Exception:
            pass

        if plugin_dirs:
            for d in plugin_dirs:
                if not d.exists():
                    continue
                for f in d.glob("*.py"):
                    try:
                        mod_name = f.stem
                        spec = importlib.util.spec_from_file_location(mod_name, f)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(mod)
                            for attr in dir(mod):
                                cls = getattr(mod, attr)
                                if isinstance(cls, type) and issubclass(cls, BaseScorer) and cls is not BaseScorer:
                                    self.register(cls())
                    except Exception:
                        pass

    def register_builtins(self):
        """Register all built-in scorers."""
        for scorer in [
            ExactMatchScorer(),
            KeywordScorer(),
            RegexScorer(),
            DurationScorer(),
            LengthScorer(),
        ]:
            self.register(scorer)

    def get_supported_types(self) -> list[str]:
        return list(self._scorers.keys())

    async def evaluate(self, ctx: ScoringContext, rule_type: str) -> ScoreResult:
        scorer = self._scorers.get(rule_type)
        if scorer is None:
            return ScoreResult(
                rule_id=ctx.rule_config.get("_rule_id", ""),
                rule_type=rule_type,
                score=0.0,
                threshold=ctx.rule_threshold,
                passed=False,
                error=f"No scorer registered for rule_type '{rule_type}'",
            )
        try:
            return await scorer.score(ctx)
        except Exception as e:
            return ScoreResult(
                rule_id=ctx.rule_config.get("_rule_id", ""),
                rule_type=rule_type,
                score=0.0,
                threshold=ctx.rule_threshold,
                passed=False,
                error=str(e),
            )
