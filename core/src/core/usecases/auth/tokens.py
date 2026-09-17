"""Access-токены (JWT HS256, короткоживущие) и refresh-токены (opaque, в БД хешем)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from core.usecases.auth.config import AuthConfig

_ALGORITHM = "HS256"


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    is_admin: bool
    expires_at: datetime


def issue_access_token(
    cfg: AuthConfig, *, user_id: int, is_admin: bool, now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "adm": is_admin,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=cfg.access_ttl_seconds)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(cfg: AuthConfig, token: str) -> AccessClaims | None:
    """None для любого невалидного или просроченного токена: причина клиенту не важна."""
    try:
        payload = jwt.decode(
            token, cfg.jwt_secret, algorithms=[_ALGORITHM], options={"require": ["sub", "exp"]}
        )
        return AccessClaims(
            user_id=int(payload["sub"]),
            is_admin=bool(payload.get("adm", False)),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expiry(cfg: AuthConfig, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(seconds=cfg.refresh_ttl_seconds)
