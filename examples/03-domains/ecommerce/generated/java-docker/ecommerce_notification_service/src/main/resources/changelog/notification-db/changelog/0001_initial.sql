--liquibase formatted sql

--changeset datrix:0001_initial
--comment: initial
CREATE TABLE "notification_audits" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "order_id" uuid NOT NULL,
  "order_number" varchar(64) NOT NULL,
  "recipient_email" varchar(320) NOT NULL,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_notification_audits_order_id" ON "notification_audits" ("order_id");
--rollback: initial (reverse)
--rollback DROP TABLE "notification_audits";
