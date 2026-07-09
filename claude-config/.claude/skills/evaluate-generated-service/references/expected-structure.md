### Python/FastAPI -- Expected Generated Structure per Service

```
{service_dir}/
+-- alembic-{block}.ini                    # per RDBMS block
+-- migrations-{block}/                    # per RDBMS block
|   +-- env.py
|   +-- script.py.mako
|   +-- versions/0001_initial_schema.py
+-- pyproject.toml
+-- requirements.txt
+-- requirements-dev.txt
+-- Dockerfile
+-- .dockerignore
+-- src/{python_package}/
|   +-- __init__.py
|   +-- main.py
|   +-- config.py
|   +-- auth.py
|   +-- error_handlers.py
|   +-- error_response.py
|   +-- {block_name}/                      # per RDBMS block (kebab-case)
|   |   +-- __init__.py
|   |   +-- base.py
|   |   +-- connection.py
|   |   +-- session.py
|   |   +-- health.py
|   +-- models/{block_name}/               # per RDBMS block
|   |   +-- __init__.py
|   |   +-- {entity_snake}.py              # per non-abstract entity
|   +-- schemas/{block_name}/              # per RDBMS block
|   |   +-- __init__.py
|   |   +-- {entity_snake}.py              # per non-abstract entity
|   +-- schemas/{struct_snake}.py           # per struct (at schemas root)
|   +-- services/_base.py
|   +-- services/{block_name}/             # per RDBMS block
|   |   +-- __init__.py
|   |   +-- {entity_snake}_service.py      # per non-abstract entity
|   +-- routes/                            # per REST API
|   |   +-- __init__.py
|   |   +-- {api_name_snake}.py
|   +-- redis/                             # if cache block
|   |   +-- __init__.py
|   |   +-- access.py
|   |   +-- config.py
|   |   +-- connection.py
|   |   +-- decorators.py
|   +-- mq/                                # if pubsub block
|   |   +-- __init__.py
|   |   +-- config.py
|   |   +-- connection.py
|   |   +-- consumer.py
|   |   +-- producer.py
|   |   +-- schemas.py
|   +-- jobs/                              # if jobs block
|   |   +-- config.py
|   |   +-- runner.py
|   |   +-- scheduler.py
|   +-- store/                             # if storage block
|   |   +-- store_client.py
|   +-- docdb/                             # if nosql block
|   |   +-- client.py
|   |   +-- health.py
|   +-- cqrs/                              # if CQRS block
|   +-- observability/                     # if observability configured
|   |   +-- health_endpoint.py
|   |   +-- metrics_middleware.py
|   |   +-- structured_logger.py
|   |   +-- tracing_setup.py
|   +-- enums/                             # if enums defined
|   |   +-- {enum_snake}.py
|   +-- clients/                           # if service dependencies
|   +-- middleware/
+-- tests/
    +-- unit/
    +-- integration/
```

### TypeScript/NestJS -- Expected Generated Structure per Service

```
{service_dir}/
+-- package.json
+-- tsconfig.json
+-- tsconfig.build.json
+-- Dockerfile
+-- .dockerignore
+-- nest-cli.json
+-- src/
|   +-- main.ts
|   +-- app.module.ts
|   +-- config/
|   |   +-- app.config.ts
|   +-- entities/{block_name}/             # per RDBMS block (snake_case)
|   |   +-- {entity_snake}.entity.ts       # per non-abstract entity
|   +-- dto/{block_name}/                  # per RDBMS block
|   |   +-- create-{entity_kebab}.dto.ts   # per non-abstract entity
|   |   +-- update-{entity_kebab}.dto.ts
|   |   +-- {entity_kebab}.response.dto.ts
|   +-- dto/{struct_kebab}.dto.ts           # per struct
|   +-- controllers/
|   |   +-- {api_kebab}.controller.ts      # per REST API
|   +-- services/{block_name}/
|   |   +-- {entity_kebab}.service.ts      # per non-abstract entity
|   +-- {block_name}-db/                   # database module per RDBMS block (kebab-case)
|   |   +-- database.module.ts
|   |   +-- database.config.ts
|   |   +-- database.health.ts
|   +-- nosql/                             # if nosql block
|   +-- pubsub/ or messaging/              # if pubsub block
|   +-- observability/                     # if observability
|   +-- enums/
|   |   +-- {enum_kebab}.enum.ts
+-- test/
```
