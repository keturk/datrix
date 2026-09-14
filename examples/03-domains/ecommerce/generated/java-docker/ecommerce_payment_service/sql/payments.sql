CREATE TABLE "payments" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "order_id" UUID NOT NULL,
    "customer_id" UUID NOT NULL,
    "amount" DECIMAL(19,4) NOT NULL,
    "method" VARCHAR(50) NOT NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',
    "transaction_id" VARCHAR(100) NOT NULL,
    "gateway_response" TEXT,
    "error_message" TEXT,
    "processed_at" TIMESTAMPTZ,
    CONSTRAINT pk_payments PRIMARY KEY (id),
    CONSTRAINT uq_payments_transaction_id UNIQUE (transaction_id),
    CONSTRAINT chk_payments_method_enum CHECK (method IN ('CreditCard', 'DebitCard', 'PayPal', 'BankTransfer')),
    CONSTRAINT chk_payments_status_enum CHECK (status IN ('Pending', 'Processing', 'Completed', 'Failed', 'Refunded'))
);


CREATE INDEX "idx_payments_customer_id_status"
    ON "payments"
    ("customer_id", "status");

CREATE INDEX "idx_payments_order_id"
    ON "payments"
    ("order_id");

CREATE INDEX "idx_payments_transaction_id"
    ON "payments"
    ("transaction_id");