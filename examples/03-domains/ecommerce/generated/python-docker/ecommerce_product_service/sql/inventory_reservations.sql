CREATE TABLE "inventory_reservations" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "reservation_id" UUID NOT NULL,
    "quantity" BIGINT NOT NULL,
    "status" VARCHAR(63) NOT NULL DEFAULT 'reserved',
    "expires_at" TIMESTAMPTZ NOT NULL,
    "product_id" UUID NOT NULL,
    CONSTRAINT pk_inventory_reservations PRIMARY KEY (id),
    CONSTRAINT chk_inventory_reservations_status_enum CHECK (status IN ('reserved', 'confirmed', 'released', 'expired'))
);


CREATE INDEX "idx_inventory_reservations_reservation_id_status"
    ON "inventory_reservations"
    ("reservation_id", "status");

ALTER TABLE "inventory_reservations"
    ADD CONSTRAINT "fk_inventory_reservations_product_id"
    FOREIGN KEY ("product_id")
    REFERENCES "products" ("id")
    ON DELETE RESTRICT
    ON UPDATE RESTRICT;