"""Task management API endpoints — CRUD + lifecycle (start/pause/resume/cancel) + SSE progress."""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db, async_session_factory
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User
from app.config import settings
from app.engine import TaskExecutionEngine, ExecResult
from app.models.objective_weight import ObjectiveWeight
from sqlalchemy import select

router = APIRouter(prefix="/tasks", tags=["Tasks"])

logger = logging.getLogger("agentmate.engine")

# In-memory task engine registry (for lifecycle control)
_task_engines: dict[str, TaskExecutionEngine] = {}


@router.post("")
async def create_task(data: dict, db: AsyncSession = Depends(get_db),
                      current_space: str | None = Depends(get_current_space)):
    """Create a new evaluation task."""
    rule_ids = data.get("rule_ids") or []
    task_data = {
        "name": data.get("name", "Untitled Task"),
        "agent_ids": data.get("agent_ids", []),
        "dataset_ids": data.get("dataset_ids", []),
        "filters": data.get("filters", {}),
        "config": {
            "concurrency": int(data.get("concurrency", settings.engine_default_concurrency)),
            "timeout_ms": int(data.get("timeout_ms", settings.engine_default_timeout_ms)),
            "max_retries": int(data.get("max_retries", settings.engine_default_max_retries)),
            "rule_ids": rule_ids,
            "global_threshold": float(data.get("global_threshold", 0.7)),
        },
        "ai_scoring_config": data.get("ai_scoring_config", {}),
        "status": "pending",
    }
    if current_space:
        task_data["space_id"] = current_space
    task = await repo.create_task(db, task_data)

    # Store weights if provided
    if data.get("objective_weights"):
        await repo.set_objective_weights(db, task.id, data["objective_weights"])

    return task


@router.get("")
async def list_tasks(status: str | None = None, limit: int = 50,
                     db: AsyncSession = Depends(get_db),
                     current_space: str | None = Depends(get_current_space)):
    return await repo.list_tasks(db, space_id=current_space, status=status, limit=limit)


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       current_space: str | None = Depends(get_current_space)):
    task = await repo.get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return task


@router.get("/{task_id}/weights")
async def get_task_weights(task_id: str, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user),
                              current_space: str | None = Depends(get_current_space)):
    """Return objective weight & threshold overrides for a task."""
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    rows = await repo.get_objective_weights(db, task_id)
    return [
        {"objective": r.objective, "weight": r.weight, "threshold": r.threshold}
        for r in rows
    ]


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    _task_engines.pop(task_id, None)
    if not await repo.delete_task(db, task_id):
        raise HTTPException(404, "Task not found")


