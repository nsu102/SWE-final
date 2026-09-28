# Bundled catalog seed

`catalog-*.sql.gz` contain every product in the catalog (49,705 Musinsa tops, one per image in S3) with S3 object keys and 768-dimensional Marqo/marqo-fashionSigLIP embeddings rounded to 4 decimals. They do not contain images, AWS credentials, local file paths, or search history.

Regenerate them from the local DB with `make seed-dump` after indexing new products.

The PostgreSQL Docker entrypoint loads them (`scripts/load_seed.sh`) after `src/backend/schema.sql` when a new database volume is created. Existing volumes are not modified automatically.
