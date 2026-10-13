import json
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT = text(
    "INSERT INTO audit_log (actor_user_id, organisation_id, action, target, ip, user_agent, detail) "
    "VALUES (:actor, :org, :action, :target, CAST(:ip AS inet), :ua, CAST(:detail AS jsonb))"
)


def client_ip(request: Request) -> str | None:
    # uvicorn --proxy-headers already resolves X-Forwarded-For from trusted proxies (Caddy).
    return request.client.host if request.client else None


async def audit(
    session: AsyncSession,
    request: Request,
    action: str,
    *,
    actor: uuid.UUID | None = None,
    organisation_id: uuid.UUID | None = None,
    target: str | None = None,
    **detail: Any,
) -> None:
    """Append to the audit log. Plain SQL on purpose: the app role may write audit rows but not
    read them back, so the ORM's RETURNING / id pre-fetch must not happen. The table itself
    rejects UPDATE, DELETE and TRUNCATE."""
    await session.execute(
        _INSERT,
        {
            "actor": actor,
            "org": organisation_id,
            "action": action,
            "target": target,
            "ip": client_ip(request),
            "ua": (request.headers.get("user-agent") or "")[:400] or None,
            "detail": json.dumps(detail, default=str),
        },
    )
