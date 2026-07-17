"""AI Judge model management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User

router = APIRouter(prefix="/ai-judges", tags=["AI Judges"])


@router.post("")
async def create_ai_judge(data: dict, db: AsyncSession = Depends(get_db),
                          current_space: str | None = Depends(get_current_space)):
    if current_space:
        data["space_id"] = current_space
    return await repo.create_ai_judge(db, data)


@router.get("")
async def list_ai_judges(provider: str | None = None, db: AsyncSession = Depends(get_db),
                         current_space: str | None = Depends(get_current_space)):
    return await repo.list_ai_judges(db, space_id=current_space, provider=provider)


@router.get("/{judge_id}")
async def get_ai_judge(judge_id: str, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    judge = await repo.get_ai_judge(db, judge_id)
    if not judge:
        raise HTTPException(404, "AI Judge model not found")
    if not await repo.verify_space_access(db, repo.AIJudgeModel, judge_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return judge


@router.put("/{judge_id}")
async def update_ai_judge(judge_id: str, data: dict, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user),
                           current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.AIJudgeModel, judge_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    judge = await repo.update_ai_judge(db, judge_id, data)
    if not judge:
        raise HTTPException(404, "AI Judge model not found")
    return judge


@router.delete("/{judge_id}", status_code=204)
async def delete_ai_judge(judge_id: str, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user),
                           current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.AIJudgeModel, judge_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_ai_judge(db, judge_id):
        raise HTTPException(404, "AI Judge model not found")


@router.post("/{judge_id}/check")
async def check_ai_judge(judge_id: str, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user),
                          current_space: str | None = Depends(get_current_space)):
    """Connectivity check for an AI judge model."""
    if not await repo.verify_space_access(db, repo.AIJudgeModel, judge_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    judge = await repo.get_ai_judge(db, judge_id)
    if not judge:
        raise HTTPException(404, "AI Judge model not found")

    from app.judge import ModelRouter
    router = ModelRouter()

    # Validate required fields before calling
    missing = []
    if not judge.api_base_url:
        missing.append("api_base_url")
    if not judge.auth_credentials:
        missing.append("auth_credentials (API Key)")
    if missing:
        return {
            "reachable": False,
            "response": None,
            "error": f"配置不完整，缺少字段: {', '.join(missing)}",
        }

    model_cfg = {
        "provider": judge.provider or "openai",
        "model_name": judge.model_name or "gpt-4o",
        "api_base_url": judge.api_base_url.rstrip("/"),
        "auth_credentials": judge.auth_credentials or "",
    }
    result = await router.invoke(model_cfg, "Reply with OK if you receive this.", {"max_tokens": 10})
    return {
        "reachable": result.error is None,
        "response": result.raw_response[:200] if result.raw_response else None,
        "error": result.error,
    }


@router.post("/preview-score")
async def preview_ai_score(data: dict, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user),
                            current_space: str | None = Depends(get_current_space)):
    """Preview AI scoring with custom input/output."""
    from app.judge import ModelRouter, PromptRenderer, PromptContext
    from app.judge.scorer import LLMJudgeScorer
    from app.scoring import ScoringContext

    judge_id = data.get("ai_judge_model_id")
    if not judge_id:
        raise HTTPException(400, "ai_judge_model_id is required")

    if not await repo.verify_space_access(db, repo.AIJudgeModel, judge_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")

    judge = await repo.get_ai_judge(db, judge_id)
    if not judge:
        raise HTTPException(404, "AI Judge model not found")

    scorer = LLMJudgeScorer()
    judge_models = {judge.id: {
        "provider": judge.provider, "model_name": judge.model_name,
        "api_base_url": judge.api_base_url, "auth_credentials": judge.auth_credentials or "",
    }}

    ctx = ScoringContext(
        case_input=data.get("input", ""),
        case_expected_output=data.get("expected_output"),
        actual_output=data.get("actual_output", ""),
        rule_config={"judge_model_ids": [judge.id], "criteria": data.get("criteria", "")},
        rule_type="llm_judge",
        rule_weight=1.0,
        rule_threshold=0.7,
        judge_models=judge_models,
        prompt_template=data.get("prompt_template"),
        rubric_text=data.get("rubric_text"),
    )
    result = await scorer.score(ctx)
    return {"score": result.score, "reasoning": result.ai_reasoning, "details": result.details}
