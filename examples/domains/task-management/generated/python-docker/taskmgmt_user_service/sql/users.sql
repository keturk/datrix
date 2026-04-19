CREATE TABLE "users" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "name" VARCHAR(100) NOT NULL,    "email" VARCHAR(320) NOT NULL,    CONSTRAINT pk_users PRIMARY KEY (id),    CONSTRAINT uq_users_email UNIQUE (email));


CREATE INDEX "idx_users_email"
    ON "users"
    ("email");