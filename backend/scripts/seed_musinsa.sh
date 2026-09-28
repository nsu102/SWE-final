#!/usr/bin/env bash
set -euo pipefail

backend_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_root="$(dirname "$backend_root")"
crawler_root="${CRAWLER_ROOT:-$workspace_root/crawler}"
data_root="$crawler_root/data"
if [[ ! -f "$data_root/musinsa/tops/products.csv" ]]; then
  # ponytail: fall back to the catalog snapshot committed under backend/data
  data_root="$backend_root/data"
fi

set -a
if [[ -f "$backend_root/.env" ]]; then
  # shellcheck disable=SC1091
  source "$backend_root/.env"
fi
if [[ -f "$crawler_root/.env" ]]; then
  # S3 credentials for local development only.
  # shellcheck disable=SC1091
  source "$crawler_root/.env"
fi
set +a

python_bin="${PYTHON:-$backend_root/work/.venv/bin/python}"
if [[ ! -x "$python_bin" && -x "$crawler_root/work/.venv/bin/python" ]]; then
  python_bin="$crawler_root/work/.venv/bin/python"
fi
if [[ ! -x "$python_bin" ]]; then
  echo "Python environment not found. Create work/.venv as described in README.md." >&2
  exit 1
fi

args=(
  --platform musinsa
  --products "$data_root/musinsa/tops/products.csv"
  --selections "$data_root/musinsa/tops/selected/selections.jsonl"
  --batch-size "${SEED_BATCH_SIZE:-16}"
  --skip-existing
)
if [[ -n "${SEED_LIMIT:-}" ]]; then
  args+=(--target-count "$SEED_LIMIT")
fi
if [[ "${SEED_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

cd "$backend_root"
exec "$python_bin" -m src.jobs.index_catalog "${args[@]}"
