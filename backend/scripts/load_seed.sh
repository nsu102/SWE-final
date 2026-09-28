#!/usr/bin/env bash
set -euo pipefail
# Postgres 컨테이너가 빈 볼륨으로 처음 뜰 때 001-schema.sql 다음에 실행됩니다.
for part in /seed/*.sql.gz; do
  echo "loading $part"
  gunzip -c "$part" | psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
done
