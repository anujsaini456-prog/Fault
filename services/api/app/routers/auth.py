import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit, client_ip
from app.config import Settings
from app.db import set_rls_auth_email, set_rls_user
from app.deps import DB, SettingsDep
from app.models import RefreshToken, User
from app.ratelimit import RateLimiter, get_rate_limiter
from app.schemas import (
    LoginOut,
    LoginRequest,
    MembershipOut,
    MfaRequiredOut,
    MfaSetupOut,
    MfaVerifyRequest,
    RefreshRequest,
    SessionOut,
    UserOut,
)
from app.security import (
    decode_jwt,
    decrypt_str,
    encrypt_str,
    hash_refresh_token,
    issue_jwt,
    new_refresh_token,
    new_totp_secret,
    totp_enrolment,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "fs_refresh"
MFA_REQUIRED_ROLES = {"admin"}
BAD_CREDENTIALS = "Invalid email or password, or the account is temporarily locked."

Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
ClientKind = Annotated[str | None, Header(alias="X-Client")]


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        mfa_enabled=user.mfa_enabled,
        memberships=[
            MembershipOut(
                organisation_id=m.organisation_id,
                organisation_name=m.organisation.name,
                site_id=m.site_id,
                role=m.role,  # type: ignore[arg-type]
            )
            for m in user.memberships
        ],
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _require_client(client: str | None) -> str:
    # A custom header can't be sent cross-site without a CORS preflight, which this API never
    # approves. Together with SameSite=Strict this makes cookie-based refresh CSRF-proof.
    if client not in ("web", "mobile"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing or invalid X-Client header")
    return client


async def _register_failure(db: AsyncSession, request: Request, settings: Settings, user: User) -> None:
    user.failed_logins += 1
    if user.failed_logins >= settings.max_failed_logins:
        user.locked_until = _now() + timedelta(seconds=settings.lockout_s)
        user.failed_logins = 0
        await audit(db, request, "account_locked", actor=user.id, target=str(user.id))
    # Persist the counter and the audit row even though the request is about to fail.
    await db.commit()


async def _issue_session(
    db: AsyncSession,
    request: Request,
    response: Response,
    settings: Settings,
    user: User,
    client: str,
    family_id: uuid.UUID | None = None,
) -> SessionOut:
    token, token_hash = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            token_hash=token_hash,
            expires_at=_now() + timedelta(seconds=settings.refresh_token_ttl_s),
        )
    )
    user.last_login_at = _now()
    if client == "web":
        response.set_cookie(
            REFRESH_COOKIE,
            token,
            max_age=settings.refresh_token_ttl_s,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            path=settings.cookie_path,
        )
    return SessionOut(
        access_token=issue_jwt(settings, user.id, "access", {"mfa": user.mfa_enabled}),
        expires_in=settings.access_token_ttl_s,
        refresh_token=token if client == "mobile" else None,
        user=user_out(user),
    )


@router.post("/login", response_model=LoginOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DB,
    settings: SettingsDep,
    limiter: Limiter,
    x_client: ClientKind = None,
) -> LoginOut:
    client = _require_client(x_client)
    await limiter.hit(f"login:ip:{client_ip(request)}", settings.login_rate_per_min)
    await limiter.hit(f"login:email:{body.email}", settings.login_rate_per_min)

    await set_rls_auth_email(db, body.email)
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()

    locked = user is not None and user.locked_until is not None and user.locked_until > _now()
    # Always run the hash check, even for unknown or locked users, so timing reveals nothing.
    password_ok = verify_password(user.password_hash if user else None, body.password)

    if user is None or not user.is_active or locked or not password_ok:
        await audit(
            db,
            request,
            "login_failed",
            actor=user.id if user else None,
            reason="locked" if locked else "bad_credentials",
            email=body.email,
        )
        if user is not None and not locked and not password_ok:
            await _register_failure(db, request, settings, user)
        else:
            await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)

    user.failed_logins = 0
    await set_rls_user(db, user.id)
    await db.refresh(user, ["memberships"])

    if user.mfa_enabled:
        await audit(db, request, "login_password_ok", actor=user.id)
        return MfaRequiredOut(mfa_token=issue_jwt(settings, user.id, "mfa", {"stage": "verify"}))

    if any(m.role in MFA_REQUIRED_ROLES for m in user.memberships):
        enrol = totp_enrolment(new_totp_secret(), user.email, settings.totp_issuer)
        user.mfa_secret_enc = encrypt_str(settings, enrol.secret)
        user.last_totp_step = None
        await audit(db, request, "mfa_enrolment_started", actor=user.id)
        return MfaSetupOut(
            mfa_token=issue_jwt(settings, user.id, "mfa", {"stage": "setup"}),
            otpauth_uri=enrol.otpauth_uri,
            secret=enrol.secret,
            qr_svg=enrol.qr_svg,
        )

    await audit(db, request, "login", actor=user.id, mfa=False)
    return await _issue_session(db, request, response, settings, user, client)


@router.post("/mfa/verify", response_model=SessionOut)
async def verify_mfa(
    body: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: DB,
    settings: SettingsDep,
    limiter: Limiter,
    x_client: ClientKind = None,
) -> SessionOut:
    client = _require_client(x_client)
    await limiter.hit(f"mfa:ip:{client_ip(request)}", settings.login_rate_per_min)
    try:
        claims = decode_jwt(settings, body.mfa_token, "mfa")
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired. Start again.") from None
    await limiter.hit(f"mfa:user:{user_id}", settings.login_rate_per_min)

    await set_rls_user(db, user_id)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or user.mfa_secret_enc is None
        or (user.locked_until is not None and user.locked_until > _now())
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired. Start again.")

    step = verify_totp(decrypt_str(settings, user.mfa_secret_enc), body.code, user.last_totp_step)
    if step is None:
        await audit(db, request, "mfa_failed", actor=user.id)
        await _register_failure(db, request, settings, user)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "That code didn't work. Check your app and try again."
        )

    user.last_totp_step = step
    user.failed_logins = 0
    if claims.get("stage") == "setup" and not user.mfa_enabled:
        user.mfa_enabled = True
        await audit(db, request, "mfa_enrolled", actor=user.id)
    await audit(db, request, "login", actor=user.id, mfa=True)
    return await _issue_session(db, request, response, settings, user, client)


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    request: Request,
    response: Response,
    db: DB,
    settings: SettingsDep,
    body: RefreshRequest | None = None,
    x_client: ClientKind = None,
    cookie_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> SessionOut:
    client = _require_client(x_client)
    token = (body.refresh_token if body else None) if client == "mobile" else cookie_token
    expired = HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.")
    if not token:
        raise expired

    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
    ).scalar_one_or_none()
    if row is None:
        raise expired
    if row.revoked_at is not None:
        # A rotated-out token came back: it was stolen or replayed. Kill the whole family.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await audit(db, request, "refresh_token_reuse", actor=row.user_id)
        await db.commit()
        raise expired
    if row.expires_at <= _now():
        raise expired

    row.revoked_at = _now()
    await set_rls_user(db, row.user_id)
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise expired
    return await _issue_session(db, request, response, settings, user, client, family_id=row.family_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: DB,
    settings: SettingsDep,
    body: RefreshRequest | None = None,
    x_client: ClientKind = None,
    cookie_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    client = _require_client(x_client)
    token = (body.refresh_token if body else None) if client == "mobile" else cookie_token
    if token:
        row = (
            await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
        ).scalar_one_or_none()
        if row is not None:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
            await audit(db, request, "logout", actor=row.user_id)
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    out.delete_cookie(
        REFRESH_COOKIE,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return out
