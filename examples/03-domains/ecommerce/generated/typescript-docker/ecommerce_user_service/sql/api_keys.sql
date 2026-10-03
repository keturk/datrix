-- Issued API keys. Only the SHA-256 hash of a key is stored;
-- keyPrefix is display-only and never used to verify a key.
CREATE TABLE "api_keys" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "key_hash" VARCHAR(64) NOT NULL,
    "owner_id" UUID NOT NULL,
    "key_prefix" VARCHAR(12) NOT NULL,
    "scopes" JSONB NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT TRUE,
    "expires_at" TIMESTAMPTZ,
    "last_used_at" TIMESTAMPTZ,
    "rate_limit" BIGINT NOT NULL DEFAULT 100,
    CONSTRAINT pk_api_keys PRIMARY KEY (id),
    CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash)
);
