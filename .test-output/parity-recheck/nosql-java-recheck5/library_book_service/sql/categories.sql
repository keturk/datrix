CREATE TABLE "categories" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "name" VARCHAR(100) NOT NULL,    "description" VARCHAR(500),    CONSTRAINT pk_categories PRIMARY KEY (id),    CONSTRAINT uq_categories_name UNIQUE (name));
