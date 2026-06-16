"""Scoring data structures shared across all scorer plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoringContext:
    """Context passed to every scorer during evaluation."""
    case_input: str
    case_expected_output: str | None
    actual_output: str
    rule_config: dict
    rule_type: str
    rule_weight: float
    rule_threshold: float
    judge_models: dict[str, Any] = field(default_factory=dict)
    prompt_template: str | None = None
    rubric_text: str | None = None
    criteria: str | None = None
    parameters: dict | None = None
    arbitration_config: dict | None = None

    # Evaluation strategy (overrides rule_type default)
    eval_strategy: str = "simple"
    # Structured prompt sections
    system_prompt: str | None = None
    output_schema: dict | None = None
    few_shot_examples: list | None = None
    pairwise_alternative: str | None = None  # Second output for pairwise comparison


@dataclass
class ScoreResult:
    """Result from a single rule evaluation."""
    rule_id: str
    rule_type: str
    score: float            # normalized 0.0 ~ 1.0
    raw_score: Any = None
    threshold: float = 0.8
    passed: bool = False
    details: dict | None = None
    ai_reasoning: str | None = None
    ai_dimension_scores: dict | None = None
    ai_arbitration: dict | None = None
    error: str | None = None
    # Multi-type scoring fields
    data_type: str = "NUMERIC"  # NUMERIC / BOOLEAN / CATEGORICAL
    categorical_value: str | None = None  # selected category label
    boolean_value: bool | None = None


@dataclass
class ObjectiveScore:
    name: str
    score: float
    weight: float
    threshold: float
    passed: bool


@dataclass
class CategoryScore:
    name: str
    score: float
    weight: float
    passed: bool


@dataclass
class AggregatedScores:
    total_score: float
    passed: bool
    objective_scores: dict[str, ObjectiveScore]
    category_scores: dict[str, CategoryScore]
