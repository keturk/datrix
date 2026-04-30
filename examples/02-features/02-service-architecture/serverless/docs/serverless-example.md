# Serverless block example

This folder demonstrates the `serverless` deployment boundary: the same DSL constructs as in-process code (`subscribe`, `job`, HTTP verbs with `@path`, `enqueue`) are grouped so their YAML can target Lambda, Azure Functions, or in-container execution per profile.

## What is included

- **`order-service.dtrx`**: One service with `rest_api`, in-process `jobs`, `pubsub`, `queues`, and **three** `serverless` blocks (event handlers, scheduled tasks, queue workers). Covers all four serverless member kinds.
- **`shared-ingestion.dtrx`**: A `shared` block with `pubsub`, `storage`, and `serverless` handlers so shared infrastructure can own serverless functions.
- **`config/`**: Profiled serverless YAML under `config/order-service/` and `config/shared/`, plus the usual service and system configs copied from sibling examples.

## In-process vs serverless

- **In-process**: `jobs { job QuickCleanup { ... } }` runs in the long-lived service container with `jobs.yaml`.
- **Serverless**: Members inside `serverless('...yaml') { ... }` use the same syntax; `event-handlers.yaml`, `scheduled-tasks.yaml`, and `queue-workers.yaml` set `platform: lambda` (or `functions`) in production and `platform: container` in development so local runs stay in-process.

## Generate

From the monorepo root:

```powershell
powershell -File "D:/datrix/datrix/scripts/dev/generate.ps1" "D:/datrix/datrix/examples/02-features/02-service-architecture/serverless/system.dtrx"
```

Output defaults under `.generated/python/docker/02-features/02-service-architecture/serverless/` (see `test-projects.json` for overrides).

## Further reading

See `design/03-serverless-functions.md` for rationale, config schema, and planned codegen.
