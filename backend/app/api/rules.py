"""Scoring rules & objectives API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User
from app.scoring.dispatcher import RuleDispatcher

router = APIRouter(tags=["Rules"])
rules_router = APIRouter(prefix="/rules", tags=["Rules"])
objectives_router = APIRouter(prefix="/objectives", tags=["Objectives"])

_dispatcher = RuleDispatcher()
_dispatcher.register_builtins()


@rules_router.post("")
async def create_rule(data: dict, db: AsyncSession = Depends(get_db),
                      current_space: str | None = Depends(get_current_space)):
    # Normalize config & objectives: ensure stored as dict/list, not JSON string
    import json as _json
    for field in ("config", "objectives"):
        if isinstance(data.get(field), str):
            try:
                data[field] = _json.loads(data[field])
            except (_json.JSONDecodeError, TypeError):
                data[field] = {} if field == "config" else []
    if current_space:
        data["space_id"] = current_space
    return await repo.create_rule(db, data)


@rules_router.get("")
async def list_rules(type: str | None = None, enabled: bool | None = None,
                     score_config_id: str | None = None,
                     db: AsyncSession = Depends(get_db),
                     current_space: str | None = Depends(get_current_space)):
    if score_config_id:
        return await repo.list_rules_by_score_config(db, score_config_id, space_id=current_space)
    return await repo.list_rules(db, space_id=current_space, type_filter=type, enabled=enabled)


@rules_router.get("/types")
async def list_rule_types():
    return {"types": _dispatcher.get_supported_types()}


@rules_router.get("/{rule_id}")
async def get_rule(rule_id: str, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user),
                    current_space: str | None = Depends(get_current_space)):
    rule = await repo.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    if not await repo.verify_space_access(db, repo.Rule, rule_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return rule


@rules_router.put("/{rule_id}")
async def update_rule(rule_id: str, data: dict, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Rule, rule_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    import json as _json
    for field in ("config", "objectives"):
        if isinstance(data.get(field), str):
            try:
                data[field] = _json.loads(data[field])
            except (_json.JSONDecodeError, TypeError):
                data[field] = {} if field == "config" else []
    rule = await repo.update_rule(db, rule_id, data)
    if not rule:
        raise HTTPException(404, "Rule not found")
    return rule


@rules_router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Rule, rule_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_rule(db, rule_id):
        raise HTTPException(404, "Rule not found")


@rules_router.post("/{rule_id}/preview")
async def preview_rule(rule_id: str, data: dict, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    """Preview what a rule would score for given input/output."""
    if not await repo.verify_space_access(db, repo.Rule, rule_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    rule = await repo.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")

    from app.scoring import ScoringContext
    raw_config = rule.config
    if not isinstance(raw_config, dict):
        raw_config = {}
    ctx = ScoringContext(
        case_input=data.get("input", ""),
        case_expected_output=data.get("expected_output"),
        actual_output=data.get("actual_output", ""),
        rule_config={**raw_config, "_rule_id": rule.id, "_response_time_ms": data.get("response_time_ms", 0)},
        rule_type=rule.type,
        rule_weight=rule.weight,
        rule_threshold=rule.threshold,
    )
    result = await _dispatcher.evaluate(ctx, rule.type)
    return result


@objectives_router.post("")
async def create_objective(data: dict, db: AsyncSession = Depends(get_db),
                           current_space: str | None = Depends(get_current_space)):
    if current_space:
        data["space_id"] = current_space
    return await repo.create_objective(db, data)


@objectives_router.get("")
async def list_objectives(db: AsyncSession = Depends(get_db),
                          current_space: str | None = Depends(get_current_space)):
    return await repo.list_objectives(db, space_id=current_space)


@objectives_router.put("/{objective_id}")
async def update_objective(objective_id: str, data: dict, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user),
                            current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Objective, objective_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    obj = await repo.update_objective(db, objective_id, data)
    if not obj:
        raise HTTPException(404, "Objective not found")
    return obj


@objectives_router.delete("/{objective_id}", status_code=204)
async def delete_objective(objective_id: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user),
                            current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Objective, objective_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_objective(db, objective_id):
        raise HTTPException(404, "Objective not found")


# ── Bulk Import ────────────────────────────────────────────────

@rules_router.post("/import")
async def import_rules(data: dict, db: AsyncSession = Depends(get_db),
                       current_space: str | None = Depends(get_current_space)):
    """Bulk import objectives & rules from a JSON definition file."""
    import json as _json

    results: dict[str, any] = {"objectives": [], "rules": []}

    # Import objectives first
    from sqlalchemy import select as _sa_select
    for obj in data.get("objectives", []):
        # Check if already exists
        existing = (await db.execute(
            _sa_select(repo.Objective).where(repo.Objective.name == obj["name"])
        )).scalar_one_or_none()
        if existing:
            results["objectives"].append({"name": obj["name"], "id": existing.id, "status": "skipped", "error": "已存在"})
            continue
        payload = {
            "name": obj["name"],
            "description": obj.get("description", ""),
            "default_weight": obj.get("default_weight", 1.0),
        }
        if current_space:
            payload["space_id"] = current_space
        try:
            created = await repo.create_objective(db, payload)
            results["objectives"].append({"name": obj["name"], "id": created.id, "status": "created"})
        except Exception as e:
            results["objectives"].append({"name": obj["name"], "status": "error", "error": str(e)})

    # Import rules
    for rule in data.get("rules", []):
        payload = {
            "name": rule["name"],
            "type": rule["type"],
            "description": rule.get("description", ""),
            "config": rule.get("config", {}),
            "objectives": rule.get("objectives", []),
            "weight": rule.get("weight", 1.0),
            "threshold": rule.get("threshold", 0.8),
            "enabled": rule.get("enabled", True),
        }
        if current_space:
            payload["space_id"] = current_space
        for field in ("config", "objectives"):
            if isinstance(payload.get(field), str):
                try:
                    payload[field] = _json.loads(payload[field])
                except (_json.JSONDecodeError, TypeError):
                    payload[field] = {} if field == "config" else []
        try:
            created = await repo.create_rule(db, payload)
            results["rules"].append({"name": rule["name"], "id": created.id, "status": "created"})
        except Exception as e:
            results["rules"].append({"name": rule["name"], "status": "error", "error": str(e)})

    await db.commit()
    return {
        "message": f"Imported {sum(1 for r in results['objectives'] if r['status'] == 'created')} objectives, "
                   f"{sum(1 for r in results['rules'] if r['status'] == 'created')} rules",
        "results": results,
    }


router.include_router(rules_router)
router.include_router(objectives_router)
