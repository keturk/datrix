CREATE TABLE "user_preferenceses" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "language" VARCHAR(10) NOT NULL DEFAULT 'en',    "timezone" VARCHAR(50) NOT NULL DEFAULT 'UTC',    "email_notifications" BOOLEAN NOT NULL DEFAULT TRUE,    "sms_notifications" BOOLEAN NOT NULL DEFAULT FALSE,    "preferences" JSONB NOT NULL,    "user_id" UUID,    CONSTRAINT pk_user_preferenceses PRIMARY KEY (id));


ALTER TABLE "user_preferenceses"
    ADD CONSTRAINT "fk_user_preferenceses_user_id"
    FOREIGN KEY ("user_id")
    REFERENCES "users" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;