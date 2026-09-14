CREATE TABLE "order_items" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "product_id" UUID NOT NULL,
    "product_name" VARCHAR(200) NOT NULL,
    -- 'min(1)' sets a minimum value constraint
    "quantity" BIGINT NOT NULL,
    -- 'positive' ensures the value is greater than zero
    "unit_price" DECIMAL(19,4) NOT NULL,
    "order_id" UUID NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (id)
);


ALTER TABLE "order_items"
    ADD CONSTRAINT "fk_order_items_order_id"
    FOREIGN KEY ("order_id")
    REFERENCES "orders" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;