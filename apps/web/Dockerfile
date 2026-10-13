# syntax=docker/dockerfile:1
# Build context: repository root (needs the workspace + shared packages).
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile --filter "@fault-sigma/web..." \
 && pnpm --filter @fault-sigma/web build

FROM caddy:2.8.4-alpine
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /repo/apps/web/dist /srv
