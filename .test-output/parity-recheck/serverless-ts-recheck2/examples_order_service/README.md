# examples.OrderService

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
| Order | id, amount, currency, status | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/orders | list_orders |
| GET | /api/v1/orders/:id | get_order |

## Events

| Topic | Events |
|-------|--------|
| OrderEvents | OrderPlaced, OrderCancelled |


## Serverless Handlers

Handlers listed below are deployed as serverless functions. Infrastructure provisioning is managed externally; this section documents the handler configuration only.

| Handler | Block | Trigger | Configuration |
|---------|-------|---------|---------------|
| order_events_order_placed | eventHandlers | pubsub | timeout 300s, memory 512MB, platform container |
| order_events_order_cancelled | eventHandlers | pubsub | timeout 300s, memory 512MB, platform container |
| stripe_webhook | eventHandlers | http | timeout 300s, memory 512MB, platform container |
| daily_order_report | scheduledTasks | schedule | timeout 600s, memory 512MB, platform container |
| examples_order_service_process_shipment | queueWorkers | queue | timeout 300s, memory 512MB, platform container |



## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

## Dependencies

- examples.OrderService
