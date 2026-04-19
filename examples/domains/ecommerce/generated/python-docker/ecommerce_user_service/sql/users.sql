CREATE TABLE "users" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "email" VARCHAR(320) NOT NULL,    "password_hash" VARCHAR(255) NOT NULL,    "first_name" VARCHAR(100) NOT NULL,    "last_name" VARCHAR(100) NOT NULL,    "phone_number" VARCHAR(20),    "role" VARCHAR(50) NOT NULL DEFAULT 'Customer',    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',    "last_login_at" TIMESTAMP,    "email_verified_at" TIMESTAMP,    "email_verification_token" TEXT,    "password_reset_token" TEXT,    "password_reset_expiry" TIMESTAMP,    "shipping_address" JSONB,    "billing_address" JSONB,    CONSTRAINT pk_users PRIMARY KEY (id),    CONSTRAINT uq_users_email UNIQUE (email));


CREATE INDEX "idx_users_status_role"
    ON "users"
    ("status", "role");

CREATE INDEX "idx_users_email"
    ON "users"
    ("email");