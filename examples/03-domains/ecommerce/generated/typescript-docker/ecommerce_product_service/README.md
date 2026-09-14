# ecommerce.ProductService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8004)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key | Description |
|--------|--------|-------------|-------------|
| Category | createdAt, updatedAt, id, name, description, slug | id |  |
| Product | createdAt, updatedAt, id, slug, price, compareAtPrice, inventory, name, description, status, productMetadata, images, tags, categoryId | id |  |
| InventoryReservation | createdAt, updatedAt, id, reservationId, quantity, status, expiresAt, productId | id |  |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/products/products | list_products |
| GET | /api/v1/products/products/:id | get_product |
| PUT | /api/v1/products/products/:id | update_product |
| DELETE | /api/v1/products/products/:id | delete_product |
| GET | /api/v1/products/slug/:slug | get |
| GET | /api/v1/products/search | get |
| GET | /api/v1/products/category/:categoryId | get |
| POST | /api/v1/products | post |
| PUT | /api/v1/products/:id/inventory | put |
| PUT | /api/v1/products/:id/publish | put |
| POST | /api/v1/products/service/check-availability | checkAvailability |
| POST | /api/v1/products/service/reserve-inventory | reserveInventory |
| POST | /api/v1/products/service/confirm-reservation | reservationConfirmation |
| POST | /api/v1/products/service/release-reservation | reservationRelease |
| GET | /api/v1/products/service/:id | productByIdInternal |
| POST | /api/v1/products/service/bulk | productsBulk |

## Events

| Topic | Events |
|-------|--------|
| ProductEvents | ProductCreated, InventoryUpdated, InventoryReserved, InventoryReleased |

## Cache

This service uses a cache block. Runtime connection details are resolved from the generated config store and secrets resolver.




## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

