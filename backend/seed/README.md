# Bundled catalog seed

`catalog-*.sql.gz` hold the whole catalog: 34,777 Musinsa tops whose selected photo shows the
garment without a person, with S3 object keys and 128-dimensional
`yainage90/fashion-image-feature-extractor` embeddings rounded to 4 decimals (top-24 results
match the full-precision DB 99.8%). They contain no images, AWS credentials, local paths or
search history.

- Local: the PostgreSQL Docker entrypoint loads them (`scripts/load_seed.sh`) after
  `src/backend/schema.sql` when a new volume is created. Existing volumes are not modified.
- Production (private RDS): they are baked into the Lambda image and loaded by
  `scripts/deploy.sh seed` (`src/jobs/load_seed.py`: upsert + remove products not in the seed).

Regenerate from the local DB with `make seed-dump` after re-selecting or re-embedding products.
