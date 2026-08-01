CREATE TABLE "warehouses" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "name" VARCHAR(200) NOT NULL,    "code" VARCHAR(100) NOT NULL,    "boundary" geometry NOT NULL,    "center_point" geometry NOT NULL,    "capacity_square_meters" BIGINT NOT NULL,    CONSTRAINT pk_warehouses PRIMARY KEY (id),    CONSTRAINT uq_warehouses_code UNIQUE (code));


CREATE INDEX "gist_warehouses_boundary" ON "warehouses" USING GIST ("boundary");

CREATE INDEX "gist_warehouses_center_point" ON "warehouses" USING GIST ("center_point");