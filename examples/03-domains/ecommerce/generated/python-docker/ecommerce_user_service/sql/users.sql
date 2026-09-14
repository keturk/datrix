CREATE TABLE "users" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "email" VARCHAR(320) NOT NULL,
    "password_hash" VARCHAR(255) NOT NULL,
    "first_name" VARCHAR(100) NOT NULL,
    "last_name" VARCHAR(100) NOT NULL,
    "phone_number" VARCHAR(20),
    "role" VARCHAR(50) NOT NULL DEFAULT 'Customer',
    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',
    "last_login_at" TIMESTAMPTZ,
    "email_verified_at" TIMESTAMPTZ,
    "email_verification_token" TEXT,
    "password_reset_token" TEXT,
    "password_reset_expiry" TIMESTAMPTZ,
    -- Embedded struct fields for complex nested data
    "shipping_address" JSONB,
    "billing_address" JSONB,
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT chk_users_role_enum CHECK (role IN ('Customer', 'Admin', 'Support')),
    CONSTRAINT chk_users_status_enum CHECK (status IN ('Active', 'Inactive', 'Suspended', 'Pending'))
);


CREATE INDEX "idx_users_status_role"
    ON "users"
    ("status", "role");

CREATE INDEX "idx_users_email"
    ON "users"
    ("email");