"""Annotation API endpoints — human review of task results."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User

router = APIRouter(prefix="/annotations", tags=["Annotations"])


@router.post("")
async def create_annotation(data: dict, db: AsyncSession = Depends(get_db),
                            current_space: str | None = Depends(get_current_space)):
    if current_space:
        data["space_id"] = current_space
    return await repo.create_annotation(db, data)


@router.get("")
async def list_annotations(task_result_id: str | None = None,
                            status: str | None = None,
                            db: AsyncSession = Depends(get_db),
                            current_space: str | None = Depends(get_current_space)):
    if status == "pending":
        return await repo.list_pending_annotations(db)
    return await repo.list_annotations(db, space_id=current_space, task_result_id=task_result_id, status=status)


@router.get("/{annotation_id}")
async def get_annotation(annotation_id: str, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user),
                          current_space: str | None = Depends(get_current_space)):
    ann = await repo.get_annotation(db, annotation_id)
    if not ann:
        raise HTTPException(404, "Annotation not found")
    if not await repo.verify_space_access(db, repo.Annotation, annotation_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return ann


@router.put("/{annotation_id}")
async def update_annotation(annotation_id: str, data: dict, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user),
                             current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Annotation, annotation_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    ann = await repo.update_annotation(db, annotation_id, data)
    if not ann:
        raise HTTPException(404, "Annotation not found")
    return ann


@router.delete("/{annotation_id}", status_code=204)
async def delete_annotation(annotation_id: str, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user),
                             current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Annotation, annotation_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_annotation(db, annotation_id):
        raise HTTPException(404, "Annotation not found")


@router.get("/judge-accuracy/stats")
async def judge_accuracy_stats(judge_model_id: str | None = None,
                                db: AsyncSession = Depends(get_db),
                                current_space: str | None = Depends(get_current_space)):
    """Compare AI judge scores with human annotations to measure judge accuracy."""
    return await repo.judge_accuracy(db, judge_model_id, space_id=current_space)
