"""Eval prompt template management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User
from app.judge import PromptRenderer, PromptContext
from app.judge.strategies import get_strategy

router = APIRouter(prefix="/eval-prompts", tags=["Eval Prompts"])


def _normalize_json_fields(data: dict) -> dict:
    """Convert JSON string fields to Python objects for JSON column types."""
    import json as _json
    for field in ("output_schema", "few_shot_examples", "variables", "tags"):
        val = data.get(field)
        if isinstance(val, str) and val.strip():
            try:
                data[field] = _json.loads(val)
            except (_json.JSONDecodeError, TypeError) as exc:
                raise HTTPException(400, f"字段 '{field}' 不是合法的 JSON: {exc}")
        elif isinstance(val, str) and not val.strip():
            # Empty string → remove key so ORM default applies
            data.pop(field, None)
    return data


@router.post("")
async def create_prompt(data: dict, db: AsyncSession = Depends(get_db),
                        current_space: str | None = Depends(get_current_space)):
    data = _normalize_json_fields(data)
    # Validate required fields
    if not data.get("name"):
        raise HTTPException(400, "字段 'name' 不能为空")
    if not data.get("user_prompt_template"):
        raise HTTPException(400, "字段 'user_prompt_template'（User Prompt 模板）不能为空")
    # If only old-style template_content is provided, copy to user_prompt_template
    if not data.get("user_prompt_template") and data.get("template_content"):
        data["user_prompt_template"] = data.pop("template_content")
    if current_space:
        data["space_id"] = current_space
    return await repo.create_eval_prompt(db, data)


@router.get("")
async def list_prompts(db: AsyncSession = Depends(get_db),
                       current_space: str | None = Depends(get_current_space)):
    return await repo.list_eval_prompts(db, space_id=current_space)


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: str, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      current_space: str | None = Depends(get_current_space)):
    ep = await repo.get_eval_prompt(db, prompt_id)
    if not ep:
        raise HTTPException(404, "Eval prompt not found")
    if not await repo.verify_space_access(db, repo.EvalPromptTemplate, prompt_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return ep


@router.put("/{prompt_id}")
async def update_prompt(prompt_id: str, data: dict, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.EvalPromptTemplate, prompt_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    data = _normalize_json_fields(data)
    if not data.get("name"):
        raise HTTPException(400, "字段 'name' 不能为空")
    ep = await repo.update_eval_prompt(db, prompt_id, data)
    if not ep:
        raise HTTPException(404, "Eval prompt not found")
    return ep


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(prompt_id: str, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.EvalPromptTemplate, prompt_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_eval_prompt(db, prompt_id):
        raise HTTPException(404, "Eval prompt not found")


@router.post("/{prompt_id}/render")
async def render_prompt(prompt_id: str, data: dict, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         current_space: str | None = Depends(get_current_space)):
    """Render a prompt template with sample data — no API call, returns rendered text."""
    if not await repo.verify_space_access(db, repo.EvalPromptTemplate, prompt_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    ep = await repo.get_eval_prompt(db, prompt_id)
    if not ep:
        raise HTTPException(404, "Eval prompt not found")

    strategy_name = data.get("strategy") or ep.strategy or "simple"
    strategy = get_strategy(strategy_name)

    prompt_ctx = PromptContext(
        input=data.get("input", ""),
        expected_output=data.get("expected_output", ""),
        actual_output=data.get("actual_output", ""),
        rubric=data.get("rubric", ""),
        criteria=data.get("criteria", ""),
        pairwise_alternative=data.get("pairwise_alternative", ""),
        few_shot_examples=data.get("few_shot_examples") or ep.few_shot_examples or [],
        output_schema=data.get("output_schema") or ep.output_schema or {},
    )

    system_prompt = data.get("system_prompt") or ep.system_prompt
    user_template = data.get("user_prompt_template") or ep.user_prompt_template or ep.template_content or ""
    sp, up = strategy.build_prompt(prompt_ctx, system_prompt, user_template)

    return {
        "strategy": strategy_name,
        "system_prompt": sp,
        "user_prompt": up,
        "rendered": f"{sp}\n\n{up}" if sp else up,
    }


@router.post("/{prompt_id}/execute")
async def execute_prompt(prompt_id: str, data: dict, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user),
                          current_space: str | None = Depends(get_current_space)):
    """Execute AI judge scoring with a prompt template — renders + calls LLM."""
    from app.judge import ModelRouter

    if not await repo.verify_space_access(db, repo.EvalPromptTemplate, prompt_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    ep = await repo.get_eval_prompt(db, prompt_id)
    if not ep:
        raise HTTPException(404, "Eval prompt not found")

    judge_id = data.get("ai_judge_model_id")
    if not judge_id:
        raise HTTPException(400, "ai_judge_model_id is required")

    judge = await repo.get_ai_judge(db, judge_id)
    if not judge:
        raise HTTPException(404, "AI Judge model not found")

    strategy_name = data.get("strategy") or ep.strategy or "simple"
    strategy = get_strategy(strategy_name)

    prompt_ctx = PromptContext(
        input=data.get("input", ""),
        expected_output=data.get("expected_output", ""),
        actual_output=data.get("actual_output", ""),
        rubric=data.get("rubric", ""),
        criteria=data.get("criteria", ""),
        pairwise_alternative=data.get("pairwise_alternative", ""),
        few_shot_examples=data.get("few_shot_examples") or ep.few_shot_examples or [],
        output_schema=data.get("output_schema") or ep.output_schema or {},
    )

    system_prompt = data.get("system_prompt") or ep.system_prompt
    user_template = data.get("user_prompt_template") or ep.user_prompt_template or ep.template_content or ""
    sp, up = strategy.build_prompt(prompt_ctx, system_prompt, user_template)
    full_prompt = f"{sp}\n\n{up}" if sp else up

    model_cfg = {
        "provider": judge.provider,
        "model_name": judge.model_name,
        "api_base_url": judge.api_base_url,
        "auth_credentials": judge.auth_credentials or "",
    }
    router = ModelRouter()
    result = await router.invoke(model_cfg, full_prompt, {"max_tokens": 2048, "temperature": 0.0})

    # Parse with strategy
    parsed = strategy.parse_response(result.raw_response or "", ep.output_schema or {})

    return {
        "strategy": strategy_name,
        "score": parsed.get("score", 0.0),
        "reasoning": parsed.get("reasoning", result.reasoning),
        "dimension_scores": parsed.get("dimension_scores", result.dimension_scores),
        "raw_response": result.raw_response,
        "error": result.error,
        "latency_ms": result.latency_ms,
        "rendered_prompt": full_prompt,
    }


@router.get("/strategies/list")
async def list_strategies():
    """Return available evaluation strategies."""
    from app.judge.strategies import STRATEGY_REGISTRY
    return [
        {"value": k, "label": _strategy_label(k)}
        for k in STRATEGY_REGISTRY
    ]


def _strategy_label(name: str) -> str:
    labels = {
        "simple": "通用评分 (Simple)",
        "reference": "参照对比 (Reference)",
        "rubric": "多维度评分 (Rubric)",
        "chain_of_thought": "思维链评分 (Chain-of-Thought)",
        "few_shot": "少样本评分 (Few-Shot)",
        "pairwise": "对比选择 (Pairwise)",
    }
    return labels.get(name, name)
