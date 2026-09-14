CREATE TABLE "shipments" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "order_id" UUID NOT NULL,
    "tracking_number" VARCHAR(50) NOT NULL,
    "carrier" VARCHAR(50) NOT NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',
    "destination" JSONB NOT NULL,
    -- Decimal(precision, scale) for fixed-point numbers
    "weight" NUMERIC(10,2) NOT NULL,
    "estimated_delivery" TIMESTAMPTZ,
    "actual_delivery" TIMESTAMPTZ,
    "failure_reason" TEXT,
    CONSTRAINT pk_shipments PRIMARY KEY (id),
    CONSTRAINT uq_shipments_tracking_number UNIQUE (tracking_number),
    CONSTRAINT chk_shipments_carrier_enum CHECK (carrier IN ('FedEx', 'UPS', 'USPS', 'DHL')),
    CONSTRAINT chk_shipments_status_enum CHECK (status IN ('Pending', 'PickedUp', 'InTransit', 'OutForDelivery', 'Delivered', 'Failed', 'Returned'))
);


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