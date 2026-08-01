# warehouse.WarehouseService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8000)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| BaseEntity | id, createdAt, updatedAt | id |
| Warehouse | id, createdAt, updatedAt, name, code, boundary, centerPoint, capacitySquareMeters | id |
| DeliveryZone | id, createdAt, updatedAt, name, zoneCode, coverageArea, radiusNm | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/warehouses/containing | get |
| GET | /api/v1/warehouses/nearby | get |
| GET | /api/v1/delivery-zones/for-location | get |
| GET | /api/v1/warehouses/:warehouseId/area | get |






## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

