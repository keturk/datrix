CREATE TABLE "user_preferences" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "language" VARCHAR(10) NOT NULL DEFAULT 'en',
    "timezone" VARCHAR(50) NOT NULL DEFAULT 'UTC',
    "email_notifications" BOOLEAN NOT NULL DEFAULT TRUE,
    "sms_notifications" BOOLEAN NOT NULL DEFAULT FALSE,
    -- JSON type for schemaless data
    "preferences" JSONB NOT NULL,
    "user_id" UUID NOT NULL,
    CONSTRAINT pk_user_preferences PRIMARY KEY (id)
);


ALTER TABLE "user_preferences"
    ADD CONSTRAINT "fk_user_preferences_user_id"
    FOREIGN KEY ("user_id")
    REFERENCES "users" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;