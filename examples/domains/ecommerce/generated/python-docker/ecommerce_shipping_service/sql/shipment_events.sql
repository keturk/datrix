CREATE TABLE "shipment_events" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "timestamp" TIMESTAMP NOT NULL,    "status" VARCHAR(50) NOT NULL,    "location" VARCHAR(200) NOT NULL,    "description" TEXT,    "shipment_id" UUID,    CONSTRAINT pk_shipment_events PRIMARY KEY (id));


CREATE INDEX "idx_shipment_events_shipment_id_timestamp"
    ON "shipment_events"
    ("shipment_id", "timestamp");

ALTER TABLE "shipment_events"
    ADD CONSTRAINT "fk_shipment_events_shipment_id"
    FOREIGN KEY ("shipment_id")
    REFERENCES "shipments" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;