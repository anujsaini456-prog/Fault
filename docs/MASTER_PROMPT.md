# FAULT SIGMA — MASTER BUILD PROMPT

> Copy everything below this line into your AI coding tool (Claude Code, Cursor, etc.) or hand it to a development team.

## 1. Role
You are a senior full-stack architect and security engineer. You build industrial analytics software for power and utility companies. Build **Fault Sigma**, a production-grade, secure, self-hostable platform that turns raw fault data into clear executive decisions. Write clean, typed, tested, documented code. Do not cut corners on security. Do not use any paid service. Do not send any customer data to a third party.

## 2. Product vision
Fault Sigma brings together all fault-related data in one place: SCADA, disturbance recorders, spreadsheets, reports and field photos. It converts that data into:
1. **Answers**: what failed, where, why, how often, and at what cost.
2. **Foresight**: which assets are trending toward failure, and how risky they are.
3. **Decisions**: ranked, costed actions that leaders can approve, track and audit.

The main user is a **C-level or senior executive** who has 2 minutes on a phone. The secondary users are analysts and engineers who need full depth. Every screen must answer "So what? What should I do?"

## 3. Users and roles (RBAC)
| Role | Can do |
|---|---|
| **Executive** | View dashboards, drill down, ask questions, approve or reject decisions, export board packs. Read-only on raw data. |
| **Analyst** | Everything an Executive can do, plus upload data, build reports, run what-if scenarios and draft recommendations. |
| **Engineer** | Upload and annotate DR files and images, classify faults, enter root causes. |
| **Admin** | Manage users, roles, sites, connectors and retention policies. View audit logs. |

The system is multi-tenant: Organisation → Region → Site/Substation → Asset. Users only see the organisations and sites they are assigned to, and this is enforced in the database with Row-Level Security.

## 4. Data ingestion
### 4.1 File uploads (web and mobile)
| Type | Formats | Processing |
|---|---|---|
| Spreadsheets | `.xlsx`, `.xls`, `.csv` | Preview the data. Map columns to the Fault Sigma schema with auto-suggestions. Validate types and units, flag bad rows, and save the mapping as a reusable template. |
| PDF | Text PDFs and scanned PDFs | Extract tables (pdfplumber/camelot) and text. Run local OCR (Tesseract) on scanned pages. Show the extracted fields to a person for confirmation before saving. |
| DR / disturbance records | **IEEE COMTRADE** (`.cfg` + `.dat` ASCII/binary, `.hdr`, `.inf`, `.cff`), zipped bundles | Parse analog and digital channels. Run fault analysis as described in §5.2. Store the waveform and the derived metrics. |
| Images | `.jpg`, `.png`, `.heic` | Store as evidence linked to a fault or asset. Run local OCR on relay displays, nameplates and handwritten logs. Read EXIF time and GPS, then remove EXIF metadata before storing the image. |

Every upload must:
- Enforce a size limit.
- Check the file type by magic bytes, not by extension.
- Pass a ClamAV virus scan.
- Be parsed in a sandboxed background worker.
- Be stored with a SHA-256 hash for provenance and de-duplication.

Re-uploading the same file must not create duplicate records.

### 4.2 Live connections (read-only, outbound-only)
- Ship a separate **Edge Connector**: a small Python service in Docker that runs inside the plant or utility network.
- Supported protocols:
  - **OPC UA** (asyncua)
  - **Modbus TCP** (pymodbus)
  - **IEC 60870-5-104** (lib60870 / c104)
  - **DNP3** (opendnp3 bindings)
  - **MQTT** (Sparkplug B)
  - Scheduled pulls from a historian over SQL or REST
  - Polling a folder or SFTP location for new COMTRADE files from DR and IED devices
- The connector **only reads**. It never writes setpoints or commands to SCADA, and write function codes are disabled in code.
- The connector opens **outbound** TLS/mTLS connections to Fault Sigma (MQTT over TLS or HTTPS). It needs no inbound firewall ports. It must work through a data diode or DMZ.
- If the connection drops, the connector buffers data locally in SQLite and back-fills when the link returns. It sends a heartbeat, and its health is shown in the Admin view.
- Tag mapping UI: map SCADA tags to assets, signals and units, with deadband and sampling settings.

### 4.3 Data quality layer
- Every metric shows its **source, freshness and quality score**: completeness, duplicates, out-of-range values and unit mismatches.
- Executives see a simple "trust badge" (High, Medium or Low) on each KPI.

## 5. Analytics engine
### 5.1 Core KPIs (filter by time, region, site, asset class and voltage level)
- Fault count and rate per 100 km or per asset
- **MTBF, MTTR, availability**
- **SAIDI, SAIFI, CAIDI**, Energy Not Supplied (ENS)
- **DPMO and Sigma level**: Φ⁻¹(1 − DPMO/10⁶) + 1.5
- Cost of faults: repair, penalties, lost revenue and ENS × value of lost load
- Protection performance: correct, mal-operation or failure-to-trip %, and average clearing time

