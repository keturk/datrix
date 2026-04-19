CREATE TABLE "projects" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "name" VARCHAR(200) NOT NULL,    "owner_id" UUID NOT NULL,    CONSTRAINT pk_projects PRIMARY KEY (id));


CREATE INDEX "idx_projects_owner_id"
    ON "projects"
    ("owner_id");