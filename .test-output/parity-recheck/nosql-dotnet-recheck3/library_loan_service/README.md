# library.LoanService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8001)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| BaseEntity | id, createdAt, updatedAt | id |
| Loan | id, createdAt, updatedAt, bookId, memberId, status, dueDate, returnedAt | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/loans | post |
| GET | /api/v1/loans/member/:memberId | get |






## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

## Dependencies

- library.BookService
- library.MemberService
