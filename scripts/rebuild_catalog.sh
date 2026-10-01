#!/usr/bin/env bash
# 사람 없는 상품 사진으로 카탈로그를 다시 만듭니다.
# 무신사 이미지 재선별(병렬) → 결과 병합 → 백엔드 재임베딩(옷 영역·색·크롭) + 제외 상품 삭제.
# 중간에 멈춰도 다시 실행하면 끝난 상품은 건너뜁니다.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
py="$root/backend/work/.venv/bin/python"
workers="${WORKERS:-10}"  # threads in one process: network overlaps, the GPU parses one image at a time
data="$root/crawler/data/musinsa/tops"
mkdir -p "$root/crawler/logs" "$data/selected"
[[ -f "$data/products.csv" ]] || cp "$root/backend/data/musinsa/tops/products.csv" "$data/products.csv"

cd "$root/crawler"
# Results from earlier sharded runs count as done: fold them into the main file first.
if compgen -G "$data/selected/shard-*/selections.jsonl" > /dev/null; then
  cat "$data"/selected/shard-*/selections.jsonl >> "$data/selected/selections.jsonl"
  rm -r "$data"/selected/shard-*
fi
total=$(( $(wc -l < "$data/products.csv") - 1 ))
processed_count() {  # unique goods with a valid result line (tolerates a half-written last line)
  "$py" -c 'import json, sys
done = set()
for line in open(sys.argv[1], encoding="utf-8"):
    try: done.add(json.loads(line)["goods_no"])
    except (ValueError, KeyError): pass
print(len(done))' "$data/selected/selections.jsonl" 2>/dev/null || echo 0
}
# Each pass skips finished products; failed ones (network errors) get retried by the next pass.
for pass in 1 2 3; do
  echo "pass $pass: selecting person-free images with $workers workers (log: crawler/logs/select.log)"
  "$py" -m src.musinsa.select_images --workers "$workers" --output "$data/selected" \
    --delay 0.3 --delete-local-after-upload 2>&1 | tee -a logs/select.log || true
  processed=$(processed_count)
  echo "processed $processed/$total products"
  (( processed * 1000 >= total * 995 )) && break
done
if (( processed * 1000 < total * 995 )); then
  # --prune deletes products missing from the selections, so never index a partial run.
  echo "not indexing a partial run; rerun this script to retry the remaining products" >&2
  exit 1
fi

cd "$root/backend"
set -a; source .env; set +a
"$py" -m src.jobs.index_catalog --platform musinsa \
  --products "$data/products.csv" --selections "$data/selected/selections.jsonl" --refresh --prune
echo "done. share with the team: (cd backend && make seed-dump) && commit backend/seed"
