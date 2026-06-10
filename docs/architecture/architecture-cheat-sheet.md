# Architecture Cheat Sheet

Pipeline (user sources): `.dtrx -> Parser (datrix-language) -> extension directives on AST -> extension resolution (registry / TypeRegistry when invoked) -> Semantic Analysis -> Config Resolution -> Application (AST) -> Generators`

**Builtins and stdlib (language layer, before generators):** builtins ship as pre-parsed ASTs (traits, scalars, enums, and the four builtin domain exceptions in `builtins.dtrx`). Eight stdlib `.dtrx` modules ship as pre-parsed ASTs under `datrix-language/src/datrix_language/stdlib/` and stay lazy until semantic analysis needs them. User files still go through Tree-sitter parse + transformers into `Application`; stdlib symbols are registered as placeholders on the app scope and the owning stdlib module is deserialized on first reference during semantic analysis.

```
builtins        -> pre-parsed builtin ASTs
stdlib/*.dtrx   -> eight pre-parsed module ASTs (lazy-loaded)
user *.dtrx     -> TreeSitterParser + transformers -> Application
semantic analysis -> stdlib placeholders + lazy module injection -> continuing phases -> Generators
```

**Load order:** builtins → stdlib placeholder registration → user parse/transform → semantic analysis (lazy stdlib deserialization when a stdlib export is first resolved).

No IR layer. Parser produces `Application` directly. Named `GenerationPipeline.run` stages include: `parse` → `resolve_service_configs` → `analyze` → `resolve_infrastructure_configs` → `validate_deployment` → `apply_cli_overrides` → `normalize_service_memory_limits` → `discover_generators` / `discover_platforms` → `generate:{name}` (per generator) → file write → migrations (when configured) → language hooks + JSON format → `snapshot` (service filter and incremental merge sit between infra resolution and discovery when enabled). There is **no** `platform_validation` stage; cross-model and `(provider, DeploymentProvider)` realization checks run inside `resolve_infrastructure_configs` (the Stage 2 cross-model hook), and deployment-presence checks run in `validate_deployment`.

## Packages (12)

Optional **datrix-extensions** (domain packs, `datrix.extensions` entry points) plus eleven core packages below.

| Package | Purpose |
|---------|---------|
| datrix-common | Foundation: AST model, types, semantic analysis, config resolution, generation framework. ZERO deps on other Datrix packages |
| datrix-language | Parser (Tree-sitter) + CST-to-AST transformers; shipped stdlib sources in `src/datrix_language/stdlib/` (eight `.dtrx` modules, pre-parsed at build time, lazy-loaded in analysis). Depends on datrix-common |
| datrix-codegen-component | Platform-agnostic artifacts (docs, config, scripts) |
| datrix-codegen-python | Python generation (FastAPI). Jinja2 + ruff format |
| datrix-codegen-typescript | TypeScript generation (NestJS/Express). Jinja2 + Prettier |
| datrix-codegen-sql | SQL DDL (PostgreSQL, MySQL) |
| datrix-codegen-docker | Docker/Compose generation. YAML builders |
| datrix-codegen-k8s | Kubernetes manifests |
| datrix-codegen-aws | AWS infrastructure (CDK/CloudFormation): VPC, ECS, RDS, ElastiCache, SNS/SQS, MSK (Kafka), DynamoDB, S3 |
| datrix-codegen-azure | Azure infrastructure (Bicep/ARM): App Service, Functions, Flexible Server, Cosmos DB, Service Bus, Event Hubs (Kafka), Redis, Blob, APIM, Front Door, AI Search |
| datrix-cli | CLI. Discovers generator plugins dynamically via entry points |
| datrix-extensions | Optional domain extension packs (`datrix.extensions`). Depends on datrix-common |

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

Generators and extensions discovered via entry points: `datrix.generators`, `datrix.platforms`, `datrix.language_hooks`, `datrix.language_runtime_spec`, **`datrix.extensions`** (`DatrixExtension`).
Language generators subclass `LanguageGenerator` (9 abstract methods).
Type mappings registered with `TypeMappingRegistry.global_registry`.

## Transpiler pipeline (per file)

```
Stage 1: NameResolver     -> ResolutionTable (id(ast_node) -> ResolutionInfo)
Stage 2: QueryExpander    -> updated table + query annotations
Stage 3: LanguageTranspiler (Python / TypeScript / …) -> TranspileResult (code + imports + flags)
```

