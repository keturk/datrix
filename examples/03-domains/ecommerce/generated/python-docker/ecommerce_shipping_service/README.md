# ecommerce.ShippingService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8005)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key | Description |
|--------|--------|-------------|-------------|
| Shipment | createdAt, updatedAt, id, orderId, trackingNumber, carrier, status, destination, weight, estimatedDelivery, actualDelivery, failureReason | id |  |
| ShipmentEvent | createdAt, updatedAt, id, timestamp, status, location, description, shipmentId | id |  |
| ShipmentItem | createdAt, updatedAt, id, productId, quantity, shipmentId | id |  |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/shipments/shipments/:id | get_shipment |
| GET | /api/v1/shipments/order/:orderId | get |
| GET | /api/v1/shipments/track/:trackingNumber | get |
| POST | /api/v1/shipments | createShipment |
| PUT | /api/v1/shipments/:id/status | put |
| POST | /api/v1/shipments/:id/events | post |
| POST | /api/v1/shipments/rates | post |
| POST | /api/v1/shipments/webhook/fedex | post |

## Events

| Topic | Events |
|-------|--------|
| ShipmentEvents | ShipmentCreated, ShipmentDispatched, ShipmentDelivered, ShipmentFailed |

## Cache

This service uses a cache block. Runtime connection details are resolved from the generated config store and secrets resolver.




## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

