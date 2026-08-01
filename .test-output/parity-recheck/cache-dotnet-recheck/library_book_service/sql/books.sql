CREATE TABLE "books" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,    "title" VARCHAR(200) NOT NULL,    "isbn" VARCHAR(13) NOT NULL,    "author" VARCHAR(100) NOT NULL,    "publication_year" BIGINT NOT NULL,    "status" VARCHAR(50) NOT NULL DEFAULT 'Available',    "format" VARCHAR(50) NOT NULL DEFAULT 'Hardcover',    "catalog_number" VARCHAR(50),    "keywords" JSONB NOT NULL DEFAULT '[]',    "rating" NUMERIC(3,2) NOT NULL DEFAULT 0.0,    "category_id" UUID NOT NULL,    CONSTRAINT pk_books PRIMARY KEY (id),    CONSTRAINT chk_books_isbn_min_length CHECK (LENGTH(isbn) >= 10),    CONSTRAINT chk_books_status_enum CHECK (status IN ('Available', 'CheckedOut', 'Reserved', 'Maintenance')),    CONSTRAINT chk_books_format_enum CHECK (format IN ('Hardcover', 'Paperback', 'eBook', 'Audiobook')));


ALTER TABLE "books"
    ADD CONSTRAINT "fk_books_category_id"
    FOREIGN KEY ("category_id")
    REFERENCES "categories" ("id")
    ON DELETE RESTRICT
    ON UPDATE NO ACTION;