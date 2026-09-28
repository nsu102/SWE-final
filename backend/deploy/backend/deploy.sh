#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
test -f .env || { echo 'Create deploy/backend/.env using env.example'; exit 1; }
test -s certs/global-bundle.pem || { echo 'Install the RDS CA bundle first (README.md).'; exit 1; }
docker compose build api
# Run migration separately with the schema-owner URL if app has no DDL permission.
if [[ "${RUN_MIGRATIONS:-false}" == true ]]; then
  docker compose run --rm api python -m src.backend.migrate
fi
docker compose up -d api
bash healthcheck.sh
