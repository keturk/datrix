CREATE TABLE "members" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "name" VARCHAR(100) NOT NULL,    "email" VARCHAR(320) NOT NULL,    "email_verification_token" TEXT,    CONSTRAINT pk_members PRIMARY KEY (id),    CONSTRAINT uq_members_email UNIQUE (email));
