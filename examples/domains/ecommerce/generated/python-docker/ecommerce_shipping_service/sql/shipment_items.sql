CREATE TABLE "shipment_items" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "product_id" UUID NOT NULL,    "quantity" BIGINT NOT NULL,    "shipment_id" UUID,    CONSTRAINT pk_shipment_items PRIMARY KEY (id));


ALTER TABLE "shipment_items"
    ADD CONSTRAINT "fk_shipment_items_shipment_id"
    FOREIGN KEY ("shipment_id")
    REFERENCES "shipments" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;