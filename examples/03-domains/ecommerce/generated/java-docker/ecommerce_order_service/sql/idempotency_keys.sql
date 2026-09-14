-- Entity for idempotency key deduplication
CREATE TABLE "idempotency_keys" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "key" VARCHAR(100) NOT NULL,
    "operation" VARCHAR(50) NOT NULL,
    "resource_id" UUID,
    "response" JSONB,
    "expires_at" TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_idempotency_keys PRIMARY KEY (id),
    CONSTRAINT uq_idempotency_keys_key UNIQUE (key)
);
