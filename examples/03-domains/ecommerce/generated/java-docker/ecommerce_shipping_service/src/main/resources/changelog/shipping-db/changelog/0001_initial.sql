--liquibase formatted sql

--changeset datrix:0001_initial
--comment: initial
CREATE TABLE "shipments" (
  "actual_delivery" timestamptz,
  "carrier" varchar(6) NOT NULL CHECK ("carrier" IN ('fed_ex', 'ups', 'usps', 'dhl')),
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "destination" jsonb NOT NULL,
  "estimated_delivery" timestamptz,
  "failure_reason" text,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "order_id" uuid NOT NULL,
  "status" varchar(16) NOT NULL DEFAULT 'pending' CHECK ("status" IN ('pending', 'picked_up', 'in_transit', 'out_for_delivery', 'delivered', 'failed', 'returned')),
  "tracking_number" varchar(50) NOT NULL UNIQUE,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  "weight" numeric(10, 2) NOT NULL,
  PRIMARY KEY ("id")
);
CREATE TABLE "shipment_events" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "description" text,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "location" varchar(200) NOT NULL,
  "shipment_id" uuid NOT NULL,
  "status" varchar(16) NOT NULL CHECK ("status" IN ('pending', 'picked_up', 'in_transit', 'out_for_delivery', 'delivered', 'failed', 'returned')),
  "timestamp" timestamptz NOT NULL,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE TABLE "shipment_items" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "product_id" uuid NOT NULL,
  "quantity" integer NOT NULL,
  "shipment_id" uuid NOT NULL,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_shipments_order_id" ON "shipments" ("order_id");
CREATE INDEX "ix_shipments_tracking_number" ON "shipments" ("tracking_number");
CREATE INDEX "ix_shipments_status" ON "shipments" ("status");
CREATE INDEX "ix_shipments_carrier_status" ON "shipments" ("carrier", "status");
CREATE INDEX "ix_shipment_events_shipment_id_timestamp" ON "shipment_events" ("shipment_id", "timestamp");
CREATE INDEX "ix_shipment_events_shipment_id" ON "shipment_events" ("shipment_id");
CREATE INDEX "ix_shipment_items_shipment_id" ON "shipment_items" ("shipment_id");
ALTER TABLE "shipment_events" ADD CONSTRAINT "fk_shipment_events_shipment_id_shipments" FOREIGN KEY ("shipment_id") REFERENCES "shipments" ("id") ON DELETE restrict ON UPDATE restrict;
ALTER TABLE "shipment_items" ADD CONSTRAINT "fk_shipment_items_shipment_id_shipments" FOREIGN KEY ("shipment_id") REFERENCES "shipments" ("id") ON DELETE restrict ON UPDATE restrict;
--rollback: initial (reverse)
--rollback ALTER TABLE "shipment_items" DROP CONSTRAINT "fk_shipment_items_shipment_id_shipments";
--rollback ALTER TABLE "shipment_events" DROP CONSTRAINT "fk_shipment_events_shipment_id_shipments";
--rollback DROP TABLE "shipment_items";
--rollback DROP TABLE "shipment_events";
--rollback DROP TABLE "shipments";
