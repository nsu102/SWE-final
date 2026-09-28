# Bundled catalog seed

`002-musinsa-900.sql.gz` contains 900 Musinsa product rows, S3 object references, and 768-dimensional Marqo/marqo-fashionSigLIP embeddings. It does not contain images, AWS credentials, local file paths, or search history.

The PostgreSQL Docker entrypoint imports it automatically after `src/backend/schema.sql` when a new database volume is created. Existing volumes are not modified automatically.
