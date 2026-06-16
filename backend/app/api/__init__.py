"""API router aggregation."""

from fastapi import APIRouter

from app.api.agents import router as agents_router
from app.api.datasets import router as datasets_router
from app.api.rules import router as rules_router
from app.api.score_configs import router as score_configs_router
from app.api.ai_judges import router as ai_judges_router
from app.api.eval_prompts import router as eval_prompts_router
from app.api.rubrics import router as rubrics_router
from app.api.tasks import router as tasks_router
from app.api.results import router as results_router
from app.api.test_cases import router as test_cases_router
from app.api.annotations import router as annotations_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.spaces import router as spaces_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(agents_router)
api_router.include_router(datasets_router)
api_router.include_router(rules_router)
api_router.include_router(score_configs_router)
api_router.include_router(ai_judges_router)
api_router.include_router(eval_prompts_router)
api_router.include_router(rubrics_router)
api_router.include_router(tasks_router)
api_router.include_router(results_router)
api_router.include_router(test_cases_router)
api_router.include_router(annotations_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(spaces_router)
