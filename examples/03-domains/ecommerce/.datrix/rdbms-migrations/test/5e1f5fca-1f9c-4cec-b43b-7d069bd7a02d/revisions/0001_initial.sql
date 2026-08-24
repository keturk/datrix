--liquibase formatted sql

--changeset datrix:0001_initial
--comment: initial
CREATE TABLE "idempotency_keys" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "expires_at" timestamptz NOT NULL,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "key" varchar(100) NOT NULL UNIQUE,
  "operation" varchar(50) NOT NULL,
  "resource_id" uuid,
  "response" jsonb,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE TABLE "orders" (
  "billing_address" jsonb NOT NULL,
  "cancellation_reason" text,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "customer_id" uuid NOT NULL,
  "discount" numeric(19, 4) NOT NULL,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "inventory_reservation_id" uuid NOT NULL,
  "order_number" varchar(20) NOT NULL UNIQUE,
  "payment_id" uuid,
  "shipment_id" uuid,
  "shipping_address" jsonb NOT NULL,
  "shipping_cost" numeric(19, 4) NOT NULL,
  "status" varchar(15) NOT NULL DEFAULT 'pending' CHECK ("status" IN ('pending', 'payment_pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded')),
  "subtotal" numeric(19, 4) NOT NULL,
  "tax" numeric(19, 4) NOT NULL,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE TABLE "order_items" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "order_id" uuid NOT NULL,
  "product_id" uuid NOT NULL,
  "product_name" varchar(200) NOT NULL,
  "quantity" integer NOT NULL,
  "unit_price" numeric(19, 4) NOT NULL,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_idempotency_keys_operation" ON "idempotency_keys" ("operation");
CREATE INDEX "ix_idempotency_keys_expires_at" ON "idempotency_keys" ("expires_at");
CREATE INDEX "ix_orders_customer_id_status" ON "orders" ("customer_id", "status");
CREATE INDEX "ix_orders_status_created_at" ON "orders" ("status", "created_at");
CREATE INDEX "ix_orders_order_number" ON "orders" ("order_number");
CREATE INDEX "ix_orders_customer_id" ON "orders" ("customer_id");
CREATE INDEX "ix_order_items_product_id" ON "order_items" ("product_id");
CREATE INDEX "ix_order_items_order_id" ON "order_items" ("order_id");
ALTER TABLE "order_items" ADD CONSTRAINT "fk_order_items_order_id_orders" FOREIGN KEY ("order_id") REFERENCES "orders" ("id") ON DELETE restrict ON UPDATE restrict;
--rollback: initial (reverse)
--rollback ALTER TABLE "order_items" DROP CONSTRAINT "fk_order_items_order_id_orders";
--rollback DROP TABLE "order_items";
--rollback DROP TABLE "orders";
--rollback DROP TABLE "idempotency_keys";
