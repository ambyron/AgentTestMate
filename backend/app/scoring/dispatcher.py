"""RuleDispatcher — plugin-aware scoring rule dispatcher."""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
from pathlib import Path
from typing import Any

from app.config import settings
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
                evaluation_failed=True,
            )
        try:
            result = await self._score_with_deadline(scorer, ctx)
            result.data_type = getattr(scorer, "score_data_type", "NUMERIC")
            # A score of exactly 0.0 produced by an evaluator error is not a real
            # evaluation result — normalize the flag so the aggregator can skip it.
            if result.error and result.score == 0.0:
                result.evaluation_failed = True
            return result
        except asyncio.TimeoutError:
            return ScoreResult(
                rule_id=ctx.rule_config.get("_rule_id", ""),
                rule_type=rule_type,
                score=0.0,
                threshold=ctx.rule_threshold,
                passed=False,
                error=f"评估超时（超过硬上限 {settings.ai_judge_hard_deadline_ms}ms）",
                evaluation_failed=True,
                details={"ai_error": True, "error_kinds": ["timeout"]},
            )
        except Exception as e:
            return ScoreResult(
                rule_id=ctx.rule_config.get("_rule_id", ""),
                rule_type=rule_type,
                score=0.0,
                threshold=ctx.rule_threshold,
                passed=False,
                error=str(e),
                evaluation_failed=True,
            )

    @staticmethod
    async def _score_with_deadline(scorer: BaseScorer, ctx: ScoringContext) -> ScoreResult:
        """Run a scorer under a hard wall-clock ceiling.

        The httpx timeout only bounds a *single* HTTP attempt; retries multiply
        that. This ceiling guarantees that no rule can ever hang a case forever.
        """
        hard_ms = ctx.parameters.get("hard_deadline_ms") if ctx.parameters else None
        try:
            hard_ms = int(hard_ms) if hard_ms else settings.ai_judge_hard_deadline_ms
        except (TypeError, ValueError):
            hard_ms = settings.ai_judge_hard_deadline_ms
        if hard_ms <= 0:
            return await scorer.score(ctx)
        return await asyncio.wait_for(scorer.score(ctx), timeout=hard_ms / 1000.0)
