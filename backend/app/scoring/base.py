"""BaseScorer — abstract base for all scorer plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.scoring import ScoringContext, ScoreResult


class BaseScorer(ABC):
    """Abstract base class for all scoring rule implementations."""

    @property
    @abstractmethod
    def rule_type(self) -> str:
        """Unique rule type identifier."""

    # Scoring data type: NUMERIC / BOOLEAN / CATEGORICAL
    # Determines how score is computed, aggregated, and displayed.
    score_data_type: str = "NUMERIC"

    @abstractmethod
    async def score(self, ctx: ScoringContext) -> ScoreResult:
        """Evaluate a single test case against this rule."""
