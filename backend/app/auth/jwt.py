"""JWT token creation and verification."""

from datetime import datetime, timedelta, timezone

import jwt as _jwt

from app.config import settings


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token with HS256 signing."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire})
    return _jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token. Returns payload dict or None."""
    try:
        return _jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except _jwt.PyJWTError:
        return None
