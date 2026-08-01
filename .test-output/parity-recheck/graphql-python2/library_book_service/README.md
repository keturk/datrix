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
| Category | id, createdAt, updatedAt, name | id |
| Book | id, createdAt, updatedAt, title, author, publicationYear, status, categoryId | id |


## Events

| Topic | Events |
|-------|--------|
| BookEvents | BookAdded, BookStatusChanged |





## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

