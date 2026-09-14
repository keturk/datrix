CREATE TABLE "user_sessions" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "token" VARCHAR(255) NOT NULL,
    "device_name" VARCHAR(500),
    "ip_address" INET,
    "user_agent" VARCHAR(255),
    "expires_at" TIMESTAMPTZ NOT NULL,
    "last_activity_at" TIMESTAMPTZ,
    "user_id" UUID NOT NULL,
    CONSTRAINT pk_user_sessions PRIMARY KEY (id),
    CONSTRAINT uq_user_sessions_token UNIQUE (token)
);


CREATE INDEX "idx_user_sessions_user_id_expires_at"
    ON "user_sessions"
    ("user_id", "expires_at");

CREATE INDEX "idx_user_sessions_token"
    ON "user_sessions"
    ("token");

ALTER TABLE "user_sessions"
    ADD CONSTRAINT "fk_user_sessions_user_id"
    FOREIGN KEY ("user_id")
    REFERENCES "users" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;