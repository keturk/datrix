# library.NotificationService

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
| NotificationDeliveryLog | id, createdAt, updatedAt, bookId, recipientEmail, messagePreview | id |







## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

## Dependencies

- library.BookService
