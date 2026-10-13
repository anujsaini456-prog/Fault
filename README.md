# Fault Sigma

Fault Sigma is a secure, self-hosted platform that executives use to analyse faults and make data-driven decisions.

It brings together data from SCADA, disturbance-recorder (COMTRADE) files, Excel/CSV, PDF reports and field photos. From that data it produces KPIs, risk rankings and decision support. It ships as a web app and a mobile app, both with sign-in.

The platform runs on free and open-source software only. There are no third-party data flows, and SCADA access is read-only and outbound-only.

The full build specification is in **[docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md)**.

## Status

**Phase 1 (Foundation) is complete.** It includes the monorepo, Docker Compose, the API, sign-in with MFA, role-based access, Postgres Row-Level Security, the audit log, web and mobile sign-in, and an empty executive dashboard. The KPI tiles say "No data yet" until data ingestion arrives in Phase 2 and analytics in Phase 3.

## Quick start

You need Docker Desktop (or Docker Engine with Compose v2).

```sh
cp .env.example .env      # then replace every change-me value with a long random string
docker compose up -d      # builds and starts everything; first run takes a few minutes
```

Open **https://localhost**. Caddy uses its own local certificate authority for `localhost`, so your browser warns about the certificate on first visit. For a real hostname, set `FS_DOMAIN` and Caddy will get a certificate automatically.

### Demo accounts (created by the seed)

| Email | Password (from `.env`) | Organisation | Notes |
|---|---|---|---|
| `FS_SEED_ADMIN_EMAIL` (default `admin@example.com`) | `FS_SEED_ADMIN_PASSWORD` | Northgrid Power | Admin. Must enrol an authenticator app on first sign-in. |
| `ceo@northgrid.example` | `FS_SEED_EXEC_PASSWORD` | Northgrid Power | Executive, 3 sites |
| `ceo@southern.example` | `FS_SEED_EXEC_PASSWORD` | Southern Utilities | Executive, 2 sites. Sees no Northgrid data. |

Signing in as each executive in turn shows tenant isolation in action.

## Repository layout

```
apps/web/              React 19 + Vite + Tailwind + TanStack Query
apps/mobile/           Expo SDK 57 + expo-router (SecureStore, biometric unlock, screenshot blocking, offline cache)
packages/core/         Shared roles, Zod schemas and a typed API client (used by web and mobile)
services/api/          FastAPI + SQLAlchemy 2 (async) + Alembic
infra/postgres/        Database role setup (owner vs RLS-restricted app role)
infra/caddy/           Reverse proxy, HTTPS and strict security headers
docs/                  Specification, ADRs, PRIVACY.md
compose.yaml           The whole stack
```

## Development

Prerequisites: Node 20+, pnpm (`corepack enable pnpm`), Docker, and Python 3.12+ if you want to run the API outside Docker.

```sh
pnpm install
pnpm typecheck && pnpm test                      # core + web: typecheck and unit tests

docker compose up -d db redis
docker compose --profile test run --rm api-test  # API: unit + Postgres integration tests, with coverage
```

**Web, with hot reload.** Start the stack, then run `pnpm --filter @fault-sigma/web dev`. Vite proxies `/api` to `localhost:8000`, so run the API locally with `FS_COOKIE_SECURE=false`, or publish the api container's port.

**Mobile.** Run `pnpm --filter @fault-sigma/mobile start`, then open the app in Expo Go or a development build. Point it at your server with `EXPO_PUBLIC_API_URL=https://your-host/api`. A phone can't reach `localhost` on your computer, so use the computer's LAN hostname with a trusted certificate.

## Security model (summary)

- **Passwords** are hashed with Argon2id. Sign-in has per-IP and per-account rate limits, and accounts lock after 5 failures.
- **MFA:** TOTP is required for admins and optional for other roles. Codes can't be replayed, and secrets are encrypted at rest with AES-GCM.
- **Tokens:** access tokens are 15-minute JWTs held in memory only. Refresh tokens are opaque and rotate on every use, and reusing an old one revokes the whole session family. On the web they live in an `httpOnly; Secure; SameSite=Strict` cookie; on mobile they live in the Keychain or Keystore.
- **Authorisation:** role checks in the API, plus **Postgres Row-Level Security**. The API connects as a role that cannot bypass RLS, so a missing check in the code still cannot leak another organisation's data.
- **Audit:** the log is append-only, enforced by database triggers and grants.
- **No outbound calls:** a strict same-origin CSP, no CDNs, no analytics, and telemetry off in TimescaleDB. See [docs/PRIVACY.md](docs/PRIVACY.md).

The reasoning behind these choices is in [docs/ADR-0001-architecture.md](docs/ADR-0001-architecture.md), [docs/ADR-0002-authentication.md](docs/ADR-0002-authentication.md) and [docs/ADR-0003-tenant-isolation.md](docs/ADR-0003-tenant-isolation.md).
