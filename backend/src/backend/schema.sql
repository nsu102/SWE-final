CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS products (
    platform TEXT NOT NULL,
    goods_no TEXT NOT NULL,
    goods_name TEXT NOT NULL,
    brand_name TEXT NOT NULL DEFAULT '',
    price INTEGER,
    product_url TEXT NOT NULL,
    image_path TEXT,
    s3_bucket TEXT,
    s3_key TEXT,
    embedding vector(768) NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (platform, goods_no)
);

CREATE INDEX IF NOT EXISTS products_embedding_hnsw_idx
ON products USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS products_platform_idx ON products (platform);

ALTER TABLE products ALTER COLUMN image_path DROP NOT NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS s3_bucket TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS s3_key TEXT;

-- Migrate embedding dimension when switching model (e.g. 512 fashion-clip ->
-- 768 marqo-fashionSigLIP). Old vectors are incompatible with the new model,
-- so clear them; index_catalog rebuilds. Guarded on dim so it runs once.
DO $$
DECLARE dims int;
BEGIN
    SELECT atttypmod INTO dims FROM pg_attribute
    WHERE attrelid = 'products'::regclass AND attname = 'embedding';
    IF dims IS NOT NULL AND dims <> 768 THEN
        DROP INDEX IF EXISTS products_embedding_hnsw_idx;
        DELETE FROM products;
        ALTER TABLE products ALTER COLUMN embedding TYPE vector(768);
        CREATE INDEX products_embedding_hnsw_idx
            ON products USING hnsw (embedding vector_cosine_ops);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS search_events (
    id BIGSERIAL PRIMARY KEY,
    query_id UUID NOT NULL,
    platform_filter TEXT,
    result_count INTEGER NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
