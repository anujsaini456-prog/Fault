"""Password hashing, tokens, TOTP and column encryption. Pure functions; no DB access."""

import base64
import hashlib
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import jwt
import pyotp
import segno
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings

# --- Passwords (Argon2id, OWASP-recommended parameters) ---------------------------------------

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
# Verified against when the email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.lower() == password or password.upper() == password:
        problems.append("must mix upper and lower case")
    if not any(c.isdigit() for c in password):
        problems.append("must contain a digit")
    return problems


# --- JWTs ---------------------------------------------------------------------------------------

TokenType = Literal["access", "mfa"]
_ALG = "HS256"


def issue_jwt(settings: Settings, sub: uuid.UUID, typ: TokenType, extra: dict[str, Any] | None = None) -> str:
    now = int(time.time())
    ttl = settings.access_token_ttl_s if typ == "access" else settings.mfa_token_ttl_s
    claims = {"sub": str(sub), "typ": typ, "iat": now, "exp": now + ttl, "jti": secrets.token_hex(8)}
    claims.update(extra or {})
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=_ALG)


def decode_jwt(settings: Settings, token: str, typ: TokenType) -> dict[str, Any]:
    """Raises jwt.PyJWTError on any problem, including a token of the wrong type."""
    claims: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[_ALG],
        options={"require": ["sub", "typ", "exp", "iat"]},
    )
    if claims.get("typ") != typ:
        raise jwt.InvalidTokenError("wrong token type")
    return claims


# --- Refresh tokens (opaque, stored only as a hash) ---------------------------------------------


def new_refresh_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- TOTP ---------------------------------------------------------------------------------------

TOTP_PERIOD = 30


def new_totp_secret() -> str:
    return pyotp.random_base32()


@dataclass(frozen=True)
class TotpEnrolment:
    secret: str
    otpauth_uri: str
    qr_svg: str


def totp_enrolment(secret: str, email: str, issuer: str) -> TotpEnrolment:
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)
    qr_svg = segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#0f172a", light="#ffffff")
    return TotpEnrolment(secret=secret, otpauth_uri=uri, qr_svg=qr_svg)


def verify_totp(secret: str, code: str, last_step: int | None, now: float | None = None) -> int | None:
    """Return the matched time step, or None. Allows ±1 step of clock drift and rejects
    any step at or before `last_step`, so a code can never be replayed."""
    totp = pyotp.TOTP(secret)
    current = int((now if now is not None else time.time()) // TOTP_PERIOD)
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if secrets.compare_digest(totp.at(step * TOTP_PERIOD), code):
            return step
    return None


# --- Column encryption (AES-256-GCM) ------------------------------------------------------------


def _data_key(settings: Settings) -> bytes:
    material = (settings.data_key or settings.jwt_secret).get_secret_value().encode()
    return hashlib.sha256(b"fault-sigma/column-key/v1" + material).digest()


def encrypt_str(settings: Settings, plaintext: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_data_key(settings)).encrypt(nonce, plaintext.encode(), b"fs-v1")
    return "v1:" + base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_str(settings: Settings, token: str) -> str:
    version, _, payload = token.partition(":")
    if version != "v1":
        raise ValueError("unknown ciphertext version")
    raw = base64.urlsafe_b64decode(payload)
    return AESGCM(_data_key(settings)).decrypt(raw[:12], raw[12:], b"fs-v1").decode()