Orchestration: `StagePipeline` in **datrix-common** runs Stages 1–2 and configures the emitter; templates call the language transpiler for DSL bodies. Details: [code-generation.md](../../../datrix-common/docs/architecture/code-generation.md), [datrix-common architecture](../../../datrix-common/docs/architecture.md#transpiler-architecture-staged-pipeline).

| Category | Type | Lifetime |
|----------|------|----------|
| Config | `TranspileContext` | Per service; frozen |
| Per-file state | `FileScope` / language subclass | Fresh per emitted file; mutable |
| Upward artifacts | `TranspileResult` | Per visit; frozen |

## Domain extensions

- **DSL:** `use extension <name>;` inside `system { }` (stored on `app.extension_directives`).
- **Protocol `DatrixExtension` (eight surfaces):** properties `name`, `version`; methods `scalar_definitions()`, `builtin_objects()`, `value_struct_definitions()`, `db_extensions()`, `extra_dependencies()`, `template_dirs()` (`datrix_common.plugin.extension`).
- **Discovery:** `PluginRegistry.discover_extensions()`; load declared names: `load_declared_extensions(declared)`.
- **Types:** `TypeRegistry.load_extensions(extensions)` when callers register pack scalars.
- **Declared names in codegen:** `declared_extension_names(app)` → passed into `LanguageGenerator` / resolvers.
- **Python maps:** `PYTHON_EXTENSION_MAPS` + `build_python_type_map()` in `datrix_codegen_python.type_mappings` (raises `ExtensionNotSupportedError` if a declared extension has no Python map).
- **TypeScript / SQL:** Same split-ownership rule as Python; extension-only scalars would use the same *pattern* (per-extension dict merged into the language’s effective map) when implemented alongside core `TYPESCRIPT_TYPE_MAP` / `SQL_TYPE_MAP` — no separate `TS_EXTENSION_MAPS` / `SQL_EXTENSION_MAPS` modules in the tree yet.

Full guide: [extensions-guide.md](../../../datrix-extensions/docs/extensions-guide.md) · Core protocol: [datrix-common extensions](../../../datrix-common/docs/extensions.md).

## Extern Services

Contract-only declarations for external libraries/tools that Datrix does not generate. Consumed via `uses` (same as shared blocks and inter-service dependencies).

- **Container kinds:** `system`, `module`, `service`, `shared`, **`extern service`**
- **Extern service = contract only** — user builds and deploys the implementation
- **Allowed members:** `struct`, `enum`, `rest_api` (signature-only), `errors`, `auth`, `health`
- **No infrastructure blocks** (`rdbms`, `cache`, `pubsub`, etc.)
- **Config:** `deployment: container` (image + port, compose/K8s entries generated) or `deployment: external` (remote URL, no deployment artifacts)
- **Generated artifacts:** typed HTTP client, request/response models, error classes, contract validation (per consuming service)
- **AST:** `ExternService` in `datrix_common.datrix_model.extern_service`, registered on `Application.extern_services`
- **`uses` resolution order:** shared block → extern service → regular service

## RDBMS Migration Contract

Incremental, language-neutral, UUID-scoped. State lives under `{app_dir}/.datrix/rdbms-migrations/{rdbms_id}/`:
- `schema.json` — canonical schema snapshot (target-language/engine agnostic)
- `ledger.json` — ordered revision chain with database-agnostic canonical operations

Key rules:
- Every `RdbmsConfig` requires `id: UUID` in ConfigDSL
- Migration revisions are immutable once generated (append-only)
- Destructive changes are generation errors (no override)
- `RdbmsMigrationAdapter` protocol in `datrix-codegen-common` — Python/Alembic, TypeScript/MikroORM, SQL are adapters
- Shared-owned RDBMS migrations use `SharedPaths.rdbms_dir`, one apply unit per `rdbms_id`
- `GeneratedFile.retention = "append_only"` protects historical migration files from manifest cleanup

## Key Capabilities

- Background jobs (APScheduler), incremental RDBMS migrations (Alembic/MikroORM adapters), seed data
- Elasticsearch integration, inter-service HTTP auth (shared secret), JWT gateway
- GraphQL DataLoaders, rate limiting (gateway + per-route Redis), RFC 7807 errors
- Prometheus metrics, Grafana dashboards, cAdvisor, alert rules
- Multi-service NGINX gateway (upstreams, health aliases, CORS, rate limit zones)
- ArcGIS FeatureServer paged ingestion (`arcgisFeatureLayer` integration kind): metadata-aware pagination, deterministic checksums, watermark optimization, archive/refresh modes

## DSL grammar snapshot (`.dtrx`)

High-level constructs the parser and transformers understand today. Full detail: [language-reference.md](../reference/language-reference.md) and [datrix-syntax-reference.md](../../../datrix-language/docs/reference/datrix-syntax-reference.md).

| Layer | Constructs |
|-------|------------|
| File structure | `include`, `from X import Y`, `system`, `module`, `service`, `extern service` |
| Declarations | `entity`, `abstract entity`, `trait`, `enum`, `struct`, `const`, `fn` |
| Field features | Types, optional (`?`), sized (`String(200)`), collections (`Array<T>`, `Map<K,V>`, `Set<T>`), modifiers (`: unique, indexed, immutable, server, …`), defaults (`= expr`). **Server-managed fields** use the **`server`** modifier (e.g. `UUID id : primaryKey, server = uuid();`) — there is **no** `@` prefix on field types. |
| Catalog types | Module- or service-level **`scalar Name : BaseType { constraints… }`** for constrained aliases on existing types |
| Errors | Module- or service-level **`exceptions { … }`** with `Name : status(N), message("…");` and optional structured fields |
| REST (unchanged) | Endpoint decorators such as **`@retry`**, **`@rateLimit`**, **`@cache`** remain **`@`-prefixed**; that is separate from field modifiers |

## Technology

Python 3.11+, Tree-sitter, Pydantic v2, Jinja2, ruff/Prettier, mypy strict, pytest.

**AST dispatch:** `ExpressionVisitor[T]` / `StatementVisitor[T]` + `node.accept()` for expressions/statements (same pattern as `TypeVisitor[T]` for types); `CallTargetEmitter` + `dispatch_call()` for call targets — see [datrix-common-api — Transpiler modules](../../../datrix-common/docs/datrix-common-api.md#transpiler-modules).

## Full docs

- [architecture-overview.md](./architecture-overview.md)
- [datrix-stdlib-reference.md](../../../datrix-language/docs/reference/datrix-stdlib-reference.md) (stdlib module catalog)
- [code-generation.md](../../../datrix-common/docs/architecture/code-generation.md)
- [datrix-common-api.md — Transpiler modules](../../../datrix-common/docs/datrix-common-api.md#transpiler-modules)
