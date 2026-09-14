CREATE TABLE "notification_audits" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "order_id" UUID NOT NULL,
    "recipient_email" VARCHAR(320) NOT NULL,
    "order_number" VARCHAR(64) NOT NULL,
    CONSTRAINT pk_notification_audits PRIMARY KEY (id)
);
