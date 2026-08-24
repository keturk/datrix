--liquibase formatted sql

--changeset datrix:0001_initial
--comment: initial
CREATE TABLE "categories" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "description" text,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "name" varchar(100) NOT NULL UNIQUE,
  "slug" varchar(255) NOT NULL UNIQUE,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE TABLE "inventory_reservations" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "expires_at" timestamptz NOT NULL,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "product_id" uuid NOT NULL,
  "quantity" integer NOT NULL,
  "reservation_id" uuid NOT NULL,
  "status" varchar(9) NOT NULL DEFAULT 'reserved' CHECK ("status" IN ('reserved', 'confirmed', 'released', 'expired')),
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE TABLE "products" (
  "category_id" uuid NOT NULL,
  "compare_at_price" numeric(19, 4),
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "description" text NOT NULL,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "images" jsonb NOT NULL,
  "inventory" integer NOT NULL DEFAULT 0,
  "name" varchar(200) NOT NULL,
  "price" numeric(19, 4) NOT NULL,
  "product_metadata" jsonb,
  "slug" varchar(200) UNIQUE,
  "status" varchar(12) NOT NULL DEFAULT 'draft' CHECK ("status" IN ('draft', 'active', 'discontinued')),
  "tags" jsonb NOT NULL,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_inventory_reservations_reservation_id_status" ON "inventory_reservations" ("reservation_id", "status");
CREATE INDEX "ix_inventory_reservations_reservation_id" ON "inventory_reservations" ("reservation_id");
CREATE INDEX "ix_inventory_reservations_expires_at" ON "inventory_reservations" ("expires_at");
CREATE INDEX "ix_inventory_reservations_product_id" ON "inventory_reservations" ("product_id");
CREATE INDEX "ix_products_category_id_status" ON "products" ("category_id", "status");
CREATE INDEX "ix_products_status_inventory" ON "products" ("status", "inventory");
CREATE INDEX "ix_products_fulltext" ON "products" USING gin (to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '')));
CREATE INDEX "ix_products_category_id" ON "products" ("category_id");
ALTER TABLE "inventory_reservations" ADD CONSTRAINT "fk_inventory_reservations_product_id_products" FOREIGN KEY ("product_id") REFERENCES "products" ("id") ON DELETE restrict ON UPDATE restrict;
ALTER TABLE "products" ADD CONSTRAINT "fk_products_category_id_categories" FOREIGN KEY ("category_id") REFERENCES "categories" ("id") ON DELETE restrict ON UPDATE restrict;
--rollback: initial (reverse)
--rollback ALTER TABLE "products" DROP CONSTRAINT "fk_products_category_id_categories";
--rollback ALTER TABLE "inventory_reservations" DROP CONSTRAINT "fk_inventory_reservations_product_id_products";
--rollback DROP TABLE "products";
--rollback DROP TABLE "inventory_reservations";
--rollback DROP TABLE "categories";
