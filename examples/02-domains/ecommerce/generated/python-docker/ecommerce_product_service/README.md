# ecommerce.ProductService

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
| Category | id, createdAt, updatedAt, name, description, slug | id |
| Product | id, createdAt, updatedAt, slug, price, compareAtPrice, inventory, name, description, status, productMetadata, images, tags | id |
| InventoryReservation | id, createdAt, updatedAt, reservationId, quantity, status, expiresAt | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/products/products | list_products |
| GET | /api/v1/products/products/:id | get_product |
| POST | /api/v1/products/products | create_product |
| PUT | /api/v1/products/products/:id | update_product |
| DELETE | /api/v1/products/products/:id | delete_product |
| GET | /api/v1/products/slug/:slug | get |
| GET | /api/v1/products/search | get |
| GET | /api/v1/products/category/:categoryId | get |
| POST | /api/v1/products | post |
| PUT | /api/v1/products/:id/inventory | put |
| PUT | /api/v1/products/:id/publish | put |
| POST | /api/v1/products/internal/check-availability | post |
| POST | /api/v1/products/internal/reserve-inventory | post |
| POST | /api/v1/products/internal/confirm-reservation | post |
| POST | /api/v1/products/internal/release-reservation | post |
| GET | /api/v1/products/internal/:id | get |
| POST | /api/v1/products/internal/bulk | post |

## Events

| Topic | Events |
|-------|--------|
| ProductEvents | ProductCreated, InventoryUpdated, InventoryReserved, InventoryReleased |

## Cache

This service uses a cache block. See `.env.example` for `REDIS_URL`.

## Environment variables

See `.env.example` for required environment variables.

