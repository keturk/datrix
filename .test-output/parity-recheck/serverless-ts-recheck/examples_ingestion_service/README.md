# examples.IngestionService

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




## Serverless Handlers

Handlers listed below are deployed as serverless functions. Infrastructure provisioning is managed externally; this section documents the handler configuration only.

| Handler | Block | Trigger | Configuration |
|---------|-------|---------|---------------|
| weekly_data_pull | ingestionHandlers | schedule | timeout 300s, memory 512MB, platform container |
| ingestion_events_source_ingested | ingestionHandlers | pubsub | timeout 300s, memory 512MB, platform container |



## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

## Dependencies

- examples.IngestionService
