CREATE TABLE "products" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "slug" VARCHAR(200) NOT NULL,    "price" DECIMAL(19,4) NOT NULL,    "compare_at_price" DECIMAL(19,4),    "inventory" BIGINT NOT NULL DEFAULT 0,    "name" VARCHAR(200) NOT NULL,    "description" TEXT NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Draft',    "product_metadata" JSONB,    "images" JSONB NOT NULL,    "tags" JSONB NOT NULL,    "category_id" UUID,    CONSTRAINT pk_products PRIMARY KEY (id),    CONSTRAINT uq_products_slug UNIQUE (slug));


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