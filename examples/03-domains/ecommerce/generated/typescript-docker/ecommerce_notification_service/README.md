# ecommerce.NotificationService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8001)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key | Description |
|--------|--------|-------------|-------------|
| NotificationAudit | createdAt, updatedAt, id, orderId, recipientEmail, orderNumber | id |  |
| DeviceRegistration | id, subject, token, platform, createdAt, updatedAt | id |  |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /push/devices | registerDevice |
| POST | /push/devices/unregister | unregisterDevice |






## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

## Dependencies

- ecommerce.OrderService
