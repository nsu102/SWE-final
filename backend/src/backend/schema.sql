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
    embedding vector(128) NOT NULL,
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

-- Migrate embedding dimension when switching model (now 128-dim
-- yainage90/fashion-image-feature-extractor). Old vectors are incompatible with the new model,
-- so clear them; index_catalog rebuilds. Guarded on dim so it runs once.
DO $$
DECLARE dims int;
BEGIN
    SELECT atttypmod INTO dims FROM pg_attribute
    WHERE attrelid = 'products'::regclass AND attname = 'embedding';
    IF dims IS NOT NULL AND dims <> 128 THEN
        DROP INDEX IF EXISTS products_embedding_hnsw_idx;
        DELETE FROM products;
        ALTER TABLE products ALTER COLUMN embedding TYPE vector(128);
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

-- Accounts. Passwords are scrypt hashes.
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- JWT auth: access tokens are stateless; each refresh token's jti is recorded so a login can be
-- revoked (logout, password reset) and a replayed, already-rotated token revokes its whole family.
CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS refresh_tokens_family_idx ON refresh_tokens (family);
CREATE INDEX IF NOT EXISTS refresh_tokens_user_idx ON refresh_tokens (user_id);
-- Replaced by refresh_tokens (opaque cookie sessions -> JWT).
DROP TABLE IF EXISTS sessions;

-- A logged-in search is a search_events row with user_id set (ARCHIVE).
-- hidden_at marks "CLEAR ALL" so the latest batch can be restored (RETURN).
ALTER TABLE search_events ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE search_events ADD COLUMN IF NOT EXISTS label TEXT;
ALTER TABLE search_events ADD COLUMN IF NOT EXISTS thumb TEXT;
ALTER TABLE search_events ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS search_events_user_idx
ON search_events (user_id, created_at DESC) WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS search_results (
    event_id BIGINT NOT NULL REFERENCES search_events(id) ON DELETE CASCADE,
    rank SMALLINT NOT NULL,
    platform TEXT NOT NULL,
    goods_no TEXT NOT NULL,
    similarity REAL NOT NULL,
    PRIMARY KEY (event_id, rank),
    FOREIGN KEY (platform, goods_no) REFERENCES products (platform, goods_no) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    goods_no TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, platform, goods_no),
    FOREIGN KEY (platform, goods_no) REFERENCES products (platform, goods_no) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ
);

-- Garment colour (median CIE Lab of the parsed top) for colour-aware reranking, and the
-- garment box (fractions of width/height) used to crop product photos for display.
ALTER TABLE products ADD COLUMN IF NOT EXISTS color_lab REAL[];
ALTER TABLE products ADD COLUMN IF NOT EXISTS crop_box REAL[];

-- Kakao login: a Kakao-only account has no password and may have no email (not shared or unverified).
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_id TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
