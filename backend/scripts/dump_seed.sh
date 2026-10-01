#!/usr/bin/env bash
# 로컬 DB(make db-up)의 전체 카탈로그를 seed/catalog-*.sql.gz로 다시 만듭니다.
# ponytail: 임베딩은 소수 4자리로 반올림(halfvec 수준, top-20 일치율 99.9%)해 파일당 GitHub 50MB 경고선 아래로 유지.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

rows_per_part="${SEED_ROWS_PER_PART:-25000}"
psql_() { docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tA'; }
cols="platform, goods_no, goods_name, brand_name, price, product_url, embedding, embedding_model, s3_bucket, s3_key, color_lab, crop_box"
total=$(echo "SELECT count(*) FROM products" | psql_)
parts=$(( (total + rows_per_part - 1) / rows_per_part ))

rm -f seed/*.sql.gz
for (( i = 0; i < parts; i++ )); do
  file="seed/catalog-$(printf '%02d' $((i + 1))).sql.gz"
  {
    echo "COPY public.products ($cols) FROM stdin;"
    echo "COPY (
      SELECT platform, goods_no, goods_name, brand_name, price, product_url,
             '[' || array_to_string(ARRAY(
               SELECT round(x::numeric, 4)::real FROM unnest(embedding::real[]) x
             ), ',') || ']',
             embedding_model, s3_bucket, s3_key, color_lab, crop_box
      FROM products ORDER BY platform, goods_no
      LIMIT $rows_per_part OFFSET $((i * rows_per_part))
    ) TO STDOUT" | psql_
    echo '\.'
  } | gzip -9 > "$file"
  echo "$file $(du -h "$file" | cut -f1)"
done
echo "total=$total parts=$parts"
