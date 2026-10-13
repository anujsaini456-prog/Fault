from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit import audit
from app.deps import DB, admin_org_ids, require_role
from app.models import AuditLog, Membership, Organisation, Site, User
from app.schemas import AuditEntryOut, CreateUserRequest, MembershipOut, UserOut
from app.security import hash_password, password_problems

router = APIRouter(prefix="/admin", tags=["admin"])

AdminUser = Annotated[User, Depends(require_role("admin"))]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: CreateUserRequest, admin: AdminUser, db: DB, request: Request) -> UserOut:
    if body.organisation_id not in admin_org_ids(admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not an administrator of that organisation")
    if body.site_id is not None:
        site = (
            await db.execute(
                select(Site).where(Site.id == body.site_id, Site.organisation_id == body.organisation_id)
            )
        ).scalar_one_or_none()
        if site is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Site not found in that organisation")
    if problems := password_problems(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Password " + "; ".join(problems))

    user = User(email=body.email, full_name=body.full_name, password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists") from None
    db.add(
        Membership(
            user_id=user.id, organisation_id=body.organisation_id, site_id=body.site_id, role=body.role
        )
    )
    org = (await db.execute(select(Organisation).where(Organisation.id == body.organisation_id))).scalar_one()
    await audit(
        db,
        request,
        "user_created",
        actor=admin.id,
        organisation_id=org.id,
        target=str(user.id),
        role=body.role,
    )
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        mfa_enabled=False,
        memberships=[
            MembershipOut(
                organisation_id=org.id, organisation_name=org.name, site_id=body.site_id, role=body.role
            )
        ],
    )


@router.get("/audit", response_model=list[AuditEntryOut])
async def list_audit(
    admin: AdminUser, db: DB, request: Request, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[AuditEntryOut]:
    rows = (await db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))).scalars().all()
    await audit(db, request, "audit_log_viewed", actor=admin.id, count=len(rows))
    return [
        AuditEntryOut(
            id=r.id,
            at=r.at.isoformat(),
            actor_user_id=r.actor_user_id,
            organisation_id=r.organisation_id,
            action=r.action,
            target=r.target,
            ip=str(r.ip) if r.ip else None,
            detail=r.detail,
        )
        for r in rows
    ]
