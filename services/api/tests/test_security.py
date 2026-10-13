import time
import uuid

import jwt
import pyotp
import pytest

from app.config import get_settings
from app.security import (
    TOTP_PERIOD,
    decode_jwt,
    decrypt_str,
    encrypt_str,
    hash_password,
    hash_refresh_token,
    issue_jwt,
    new_refresh_token,
    password_problems,
    totp_enrolment,
    verify_password,
    verify_totp,
)

settings = get_settings()


def test_password_roundtrip_uses_argon2id() -> None:
    h = hash_password("Correct-Horse-42")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "Correct-Horse-42")
    assert not verify_password(h, "wrong")


def test_unknown_user_never_verifies() -> None:
    assert not verify_password(None, "anything")


def test_corrupt_hash_is_rejected_not_raised() -> None:
    assert not verify_password("not-a-hash", "x")


@pytest.mark.parametrize(
    ("pw", "ok"),
    [
        ("Correct-Horse-42", True),
        ("short1A", False),
        ("alllowercase123", False),
        ("NoDigitsHereAtAll", False),
    ],
)
def test_password_policy(pw: str, ok: bool) -> None:
    assert (password_problems(pw) == []) is ok


def test_jwt_roundtrip_and_type_check() -> None:
    uid = uuid.uuid4()
    token = issue_jwt(settings, uid, "access")
    assert decode_jwt(settings, token, "access")["sub"] == str(uid)
    with pytest.raises(jwt.InvalidTokenError):
        decode_jwt(settings, token, "mfa")


def test_jwt_rejects_tampering_and_expiry() -> None:
    token = issue_jwt(settings, uuid.uuid4(), "access")
    with pytest.raises(jwt.PyJWTError):
        decode_jwt(settings, token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1], "access")
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "typ": "access", "iat": 1, "exp": 2},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_jwt(settings, expired, "access")


def test_jwt_rejects_alg_none() -> None:
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "typ": "access", "iat": 1, "exp": 9_999_999_999}, None, algorithm="none"
    )
    with pytest.raises(jwt.PyJWTError):
        decode_jwt(settings, forged, "access")


def test_refresh_tokens_are_random_and_hashed() -> None:
    a, ha = new_refresh_token()
    b, hb = new_refresh_token()
    assert a != b and ha != hb
    assert hash_refresh_token(a) == ha and len(ha) == 64


def test_totp_accepts_drift_and_blocks_replay() -> None:
    secret = pyotp.random_base32()
    now = time.time()
    code = pyotp.TOTP(secret).at(now)
    step = verify_totp(secret, code, None, now)
    assert step == int(now // TOTP_PERIOD)
    assert verify_totp(secret, code, step, now) is None  # replay
    prev = pyotp.TOTP(secret).at(now - TOTP_PERIOD)
    assert verify_totp(secret, prev, None, now) is not None  # one step of drift is fine
    old = pyotp.TOTP(secret).at(now - 5 * TOTP_PERIOD)
    assert verify_totp(secret, old, None, now) is None


def test_totp_enrolment_contains_issuer_and_qr() -> None:
    e = totp_enrolment(pyotp.random_base32(), "ceo@x.test", "Fault Sigma")
    assert e.otpauth_uri.startswith("otpauth://totp/Fault%20Sigma:ceo%40x.test")
    assert e.qr_svg.startswith("<svg")


def test_column_encryption_roundtrip_and_integrity() -> None:
    ct = encrypt_str(settings, "JBSWY3DPEHPK3PXP")
    assert ct.startswith("v1:") and "JBSWY3DP" not in ct
    assert decrypt_str(settings, ct) == "JBSWY3DPEHPK3PXP"
    assert encrypt_str(settings, "same") != encrypt_str(settings, "same")  # random nonce
    tampered = ct[:-4] + ("AAAA" if not ct.endswith("AAAA") else "BBBB")
    with pytest.raises(Exception):  # noqa: B017 - cryptography raises InvalidTag
        decrypt_str(settings, tampered)
