CREATE TABLE "inventory_reservations" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "reservation_id" UUID NOT NULL,    "quantity" BIGINT NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Reserved',    "expires_at" TIMESTAMP NOT NULL,    "product_id" UUID,    CONSTRAINT pk_inventory_reservations PRIMARY KEY (id));


CREATE INDEX "idx_inventory_reservations_reservation_id_status"
    ON "inventory_reservations"
    ("reservation_id", "status");

ALTER TABLE "inventory_reservations"
    ADD CONSTRAINT "fk_inventory_reservations_product_id"
    FOREIGN KEY ("product_id")
    REFERENCES "products" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;