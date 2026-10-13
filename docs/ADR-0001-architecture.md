# ADR-0001: Overall architecture

**Status:** Accepted (Phase 1)

## Context
Fault Sigma has to be self-hostable on a single on-premises server, use only free and open-source software, serve both a web app and a mobile app, and never send data to third parties.

## Decision
- **Monorepo** (pnpm workspaces + Turborepo). `packages/core` holds the roles, the Zod schemas and a typed API client that both web and mobile import, so a contract change shows up as a type error in both apps.
- **Python FastAPI API.** The later phases (COMTRADE parsing, pandas, scipy, statsmodels, OCR) are Python-native, so keeping the API in the same language avoids a second backend.
- **PostgreSQL 16 + TimescaleDB** in one database. It holds relational tenancy data now and time-series waveforms and SCADA readings later. RLS gives tenant isolation inside the database itself (see ADR-0003).
- **Caddy** serves the built web app and reverse-proxies `/api`, so everything is same-origin. That lets the refresh cookie be `SameSite=Strict` with no CORS at all.
- **Docker Compose** with a one-shot `migrate` service. Migrations and the seed run with the schema-owner credentials, and the long-running API only ever holds the restricted app-role credentials.
- **Redis** backs the rate limiter now and the job queue in Phase 2.
- **Swagger UI is disabled** because it loads assets from a public CDN. `/openapi.json` is still served for client generation.
- **React 19.2 everywhere** (the spec says React 18). Expo SDK 57 requires React 19, and a monorepo with hoisted dependencies needs a single React version. Otherwise the type definitions clash. Nothing in the web app depends on React 18 behaviour.

## Deferred
- **MinIO object storage moves to Phase 2.** It is first needed when files are uploaded. MinIO's community distribution changed in 2025, so the S3-compatible store (MinIO, SeaweedFS or Garage) will be chosen then.
- The **API client is hand-written** in `packages/core` and validated with Zod at runtime. If the API surface grows, generating it from OpenAPI becomes worthwhile.
- **shadcn/ui** will be added when there are enough interactive components to justify it. Phase 1 uses Tailwind directly.
