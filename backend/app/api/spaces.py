"""Spaces API — user space CRUD for data isolation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.__init_db import get_db
from app.auth.deps import get_current_user, require_admin
from app.models.user import User
from app import repositories as repo

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_space(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a personal space. One user can only have one space."""
    existing = await repo.get_space_by_owner(db, current_user.id)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Space already exists")

    space = await repo.create_space(db, {
        "name": data.get("name", f"{current_user.username}'s Space"),
        "description": data.get("description", ""),
        "owner_id": current_user.id,
    })
    await db.commit()
    return {
        "id": space.id,
        "name": space.name,
        "description": space.description,
        "owner_id": space.owner_id,
        "created_at": str(space.created_at),
    }


@router.get("/me")
async def get_my_space(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's space."""
    space = await repo.get_space_by_owner(db, current_user.id)
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    return {
        "id": space.id,
        "name": space.name,
        "description": space.description,
        "owner_id": space.owner_id,
        "created_at": str(space.created_at),
        "updated_at": str(space.updated_at),
    }


@router.get("")
async def list_spaces(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """List all spaces (admin only)."""
    spaces = await repo.list_spaces(db)
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "owner_id": s.owner_id,
            "created_at": str(s.created_at),
        }
        for s in spaces
    ]


@router.get("/{space_id}")
async def get_space(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific space."""
    space = await repo.get_space(db, space_id)
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    # Non-admin users can only see their own space
    if current_user.role != "admin" and space.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return {
        "id": space.id,
        "name": space.name,
        "description": space.description,
        "owner_id": space.owner_id,
        "created_at": str(space.created_at),
        "updated_at": str(space.updated_at),
    }
