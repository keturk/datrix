CREATE TABLE "device_registrations" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "subject" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "platform" VARCHAR(50) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_device_registrations PRIMARY KEY (id),
    CONSTRAINT chk_device_registrations_platform_enum CHECK (platform IN ('Ios', 'Android', 'Web'))
);