@router.post("/{task_id}/start")
async def start_task(task_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    """Start task execution as a background job."""
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    task = await repo.get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in ("pending", "paused", "failed"):
        raise HTTPException(400, f"Cannot start task in status '{task.status}'")

    # Build engine
    config = task.config or {}
    engine = TaskExecutionEngine(
        max_concurrency=config.get("concurrency", settings.engine_default_concurrency),
        default_timeout_ms=config.get("timeout_ms", settings.engine_default_timeout_ms),
        max_retries=config.get("max_retries", settings.engine_default_max_retries),
    )
    _task_engines[task_id] = engine

    # Mark as running
    await repo.update_task(db, task_id, {
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "progress": {"total": 0, "completed": 0, "failed": 0, "passed": 0},
    })
    await db.commit()

    # Launch background execution
    background_tasks.add_task(_execute_task, task_id, engine)

    return {"message": "Task started", "task_id": task_id}


async def _execute_task(task_id: str, engine: TaskExecutionEngine):
    """Background execution of test cases — uses its own DB session."""
    from app.__init_db import async_session_factory

    async with async_session_factory() as db:
        try:
            task = await repo.get_task(db, task_id)
            if not task:
                return

            agent_ids = task.agent_ids or []
            dataset_ids = task.dataset_ids or []
            filters = task.filters or {}

            all_cases = []
            for ds_id in dataset_ids:
                cases, _ = await repo.list_test_cases(db, ds_id, page=1, size=10_000)
                all_cases.extend(cases)

            if filters.get("tags"):
                all_cases = [c for c in all_cases if any(t in (c.tags or []) for t in filters["tags"])]

            total = len(all_cases)
            await repo.update_task(db, task_id, {"progress": {"total": total, "completed": 0, "failed": 0, "passed": 0}})
            await db.commit()

            # ── Load scoring rules & setup scorer ────────────────
            from app.scoring.dispatcher import RuleDispatcher
            from app.scoring.aggregator import ScoreAggregator
            from app.scoring import ScoringContext

            # Filter rules by task-configured rule_ids if specified
            task_config = task.config or {}
            task_rule_ids = task_config.get("rule_ids") or []
            if task_rule_ids:
                all_rules = await repo.list_rules_by_ids(db, task_rule_ids)
            else:
                all_rules = await repo.list_rules(db, enabled=True)
            dispatcher = RuleDispatcher()
            dispatcher.register_builtins()
            # Register AI judge scorers if available
            try:
                from app.judge.scorer import LLMJudgeScorer, LLMJudgeRefScorer, LLMJudgeRubricScorer
                dispatcher.register(LLMJudgeScorer())
                dispatcher.register(LLMJudgeRefScorer())
                dispatcher.register(LLMJudgeRubricScorer())
            except ImportError:
                pass

            # Pre-load AI judge resources (prompt templates + judge models) for AI-type rules
            from app.models import EvalPromptTemplate, AIJudgeModel, ScoringRubric
            prompt_ids = {r.ai_eval_prompt_id for r in all_rules if r.ai_eval_prompt_id}
            judge_ids = {r.ai_judge_model_id for r in all_rules if r.ai_judge_model_id}
            rubric_ids = {r.ai_rubric_id for r in all_rules if r.ai_rubric_id}

            prompt_map: dict[str, EvalPromptTemplate] = {}
            if prompt_ids:
                rows = (await db.execute(
                    select(EvalPromptTemplate).where(EvalPromptTemplate.id.in_(prompt_ids))
                )).scalars().all()
                prompt_map = {r.id: r for r in rows}

            judge_map: dict[str, AIJudgeModel] = {}
            if judge_ids:
                rows = (await db.execute(
                    select(AIJudgeModel).where(AIJudgeModel.id.in_(judge_ids))
                )).scalars().all()
                judge_map = {r.id: r for r in rows}

            rubric_map: dict[str, ScoringRubric] = {}
            if rubric_ids:
                rows = (await db.execute(
                    select(ScoringRubric).where(ScoringRubric.id.in_(rubric_ids))
                )).scalars().all()
                rubric_map = {r.id: r for r in rows}

            aggregator = ScoreAggregator()

            # Load per-task weight overrides
            obj_weight_rows = (await db.execute(
                select(ObjectiveWeight).where(ObjectiveWeight.task_id == task_id))).scalars().all()
            objective_weights: dict[str, float] = {}
            objective_thresholds: dict[str, float] = {}
            for ow in obj_weight_rows:
                objective_weights[ow.objective] = ow.weight
                if ow.threshold is not None:
                    objective_thresholds[ow.objective] = ow.threshold

            # Build rule → objectives map
            rule_objective_map: dict[str, list[str]] = {}
            rule_name_map: dict[str, str] = {}
            for r in all_rules:
                if r.objectives:
                    rule_objective_map[r.id] = r.objectives
                rule_name_map[r.id] = r.name

            # Build case info lookup
            case_info_map: dict[str, dict] = {}
            for c in all_cases:
                case_info_map[c.case_id] = {
                    "objectives": c.objectives or [],
                    "rule_refs": c.rule_refs or [],
                    "expected_output": c.expected_output or "",
                }
            # ─────────────────────────────────────────────────────

            if not agent_ids:
                agent_ids = [""]

            for agent_id in agent_ids:
                if engine.is_cancelled:
                    break

                agent_cfg = {"id": agent_id}
                if agent_id:
                    agent = await repo.get_agent(db, agent_id)
                    if not agent:
                        continue
                    agent_cfg = {
                        "id": agent.id, "api_base_url": agent.api_base_url,
                        "method": agent.method, "headers_template": agent.headers_template or {},
                        "body_template": agent.body_template or {},
                        "auth_type": agent.auth_type,
                        "auth_credentials": agent.auth_credentials or "",
                    }

                case_dicts = [
                    {"case_id": c.case_id, "input": c.input, "expected_output": c.expected_output,
                     "objectives": c.objectives or [],
                     "rule_refs": c.rule_refs or []}
                    for c in all_cases
                ]

                completed = 0
                failed = 0
                passed_count = 0

                async for exec_result in engine.execute(agent_cfg, case_dicts):
                    completed += 1

                    case_info = case_info_map.get(exec_result.case_id, {})
                    case_objectives = case_info.get("objectives", [])
                    case_rule_refs = case_info.get("rule_refs", [])
                    case_expected = case_info.get("expected_output", "")

                    # ── Score with rules ────────────────────────────
                    score_results = []
                    applicable = all_rules
                    if case_rule_refs:
                        applicable = [r for r in all_rules if r.id in case_rule_refs]

                    if applicable and case_objectives:
                        for rule in applicable:
                            # Ensure rule.config is a dict (defensive against bad imports)
                            raw_config = rule.config
                            if not isinstance(raw_config, dict):
                                raw_config = {}
                            _eval_strategy = rule.eval_strategy or {
                                "llm_judge": "simple",
                                "llm_judge_ref": "reference",
                                "llm_judge_rubric": "rubric",
                            }.get(rule.type, "simple")

                            # Resolve prompt template for AI-type rules
                            _prompt_tpl = prompt_map.get(rule.ai_eval_prompt_id) if rule.ai_eval_prompt_id else None
                            _judge_model = judge_map.get(rule.ai_judge_model_id) if rule.ai_judge_model_id else None
                            _rubric = rubric_map.get(rule.ai_rubric_id) if rule.ai_rubric_id else None

                            _judge_models: dict = {}
                            if _judge_model:
                                _judge_models[_judge_model.id] = {
                                    "provider": _judge_model.provider,
                                    "model_name": _judge_model.model_name,
                                    "api_base_url": _judge_model.api_base_url,
                                    "auth_credentials": _judge_model.auth_credentials or "",
                                }

                            ctx = ScoringContext(
                                case_input=exec_result.raw_input,
                                case_expected_output=case_expected,
                                actual_output=exec_result.raw_output,
                                rule_config={
                                    **raw_config,
                                    "_rule_id": rule.id,
                                    "_response_time_ms": exec_result.response_time_ms,
                                },
                                rule_type=rule.type,
                                rule_weight=rule.weight,
                                rule_threshold=rule.threshold,
                                eval_strategy=_eval_strategy,
                                # AI prompt template sections
                                prompt_template=_prompt_tpl.user_prompt_template if _prompt_tpl else None,
                                system_prompt=_prompt_tpl.system_prompt if _prompt_tpl else None,
                                output_schema=_prompt_tpl.output_schema if _prompt_tpl else None,
                                few_shot_examples=_prompt_tpl.few_shot_examples if _prompt_tpl else None,
                                # Judge model config
                                judge_models=_judge_models or None,
                                # Rubric text
                                rubric_text=_rubric.description if _rubric else None,
                            )
                            sr = await dispatcher.evaluate(ctx, rule.type)
                            score_results.append(sr)

                        aggregated = aggregator.aggregate(
                            score_results=score_results,
                            case_objectives=case_objectives,
                            rule_objective_map=rule_objective_map,
                            objective_weights=objective_weights,
                            objective_thresholds=objective_thresholds,
                            global_threshold=float((task.config or {}).get("global_threshold", 0.7)),
                        )

                        passed = aggregated.passed
                        total_score = aggregated.total_score

                        # ── Log detailed scoring results ──────────────
                        rule_logs = "  ".join(
                            f"{sr.rule_type}={sr.score:.4f}({'PASS' if sr.passed else 'FAIL'}{' ERR' if sr.error else ''})"
                            for sr in score_results
                        )
                        obj_logs = "  ".join(
                            f"{k}={v.score:.4f}({'PASS' if v.passed else 'FAIL'})"
                            for k, v in aggregated.objective_scores.items()
                        )
                        logger.info(
                            "[SCORE  ] case=%-12s result=%s  total=%.4f",
                            exec_result.case_id, "PASS" if passed else "FAIL", total_score,
                        )
                        if rule_logs:
                            logger.info("[SCORE  ]   rules:       %s", rule_logs)
                        if obj_logs:
                            logger.info("[SCORE  ]   objectives:  %s", obj_logs)
                        # ──────────────────────────────────────────────

                        scores_dict = {
                            "total": aggregated.total_score,
                            "passed": aggregated.passed,
                            "objectives": {
                                k: {"score": v.score, "passed": v.passed, "weight": v.weight, "threshold": v.threshold}
                                for k, v in aggregated.objective_scores.items()
                            },
                            "rules": [
                                {"rule_id": sr.rule_id, "rule_type": sr.rule_type,
                                 "name": rule_name_map.get(sr.rule_id, sr.rule_type),
                                 "score": sr.score, "passed": sr.passed,
                                 "details": sr.details, "error": sr.error}
                                for sr in score_results
                            ],
                        }
                    else:
                        # Fallback: no rules → pass/fail based on HTTP error
                        passed = exec_result.error is None
                        total_score = 1.0 if passed else 0.0
                        scores_dict = {"default": {"score": total_score, "passed": passed}}
                        logger.info(
                            "[SCORE  ] case=%-12s result=%s  score=%.4f  (no rules, HTTP fallback)",
                            exec_result.case_id, "PASS" if passed else "FAIL", total_score,
                        )

                    if not passed:
                        failed += 1
                    else:
                        passed_count += 1
                    # ────────────────────────────────────────────────

                    await repo.create_task_result(db, {
                        "task_id": task_id, "agent_id": agent_id,
                        "case_id": exec_result.case_id,
                        "raw_input": exec_result.raw_input,
                        "raw_output": exec_result.raw_output,
                        "response_time_ms": int(exec_result.response_time_ms),
                        "status_code": exec_result.status_code,
                        "error": exec_result.error,
                        "passed": passed,
                        "total_score": total_score,
                        "scores": scores_dict,
                    })

                    await repo.update_task(db, task_id, {
                        "progress": {"total": total, "completed": completed, "failed": failed, "passed": passed_count},
                    })
                    await db.commit()

            final_status = "cancelled" if engine.is_cancelled else "completed"
            await repo.update_task(db, task_id, {
                "status": final_status,
                "completed_at": datetime.now(timezone.utc),
            })
            await db.commit()

        except Exception as exc:
            logger.error("Task %s failed with exception: %s\n%s", task_id, exc, traceback.format_exc())
            # ===== 修改开始：先回滚会话，再更新状态 =====
            try:
                # 1. 回滚当前会话，清除“待回滚”状态
                await db.rollback()
                # 2. 使用当前会话（已回滚）更新状态为 faile
                await repo.update_task(db, task_id, {"status": "failed"})
                await db.commit()
            except Exception as inner_exc:
                # 如果连更新状态都失败，记录错误，但不再抛出，避免导致应用崩溃
                logger.error("Failed to update task %s status to failed: %s", task_id, inner_exc)
                # 可以选择使用新的独立会话重试一次
                try:
                    async with async_session_factory() as new_db:
                        await repo.update_task(new_db, task_id, {"status": "failed"})
                        await new_db.commit()
                except Exception as final_exc:
                    logger.error("Second attempt to update task %s status also failed: %s", task_id, final_exc)
            # ===== 修改结束 =====


        finally:
            _task_engines.pop(task_id, None)


@router.post("/{task_id}/pause")
async def pause_task(task_id: str, current_user: User = Depends(get_current_user)):
    engine = _task_engines.get(task_id)
    if not engine:
        raise HTTPException(400, "Task is not running")
    engine.pause()
    return {"message": "Task paused"}


@router.post("/{task_id}/resume")
async def resume_task(task_id: str, current_user: User = Depends(get_current_user)):
    engine = _task_engines.get(task_id)
    if not engine:
        raise HTTPException(400, "Task is not running or not paused")
    engine.resume()
    return {"message": "Task resumed"}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    engine = _task_engines.get(task_id)
    if engine:
        engine.cancel()
    await repo.update_task(db, task_id, {"status": "cancelled"})
    await db.commit()
    return {"message": "Task cancelled"}


@router.post("/{task_id}/rerun")
async def rerun_task(task_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    """Re-execute a completed/failed/cancelled task — creates a new task with identical config."""
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    old = await repo.get_task(db, task_id)
    if not old:
        raise HTTPException(404, "Task not found")
    if old.status not in ("completed", "failed", "cancelled"):
        raise HTTPException(400, f"Cannot rerun task in status '{old.status}'")

    task_data = {
        "name": (old.name or "Untitled Task") + " (副本)",
        "agent_ids": old.agent_ids or [],
        "dataset_ids": old.dataset_ids or [],
        "filters": old.filters or {},
        "config": old.config or {},
        "ai_scoring_config": old.ai_scoring_config or {},
        "status": "pending",
    }
    new_task = await repo.create_task(db, task_data)
    await db.commit()

    # Auto-start the new task
    config = new_task.config or {}
    engine = TaskExecutionEngine(
        max_concurrency=config.get("concurrency", settings.engine_default_concurrency),
        default_timeout_ms=config.get("timeout_ms", settings.engine_default_timeout_ms),
        max_retries=config.get("max_retries", settings.engine_default_max_retries),
    )
    _task_engines[new_task.id] = engine

    await repo.update_task(db, new_task.id, {
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "progress": {"total": 0, "completed": 0, "failed": 0, "passed": 0},
    })
    await db.commit()

    background_tasks.add_task(_execute_task, new_task.id, engine)

    return {"message": "Task rerun started", "task_id": new_task.id, "name": new_task.name}


@router.get("/{task_id}/progress")
async def task_progress(task_id: str, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user),
                           current_space: str | None = Depends(get_current_space)):
    """SSE stream of task progress."""
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    async def event_stream():
        while True:
            task = await repo.get_task(db, task_id)
            if not task:
                yield f"event: error\ndata: {json.dumps({'message': 'Task not found'})}\n\n"
                break

            data = json.dumps({
                "status": task.status,
                "progress": task.progress,
            })
            yield f"event: progress\ndata: {data}\n\n"

            if task.status in ("completed", "failed", "cancelled"):
                summary = await repo.get_task_summary(db, task_id)
                yield f"event: done\ndata: {json.dumps(summary)}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/compare")
async def compare_tasks(data: dict, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         current_space: str | None = Depends(get_current_space)):
    """Compare multiple tasks."""
    task_ids = data.get("task_ids", [])
    results = []
    for tid in task_ids:
        if not await repo.verify_space_access(db, repo.Task, tid, current_space, current_user.role):
            continue
        task = await repo.get_task(db, tid)
        if task:
            summary = await repo.get_task_summary(db, tid)
            results.append({"task_id": tid, "task_name": task.name, "summary": summary})
    return {"comparison": results}