### 5.2 DR / COMTRADE fault analysis
- Detect fault inception and clearing time, and calculate fault duration.
- Classify the fault type: L-G, L-L, L-L-G, 3-phase or evolving.
- Calculate peak and RMS fault current, voltage sag depth and DC offset.
- Show the sequence of events from the digital channels: relay pickup, trip, breaker open and reclose.
- Estimate distance to fault using the impedance method when line parameters are known.
- Compare against normal values for the asset, flag statistical outliers (> 3σ), and run a protection operation check.
- Provide an interactive waveform viewer with zoom, phasors and channel selection, plus a one-click PDF fault report.

### 5.3 Insight and prediction
- Root-cause Pareto (80/20), trend and seasonality detection, and correlation with weather, load and asset age when that data is supplied.
- **Asset health and risk score**: probability × consequence, shown as a heat map and a ranked list.
- Simple, explainable forecasting (Prophet/statsmodels): expected faults over the next 30, 90 and 365 days, with confidence bands.
- Anomaly alerts on live data: threshold, rate-of-change and statistical alerts, sent by in-app and push notification.

### 5.4 Decision support (core executive features)
- **Recommendations board**: ranked actions such as "Replace CB-12 at Site X", each with expected fault reduction, cost, ROI or payback, risk reduction and confidence level.
- **What-if simulator**: adjust budget, maintenance interval or replacement plan and see the projected change in SAIDI, cost and Sigma.
- **Decision log**: approve, reject or defer each recommendation with a comment, owner and due date. Then track the actual outcome against the forecast. The log is immutable and audited.
- **Ask Fault Sigma**: natural-language Q&A over the data, such as "Why did outages rise in Q3 in the North region?". The answer comes with charts and cites the source data. It runs on a **local LLM through Ollama** (e.g. Llama 3 / Qwen / Mistral). Data never leaves the server. The feature turns off cleanly if no model is installed.
- **Board pack export**: a one-click PDF or PPTX executive summary with KPIs, top risks, decisions needed and trends. It can be scheduled weekly or monthly.

## 6. Tech stack (all free and open source, self-hostable)
| Layer | Choice |
|---|---|
| Monorepo | pnpm workspaces + Turborepo, TypeScript strict mode |
| Web app | React 18 + Vite + TypeScript, Tailwind + shadcn/ui, TanStack Query, React Router, **Apache ECharts** (dashboards and waveforms) |
| Mobile app | **Expo (React Native) + expo-router**, sharing the API client, types and validation with the web app. Uses expo-secure-store, biometric unlock (expo-local-authentication), push notifications and offline cache. |
| Shared packages | `packages/core` (types, Zod schemas, KPI formulas), `packages/api-client` (generated from OpenAPI) |
| API | **Python FastAPI** (async), Pydantic v2, SQLAlchemy 2 + Alembic |
| Workers | Redis + arq (or Celery) for parsing, OCR, analytics and report jobs |
| Database | **PostgreSQL 16 + TimescaleDB** for time series, with Row-Level Security per organisation and site |
| File storage | MinIO (S3-compatible, self-hosted) with server-side encryption |
| Live messaging | Eclipse Mosquitto (MQTT over TLS) |
| Parsing | `comtrade` (Python), pandas, openpyxl, pdfplumber, camelot, Tesseract OCR, Pillow |
| Analytics | numpy, scipy, statsmodels, Prophet, scikit-learn |
| Local AI (optional) | Ollama with an open-weights model, called only over localhost |
| Auth | Built into FastAPI (details in §7) |
| Reverse proxy | Caddy (automatic HTTPS) |
| Deploy | Docker Compose, one command: `docker compose up -d` |
| CI | GitHub Actions free tier: lint, typecheck, tests, Trivy and pip-audit/npm audit scans |

**Hosting options, all at zero cost:**
1. On-premises server or VM. This is recommended when SCADA is involved.
2. Oracle Cloud Always Free ARM VM (4 vCPU, 24 GB RAM).
3. A local laptop for demos.

Mobile builds: use Expo EAS free tier or local builds.

## 7. Security and privacy (mandatory)
- **No data sharing**:
  - No third-party analytics, trackers, ads or crash reporters that send data out.
  - No external AI APIs.
  - Fonts, icons and libraries are self-hosted, with no runtime CDN calls.
  - The CSP must block all external origins.
  - Telemetry is off. A `PRIVACY.md` must list every network call the system makes.
- **Authentication**:
  - Email and password hashed with **Argon2id**.
  - Mandatory **TOTP MFA** for Admins, optional for other roles.
  - Short-lived JWT access tokens (15 min) and rotating refresh tokens stored in httpOnly, Secure, SameSite=Strict cookies on web and in SecureStore on mobile.
  - Account lockout and rate limiting.
  - Password-reset emails through a self-hosted SMTP server or the organisation's own SMTP server.
  - Optional SSO through self-hosted Keycloak (OIDC).
