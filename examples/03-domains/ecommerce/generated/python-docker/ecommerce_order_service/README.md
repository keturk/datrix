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

| Entity | Fields | Primary key | Description |
|--------|--------|-------------|-------------|
| Order | createdAt, updatedAt, id, customerId, orderNumber, status, subtotal, tax, shippingCost, discount, shippingAddress, billingAddress, inventoryReservationId, paymentId, shipmentId, cancellationReason | id |  |
| OrderItem | createdAt, updatedAt, id, productId, productName, quantity, unitPrice, orderId | id |  |
| IdempotencyKey | createdAt, updatedAt, id, key, operation, resourceId, response, expiresAt | id |  |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/orders | get |
| GET | /api/v1/orders/:id | get |
| POST | /api/v1/orders | post |
| PUT | /api/v1/orders/:id/cancel | put |
| GET | /api/v1/orders/service/:id | orderByIdInternal |
| POST | /api/v1/orders/:id/confirm-payment | paymentConfirmation |
| POST | /api/v1/orders/:id/update-shipment | shipmentUpdate |

## Events

| Topic | Events |
|-------|--------|
| OrderEvents | OrderCreated, OrderConfirmed, OrderCancelled, OrderStatusChanged |

## Cache

This service uses a cache block. Runtime connection details are resolved from the generated config store and secrets resolver.




## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

## Dependencies

- ecommerce.ProductService
- ecommerce.UserService
