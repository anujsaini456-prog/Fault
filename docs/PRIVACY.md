# Privacy: every network call Fault Sigma makes

Fault Sigma sends no data to third parties. It has no analytics, trackers, advertising, crash reporting, external AI services or runtime CDNs. This file lists **every** network connection the running system makes. A change that adds a connection must update this file.

## At runtime (Phase 1)

| From | To | Why | Leaves your network? |
|---|---|---|---|
| Browser / mobile app | Your Fault Sigma host (Caddy, port 443) | The app itself and `/api` | No |
| Caddy | `api:8000` | Reverse proxy | No (Docker network) |
| API | `db:5432`, `redis:6379` | Database, rate limiting | No (Docker network) |
| Caddy | Let's Encrypt / ZeroSSL ACME servers | Only when `FS_DOMAIN` is a public hostname, to get a TLS certificate. The only data sent is the hostname. | Yes, but not for `localhost` or internal names. You can also supply your own certificate. |

Telemetry that is turned off:
- **TimescaleDB:** `timescaledb.telemetry_level=off` and `TIMESCALEDB_TELEMETRY=off`.
- **Caddy:** has no telemetry, and its admin API is disabled.
- **Expo:** the mobile app ships no analytics modules.

## Browser enforcement
The Content-Security-Policy is `default-src 'self'` with `connect-src 'self'`. The browser itself refuses any request to another origin. The web bundle contains no external URLs except XML namespace identifiers and React's error-message link, and none of these is ever fetched.

## Build time only (not runtime)
Building images and apps downloads packages from Docker Hub, PyPI and the npm registry. Mobile builds may use Expo EAS (free tier) or local builds. None of these steps involves customer data.

## Planned (later phases)
- **SMTP:** password-reset and alert emails, through your own SMTP server only.
- **Edge Connector:** outbound mTLS from inside your network to your Fault Sigma host.
- **Ollama:** local LLM over `localhost` only.
- **Push notifications:** these go through Apple/Google push services and are designed to carry no fault data, only a "you have N alerts" prompt. They can be switched off per deployment.
