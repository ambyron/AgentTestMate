"""Auth API — login, current user, change password."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.__init_db import get_db
from app.auth.deps import get_current_user
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.models.user import User
from app import repositories as repo

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_space_id(db: AsyncSession, user: User) -> str | None:
    """Helper to look up a user's space_id."""
    space = await repo.get_space_by_owner(db, user.id)
    return space.id if space else None


@router.post("/login")
async def login(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and return a JWT access token."""
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username and password required")

    user = await repo.get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    # Update last_login
    from datetime import datetime, timezone
    await repo.update_user(db, user.id, {"last_login": datetime.now(timezone.utc)})

    space_id = await _get_space_id(db, user)

    token = create_access_token({"sub": user.id, "username": user.username, "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "display_name": user.display_name,
            "is_active": user.is_active,
            "space_id": space_id,
        },
    }


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the currently authenticated user's profile."""
    space_id = await _get_space_id(db, current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "display_name": current_user.display_name,
        "is_active": current_user.is_active,
        "space_id": space_id,
        "last_login": str(current_user.last_login) if current_user.last_login else None,
        "created_at": str(current_user.created_at),
    }


@router.put("/change-password")
async def change_password(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the current user's password."""
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password or not new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old and new passwords required")

    if len(new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")

    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect")

    await repo.update_user(db, current_user.id, {"hashed_password": hash_password(new_password)})
    await db.commit()
    return {"message": "Password updated successfully"}
