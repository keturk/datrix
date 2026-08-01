# library.BookService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8000)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| BaseEntity | id, createdAt, updatedAt | id |
| Category | id, createdAt, updatedAt, name, description | id |
| User | id, createdAt, updatedAt, email, passwordHash, role | id |
| Book | id, createdAt, updatedAt, title, isbn, author, publicationYear, status, format, catalogNumber, keywords, rating, categoryId | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/books | list_books |
| GET | /api/v1/books/:id | get_book |
| POST | /api/v1/books | create_book |
| PUT | /api/v1/books/:id | update_book |
| DELETE | /api/v1/books/:id | delete_book |
| GET | /api/v1/categories | list_categories |
| GET | /api/v1/categories/:id | get_category |
| GET | /api/v1/books/search | get |
| POST | /api/v1/books/:bookId/reindex | post |
| POST | /api/v1/books/:bookId/notify | post |

## Events

| Topic | Events |
|-------|--------|
| BookEvents | BookAdded, BookStatusChanged |





## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

