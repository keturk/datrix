CREATE TABLE "shipments" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "order_id" UUID NOT NULL,    "tracking_number" VARCHAR(50) NOT NULL,    "carrier" VARCHAR(50) NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',    "destination" JSONB NOT NULL,    "weight" NUMERIC(10,2) NOT NULL,    "estimated_delivery" TIMESTAMP,    "actual_delivery" TIMESTAMP,    "failure_reason" TEXT,    CONSTRAINT pk_shipments PRIMARY KEY (id),    CONSTRAINT uq_shipments_tracking_number UNIQUE (tracking_number));


CREATE INDEX "idx_shipments_order_id"
    ON "shipments"
    ("order_id");

CREATE INDEX "idx_shipments_tracking_number"
    ON "shipments"
    ("tracking_number");

CREATE INDEX "idx_shipments_status"
    ON "shipments"
    ("status");

CREATE INDEX "idx_shipments_carrier_status"
    ON "shipments"
    ("carrier", "status");