- **Authorisation**: RBAC in the API **and** Postgres RLS (defence in depth). Deny by default.
- **Encryption**:
  - TLS 1.2 or higher everywhere, mTLS for edge connectors.
  - At rest: encrypted disk (LUKS), MinIO SSE and pgcrypto for sensitive columns.
  - Secrets come from `.env` or Docker secrets and are never committed.
- **Audit**: an append-only audit log of logins, views of sensitive data, uploads, exports, decisions and admin changes.
- **OT safety**: SCADA access is read-only and outbound-only, with no control paths. Follow IEC 62443 principles.
- **App hardening**:
  - Follow OWASP ASVS Level 2 and the OWASP Top 10.
  - Validate all input with Pydantic/Zod and use parameterised SQL only.
  - Set security headers.
  - Sandbox file parsers.
  - The mobile app blocks screenshots on sensitive screens, can wipe itself remotely on logout or revocation, and uses certificate pinning.
- **Data governance**:
  - Retention policies per data type.
  - Per-tenant export and delete (GDPR-style).
  - Encrypted daily backups (pg_dump + restic), with restore instructions that have been tested.

## 8. Core data model (minimum)
- `organisation`, `region`, `site`, `asset` (type, voltage, make, install date, criticality)
- `user`, `role`, `membership`
- `fault_event`: asset, start, end, type, cause, severity, customers affected, ENS, cost, source, quality score
- `dr_record` (COMTRADE metadata, channels, derived metrics) and `waveform` (TimescaleDB hypertable)
- `scada_signal` and `scada_reading` (hypertable)
- `connector` (config, heartbeat)
- `upload` (file hash, status, mapping template), `evidence_image`
- `recommendation`, `scenario`, `decision` (status, owner, due date, outcome)
- `alert_rule`, `alert`, `report_schedule`, `audit_log`

## 9. UX principles
- **Executive home screen (mobile first)**:
  - At the top, 5 KPI tiles, each with its trend arrow and trust badge.
  - Below that, "3 decisions waiting for you", then "Top 5 risks", then "What changed this week" in plain English.
- Every number can be tapped to drill down: Region → Site → Asset → Fault → DR waveform → Evidence.
- Use plain language, not jargon, on executive views. Engineering detail stays one tap away.
- Dark and light mode, WCAG 2.1 AA, and fast loading (< 2 s on 4G for the home screen).
- Offline mode on mobile: the last synced dashboards can be read without a connection.

## 10. Repository structure
```
fault-sigma/
  apps/web/            # React + Vite
  apps/mobile/         # Expo
  services/api/        # FastAPI
  services/worker/     # parsing / analytics jobs
  services/edge-connector/  # SCADA connector (separate deploy)
  packages/core/       # shared types, schemas, KPI formulas
  packages/api-client/ # generated client
  infra/               # docker-compose, Caddyfile, backups, seed data
  docs/                # architecture, security, PRIVACY.md, runbooks
```

## 11. Delivery phases
1. **Foundation**: monorepo, Docker Compose, auth with MFA, RBAC, RLS, audit log, web and mobile sign-in, and an empty dashboard.
2. **File ingestion**: CSV and Excel with column mapping, PDF, images with OCR, and COMTRADE parsing with the waveform viewer.
3. **Analytics**: KPIs, Sigma/DPMO, Pareto, trends, and drill-down dashboards on web and mobile.
4. **Live data**: Edge Connector (OPC UA, Modbus, IEC 104, MQTT), a live tiles view and alerts.
5. **Decision support**: risk scoring, recommendations, the what-if simulator, the decision log, board pack export and local-LLM Q&A.
6. **Hardening**: security tests, load tests, backup and restore drill, documentation and a demo seed dataset.

## 12. Acceptance criteria
- `docker compose up -d` on a clean machine brings up the full stack with demo data in under 10 minutes.
- An executive can sign in with MFA on web and mobile and see the home dashboard with live KPIs.
- Uploading a sample COMTRADE file produces the correct fault type, duration and peak current. Unit tests cover this using reference files.
- Uploading a messy Excel file shows a mapping preview, flags invalid rows and imports only the valid rows.
- A simulated OPC UA or Modbus server feeds live readings through the Edge Connector. An alert fires within 10 seconds of a threshold breach.
- A user from Organisation A cannot read Organisation B's data. This is proven by tests at both the API and the database level.
- A network capture of the running system shows **no outbound calls** to anything other than the configured connectors and SMTP server.
- Unit test coverage is at least 80% for the KPI formulas and parsers. End-to-end tests (Playwright for web, Maestro for mobile) cover sign-in, upload, drill-down and decision approval.

## 13. Rules for you (the builder)
- Ask before adding any dependency that is not free or open source, or that calls an external service.
- Explain each architectural decision briefly in `docs/ADR-*.md`.
- Never hard-code secrets. Provide `.env.example`.
- Build phase by phase. At the end of each phase, show working, tested software before moving on.
- Prefer simple, explainable analytics over black-box models. Executives must be able to see why a number is what it is.
