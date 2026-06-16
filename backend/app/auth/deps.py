"""FastAPI dependency injection for authentication and authorization."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.__init_db import get_db
from app.auth.jwt import decode_access_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    token: str | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the Bearer token and return the current user."""
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(token.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    from app.repositories import get_user_by_id
    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or deactivated")

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require the current user to have the admin role."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_optional_user(
    token: str | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Return the current user if a valid Bearer token is provided, else None."""
    if token is None:
        return None
    payload = decode_access_token(token.credentials)
    if payload is None:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    from app.repositories import get_user_by_id
    return await get_user_by_id(db, user_id)


async def get_current_space(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> str | None:
    """Return the current user's space_id, or None for admin (bypass filter)."""
    if current_user.role == "admin":
        return None
    from app.repositories import get_space_by_owner
    space = await get_space_by_owner(db, current_user.id)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No space found. Please create a space first.",
        )
    return space.id
