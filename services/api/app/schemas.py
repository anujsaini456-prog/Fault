"""API request/response models. Mirrors packages/core/src/schemas.ts — keep the two in step."""

import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

Role = Literal["executive", "analyst", "engineer", "admin"]
ROLES: tuple[Role, ...] = ("executive", "analyst", "engineer", "admin")


# Structural check only. Accounts are created by admins (no self-sign-up), and on-premises
# deployments commonly use internal domains such as corp.local that strict validators reject.
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    AfterValidator(str.lower),
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(Strict):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class MfaVerifyRequest(Strict):
    mfa_token: str = Field(min_length=1, max_length=2000)
    code: str = Field(pattern=r"^\d{6}$")


class RefreshRequest(Strict):
    refresh_token: str | None = Field(default=None, max_length=200)


class MembershipOut(BaseModel):
    organisation_id: uuid.UUID
    organisation_name: str
    site_id: uuid.UUID | None
    role: Role


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    mfa_enabled: bool
    memberships: list[MembershipOut]


class SessionOut(BaseModel):
    status: Literal["ok"] = "ok"
    access_token: str
    expires_in: int
    refresh_token: str | None = None
    user: UserOut


class MfaRequiredOut(BaseModel):
    status: Literal["mfa_required"] = "mfa_required"
    mfa_token: str


class MfaSetupOut(BaseModel):
    status: Literal["mfa_setup_required"] = "mfa_setup_required"
    mfa_token: str
    otpauth_uri: str
    secret: str
    qr_svg: str


LoginOut = SessionOut | MfaRequiredOut | MfaSetupOut


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str


class KpiTile(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    trend: Literal["up", "down", "flat"] | None
    higher_is_better: bool
    trust: Literal["high", "medium", "low", "none"]


class DashboardHome(BaseModel):
    organisations: list[OrgOut]
    site_count: int
    kpis: list[KpiTile]
    decisions_waiting: list[dict[str, object]]
    top_risks: list[dict[str, object]]
    what_changed: list[str]


class CreateUserRequest(Strict):
    email: Email
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)
    organisation_id: uuid.UUID
    site_id: uuid.UUID | None = None
    role: Role


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    at: str
    actor_user_id: uuid.UUID | None
    organisation_id: uuid.UUID | None
    action: str
    target: str | None
    ip: str | None
    detail: dict[str, object]
