CREATE TABLE "tags" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "name" VARCHAR(50) NOT NULL,    "description" VARCHAR(200),    CONSTRAINT pk_tags PRIMARY KEY (id),    CONSTRAINT uq_tags_name UNIQUE (name));
