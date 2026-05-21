# External Infrastructure Pattern (hostdemo)

This example shows a two-service system where `test` and `development` run with Docker Compose defaults, while `production` is modeled for AWS through ConfigDSL deployment and service flavor settings.

## Prerequisites

- Datrix CLI installed (`datrix` on your `PATH`).
- `test` and `development` work with the default Docker Compose deployment target.
- `production` sets `deployment.runtime = "ecs-fargate"` and `deployment.provider = "aws"` in `config/system.dcfg`, with service-level `flavor = "ecs-fargate"` and managed infrastructure replacements in each service `.dcfg` file.

## Local Dependencies

For local Docker Compose profiles, the generated stack owns the service dependencies declared in ConfigDSL:

- PostgreSQL on `5432` for `hostdemo_blog` and `hostdemo_user`.
- Redis on `6379`.
- Elasticsearch on `9200`.
- MinIO API on `9000` for buckets `hostdemo-blog` and `hostdemo-user`.

## Commands

From this directory:

```bash
datrix validate system.dtrx
datrix generate --source system.dtrx --output ../../../../.projects/hostdemo-test --profile test
datrix generate --source system.dtrx --output ../../../../.projects/hostdemo-development --profile development
```

`datrix validate` loads every profile, including `production`. Adjust `--output` to any empty or disposable folder.

## Production Profile Note

Installing `datrix-codegen-aws` is not enough on its own: the generate pipeline must also provide AWS deployment settings. Treat the `production` profile in `config/system.dcfg`, `config/blog-service.dcfg`, and `config/user-service.dcfg` as the reference for how managed services are expressed, and rely on validation here.
