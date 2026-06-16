"""ScoreConfig API endpoints — CRUD for scoring configuration templates."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User

router = APIRouter(prefix="/score-configs", tags=["ScoreConfigs"])


@router.post("")
async def create_score_config(data: dict, db: AsyncSession = Depends(get_db),
                              current_space: str | None = Depends(get_current_space)):
    if current_space:
        data["space_id"] = current_space
    return await repo.create_score_config(db, data)


@router.get("")
async def list_score_configs(data_type: str | None = None, db: AsyncSession = Depends(get_db),
                             current_space: str | None = Depends(get_current_space)):
    return await repo.list_score_configs(db, space_id=current_space, data_type=data_type)


@router.get("/{config_id}")
async def get_score_config(config_id: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user),
                            current_space: str | None = Depends(get_current_space)):
    sc = await repo.get_score_config(db, config_id)
    if not sc:
        raise HTTPException(404, "ScoreConfig not found")
    if not await repo.verify_space_access(db, repo.ScoreConfig, config_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return sc


@router.put("/{config_id}")
async def update_score_config(config_id: str, data: dict, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user),
                               current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.ScoreConfig, config_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    sc = await repo.update_score_config(db, config_id, data)
    if not sc:
        raise HTTPException(404, "ScoreConfig not found")
    return sc


@router.delete("/{config_id}", status_code=204)
async def delete_score_config(config_id: str, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user),
                               current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.ScoreConfig, config_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_score_config(db, config_id):
        raise HTTPException(404, "ScoreConfig not found")
