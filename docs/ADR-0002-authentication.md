# ADR-0002: Authentication and sessions

**Status:** Accepted (Phase 1)

## Decision
| Concern | Choice | Why |
|---|---|---|
| Password hashing | Argon2id (t=3, m=64 MiB, p=4) | OWASP's first recommendation. Unknown emails are checked against a dummy hash so that timing doesn't reveal which accounts exist. |
| Password policy | 12 or more characters, mixed case, at least one digit | Accounts are created by admins. There is no self-sign-up. |
| Failed sign-ins | One generic message. Lock for 15 minutes after 5 failures (wrong passwords and wrong TOTP codes both count). Per-IP and per-account rate limits in Redis. | Slows brute force and doesn't reveal whether an account exists or is locked. |
| MFA | TOTP (RFC 6238), ±1 step of drift allowed, replay blocked by storing the last used step. Required for `admin`, enrolment forced at first sign-in. | Works with any free authenticator app and needs no SMS provider (which would be a third party). |
| TOTP secret storage | AES-256-GCM in the app, key from `FS_DATA_KEY` | A database dump alone cannot be used to recover second factors. Encrypting in the app rather than with pgcrypto keeps the key out of SQL and out of query logs. |
| Access token | HS256 JWT, 15 minutes, held in memory only | It can't be stolen from storage, and its short life limits the damage if it leaks. |
| Refresh token | 256-bit random value, stored only as a SHA-256 hash, rotated on every use, 30-day expiry | If an already-used token comes back, the whole session family is revoked. That catches theft. |
| Web transport | `httpOnly; Secure; SameSite=Strict` cookie scoped to `/api/auth`, plus a required `X-Client` header | Page scripts can't read it. Cross-site requests can't send it, and the custom header forces a CORS preflight that is never approved. |
| Mobile transport | Refresh token in the request body, stored in SecureStore with `WHEN_UNLOCKED_THIS_DEVICE_ONLY` | It isn't backed up and doesn't move to other devices. Biometric unlock is required before it is used. |
| Intermediate MFA step | A separate 5-minute JWT with `typ=mfa` | It is rejected everywhere an access token is expected. |

## Known limits and next steps
- **Access tokens can't be revoked individually.** They expire within 15 minutes, and refresh is revoked immediately on logout or reuse. A deny-list in Redis can be added if needed.
- **First-sign-in enrolment** means whoever first signs in with the admin password enrols the authenticator. Seed passwords must therefore be rotated, or the admin must sign in straight after deployment.
- **Not built yet:** password reset by email (it needs the organisation's own SMTP server), Keycloak OIDC, and certificate pinning on mobile (it needs a native build and a known server certificate). These are planned for the hardening phase.
