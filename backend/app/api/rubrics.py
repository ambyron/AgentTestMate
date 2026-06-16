"""Scoring rubric management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User

router = APIRouter(prefix="/rubrics", tags=["Rubrics"])


@router.post("")
async def create_rubric(data: dict, db: AsyncSession = Depends(get_db),
                        current_space: str | None = Depends(get_current_space)):
    if current_space:
        data["space_id"] = current_space
    return await repo.create_rubric(db, data)


@router.get("")
async def list_rubrics(db: AsyncSession = Depends(get_db),
                       current_space: str | None = Depends(get_current_space)):
    return await repo.list_rubrics(db, space_id=current_space)


@router.get("/{rubric_id}")
async def get_rubric(rubric_id: str, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      current_space: str | None = Depends(get_current_space)):
    rb = await repo.get_rubric(db, rubric_id)
    if not rb:
        raise HTTPException(404, "Rubric not found")
    if not await repo.verify_space_access(db, repo.ScoringRubric, rubric_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return rb


@router.put("/{rubric_id}")
async def update_rubric(rubric_id: str, data: dict, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.ScoringRubric, rubric_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    rb = await repo.update_rubric(db, rubric_id, data)
    if not rb:
        raise HTTPException(404, "Rubric not found")
    return rb


@router.delete("/{rubric_id}", status_code=204)
async def delete_rubric(rubric_id: str, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.ScoringRubric, rubric_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_rubric(db, rubric_id):
        raise HTTPException(404, "Rubric not found")
