#!/usr/bin/env bash
set -euo pipefail

backend_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_root="$(dirname "$backend_root")"
crawler_root="${CRAWLER_ROOT:-}"

if [[ -z "$crawler_root" && -d "$workspace_root/SWE-crawl" ]]; then
  crawler_root="$workspace_root/SWE-crawl"
fi

if [[ -z "$crawler_root" ]]; then
  while IFS= read -r git_config; do
    if grep -Eq 'github\.com[:/]nsu102/SWE-crawl(\.git)?' "$git_config"; then
      crawler_root="$(dirname "$(dirname "$git_config")")"
      break
    fi
  done < <(find "$workspace_root" -mindepth 3 -maxdepth 3 -path '*/.git/config' -type f -print)
fi

if [[ -z "$crawler_root" || ! -f "$crawler_root/data/musinsa/tops/products.csv" ]]; then
  echo "SWE-crawl data not found. Set CRAWLER_ROOT=/absolute/path/to/SWE-crawl." >&2
  exit 1
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
  --products "$crawler_root/data/musinsa/tops/products.csv"
  --selections "$crawler_root/data/musinsa/tops/selected/selections.jsonl"
  --batch-size "${SEED_BATCH_SIZE:-16}"
  --target-count "${SEED_LIMIT:-900}"
  --skip-existing
)
if [[ "${SEED_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

cd "$backend_root"
exec "$python_bin" -m src.jobs.index_catalog "${args[@]}"
