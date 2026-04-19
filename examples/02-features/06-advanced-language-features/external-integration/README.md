# External infrastructure pattern (hostdemo)

This example shows a two-service system where **test** and **development** run databases, cache, search, and object storage **inside Docker**, while **staging** treats PostgreSQL, Redis, Elasticsearch, and MinIO as **already running on the host** (reachable via `host.docker.internal`). **RabbitMQ** stays **containerized** on staging. **Production** is modeled for **AWS** (`hosting: aws`) with managed-style flavors (RDS, ElastiCache URL, S3, external message brokers, external Elasticsearch with TLS and basic auth).

## Prerequisites

- Datrix CLI installed (`datrix` on your `PATH`).
- **`test`**, **development**, and **staging** work with the default **Docker** generator.
- **`production`** sets **`hosting: aws`** so YAML validates against AWS-oriented flavors (RDS, S3, and so on). The generate pipeline **auto-resolves platform config only for Docker** today, so `datrix generate --profile production` stops at discovery unless caller-supplied tooling wires `AwsPlatformConfig` (see `datrix_common.generation.discovery`). Use **`datrix validate`** to exercise the production profile here.

### Staging: services on the host

Before `datrix generate --profile staging`, run (or equivalent) on the machine that hosts Docker:

- PostgreSQL on **5432** (databases `hostdemo_blog`, `hostdemo_user` — match `config/*/datasources.yaml` staging blocks).
- Redis on **6379**.
- Elasticsearch on **9200** (single-node is fine for demos).
- MinIO API on **9000** (buckets `hostdemo-blog`, `hostdemo-user`).

The generated Compose file adds `extra_hosts` so containers can reach `host.docker.internal`. You should **not** expect Compose to start Postgres, Redis, Elasticsearch, or MinIO for staging.

## Commands

From this directory:

```bash
datrix validate system.dtrx
datrix generate --source system.dtrx --output ../../../../.projects/hostdemo-test --profile test
datrix generate --source system.dtrx --output ../../../../.projects/hostdemo-staging --profile staging
```

`datrix validate` loads every profile, including **production**. Adjust `--output` to any empty or disposable folder.

## What to check after staging generate

- No **postgres**, **redis**, **elasticsearch**, or **minio** service entries for the externalized dependencies (only app services, gateway, RabbitMQ, etc., depending on generators).
- `extra_hosts` (or equivalent) present so apps resolve `host.docker.internal`.
- RabbitMQ still defined as a **container** for staging pub/sub.

## Production profile note

Installing `datrix-codegen-aws` is not enough on its own: the generate pipeline must also provide AWS deployment settings (`AwsPlatformConfig`). Until that is wired for the CLI, treat the **production** section of `config/system-config.yaml` and per-service YAML as the reference for how managed services are expressed, and rely on **validation** here.
