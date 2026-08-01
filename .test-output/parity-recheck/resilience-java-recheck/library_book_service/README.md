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
| Book | createdAt, updatedAt, id, title, author | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/books | list_books |
| GET | /api/v1/books/:id | get_book |
| POST | /api/v1/books | create_book |
| PUT | /api/v1/books/:id | update_book |
| DELETE | /api/v1/books/:id | delete_book |






## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

