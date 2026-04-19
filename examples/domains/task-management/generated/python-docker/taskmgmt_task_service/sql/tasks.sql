CREATE TABLE "tasks" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,    "project_id" UUID NOT NULL,    "assignee_id" UUID NOT NULL,    "title" VARCHAR(200) NOT NULL,    "completed" BOOLEAN NOT NULL DEFAULT FALSE,    CONSTRAINT pk_tasks PRIMARY KEY (id));


CREATE INDEX "idx_tasks_project_id_assignee_id"
    ON "tasks"
    ("project_id", "assignee_id");