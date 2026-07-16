"""AI Judge Scorer — strategy-based LLM-as-a-judge evaluation.

Replaces the previous 3-class approach (LLMJudgeScorer / LLMJudgeRefScorer /
LLMJudgeRubricScorer) with a single scorer that dispatches to the appropriate
EvalStrategy based on the evaluation strategy setting.
"""

from __future__ import annotations

from app.judge import (
    ArbitrationEngine,
    ModelRouter,
    PromptContext,
    PromptRenderer,
    JudgeResponse,
)
from app.judge.strategies import get_strategy, STRATEGY_REGISTRY
from app.scoring.base import BaseScorer
from app.scoring import ScoringContext, ScoreResult

import logging

logger = logging.getLogger("agentmate.judge.scorer")

# Strategy name → rule_type mapping for backward compatibility
_STRATEGY_TO_RULE_TYPE = {
    "simple": "llm_judge",
    "reference": "llm_judge_ref",
    "rubric": "llm_judge_rubric",
    "chain_of_thought": "llm_judge",
    "few_shot": "llm_judge",
    "pairwise": "llm_judge",
}

# Backward compatibility: rule_type → default strategy
_RULE_TYPE_TO_STRATEGY = {
    "llm_judge": "simple",
    "llm_judge_ref": "reference",
    "llm_judge_rubric": "rubric",
}


class LLMJudgeScorer(BaseScorer):
    """Single AI-powered scorer using strategy-based prompt engineering.

    Evaluates LLM responses using configurable strategies:
    - simple:            general AI evaluation
    - reference:         reference-based (compares with expected_output)
    - rubric:            multi-dimension rubric evaluation
    - chain_of_thought:  step-by-step reasoning before scoring
    - few_shot:          examples-guided evaluation
    - pairwise:          compare two outputs side by side
    """

    def __init__(self):
        self.prompt_renderer = PromptRenderer()
        self.model_router = ModelRouter()
        self.arbitration = ArbitrationEngine()

    @property
    def rule_type(self) -> str:
        return "llm_judge"

    async def score(self, ctx: ScoringContext) -> ScoreResult:
        # Determine strategy — explicit setting > inference from rule_type > default
        strategy_name = (
            ctx.eval_strategy
            or _RULE_TYPE_TO_STRATEGY.get(ctx.rule_type)
            or "simple"
        )
        strategy = get_strategy(strategy_name)

        # Build prompt context
        prompt_ctx = PromptContext(
            input=ctx.case_input,
            expected_output=ctx.case_expected_output or "",
            actual_output=ctx.actual_output,
            rubric=ctx.rubric_text or "",
            criteria=ctx.criteria or "",
            pairwise_alternative=ctx.pairwise_alternative or "",
            few_shot_examples=ctx.few_shot_examples or [],
            output_schema=ctx.output_schema or {},
        )

        # Resolve prompt template: explicit sections > template string > strategy default
        system_prompt = ctx.system_prompt
        user_template = ctx.prompt_template
        system_prompt, user_prompt = strategy.build_prompt(
            prompt_ctx, system_prompt, user_template,
        )
        full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt

        # Resolve judge models
        judge_models = ctx.judge_models or {}
        model_ids = ctx.rule_config.get("judge_model_ids", list(judge_models.keys()))
        params = ctx.parameters or {}

        # Invoke all judge models in parallel
        from asyncio import gather
        results = await gather(*[
            self.model_router.invoke(judge_models[mid], full_prompt, params)
            for mid in model_ids if mid in judge_models
        ], return_exceptions=True)

        valid_results: list[JudgeResponse] = []
        for r in results:
            if isinstance(r, JudgeResponse):
                # Apply strategy-specific output parsing
                parsed = strategy.parse_response(
                    r.raw_response or "", ctx.output_schema,
                )
                r.score = parsed.get("score", r.score)
                r.reasoning = parsed.get("reasoning", r.reasoning)
                r.dimension_scores = parsed.get("dimension_scores", r.dimension_scores)
                valid_results.append(r)
            elif isinstance(r, Exception):
                logger.warning("[SCORER] Judge model call failed: %s", r)

        if not valid_results:
            return ScoreResult(
                rule_id=ctx.rule_config.get("_rule_id", ""),
                rule_type=self.rule_type,
                score=0.0,
                threshold=ctx.rule_threshold,
                passed=False,
                error="All AI judge calls failed",
            )

        # Arbitration (multi-judge consensus)
        arbitration = None
        if len(valid_results) > 1:
            arb_config = ctx.arbitration_config or {}
            arbitration = await self.arbitration.arbitrate(
                valid_results,
                strategy=arb_config.get("strategy", "avg"),
                weights=arb_config.get("weights"),
            )
            final_score = arbitration.final_score
        else:
            final_score = valid_results[0].score

        primary = valid_results[0]
        return ScoreResult(
            rule_id=ctx.rule_config.get("_rule_id", ""),
            rule_type=_STRATEGY_TO_RULE_TYPE.get(strategy_name, self.rule_type),
            score=final_score,
            threshold=ctx.rule_threshold,
            passed=final_score >= ctx.rule_threshold,
            details={
                "strategy": strategy_name,
                "judge_model_ids": model_ids,
            },
            ai_reasoning=primary.reasoning,
            ai_dimension_scores=primary.dimension_scores,
            ai_arbitration=arbitration.dict() if arbitration else None,
        )



