-- Event log entity for shipment tracking history
CREATE TABLE "shipment_events" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "timestamp" TIMESTAMPTZ NOT NULL,
    "status" VARCHAR(50) NOT NULL,
    "location" VARCHAR(200) NOT NULL,
    "description" TEXT,
    "shipment_id" UUID NOT NULL,
    CONSTRAINT pk_shipment_events PRIMARY KEY (id),
    CONSTRAINT chk_shipment_events_status_enum CHECK (status IN ('Pending', 'PickedUp', 'InTransit', 'OutForDelivery', 'Delivered', 'Failed', 'Returned'))
);


CREATE INDEX "idx_shipment_events_shipment_id_timestamp"
    ON "shipment_events"
    ("shipment_id", "timestamp");

ALTER TABLE "shipment_events"
    ADD CONSTRAINT "fk_shipment_events_shipment_id"
    FOREIGN KEY ("shipment_id")
    REFERENCES "shipments" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;