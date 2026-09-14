CREATE TABLE "refunds" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "amount" DECIMAL(19,4) NOT NULL,
    "reason" VARCHAR(500) NOT NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',
    "refund_transaction_id" TEXT,
    "error_message" TEXT,
    "processed_at" TIMESTAMPTZ,
    "payment_id" UUID NOT NULL,
    CONSTRAINT pk_refunds PRIMARY KEY (id),
    CONSTRAINT chk_refunds_status_enum CHECK (status IN ('Pending', 'Processing', 'Completed', 'Failed', 'Refunded'))
);


ALTER TABLE "refunds"
    ADD CONSTRAINT "fk_refunds_payment_id"
    FOREIGN KEY ("payment_id")
    REFERENCES "payments" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;