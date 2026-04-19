CREATE TABLE "order_items" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "product_id" UUID NOT NULL,    "product_name" VARCHAR(200) NOT NULL,    "quantity" BIGINT NOT NULL,    "unit_price" DECIMAL(19,4) NOT NULL,    "order_id" UUID,    CONSTRAINT pk_order_items PRIMARY KEY (id));


ALTER TABLE "order_items"
    ADD CONSTRAINT "fk_order_items_order_id"
    FOREIGN KEY ("order_id")
    REFERENCES "orders" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;