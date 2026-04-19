# ecommerce.OrderService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8002)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| Order | id, createdAt, updatedAt, customerId, orderNumber, status, subtotal, tax, shippingCost, discount, shippingAddress, billingAddress, inventoryReservationId, paymentId, shipmentId, cancellationReason | id |
| OrderItem | id, createdAt, updatedAt, productId, productName, quantity, unitPrice | id |
| IdempotencyKey | id, createdAt, updatedAt, key, operation, resourceId, response, expiresAt | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/orders | get |
| GET | /api/v1/orders/:id | get |
| POST | /api/v1/orders | post |
| PUT | /api/v1/orders/:id/cancel | put |
| GET | /api/v1/orders/internal/:id | get |
| POST | /api/v1/orders/:id/confirm-payment | post |
| POST | /api/v1/orders/:id/update-shipment | post |

## Events

| Topic | Events |
|-------|--------|
| OrderEvents | OrderCreated, OrderConfirmed, OrderCancelled, OrderStatusChanged |

## Cache

This service uses a cache block. See `.env.example` for `REDIS_URL`.

## Environment variables

See `.env.example` for required environment variables.

## Dependencies

- ecommerce.ProductService
- ecommerce.PaymentService
- ecommerce.ShippingService
