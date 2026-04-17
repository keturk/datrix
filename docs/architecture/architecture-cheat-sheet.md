# Architecture Cheat Sheet

Pipeline: `.dtrx -> Parser (datrix-language) -> Semantic Analysis -> Config Resolution -> Application (AST) -> Generators`
No IR layer. Parser produces Application directly.

## Packages (11)

| Package | Purpose |
|---------|---------|
| datrix-common | Foundation: AST model, types, semantic analysis, config resolution, generation framework. ZERO deps on other Datrix packages |
| datrix-language | Parser (Tree-sitter) + CST-to-AST transformers. Depends on datrix-common |
| datrix-codegen-component | Platform-agnostic artifacts (docs, config, scripts) |
| datrix-codegen-python | Python generation (FastAPI). Jinja2 + ruff format |
| datrix-codegen-typescript | TypeScript generation (NestJS/Express). Jinja2 + Prettier |
| datrix-codegen-sql | SQL DDL (PostgreSQL, MySQL) |
| datrix-codegen-docker | Docker/Compose generation. YAML builders |
| datrix-codegen-k8s | Kubernetes manifests |
| datrix-codegen-aws | AWS infrastructure (CDK/CloudFormation) |
| datrix-codegen-azure | Azure infrastructure (Bicep/ARM) |
| datrix-cli | CLI. Discovers generator plugins dynamically via entry points |

## Entity Access (CRITICAL)

Entities are **block-scoped**, not flat. Always iterate per-service, per-block:
```python
for service in app.services.values():
    for rdbms_block in service.rdbms_blocks.values():
        for entity in rdbms_block.entities.values():
            generate(entity, service)
```
Never flatten entities across services.

## Plugin Architecture

Generators discovered via entry points: `datrix.generators`, `datrix.platforms`, `datrix.language_hooks`, `datrix.language_runtime_spec`.
Language generators subclass `LanguageGenerator` (9 abstract methods).
Type mappings registered with `TypeMappingRegistry.global_registry`.

## Key Capabilities

- Background jobs (APScheduler), Alembic migrations, seed data
- Elasticsearch integration, inter-service HTTP auth (shared secret), JWT gateway
- GraphQL DataLoaders, rate limiting (gateway + per-route Redis), RFC 7807 errors
- Prometheus metrics, Grafana dashboards, cAdvisor, alert rules
- Multi-service NGINX gateway (upstreams, health aliases, CORS, rate limit zones)

## Technology

Python 3.11+, Tree-sitter, Pydantic v2, Jinja2, ruff/Prettier, mypy strict, pytest.

## Full docs

- [architecture-overview.md](./architecture-overview.md)
- [code-generation.md](../../../datrix-common/docs/architecture/code-generation.md)
