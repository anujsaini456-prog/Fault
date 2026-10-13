# ADR-0003: Tenant isolation with Postgres Row-Level Security

**Status:** Accepted (Phase 1)

## Context
The specification requires that users only ever see the organisations and sites they are assigned to, enforced **in the database**, with the API's role checks as a second layer.

## Decision
- **Two database roles.**
  - `fault_owner` owns the schema and runs migrations. Table owners bypass RLS, so this role is never given to the API.
  - `fault_app` is what the API connects as. It is `NOBYPASSRLS` and has only the grants it needs. In particular it has `SELECT, INSERT` on `audit_log` and no `UPDATE` or `DELETE` there.
- **Per-request context.** After it validates the access token, the API runs `set_config('app.user_id', <uuid>, true)`. The `true` makes the setting **transaction-local**, so it can't leak to the next request through the connection pool.
- **Deny by default.** RLS is enabled on every tenant table, and only explicit policies grant access. With no user context, every table returns zero rows, and a test checks this.
- **Policies.**
  - `organisation` and `region`: rows in the user's member organisations.
  - `site`: members with organisation-wide scope see every site in the organisation. Site-scoped members (`membership.site_id` set) see only that site.
  - `app_user`: yourself, plus users in organisations you administer. During sign-in only, the one row whose email matches `app.auth_email` is also visible.
  - `membership`: your own memberships, plus every membership in organisations you administer. Only admins of an organisation can write to its memberships.
  - `audit_log`: anyone may append. Only admins of the related organisation may read.
- **Helper functions** such as `app_member_org_ids()` are `SECURITY DEFINER` with a fixed `search_path`. They can therefore read `membership` without recursing into its own policy.
- **The audit log is append-only.** On top of the grants, triggers reject `UPDATE`, `DELETE` and `TRUNCATE`, even by the owner.
- **`refresh_token` has no RLS.** It holds no tenant data and is only ever looked up by an unguessable 256-bit hash.

## Evidence
`services/api/tests/test_tenant_isolation.py` connects as `fault_app` and goes straight to the database, without the API. It shows:
- cross-organisation reads return nothing;
- cross-organisation writes are refused;
- site-scoped members see only their own site;
- with no user context, nothing is visible;
- the audit log cannot be altered.

The same file also checks isolation through the HTTP API.

## Consequences
- Every new tenant table must have RLS enabled and policies in the same migration that creates it. Phase 2 and later migrations must follow this pattern.
- Because emails are unique across all tenants, an admin who tries to create a user whose email already exists in another organisation gets a 409 conflict. That reveals the email is in use somewhere. This is accepted, because accounts are created by admins and the same person can belong to several organisations.
