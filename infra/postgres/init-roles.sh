#!/bin/sh
# Runs once, as the Postgres superuser, the first time the data volume is created.
#   fault_owner : owns the schema, runs migrations. Owners bypass RLS — never used by the API.
#   fault_app   : what the API connects as. Not owner, no BYPASSRLS, so every policy applies.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE fault_owner LOGIN PASSWORD '${FS_DB_OWNER_PASSWORD}';
CREATE ROLE fault_app LOGIN PASSWORD '${FS_DB_APP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE DATABASE faultsigma OWNER fault_owner;
CREATE DATABASE faultsigma_test OWNER fault_owner;
REVOKE ALL ON DATABASE faultsigma FROM PUBLIC;
REVOKE ALL ON DATABASE faultsigma_test FROM PUBLIC;
GRANT CONNECT ON DATABASE faultsigma, faultsigma_test TO fault_owner, fault_app;
SQL

for db in faultsigma faultsigma_test; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<SQL
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO fault_owner;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS timescaledb;
SQL
done
