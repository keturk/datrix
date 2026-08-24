--liquibase formatted sql

--changeset datrix:0001_initial
--comment: initial
CREATE TABLE "users" (
  "billing_address" jsonb,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "email" varchar(320) NOT NULL UNIQUE,
  "email_verification_token" text,
  "email_verified_at" timestamptz,
  "first_name" varchar(100) NOT NULL,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "last_login_at" timestamptz,
  "last_name" varchar(100) NOT NULL,
  "password_hash" varchar(255) NOT NULL,
  "password_reset_expiry" timestamptz,
  "password_reset_token" text,
  "phone_number" varchar(20),
  "role" varchar(8) NOT NULL DEFAULT 'customer' CHECK ("role" IN ('customer', 'admin', 'support')),
  "shipping_address" jsonb,
  "status" varchar(9) NOT NULL DEFAULT 'pending' CHECK ("status" IN ('active', 'inactive', 'suspended', 'pending')),
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY ("id")
);
CREATE TABLE "user_preferences" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "email_notifications" boolean NOT NULL DEFAULT true,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "language" varchar(10) NOT NULL DEFAULT 'en',
  "preferences" jsonb NOT NULL,
  "sms_notifications" boolean NOT NULL DEFAULT false,
  "timezone" varchar(50) NOT NULL DEFAULT 'UTC',
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  "user_id" uuid NOT NULL,
  PRIMARY KEY ("id")
);
CREATE TABLE "user_sessions" (
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "device_name" varchar(500),
  "expires_at" timestamptz NOT NULL,
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "ip_address" varchar(45),
  "last_activity_at" timestamptz,
  "token" varchar(255) NOT NULL UNIQUE,
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  "user_agent" varchar(255),
  "user_id" uuid NOT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_users_status_role" ON "users" ("status", "role");
CREATE INDEX "ix_users_email" ON "users" ("email");
CREATE INDEX "ix_user_sessions_user_id_expires_at" ON "user_sessions" ("user_id", "expires_at");
CREATE INDEX "ix_user_sessions_token" ON "user_sessions" ("token");
CREATE INDEX "ix_user_sessions_user_id" ON "user_sessions" ("user_id");
ALTER TABLE "user_preferences" ADD CONSTRAINT "fk_user_preferences_user_id_users" FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE restrict ON UPDATE restrict;
ALTER TABLE "user_sessions" ADD CONSTRAINT "fk_user_sessions_user_id_users" FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE restrict ON UPDATE restrict;
--rollback: initial (reverse)
--rollback ALTER TABLE "user_sessions" DROP CONSTRAINT "fk_user_sessions_user_id_users";
--rollback ALTER TABLE "user_preferences" DROP CONSTRAINT "fk_user_preferences_user_id_users";
--rollback DROP TABLE "user_sessions";
--rollback DROP TABLE "user_preferences";
--rollback DROP TABLE "users";
