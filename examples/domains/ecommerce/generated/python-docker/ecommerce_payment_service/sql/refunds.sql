CREATE TABLE "refunds" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "amount" DECIMAL(19,4) NOT NULL,    "reason" VARCHAR(500) NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',    "refund_transaction_id" TEXT,    "error_message" TEXT,    "processed_at" TIMESTAMP,    "payment_id" UUID,    CONSTRAINT pk_refunds PRIMARY KEY (id));


ALTER TABLE "refunds"
    ADD CONSTRAINT "fk_refunds_payment_id"
    FOREIGN KEY ("payment_id")
    REFERENCES "payments" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;