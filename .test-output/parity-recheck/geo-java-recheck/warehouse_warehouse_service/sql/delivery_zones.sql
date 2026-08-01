CREATE TABLE "delivery_zones" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "name" VARCHAR(200) NOT NULL,    "zone_code" VARCHAR(50) NOT NULL,    "coverage_area" geometry NOT NULL,    "radius_nm" DOUBLE PRECISION NOT NULL,    CONSTRAINT pk_delivery_zones PRIMARY KEY (id),    CONSTRAINT uq_delivery_zones_zone_code UNIQUE (zone_code));


CREATE INDEX "gist_delivery_zones_coverage_area" ON "delivery_zones" USING GIST ("coverage_area");