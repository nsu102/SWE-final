#!/usr/bin/env bash
set -euo pipefail
api_url="${1:-http://127.0.0.1:8000}"
curl --fail --silent --show-error --retry 12 --retry-connrefused --retry-delay 5 --max-time 15 "$api_url/health"
echo
