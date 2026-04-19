CREATE TABLE "payments" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "order_id" UUID NOT NULL,    "customer_id" UUID NOT NULL,    "amount" DECIMAL(19,4) NOT NULL,    "method" VARCHAR(50) NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',    "transaction_id" VARCHAR(100) NOT NULL,    "gateway_response" TEXT,    "error_message" TEXT,    "processed_at" TIMESTAMP,    CONSTRAINT pk_payments PRIMARY KEY (id),    CONSTRAINT uq_payments_transaction_id UNIQUE (transaction_id));


CREATE INDEX "idx_payments_customer_id_status"
    ON "payments"
    ("customer_id", "status");

CREATE INDEX "idx_payments_order_id"
    ON "payments"
    ("order_id");

CREATE INDEX "idx_payments_transaction_id"
    ON "payments"
    ("transaction_id");