--liquibase formatted sql

--changeset datrix:0001_initial
--comment: initial
CREATE TABLE "payments" (
  "amount" numeric(19, 4) NOT NULL,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "customer_id" uuid NOT NULL,
  "error_message" text,
  "gateway_response" text,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "method" varchar(13) NOT NULL CHECK ("method" IN ('credit_card', 'debit_card', 'pay_pal', 'bank_transfer')),
  "order_id" uuid NOT NULL,
  "processed_at" timestamptz,
  "status" varchar(10) NOT NULL DEFAULT 'pending' CHECK ("status" IN ('pending', 'processing', 'completed', 'failed', 'refunded')),
  "transaction_id" varchar(100) NOT NULL UNIQUE,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE TABLE "refunds" (
  "amount" numeric(19, 4) NOT NULL,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "error_message" text,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "payment_id" uuid NOT NULL,
  "processed_at" timestamptz,
  "reason" varchar(500) NOT NULL,
  "refund_transaction_id" text,
  "status" varchar(10) NOT NULL DEFAULT 'pending' CHECK ("status" IN ('pending', 'processing', 'completed', 'failed', 'refunded')),
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_payments_customer_id_status" ON "payments" ("customer_id", "status");
CREATE INDEX "ix_payments_order_id" ON "payments" ("order_id");
CREATE INDEX "ix_payments_transaction_id" ON "payments" ("transaction_id");
CREATE INDEX "ix_payments_customer_id" ON "payments" ("customer_id");
CREATE INDEX "ix_refunds_payment_id" ON "refunds" ("payment_id");
ALTER TABLE "refunds" ADD CONSTRAINT "fk_refunds_payment_id_payments" FOREIGN KEY ("payment_id") REFERENCES "payments" ("id") ON DELETE restrict ON UPDATE restrict;
--rollback: initial (reverse)
--rollback ALTER TABLE "refunds" DROP CONSTRAINT "fk_refunds_payment_id_payments";
--rollback DROP TABLE "refunds";
--rollback DROP TABLE "payments";
