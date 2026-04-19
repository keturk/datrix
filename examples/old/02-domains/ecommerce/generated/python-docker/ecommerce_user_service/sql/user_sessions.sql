CREATE TABLE "user_sessions" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "token" VARCHAR(255) NOT NULL,    "device_name" VARCHAR(500),    "ip_address" INET,    "user_agent" VARCHAR(255),    "expires_at" TIMESTAMP NOT NULL,    "last_activity_at" TIMESTAMP,    "user_id" UUID,    CONSTRAINT pk_user_sessions PRIMARY KEY (id),    CONSTRAINT uq_user_sessions_token UNIQUE (token));


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