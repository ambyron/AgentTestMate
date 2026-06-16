"""Users API — admin-only user CRUD operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.__init_db import get_db
from app.auth.deps import get_current_user, require_admin
from app.auth.password import hash_password
from app.models.user import User
from app import repositories as repo

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    search: str = "",
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """List all users with optional search."""
    users = await repo.list_users(db, search=search, skip=skip, limit=limit)
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "display_name": u.display_name,
            "last_login": str(u.last_login) if u.last_login else None,
            "created_at": str(u.created_at),
        }
        for u in users
    ]


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Get a single user by ID."""
    user = await repo.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "display_name": user.display_name,
        "last_login": str(user.last_login) if user.last_login else None,
        "created_at": str(user.created_at),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    data: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Create a new user."""
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username and password required")

    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")

    existing = await repo.get_user_by_username(db, username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    email = data.get("email", "").strip() or None
    if email:
        from app.repositories import list_users
        all_users = await list_users(db)
        if any(u.email == email for u in all_users):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user_data = {
        "username": username,
        "hashed_password": hash_password(password),
        "email": email,
        "role": data.get("role", "user"),
        "is_active": data.get("is_active", True),
        "display_name": data.get("display_name", "").strip() or None,
    }
    user = await repo.create_user(db, user_data)
    await db.commit()  # Ensure data is persisted before response is sent
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "display_name": user.display_name,
    }


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a user's information (except password, which has its own endpoint)."""
    user = await repo.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = {}
    if "email" in data:
        update_data["email"] = data["email"].strip() or None
    if "role" in data:
        if user_id == current_user.id and data["role"] != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote yourself")
        update_data["role"] = data["role"]
    if "display_name" in data:
        update_data["display_name"] = data["display_name"].strip() or None
    if "is_active" in data:
        if user_id == current_user.id and not data["is_active"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disable yourself")
        update_data["is_active"] = data["is_active"]

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    updated = await repo.update_user(db, user_id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.commit()
    return {"message": "User updated successfully"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a user. Cannot delete yourself or the default admin account."""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    user = await repo.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.username == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the default admin account")

    await repo.delete_user(db, user_id)
    await db.commit()
    return {"message": "User deleted successfully"}


@router.put("/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Toggle a user's active status."""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot toggle your own status")

    user = await repo.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    old_active = user.is_active
    await repo.toggle_user_active(db, user_id)
    await db.commit()
    return {"message": f"User {'disabled' if old_active else 'enabled'} successfully", "is_active": not old_active}
