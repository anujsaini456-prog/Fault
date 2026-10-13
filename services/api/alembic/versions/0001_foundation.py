"""Foundation: tenancy, users, auth, audit log, Row-Level Security.

Runs as the schema owner (fault_owner). The API connects as fault_app, which is NOT the owner,
so every policy below applies to it. Security-definer helpers run as the owner and therefore
can read `membership` without recursing into its own policy.

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "fault_app"

SCHEMA = """
CREATE TABLE organisation (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(200) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE region (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id  uuid NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    name             varchar(200) NOT NULL
);
CREATE INDEX ix_region_org ON region(organisation_id);

CREATE TABLE site (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id  uuid NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    region_id        uuid REFERENCES region(id) ON DELETE SET NULL,
    name             varchar(200) NOT NULL,
    code             varchar(50)
);
CREATE INDEX ix_site_org ON site(organisation_id);

CREATE TABLE app_user (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email           varchar(320) NOT NULL UNIQUE CHECK (email = lower(email)),
    full_name       varchar(200) NOT NULL,
    password_hash   text NOT NULL,
    mfa_enabled     boolean NOT NULL DEFAULT false,
    mfa_secret_enc  text,
    last_totp_step  bigint,
    failed_logins   integer NOT NULL DEFAULT 0,
    locked_until    timestamptz,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_login_at   timestamptz
);

CREATE TABLE membership (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    organisation_id  uuid NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    site_id          uuid REFERENCES site(id) ON DELETE CASCADE,
    role             varchar(20) NOT NULL CHECK (role IN ('executive', 'analyst', 'engineer', 'admin'))
);
CREATE UNIQUE INDEX ux_membership ON membership(user_id, organisation_id, COALESCE(site_id, '00000000-0000-0000-0000-000000000000'), role);
CREATE INDEX ix_membership_org ON membership(organisation_id);

CREATE TABLE refresh_token (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    family_id   uuid NOT NULL,
    token_hash  varchar(64) NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz
);
CREATE INDEX ix_refresh_family ON refresh_token(family_id);

CREATE TABLE audit_log (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at               timestamptz NOT NULL DEFAULT now(),
    actor_user_id    uuid,
    organisation_id  uuid,
    action           varchar(64) NOT NULL,
    target           varchar(200),
    ip               inet,
    user_agent       varchar(400),
    detail           jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_audit_at ON audit_log(at DESC);
CREATE INDEX ix_audit_org ON audit_log(organisation_id);
"""

# Append-only: even the owner cannot rewrite history through normal DML.
AUDIT_GUARD = """
CREATE FUNCTION audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END $$;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_immutable();
"""

HELPERS = """
CREATE FUNCTION app_current_user_id() RETURNS uuid
    LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$$;

CREATE FUNCTION app_member_org_ids() RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT organisation_id FROM membership WHERE user_id = app_current_user_id()
$$;

CREATE FUNCTION app_admin_org_ids() RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT organisation_id FROM membership WHERE user_id = app_current_user_id() AND role = 'admin'
$$;

-- A site is visible to org-wide members (site_id IS NULL) and to members scoped to that site.
CREATE FUNCTION app_can_see_site(p_site uuid, p_org uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT EXISTS (
        SELECT 1 FROM membership
        WHERE user_id = app_current_user_id()
          AND organisation_id = p_org
          AND (site_id IS NULL OR site_id = p_site)
    )
$$;

-- Admins can see the user records of people in organisations they administer.
CREATE FUNCTION app_admin_can_see_user(p_user uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT EXISTS (
        SELECT 1 FROM membership
        WHERE user_id = p_user AND organisation_id IN (SELECT app_admin_org_ids())
    )
$$;
"""

# Deny by default: RLS is on for every tenant table, and only these policies grant access.
POLICIES = """
ALTER TABLE organisation ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_member_read ON organisation FOR SELECT
    USING (id IN (SELECT app_member_org_ids()));

ALTER TABLE region ENABLE ROW LEVEL SECURITY;
CREATE POLICY region_member_read ON region FOR SELECT
    USING (organisation_id IN (SELECT app_member_org_ids()));

ALTER TABLE site ENABLE ROW LEVEL SECURITY;
CREATE POLICY site_member_read ON site FOR SELECT
    USING (app_can_see_site(id, organisation_id));

ALTER TABLE membership ENABLE ROW LEVEL SECURITY;
CREATE POLICY membership_read ON membership FOR SELECT
    USING (user_id = app_current_user_id() OR organisation_id IN (SELECT app_admin_org_ids()));
CREATE POLICY membership_admin_write ON membership FOR ALL
    USING (organisation_id IN (SELECT app_admin_org_ids()))
    WITH CHECK (organisation_id IN (SELECT app_admin_org_ids()));

ALTER TABLE app_user ENABLE ROW LEVEL SECURITY;
-- During login only: the transaction sets app.auth_email and may see that one row.
CREATE POLICY user_read ON app_user FOR SELECT
    USING (
        id = app_current_user_id()
        OR email = NULLIF(current_setting('app.auth_email', true), '')
        OR app_admin_can_see_user(id)
    );
CREATE POLICY user_update ON app_user FOR UPDATE
    USING (
        id = app_current_user_id()
        OR email = NULLIF(current_setting('app.auth_email', true), '')
        OR app_admin_can_see_user(id)
    );
CREATE POLICY user_admin_insert ON app_user FOR INSERT
    WITH CHECK (EXISTS (SELECT app_admin_org_ids()));

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_insert ON audit_log FOR INSERT WITH CHECK (true);
CREATE POLICY audit_admin_read ON audit_log FOR SELECT
    USING (
        organisation_id IN (SELECT app_admin_org_ids())
        OR actor_user_id IN (
            SELECT user_id FROM membership WHERE organisation_id IN (SELECT app_admin_org_ids())
        )
    );
"""

GRANTS = f"""
GRANT USAGE ON SCHEMA public TO {APP_ROLE};
GRANT SELECT ON organisation, region, site TO {APP_ROLE};
GRANT SELECT, INSERT, UPDATE ON app_user TO {APP_ROLE};
GRANT SELECT, INSERT, UPDATE, DELETE ON membership TO {APP_ROLE};
-- refresh_token is reachable only by its unguessable hash; it holds no tenant data.
GRANT SELECT, INSERT, UPDATE ON refresh_token TO {APP_ROLE};
GRANT SELECT, INSERT ON audit_log TO {APP_ROLE};
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP_ROLE};
"""


def _statements(sql: str) -> list[str]:
    """Split on top-level semicolons (asyncpg runs one statement per call), keeping $$ bodies whole."""
    out, buf, in_body = [], [], False
    for line in sql.splitlines():
        if line.strip().startswith("--") and not in_body:
            continue
        buf.append(line)
        in_body ^= line.count("$$") % 2 == 1
        if not in_body and line.rstrip().endswith(";"):
            out.append("\n".join(buf).strip())
            buf = []
    if "\n".join(buf).strip():
        out.append("\n".join(buf).strip())
    return out


def upgrade() -> None:
    for block in (SCHEMA, AUDIT_GUARD, HELPERS, POLICIES, GRANTS):
        for stmt in _statements(block):
            op.execute(stmt)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS audit_log, refresh_token, membership, app_user, site, region, organisation CASCADE"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS audit_log_immutable, app_current_user_id, app_member_org_ids, "
        "app_admin_org_ids, app_can_see_site, app_admin_can_see_user"
    )
