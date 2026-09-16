"""AI Judge Scorer — strategy-based LLM-as-a-judge evaluation.

Replaces the previous 3-class approach (LLMJudgeScorer / LLMJudgeRefScorer /
LLMJudgeRubricScorer) with a single scorer that dispatches to the appropriate
EvalStrategy based on the evaluation strategy setting.
"""

from __future__ import annotations

import asyncio
import random

from app.config import settings
from app.judge import (
    ArbitrationEngine,
    ModelRouter,
    PromptContext,
    PromptRenderer,
    JudgeResponse,
    ERROR_UNKNOWN,
)
from app.judge.strategies import get_strategy
from app.scoring.base import BaseScorer
from app.scoring import ScoringContext, ScoreResult

import logging

logger = logging.getLogger("agentmate.judge.scorer")

#: Fallback per-strategy minimum max_tokens — long-form strategies need more room
#: to avoid truncated (unparseable) JSON output.
_STRATEGY_MIN_TOKENS = {
    "simple": 2048,
    "reference": 4096,
    "rubric": 4096,
    "chain_of_thought": 4096,
    "few_shot": 4096,
    "pairwise": 3000,
}

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

    async def _invoke_with_retry(self, model_cfg: dict, user_prompt: str,
                                 params: dict, system_prompt: str | None) -> JudgeResponse:
        """Invoke one judge model with exponential backoff on retryable errors.

        Only transient failures (timeout / connection / 429 / 5xx) are retried;
        auth and bad-request errors fail fast, and parse errors are not retried
        because they are usually caused by output truncation.
        """
        try:
            max_retries = int(params.get("max_retries", settings.ai_judge_max_retries))
        except (TypeError, ValueError):
            max_retries = settings.ai_judge_max_retries
        max_retries = max(0, min(max_retries, 5))

        last: JudgeResponse | None = None
        for attempt in range(1, max_retries + 2):
            result = await self.model_router.invoke(
                model_cfg, user_prompt, params, system_prompt,
            )
            result.attempts = attempt
            if result.error is None or not result.retryable:
                return result
            last = result
            if attempt <= max_retries:
                delay = min(1.0 * (2 ** (attempt - 1)), 8.0) + random.uniform(0, 0.3)
                logger.warning(
                    "[JUDGE] retry %d/%d after %s (kind=%s) in %.2fs",
                    attempt, max_retries, result.error, result.error_kind, delay,
                )
                await asyncio.sleep(delay)
        return last or JudgeResponse(error="judge invocation failed", error_kind=ERROR_UNKNOWN)

    @staticmethod
    def _effective_params(params: dict, strategy_name: str) -> dict:
        """Apply the strategy's minimum max_tokens floor to the judge params."""
        effective = dict(params or {})
        floor = _STRATEGY_MIN_TOKENS.get(strategy_name, 2048)
        try:
            current = int(effective.get("max_tokens") or 0)
        except (TypeError, ValueError):
            current = 0
        if current < floor:
            effective["max_tokens"] = floor
        return effective

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

        # Resolve judge models
        judge_models = ctx.judge_models or {}
        model_ids = ctx.rule_config.get("judge_model_ids", list(judge_models.keys()))
        params = self._effective_params(ctx.parameters or {}, strategy_name)

        # Invoke all judge models in parallel (system / user sent as separate roles)
        results = await asyncio.gather(*[
            self._invoke_with_retry(judge_models[mid], user_prompt, params, system_prompt)
            for mid in model_ids if mid in judge_models
        ], return_exceptions=True)

        valid_results: list[JudgeResponse] = []
        failed_results: list[tuple[str, str]] = []  # (model_id, error_kind)
        for mid, r in zip([m for m in model_ids if m in judge_models], results):
            if isinstance(r, JudgeResponse):
                # A transport-level failure is carried through as a hard failure.
                if r.error is not None and r.raw_response == r.error:
                    kind = r.error_kind or ERROR_UNKNOWN
                    failed_results.append((mid, kind))
                    logger.warning("[SCORER] judge model %s failed (%s): %s", mid, kind, r.error)
                    continue
                # Apply strategy-specific output parsing
                parsed = strategy.parse_response(
                    r.raw_response or "", ctx.output_schema,
                )
                # Parse failure → not a real score; record it as a failed evaluation
                if parsed.get("parse_failed"):
                    kind = parsed.get("error_kind") or ERROR_UNKNOWN
                    failed_results.append((mid, kind))
                    logger.warning(
                        "[SCORER] judge model %s produced unparseable output (%s)", mid, kind,
                    )
                    continue
                r.score = parsed.get("score", r.score)
                r.reasoning = parsed.get("reasoning", r.reasoning)
                r.dimension_scores = parsed.get("dimension_scores", r.dimension_scores)
                valid_results.append(r)
            else:
                failed_results.append((str(r), ERROR_UNKNOWN))
                logger.warning("[SCORER] Judge model call raised: %s", r)

        rule_id = ctx.rule_config.get("_rule_id", "")
        resolved_rule_type = _STRATEGY_TO_RULE_TYPE.get(strategy_name, self.rule_type)

        # Every judge model failed — mark as an evaluation failure, NOT a real 0 score.
        if not valid_results:
            kinds = [k for _, k in failed_results]
            return ScoreResult(
                rule_id=rule_id,
                rule_type=resolved_rule_type,
                score=0.0,
                threshold=ctx.rule_threshold,
                passed=False,
                error=f"AI 评估调用失败（{', '.join(sorted(set(kinds))) or 'unknown'}）",
                evaluation_failed=True,
                details={
                    "strategy": strategy_name,
                    "judge_model_ids": model_ids,
                    "ai_error": True,
                    "error_kinds": kinds,
                },
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
        # Partial failure: some judges succeeded, some did not. The score is
        # real (derived from the successful judges) but the anomaly is recorded.
        partial = bool(failed_results)
        details = {
            "strategy": strategy_name,
            "judge_model_ids": model_ids,
        }
        if partial:
            details["partial_failure"] = True
            details["failed_judges"] = [{"model_id": m, "error_kind": k} for m, k in failed_results]
        return ScoreResult(
            rule_id=rule_id,
            rule_type=resolved_rule_type,
            score=final_score,
            threshold=ctx.rule_threshold,
            passed=final_score >= ctx.rule_threshold,
            details=details,
            ai_reasoning=primary.reasoning,
            ai_dimension_scores=primary.dimension_scores,
            ai_arbitration=arbitration.dict() if arbitration else None,
        )



