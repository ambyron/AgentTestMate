"""Test case management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User

router = APIRouter(prefix="/test-cases", tags=["Test Cases"])


@router.post("")
async def create_test_case(data: dict, db: AsyncSession = Depends(get_db),
                           current_space: str | None = Depends(get_current_space)):
    dataset_id = data.get("dataset_id")
    if not dataset_id:
        raise HTTPException(400, "dataset_id is required")
    ds = await repo.get_dataset(db, dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    if current_space:
        data["space_id"] = current_space
    return await repo.create_test_case(db, data)


@router.get("")
async def list_test_cases(dataset_id: str, page: int = 1, size: int = 50,
                           db: AsyncSession = Depends(get_db)):
    items, total = await repo.list_test_cases(db, dataset_id, page, size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{case_id}")
async def get_test_case(case_id: str, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user),
                         current_space: str | None = Depends(get_current_space)):
    tc = await repo.get_test_case(db, case_id)
    if not tc:
        raise HTTPException(404, "Test case not found")
    if not await repo.verify_space_access(db, repo.TestCase, case_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return tc


@router.put("/{case_id}")
async def update_test_case(case_id: str, data: dict, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user),
                            current_space: str | None = Depends(get_current_space)):
    """Update a test case."""
    if not await repo.verify_space_access(db, repo.TestCase, case_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    tc = await repo.update_test_case(db, case_id, data)
    if not tc:
        raise HTTPException(404, "Test case not found")
    return tc


@router.delete("/{case_id}", status_code=204)
async def delete_test_case(case_id: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user),
                            current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.TestCase, case_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_test_case(db, case_id):
        raise HTTPException(404, "Test case not found")
