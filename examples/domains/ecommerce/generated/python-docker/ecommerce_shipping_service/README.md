# ecommerce.ShippingService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8004)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| Shipment | id, createdAt, updatedAt, orderId, trackingNumber, carrier, status, destination, weight, estimatedDelivery, actualDelivery, failureReason | id |
| ShipmentEvent | id, createdAt, updatedAt, timestamp, status, location, description | id |
| ShipmentItem | id, createdAt, updatedAt, productId, quantity | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/shipments/shipments/:id | get_shipment |
| GET | /api/v1/shipments/order/:orderId | get |
| GET | /api/v1/shipments/track/:trackingNumber | get |
| POST | /api/v1/shipments | post |
| PUT | /api/v1/shipments/:id/status | put |
| POST | /api/v1/shipments/:id/events | post |
| POST | /api/v1/shipments/rates | post |
| POST | /api/v1/shipments/webhook/fedex | post |

## Events

| Topic | Events |
|-------|--------|
| ShipmentEvents | ShipmentCreated, ShipmentDispatched, ShipmentDelivered, ShipmentFailed |

## Cache

This service uses a cache block. See `.env.example` for `REDIS_URL`.

## Environment variables

See `.env.example` for required environment variables.

