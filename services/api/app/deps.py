import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db, set_rls_user
from app.models import User
from app.schemas import Role
from app.security import decode_jwt

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_UNAUTHENTICATED = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "Not signed in", headers={"WWW-Authenticate": "Bearer"}
)


async def get_current_user(
    db: DB,
    settings: SettingsDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Validates the access token, then pins the DB transaction to this user so every
    following query in the request is filtered by Row-Level Security."""
    if creds is None:
        raise _UNAUTHENTICATED
    try:
        claims = decode_jwt(settings, creds.credentials, "access")
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        raise _UNAUTHENTICATED from None
    await set_rls_user(db, user_id)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: Role) -> Callable[[User], Awaitable[User]]:
    """RBAC gate, deny by default. Postgres RLS enforces the same rules underneath."""

    async def check(user: CurrentUser) -> User:
        if not any(m.role in allowed for m in user.memberships):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this")
        return user

    return check


def admin_org_ids(user: User) -> set[uuid.UUID]:
    return {m.organisation_id for m in user.memberships if m.role == "admin"}
