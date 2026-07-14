"""Repository layer — database CRUD operations for all entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func as sa_func, delete as sa_delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent, Dataset, TestCase, Rule, ScoreConfig, Objective, AIJudgeModel,
    EvalPromptTemplate, ScoringRubric, Task, TaskResult, Annotation,
    CategoryWeight, ObjectiveWeight, User, Space,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _filter_fields(data: dict, allowed: set[str]) -> dict:
    """Return only the fields from data that are in the allowed set."""
    return {k: v for k, v in data.items() if k in allowed}


# ── Per-model field allowlists (Mass Assignment protection) ────

_AGENT_FIELDS = {"name", "description", "api_base_url", "method", "headers_template",
                 "body_template", "auth_type", "auth_credentials", "status", "timeout_ms"}
_DATASET_FIELDS = {"name", "description", "dataset_type", "tags"}
_TESTCASE_FIELDS = {"case_id", "input", "expected_output", "objectives", "tags", "rule_refs", "sort_order"}
_RULE_FIELDS = {"name", "description", "type", "config", "objectives",
                "threshold", "enabled", "score_config_id", "ai_judge_model_id", "ai_eval_prompt_id",
                "ai_rubric_id", "eval_strategy", "custom_script"}
_SCORE_CONFIG_FIELDS = {"name", "description", "data_type", "min_value", "max_value", "categories", "default"}
_OBJECTIVE_FIELDS = {"name", "description", "default_weight"}
_AI_JUDGE_FIELDS = {"name", "provider", "model_name", "api_base_url", "auth_type",
                    "auth_credentials", "headers_template", "parameters", "status"}
_EVAL_PROMPT_FIELDS = {"name", "description", "strategy", "system_prompt", "user_prompt_template",
                       "template_content", "output_schema", "few_shot_examples", "variables", "tags"}
_RUBRIC_FIELDS = {"name", "description"}
_TASK_FIELDS = {"name", "config", "ai_scoring_config", "filters", "status", "progress"}
_ANNOTATION_FIELDS = {"score", "comment", "label", "annotator", "status"}
_USER_FIELDS = {"username", "email", "role", "is_active", "display_name", "hashed_password"}
_SPACE_FIELDS = {"name", "description"}
_TASK_RESULT_FIELDS = {"task_id", "agent_id", "case_id", "raw_input", "raw_output",
                       "response_time_ms", "status_code", "error", "passed", "total_score", "scores"}


def _space_filter(stmt, model, space_id: str | None):
    """Apply space-isolation filter: system defaults OR user's own space."""
    if space_id is None:
        return stmt
    return stmt.where(
        or_(model.space_id.is_(None), model.space_id == space_id)
    )


# ── Space access control ──────────────────────────────────────

async def verify_space_access(
    db: AsyncSession,
    model_class,
    resource_id: str,
    space_id: str | None,
    user_role: str,
) -> bool:
    """Verify that a resource belongs to the current user's space.

    Admin bypasses space check (space_id is None for admin).
    Returns False if the resource doesn't exist or belongs to another space.
    """
    if user_role == "admin" or space_id is None:
        return True
    resource = await db.get(model_class, resource_id)
    if resource is None:
        return False
    res_space_id = getattr(resource, "space_id", None)
    if res_space_id and res_space_id != space_id:
        return False
    return True


# ── Space ──────────────────────────────────────────────────────

