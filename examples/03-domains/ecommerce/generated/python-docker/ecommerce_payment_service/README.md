# ecommerce.PaymentService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8003)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key | Description |
|--------|--------|-------------|-------------|
| Payment | createdAt, updatedAt, id, orderId, customerId, amount, method, status, transactionId, gatewayResponse, errorMessage, processedAt | id |  |
| Refund | createdAt, updatedAt, id, amount, reason, status, refundTransactionId, errorMessage, processedAt, paymentId | id |  |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/payments/payments/:id | get_payment |
| GET | /api/v1/payments/order/:orderId | get |
| GET | /api/v1/payments/my-payments | get |
| POST | /api/v1/payments/process | post |
| POST | /api/v1/payments/:id/refund | post |
| POST | /api/v1/payments/webhook/stripe | post |

## Events

| Topic | Events |
|-------|--------|
| PaymentEvents | PaymentProcessed, PaymentFailed, PaymentRefunded |





## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

## Dependencies

- ecommerce.OrderService
