CREATE TABLE "orders" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "customer_id" UUID NOT NULL,    "order_number" VARCHAR(20) NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',    "subtotal" DECIMAL(19,4) NOT NULL,    "tax" DECIMAL(19,4) NOT NULL,    "shipping_cost" DECIMAL(19,4) NOT NULL,    "discount" DECIMAL(19,4) NOT NULL,    "shipping_address" JSONB NOT NULL,    "billing_address" JSONB NOT NULL,    "inventory_reservation_id" UUID NOT NULL,    "payment_id" UUID,    "shipment_id" UUID,    "cancellation_reason" TEXT,    CONSTRAINT pk_orders PRIMARY KEY (id),    CONSTRAINT uq_orders_order_number UNIQUE (order_number));


CREATE INDEX "idx_orders_customer_id_status"
    ON "orders"
    ("customer_id", "status");

CREATE INDEX "idx_orders_status_created_at"
    ON "orders"
    ("status", "created_at");

CREATE INDEX "idx_orders_order_number"
    ON "orders"
    ("order_number");