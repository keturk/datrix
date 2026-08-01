CREATE TABLE "book_tags" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "book_id" UUID NOT NULL,    "tag_id" UUID NOT NULL,    CONSTRAINT pk_book_tags PRIMARY KEY (id));


CREATE UNIQUE INDEX "uq_book_tags_book_id_tag_id"
    ON "book_tags"
    ("book_id", "tag_id");

ALTER TABLE "book_tags"
    ADD CONSTRAINT "fk_book_tags_book_id"
    FOREIGN KEY ("book_id")
    REFERENCES "books" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;

ALTER TABLE "book_tags"
    ADD CONSTRAINT "fk_book_tags_tag_id"
    FOREIGN KEY ("tag_id")
    REFERENCES "tags" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;