CREATE TABLE "books" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "title" VARCHAR(200) NOT NULL,    "author" VARCHAR(100) NOT NULL,    "publication_year" BIGINT NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Available',    "category_id" UUID NOT NULL,    CONSTRAINT pk_books PRIMARY KEY (id),    CONSTRAINT chk_books_status_enum CHECK (status IN ('Available', 'CheckedOut', 'Reserved')));


ALTER TABLE "books"
    ADD CONSTRAINT "fk_books_category_id"
    FOREIGN KEY ("category_id")
    REFERENCES "categories" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;