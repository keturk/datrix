-- 'with' mixes in multiple traits, adding their fields and methods
CREATE TABLE "products" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "slug" VARCHAR(200),
    -- Money is a semantic amount type; currency is modeled explicitly where needed
    "price" DECIMAL(19,4) NOT NULL,
    "compare_at_price" DECIMAL(19,4),
    -- 'min(0)' sets a minimum value constraint
    "inventory" BIGINT NOT NULL DEFAULT 0,
    "name" VARCHAR(200) NOT NULL,
    "description" TEXT NOT NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Draft',
    "product_metadata" JSONB,
    "images" JSONB NOT NULL,
    "tags" JSONB NOT NULL,
    "category_id" UUID NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (id),
    CONSTRAINT uq_products_slug UNIQUE (slug),
    CONSTRAINT chk_products_status_enum CHECK (status IN ('Draft', 'Active', 'Discontinued'))
);


CREATE INDEX "idx_products_category_id_status"
    ON "products"
    ("category_id", "status");

CREATE INDEX "idx_products_status_inventory"
    ON "products"
    ("status", "inventory");

CREATE INDEX "ft_products_name_description" ON "products" USING GIN (to_tsvector('english', "name" || ' ' || "description"));

ALTER TABLE "products"
    ADD CONSTRAINT "fk_products_category_id"
    FOREIGN KEY ("category_id")
    REFERENCES "categories" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;