async def create_space(db: AsyncSession, data: dict) -> Space:
    space = Space(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(space)
    await db.flush()
    return space


async def get_space(db: AsyncSession, space_id: str) -> Space | None:
    return await db.get(Space, space_id)


async def get_space_by_owner(db: AsyncSession, owner_id: str) -> Space | None:
    stmt = select(Space).where(Space.owner_id == owner_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_spaces(db: AsyncSession) -> list[Space]:
    result = await db.execute(select(Space).order_by(Space.created_at.desc()))
    return list(result.scalars().all())


# ── ScoreConfig ────────────────────────────────────────────────

async def list_score_configs(db: AsyncSession, space_id: str | None = None, data_type: str | None = None) -> list[ScoreConfig]:
    stmt = select(ScoreConfig)
    stmt = _space_filter(stmt, ScoreConfig, space_id)
    if data_type:
        stmt = stmt.where(ScoreConfig.data_type == data_type)
    stmt = stmt.order_by(ScoreConfig.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_score_config(db: AsyncSession, config_id: str) -> ScoreConfig | None:
    return await db.get(ScoreConfig, config_id)


async def create_score_config(db: AsyncSession, data: dict) -> ScoreConfig:
    data = _filter_fields(data, _SCORE_CONFIG_FIELDS)
    sc = ScoreConfig(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(sc)
    await db.flush()
    return sc


async def update_score_config(db: AsyncSession, config_id: str, data: dict) -> ScoreConfig | None:
    sc = await get_score_config(db, config_id)
    if not sc:
        return None
    for k, v in _filter_fields(data, _SCORE_CONFIG_FIELDS).items():
        if hasattr(sc, k) and k not in ("id", "created_at"):
            setattr(sc, k, v)
    sc.updated_at = _now()
    await db.flush()
    return sc


async def delete_score_config(db: AsyncSession, config_id: str) -> bool:
    sc = await get_score_config(db, config_id)
    if not sc:
        return False
    await db.delete(sc)
    await db.flush()
    return True


# ── Annotation ────────────────────────────────────────────────

async def list_annotations(db: AsyncSession, space_id: str | None = None, task_result_id: str | None = None,
                           status: str | None = None) -> list[Annotation]:
    stmt = select(Annotation)
    stmt = _space_filter(stmt, Annotation, space_id)
    if task_result_id:
        stmt = stmt.where(Annotation.task_result_id == task_result_id)
    if status:
        stmt = stmt.where(Annotation.status == status)
    stmt = stmt.order_by(Annotation.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_pending_annotations(db: AsyncSession) -> list[Annotation]:
    result = await db.execute(
        select(Annotation).where(Annotation.status == "pending").order_by(Annotation.created_at.desc())
    )
    return list(result.scalars().all())


async def get_annotation(db: AsyncSession, annotation_id: str) -> Annotation | None:
    return await db.get(Annotation, annotation_id)


async def create_annotation(db: AsyncSession, data: dict) -> Annotation:
    data = _filter_fields(data, _ANNOTATION_FIELDS)
    ann = Annotation(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(ann)
    await db.flush()
    return ann


async def update_annotation(db: AsyncSession, annotation_id: str, data: dict) -> Annotation | None:
    ann = await get_annotation(db, annotation_id)
    if not ann:
        return None
    for k, v in _filter_fields(data, _ANNOTATION_FIELDS).items():
        if hasattr(ann, k) and k not in ("id", "created_at"):
            setattr(ann, k, v)
    ann.updated_at = _now()
    await db.flush()
    return ann


async def delete_annotation(db: AsyncSession, annotation_id: str) -> bool:
    ann = await get_annotation(db, annotation_id)
    if not ann:
        return False
    await db.delete(ann)
    await db.flush()
    return True


# ── Agent ──────────────────────────────────────────────────

async def list_agents(db: AsyncSession, space_id: str | None = None, status: str | None = None) -> list[Agent]:
    stmt = select(Agent)
    stmt = _space_filter(stmt, Agent, space_id)
    if status:
        stmt = stmt.where(Agent.status == status)
    stmt = stmt.order_by(Agent.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, agent_id: str) -> Agent | None:
    return await db.get(Agent, agent_id)


async def create_agent(db: AsyncSession, data: dict) -> Agent:
    data = _filter_fields(data, _AGENT_FIELDS)
    agent = Agent(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(agent)
    await db.flush()
    return agent


async def update_agent(db: AsyncSession, agent_id: str, data: dict) -> Agent | None:
    agent = await get_agent(db, agent_id)
    if not agent:
        return None
    for k, v in _filter_fields(data, _AGENT_FIELDS).items():
        if hasattr(agent, k) and k not in ("id", "created_at"):
            setattr(agent, k, v)
    agent.updated_at = _now()
    await db.flush()
    return agent


async def delete_agent(db: AsyncSession, agent_id: str) -> bool:
    agent = await get_agent(db, agent_id)
    if not agent:
        return False
    await db.delete(agent)
    await db.flush()
    return True


# ── Dataset ─────────────────────────────────────────────────

async def list_datasets(db: AsyncSession, space_id: str | None = None, dataset_type: str | None = None, search: str | None = None) -> list[Dataset]:
    stmt = select(Dataset)
    stmt = _space_filter(stmt, Dataset, space_id)
    if dataset_type:
        stmt = stmt.where(Dataset.dataset_type == dataset_type)
    if search:
        stmt = stmt.where(Dataset.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Dataset.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_dataset(db: AsyncSession, dataset_id: str) -> Dataset | None:
    return await db.get(Dataset, dataset_id)


async def create_dataset(db: AsyncSession, data: dict) -> Dataset:
    ds = Dataset(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(ds)
    await db.flush()
    return ds


async def update_dataset(db: AsyncSession, dataset_id: str, data: dict) -> Dataset | None:
    ds = await get_dataset(db, dataset_id)
    if not ds:
        return None
    for k, v in _filter_fields(data, _DATASET_FIELDS).items():
        if hasattr(ds, k) and k not in ("id", "created_at"):
            setattr(ds, k, v)
    ds.updated_at = _now()
    await db.flush()
    return ds


async def delete_dataset(db: AsyncSession, dataset_id: str) -> bool:
    ds = await get_dataset(db, dataset_id)
    if not ds:
        return False
    # Delete associated test cases
    await db.execute(sa_delete(TestCase).where(TestCase.dataset_id == dataset_id))
    await db.delete(ds)
    await db.flush()
    return True


# ── TestCase ────────────────────────────────────────────────

async def list_test_cases(db: AsyncSession, dataset_id: str, page: int = 1, size: int = 50) -> tuple[list[TestCase], int]:
    stmt = select(TestCase).where(TestCase.dataset_id == dataset_id).order_by(TestCase.sort_order, TestCase.case_id)
    count_stmt = select(sa_func.count()).select_from(TestCase).where(TestCase.dataset_id == dataset_id)
    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_test_case(db: AsyncSession, case_id: str) -> TestCase | None:
    return await db.get(TestCase, case_id)


async def create_test_case(db: AsyncSession, data: dict) -> TestCase:
    data = _filter_fields(data, _TESTCASE_FIELDS)
    tc = TestCase(id=_uuid(), **data, created_at=_now())
    db.add(tc)
    await db.flush()
    return tc


async def create_test_cases_batch(db: AsyncSession, dataset_id: str, cases: list[dict]) -> list[TestCase]:
    """Batch import test cases."""
    created = []
    for data in cases:
        data["dataset_id"] = dataset_id
        tc = TestCase(id=_uuid(), **data, created_at=_now())
        db.add(tc)
        created.append(tc)
    await db.flush()
    return created


async def update_test_case(db: AsyncSession, case_id: str, data: dict) -> TestCase | None:
    tc = await get_test_case(db, case_id)
    if not tc:
        return None
    for k, v in _filter_fields(data, _TESTCASE_FIELDS).items():
        if hasattr(tc, k) and k not in ("id", "created_at", "dataset_id"):
            setattr(tc, k, v)
    await db.flush()
    return tc


async def delete_test_case(db: AsyncSession, case_id: str) -> bool:
    tc = await get_test_case(db, case_id)
    if not tc:
        return False
    await db.delete(tc)
    await db.flush()
    return True


# ── Rule ────────────────────────────────────────────────────

async def list_rules(db: AsyncSession, space_id: str | None = None, type_filter: str | None = None, enabled: bool | None = None) -> list[Rule]:
    stmt = select(Rule)
    stmt = _space_filter(stmt, Rule, space_id)
    if type_filter:
        stmt = stmt.where(Rule.type == type_filter)
    if enabled is not None:
        stmt = stmt.where(Rule.enabled == enabled)
    stmt = stmt.order_by(Rule.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_rule(db: AsyncSession, rule_id: str) -> Rule | None:
    return await db.get(Rule, rule_id)


async def create_rule(db: AsyncSession, data: dict) -> Rule:
    data = _filter_fields(data, _RULE_FIELDS)
    rule = Rule(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(rule)
    await db.flush()
    return rule


async def update_rule(db: AsyncSession, rule_id: str, data: dict) -> Rule | None:
    rule = await get_rule(db, rule_id)
    if not rule:
        return None
    for k, v in _filter_fields(data, _RULE_FIELDS).items():
        if hasattr(rule, k) and k not in ("id", "created_at"):
            setattr(rule, k, v)
    rule.updated_at = _now()
    await db.flush()
    return rule


async def delete_rule(db: AsyncSession, rule_id: str) -> bool:
    rule = await get_rule(db, rule_id)
    if not rule:
        return False
    await db.delete(rule)
    await db.flush()
    return True


async def list_rules_by_ids(db: AsyncSession, rule_ids: list[str], space_id: str | None = None) -> list[Rule]:
    stmt = select(Rule).where(Rule.id.in_(rule_ids))
    stmt = _space_filter(stmt, Rule, space_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_rules_by_score_config(db: AsyncSession, score_config_id: str, space_id: str | None = None) -> list[Rule]:
    stmt = select(Rule).where(Rule.score_config_id == score_config_id).order_by(Rule.created_at.desc())
    stmt = _space_filter(stmt, Rule, space_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Objective ───────────────────────────────────────────────

async def list_objectives(db: AsyncSession, space_id: str | None = None) -> list[Objective]:
    stmt = select(Objective).order_by(Objective.name)
    stmt = _space_filter(stmt, Objective, space_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_objective(db: AsyncSession, data: dict) -> Objective:
    data = _filter_fields(data, _OBJECTIVE_FIELDS)
    obj = Objective(id=_uuid(), **data, created_at=_now())
    db.add(obj)
    await db.flush()
    return obj


async def get_objective(db: AsyncSession, objective_id: str) -> Objective | None:
    return await db.get(Objective, objective_id)


async def update_objective(db: AsyncSession, objective_id: str, data: dict) -> Objective | None:
    obj = await db.get(Objective, objective_id)
    if not obj:
        return None
    for key, val in _filter_fields(data, _OBJECTIVE_FIELDS).items():
        if hasattr(obj, key):
            setattr(obj, key, val)
    await db.flush()
    return obj


async def delete_objective(db: AsyncSession, objective_id: str) -> bool:
    obj = await db.get(Objective, objective_id)
    if not obj:
        return False
    await db.delete(obj)
    await db.flush()
    return True


# ── AIJudgeModel ────────────────────────────────────────────

async def list_ai_judges(db: AsyncSession, space_id: str | None = None, provider: str | None = None) -> list[AIJudgeModel]:
    stmt = select(AIJudgeModel)
    stmt = _space_filter(stmt, AIJudgeModel, space_id)
    if provider:
        stmt = stmt.where(AIJudgeModel.provider == provider)
    stmt = stmt.order_by(AIJudgeModel.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_ai_judge(db: AsyncSession, judge_id: str) -> AIJudgeModel | None:
    return await db.get(AIJudgeModel, judge_id)


async def create_ai_judge(db: AsyncSession, data: dict) -> AIJudgeModel:
    data = _filter_fields(data, _AI_JUDGE_FIELDS)
    judge = AIJudgeModel(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(judge)
    await db.flush()
    return judge


async def update_ai_judge(db: AsyncSession, judge_id: str, data: dict) -> AIJudgeModel | None:
    judge = await get_ai_judge(db, judge_id)
    if not judge:
        return None
    for k, v in _filter_fields(data, _AI_JUDGE_FIELDS).items():
        if hasattr(judge, k) and k not in ("id", "created_at"):
            setattr(judge, k, v)
    judge.updated_at = _now()
    await db.flush()
    return judge


async def delete_ai_judge(db: AsyncSession, judge_id: str) -> bool:
    judge = await get_ai_judge(db, judge_id)
    if not judge:
        return False
    await db.delete(judge)
    await db.flush()
    return True


# ── EvalPromptTemplate ──────────────────────────────────────

async def list_eval_prompts(db: AsyncSession, space_id: str | None = None) -> list[EvalPromptTemplate]:
    stmt = select(EvalPromptTemplate).order_by(EvalPromptTemplate.created_at.desc())
    stmt = _space_filter(stmt, EvalPromptTemplate, space_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_eval_prompt(db: AsyncSession, prompt_id: str) -> EvalPromptTemplate | None:
    return await db.get(EvalPromptTemplate, prompt_id)


async def create_eval_prompt(db: AsyncSession, data: dict) -> EvalPromptTemplate:
    # template_content is NOT NULL in DB (legacy schema) but nullable=True in model,
    # so ensure it always has a value
    if "template_content" not in data:
        data["template_content"] = data.get("user_prompt_template", "")
    # Auto-assign seq (101+ for custom templates; 1-100 reserved for built-in)
    if "seq" not in data or data.get("seq") is None:
        from sqlalchemy import func as _sa_func
        max_seq = (await db.execute(select(_sa_func.max(EvalPromptTemplate.seq)))).scalar()
        data["seq"] = max(max_seq or 100, 100) + 1  # always ≥101
    ep = EvalPromptTemplate(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(ep)
    await db.flush()
    return ep


async def update_eval_prompt(db: AsyncSession, prompt_id: str, data: dict) -> EvalPromptTemplate | None:
    ep = await get_eval_prompt(db, prompt_id)
    if not ep:
        return None
    # Create new version
    ep.version = str((int(ep.version.split(".")[0]) + 1)) + ".0" if ep.version else "2.0"
    for k, v in _filter_fields(data, _EVAL_PROMPT_FIELDS).items():
        if hasattr(ep, k) and k not in ("id", "created_at", "version"):
            setattr(ep, k, v)
    ep.updated_at = _now()
    await db.flush()
    return ep


async def delete_eval_prompt(db: AsyncSession, prompt_id: str) -> bool:
    ep = await get_eval_prompt(db, prompt_id)
    if not ep:
        return False
    await db.delete(ep)
    await db.flush()
    return True


# ── ScoringRubric ───────────────────────────────────────────

async def list_rubrics(db: AsyncSession, space_id: str | None = None) -> list[ScoringRubric]:
    stmt = select(ScoringRubric).order_by(ScoringRubric.created_at.desc())
    stmt = _space_filter(stmt, ScoringRubric, space_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_rubric(db: AsyncSession, rubric_id: str) -> ScoringRubric | None:
    return await db.get(ScoringRubric, rubric_id)


async def create_rubric(db: AsyncSession, data: dict) -> ScoringRubric:
    data = _filter_fields(data, _RUBRIC_FIELDS)
    rb = ScoringRubric(id=_uuid(), **data, created_at=_now(), updated_at=_now())
    db.add(rb)
    await db.flush()
    return rb


async def update_rubric(db: AsyncSession, rubric_id: str, data: dict) -> ScoringRubric | None:
    rb = await get_rubric(db, rubric_id)
    if not rb:
        return None
    for k, v in _filter_fields(data, _RUBRIC_FIELDS).items():
        if hasattr(rb, k) and k not in ("id", "created_at"):
            setattr(rb, k, v)
    rb.updated_at = _now()
    await db.flush()
    return rb


async def delete_rubric(db: AsyncSession, rubric_id: str) -> bool:
    rb = await get_rubric(db, rubric_id)
    if not rb:
        return False
    await db.delete(rb)
    await db.flush()
    return True


# ── Judge Accuracy ───────────────────────────────────────────

async def judge_accuracy(db: AsyncSession, judge_model_id: str | None = None, space_id: str | None = None) -> dict:
    """Compare AI judge scores with human annotations to compute accuracy metrics."""
    from sqlalchemy import text

    conditions = []
    params: dict[str, Any] = {}

    if judge_model_id:
        conditions.append("tr.scores->>'judge_model_ids' LIKE :judge_id")
        params["judge_id"] = f"%{judge_model_id}%"

    if space_id:
        conditions.append("(an.space_id IS NULL OR an.space_id = :space_id)")
        params["space_id"] = space_id

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    query = text(f"""
        SELECT
            COUNT(*) as total_pairs,
            SUM(CASE WHEN an.score >= 5.0 AND tr.total_score >= 0.7 THEN 1
                     WHEN an.score < 5.0 AND tr.total_score < 0.7 THEN 1
                     ELSE 0 END) as agreement_count,
            AVG(tr.total_score) as avg_ai_score,
            AVG(an.score / 10.0) as avg_human_score
        FROM annotations an
        JOIN task_results tr ON tr.id = an.task_result_id
        WHERE {where_clause}
          AND tr.scores IS NOT NULL
    """)
    result = await db.execute(query, params)
    row = result.one_or_none()

    if not row or not row.total_pairs:
        return {"total_pairs": 0, "agreement_rate": 0, "avg_ai_score": 0, "avg_human_score": 0}

    agreement_rate = row.agreement_count / row.total_pairs if row.total_pairs > 0 else 0
    return {
        "total_pairs": row.total_pairs,
        "agreement_count": row.agreement_count,
        "agreement_rate": round(agreement_rate, 4),
        "avg_ai_score": round(float(row.avg_ai_score), 4) if row.avg_ai_score else 0,
        "avg_human_score": round(float(row.avg_human_score), 4) if row.avg_human_score else 0,
    }


# ── Task ────────────────────────────────────────────────────

async def list_tasks(db: AsyncSession, space_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Task]:
    stmt = select(Task)
    stmt = _space_filter(stmt, Task, space_id)
    if status:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task(db: AsyncSession, task_id: str) -> Task | None:
    return await db.get(Task, task_id)


async def create_task(db: AsyncSession, data: dict) -> Task:
    task = Task(id=_uuid(), **data, created_at=_now())
    db.add(task)
    await db.flush()
    return task


async def update_task(db: AsyncSession, task_id: str, data: dict) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None
    for k, v in _filter_fields(data, _TASK_FIELDS).items():
        if hasattr(task, k) and k not in ("id", "created_at"):
            setattr(task, k, v)
    await db.flush()
    return task


async def delete_task(db: AsyncSession, task_id: str) -> bool:
    task = await get_task(db, task_id)
    if not task:
        return False
    await db.execute(sa_delete(TaskResult).where(TaskResult.task_id == task_id))
    await db.execute(sa_delete(CategoryWeight).where(CategoryWeight.task_id == task_id))
    await db.execute(sa_delete(ObjectiveWeight).where(ObjectiveWeight.task_id == task_id))
    await db.delete(task)
    await db.flush()
    return True


# ── TaskResult ──────────────────────────────────────────────

async def list_task_results(db: AsyncSession, task_id: str, space_id: str | None = None, passed: bool | None = None,
                            page: int = 1, size: int = 50) -> tuple[list[TaskResult], int]:
    stmt = select(TaskResult).where(TaskResult.task_id == task_id)
    stmt = _space_filter(stmt, TaskResult, space_id)
    count_stmt = select(sa_func.count()).select_from(TaskResult).where(TaskResult.task_id == task_id)
    if passed is not None:
        stmt = stmt.where(TaskResult.passed == passed)
        count_stmt = count_stmt.where(TaskResult.passed == passed)
    stmt = stmt.order_by(TaskResult.executed_at)
    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_task_result(db: AsyncSession, result_id: str) -> TaskResult | None:
    return await db.get(TaskResult, result_id)


async def create_task_result(db: AsyncSession, data: dict) -> TaskResult:
    tr = TaskResult(id=_uuid(), **data, executed_at=_now())
    db.add(tr)
    await db.flush()
    return tr


async def get_task_summary(db: AsyncSession, task_id: str) -> dict:
    """Get aggregated summary for a task."""
    results, _ = await list_task_results(db, task_id, page=1, size=10_000)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    scores = [r.total_score for r in results if r.total_score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "avg_score": round(avg_score, 4),
        "pass_rate": round(passed / total, 4) if total else 0.0,
    }


# ── Weights ─────────────────────────────────────────────────

async def set_category_weights(db: AsyncSession, task_id: str, weights: dict[str, float]):
    await db.execute(sa_delete(CategoryWeight).where(CategoryWeight.task_id == task_id))
    for cat, w in weights.items():
        db.add(CategoryWeight(id=_uuid(), task_id=task_id, category=cat, weight=w))
    await db.flush()


async def get_objective_weights(db: AsyncSession, task_id: str, space_id: str | None = None) -> list[ObjectiveWeight]:
    stmt = select(ObjectiveWeight).where(ObjectiveWeight.task_id == task_id)
    stmt = _space_filter(stmt, ObjectiveWeight, space_id)
    return list((await db.execute(stmt)).scalars().all())


# ── User ─────────────────────────────────────────────────────

async def create_user(db: AsyncSession, data: dict) -> User:
    user = User(id=_uuid(), **data, created_at=_now())
    db.add(user)
    await db.flush()
    return user


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    return await db.get(User, user_id)


async def list_users(db: AsyncSession, search: str = "", skip: int = 0, limit: int = 100) -> list[User]:
    stmt = select(User)
    if search:
        stmt = stmt.where(User.username.ilike(f"%{search}%"))
    stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_user(db: AsyncSession, user_id: str, data: dict) -> User | None:
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    for k, v in _filter_fields(data, _USER_FIELDS).items():
        if hasattr(user, k) and k not in ("id", "created_at"):
            setattr(user, k, v)
    user.updated_at = _now()
    await db.flush()
    return user


async def delete_user(db: AsyncSession, user_id: str) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    await db.delete(user)
    await db.flush()
    return True


async def toggle_user_active(db: AsyncSession, user_id: str) -> User | None:
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    user.is_active = not user.is_active
    user.updated_at = _now()
    await db.flush()
    return user


# ── Weights ─────────────────────────────────────────────────

async def set_objective_weights(db: AsyncSession, task_id: str, weights: dict[str, dict]):
    """weights: {objective_name: {"weight": float, "threshold": float | None}}"""
    await db.execute(sa_delete(ObjectiveWeight).where(ObjectiveWeight.task_id == task_id))
    for obj, cfg in weights.items():
        db.add(ObjectiveWeight(
            id=_uuid(), task_id=task_id, objective=obj,
            weight=cfg.get("weight", 1.0), threshold=cfg.get("threshold"),
        ))
    await db.flush()
