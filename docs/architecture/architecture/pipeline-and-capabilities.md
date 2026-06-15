# Pipeline Flow & Capabilities

> Part of the architecture documentation. See [../architecture-overview.md](../architecture-overview.md) for the full index.

---

## System Architecture

### Pipeline Flow (Illustrative)

```
.dtrx + .dcfg + .dseed Source Files
 ↓
┌─────────────────────────────────┐
│ Parser (datrix-language) │
│ - Lexical analysis │
│ - Syntax parsing (Tree-sitter) │
│ - .dtrx, .dcfg, .dseed formats │
└─────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Application (immutable AST) │
│ - Pydantic models in datrix-common │
│ - Built by datrix-language transforms │
│ - Source locations preserved │
└─────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Extension directives (AST) │
│ use extension <name>; on system │
│ → app.extension_directives │
└─────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Extension resolution (logical) │
│ PluginRegistry: datrix.extensions │
│ entry points; load_declared_extensions │
│ TypeRegistry.load_extensions(...) │
│ when callers register pack scalars │
└─────────────────────────────────┘
 ↓
┌──────────────────────────────────────────────┐
│ Semantic Analysis (datrix-common)             │
│ SemanticAnalyzer.analyze() ordered phases:    │
│  1. Register stdlib symbols                  │
│  2. Materialize foundation for REST APIs     │
│  3. Collect symbols                          │
│  4. Resolve imports                          │
│  5. Materialize stdlib symbols used in bodies│
│  6. Resolve references                       │
│  7. Resolve field types                      │
│  8. Populate callable block names            │
│  9. Merge inheritance                        │
│ 10. Synthesize FK fields                     │
│ 11. Resolve all index fields                 │
│ 12. Check types                              │
│ 13. Run domain validators                    │
└──────────────────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Config Resolution │
│ - Parse .dcfg config files │
│ - Select active profile │
│ - Validate against schemas │
│ - Attach resolved_config to │
│ AST blocks │
└─────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Same Application, config-bound │
│ - ConfigDSL resolved per profile │
│ - resolved_config on blocks │
│ - Ready for platform validation │
│ - Generators read-only over AST │
│ - Seed declarations attached   │
└─────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Code Generators │
│ - datrix-codegen-component │
│ - datrix-codegen-python │
│ - datrix-codegen-typescript │
│ - datrix-codegen-sql │
│ (language-owned maps merge core │
│ + declared extensions, e.g. │
│ build_python_type_map) │
└─────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Platform Generators │
│ - datrix-codegen-docker │
│ - datrix-codegen-k8s │
│ - datrix-codegen-aws │
│ - datrix-codegen-azure │
└─────────────────────────────────┘
 ↓
Generated Application
  - Service source code
  - Database migrations (incremental,
    append-only revision chain per
    RDBMS block UUID)
  - Docker / K8s manifests
  - Seed scripts (profile-gated,
    multi-target, cross-component)
```

The `datrix generate` command reads `language` and `deployment` (runtime, provider, target, registry) from resolved config. Deployment-affecting CLI overrides (`--hosting`, `--platform`) are removed — see [Decision 6: Deployment Target Contract](../architecture-overview.md#decision-6-deployment-target-contract-stable). The pipeline validates deployment dimensions (runtime/provider/target/infrastructure-flavor combinations) before generation starts. Service deployment shape is derived from declared DSL blocks, not from a per-service runtime-flavor selector — see [Design Principles — Construct-Mapped Platform Realization](../design-principles.md#11-construct-mapped-platform-realization-stable).

> **Migration note:** During migration, the legacy `--language`, `--hosting`, and `--platform` CLI overrides still run in the `apply_cli_overrides` stage after service and infrastructure YAML are resolved on the AST (and after optional `--service` filtering), and before `platform_validation`.

**Pipeline stages (`GenerationPipeline.run` in `datrix-common`)** align with the diagram above through semantic analysis; afterward the implementation continues with: optional service filter → `apply_cli_overrides` → `normalize_service_memory_limits` → `deployment_validation` (validates runtime/provider/target/infrastructure-flavor combinations) → incremental merge (may early-exit when nothing changed) → `build_deployment_plan` (resolves `DeploymentPlan` with language generators, runtime generators, and provider generators from the deployment config — see [Decision 6: Deployment Target Contract](../architecture-overview.md#decision-6-deployment-target-contract-stable)) → `discover_generators` and `discover_platforms` (receives pre-resolved platform config from the plan) → execute generators → write files → optional migrations stage → `LanguageHooks` post-processing (gated by `validation_level`) → JSON normalization → `snapshot`. Extension **directives** are recorded during parse; **registry** and **type-registry** integration run when the active code path invokes `PluginRegistry` / `TypeRegistry` APIs (see [Domain extension system](repository-architecture.md#domain-extension-system)). Language generators receive declared extension names via `declared_extension_names(app)` and merge per-language maps (for example `build_python_type_map` in `datrix-codegen-python`).

#### Validation levels

`PipelineConfig.validation_level` controls which post-generation hooks run after files are written. The enum `ValidationLevel` lives in `datrix-common` (`datrix_common.generation.validation_level`) so both CLI and pipeline can use it.

| Level | Post-processing behavior |
|---|---|
| `none` | Skip `fix_imports`, `format_files`, and `validate_files`. Parser, config resolution, and semantic analysis still run (they are pre-generation and mandatory). |
| `fast` | Run `fix_imports` and `format_files` (if cheap). Skip `validate_files`. |
| `standard` | Run all three hooks: `fix_imports`, `format_files`, `validate_files`. This is the default. |
| `full` | Run `standard` plus additional checks (e.g. `ruff check` full suite, `pyright`, `tsc --noEmit`) when available via language hooks. |

CLI mapping: `--skip-validation` is shorthand for `--validation-level none`. `--validation-level` and `--skip-validation` cannot both specify a non-none level (a warning is emitted if they conflict, and `--skip-validation` wins).

**What validation levels never bypass:** `.dtrx` parse validation, `.dcfg` config loading and model validation, semantic analysis, and platform compatibility validation. These are pre-generation correctness checks, not post-generation quality checks.

### Standard library (Stable)

Datrix ships a **standard library**: eight `.dtrx` modules under `datrix-language/src/datrix_language/stdlib/` (`datrix.foundation`, `datrix.auth`, `datrix.geo`, `datrix.contact`, `datrix.api`, `datrix.data`, `datrix.billing`, `datrix.notification`). They provide commonly reused types, functions, and constants—`BaseEntity`, pagination helpers, `Address`, password/token helpers, rate-limit guards, geographic utilities, billing and notification enums, and similar patterns that were previously duplicated across dozens of example and production specs.

**Why it exists:** The same structures (base entities, auth helpers, address shapes, API guard helpers) were copy-pasted identically across projects. The stdlib centralizes those patterns so new services start from shared, reviewed definitions instead of re-declaring them in every `common.dtrx`.

**How it works (language layer):**

1. **Build-time pre-parse** — Stdlib sources are parsed when `datrix-language` is built/packaged and stored as serialized module ASTs for fast startup.
2. **Placeholder registration** — During semantic analysis, every stdlib export name is registered on the application scope as a lightweight placeholder backed by a symbol index. No full stdlib module is deserialized yet.
3. **Implicit global availability** — User modules can reference stdlib exports by simple name (`BaseEntity`, `hashPassword`, …) without import statements, the same way other global symbols are resolved once analysis runs.
4. **Lazy materialization** — The first resolution that needs symbols from a given stdlib module triggers deserialization of that module only; its declarations attach to `Application`, placeholders promote to real symbols, and analysis continues. Modules that are never referenced are never loaded.
5. **Shadowing and qualification** — User-defined types and functions with the same simple name as a stdlib export always win. To refer to the shipped definition explicitly, use qualified names (for example `datrix.contact.Address` or the owning module path) as documented in the language rules.
6. **Generators** — After analysis, generators see a normal validated `Application`: stdlib entities behave like user entities wherever they were materialized; unused stdlib leaves no footprint in the AST beyond placeholders that were never touched.

**Relationship to builtins:** Builtins supply abstract primitives—scalar kinds, builtin traits, builtin objects—that the language and type system understand everywhere. The stdlib composes those primitives into concrete patterns (for example `abstract entity BaseEntity with Timestampable`). Builtins are prerequisites; stdlib is optional in the sense that unreferenced modules never load, but the feature is always present in the toolchain.

**Relationship to domain extensions:** Extensions (`use extension …;`) add infrastructure-aware or domain-packaged scalars, extra dependencies, and DB extension hooks (PostGIS, TimescaleDB, etc.). Stdlib stays **database-agnostic** and ships with the core language—only builtin scalars and traits, no extension directives. Extensions and stdlib coexist: extensions answer "which engine extensions and pack types exist," stdlib answers "which everyday service patterns ship by default."

**Further reading:** Module-by-module catalog and naming rules live in [datrix-stdlib-reference.md](../../../../datrix-language/docs/reference/datrix-stdlib-reference.md) inside `datrix-language`.

### Phase 01 capabilities (Stable) (Python and Docker)

Details and generator APIs: [code-generation.md](../../../../datrix-common/docs/architecture/code-generation.md) (Datrix common docs) and [generators-api.md](../../../../datrix-common/docs/generators-api.md).

- **Background jobs** (Stable) — DSL `jobs` blocks plus resolved `JobsConfig` drive `JobsGenerator` (`datrix_codegen_python.generators.messaging.jobs_generator`): APScheduler wiring (`jobs/scheduler.py`, `jobs/runner.py`, `jobs/config.py`), transpiled job bodies via `PythonTranspiler`, timeout/retry/DLQ from config. For Python on Docker, `ComposeBuilder` (`datrix_codegen_docker.generators.compose.compose_builder`) adds a `<compose-service>-worker` that runs `python -m <package>.jobs.scheduler` (no HTTP port, shared env/infra deps).

- **Alembic initial schema** (Stable) — `MigrationGenerator` (`datrix_codegen_python.generators.persistence.migration_generator`) emits per-RDBMS-block Alembic trees and `0001_initial_schema.py` with explicit `op.create_table()` / column DDL from `OrmTypeResolver` and `build_initial_migration_context` (`_migration_schema.py`); table creation order is topologically sorted from foreign keys. When `schema` is configured on the RDBMS block, migrations include `CREATE SCHEMA IF NOT EXISTS`, pass `schema=` to all DDL operations, and scope the Alembic version table to the service schema.

- **Seed data** (Stable) — Optional `config/seed-data.yaml` in the generated service tree is read by `SeedGenerator` (`datrix_codegen_python.generators.persistence.seed_generator`), which emits `seed.py` and packaged `seed_data.yaml` with PostgreSQL idempotent inserts (`ON CONFLICT … DO NOTHING`).

- **Elasticsearch (config-driven)** (Stable) — When `IntegrationsProfileConfig.search` targets Elasticsearch and the service has `:searchable` fields, `IntegrationGenerator` (`datrix_codegen_python.generators.cross_cutting.integration_generator`) emits search client code, index mapping, and sync helpers. `datrix-codegen-docker` adds Elasticsearch infrastructure services, wires `ELASTICSEARCH_HOST` / `ELASTICSEARCH_PORT`, and optional `*-search-index-init` containers (see `datrix_codegen_docker.generators.compose._compose_wiring`). This is the **config-driven** search integration path (no DSL `search` block required). See also [Search engine integration](#search-engine-integration) for the DSL-level `search` block.

### Phase 02 capabilities (Stable) (Python, Docker, docs)

Cross-cutting behavior described here matches the **current** generators; see [code-generation.md](../../../../datrix-common/docs/architecture/code-generation.md) for pipeline detail.

- **Inter-service internal HTTP auth** (Stable) — Services that expose `INTERNAL` REST endpoints (and services that depend on them) receive `INTERNAL_API_TOKEN` in Docker Compose and root `.env.example`. Generated Python clients read `os.environ["INTERNAL_API_TOKEN"]` and send `X-Internal-Token` on outbound calls to those routes. This is a **shared secret** checked by string equality at runtime, not a JWT and not per-service cryptographic identity.

- **Typed, named inter-service calls** (Planned) — A cross-service call is a typed RPC against the provider's endpoint contract, not a stringly-typed HTTP request. **Cross-service callability is bound to `access(Service)`:** a custom endpoint is callable from a peer if and only if it is marked `access(Service)`, and a service-facing custom endpoint **must** carry a name (declared after the HTTP method, like a function name). External-facing endpoints (`public`, `access(authenticated)`, role-gated) carry no cross-service name and cannot be invoked as an RPC — so a peer can never reach a user-facing endpoint and bypass its end-user authorization context. The cross-service identity is `(HTTP method, name)`; callers invoke a custom endpoint as `Service.Block.<method>.<name>(args)` (e.g. `ProductService.ProductAPI.get.productBySku(sku)`) and a resource (auto-CRUD) endpoint as `Service.Block.<db>.<Entity>.<op>(args)`, with typed arguments and **no route string**. Endpoint identity is a stable contract; the `@path`/URL is a deployment detail that can change without breaking callers. The call's static type is the provider's declared return type, surfaced in the caller as a generated, validated **response struct** (only `-> JSON` endpoints stay untyped). The string-path, interpolated-path, and pathless positional call forms are removed.

  A **cross-service endpoint contract registry**, keyed by endpoint identity rather than route, is built at generation time as a **complete, consistent, content-pinned snapshot** of every transitive `uses`/discovery dependency, and is consumed identically by validation and codegen. A declared dependency whose contract is absent from the snapshot is reported as a distinct, actionable diagnostic ("regenerate the dependency first"), never confused with a genuinely-missing endpoint; resolution never binds against a stale provider revision. `Microservice.with*` combinators remain a legitimate escape hatch for genuinely dynamic, non-endpoint HTTP — they are no longer the way to call a declared dependency endpoint.

- **Dependency resilience policy** (Planned) — Resilience is a property of the dependency, declared once and applied everywhere; the generator never synthesizes values and never auto-classifies operations. A `dependencyPolicy` section under `resilience` declares, per dependency kind (`cache`, `rdbms`, `pubsub`, `objectStorage`, `service`, `extern`), availability, health severity, and operation-level `onFailure` behavior (`raise`/`deny`/`degrade`/`warn`/`fallback`). A safe baseline is authored **once at the application level** (a `defaults` block every dependency of that kind inherits); an individual dependency overrides only where it differs. A policy-managed operation — or a `service` dependency that has inter-service calls — left uncovered at every level is a generation error (`RESILIENCE_POLICY_REQUIRED`); nothing is invented to fill the gap, and degradation applies only where the author declared it and the operation semantics permit (e.g. a cache write degrades only when known to run after the source-of-truth commit; a rate-limit counter does not fail open by default). Every typed inter-service call routes through a generated **per-dependency resilient client** driven by this policy: timeout, circuit breaker, and bulkhead are non-amplifying and stay on, while **retry is off by default** and enabled only when the provider endpoint is marked `idempotent` (HTTP `GET` is not a safe proxy for idempotency), bounded by a retry budget and suppressed while the breaker is open.

- **User-facing JWT (gateway apps)** (Stable) — When gateway JWT settings are present in project config, Compose emits `JWT_SECRET`, `JWT_ALGORITHM`, and `JWT_EXPIRY` into service environments (see `datrix_codegen_docker.generators.compose.compose_builder`). Python gateway generation (`datrix_codegen_python.generators.api.gateway_generator`) emits JWT verification aligned with those settings.

- **Config-driven operational settings** (Stable) — Service and project YAML profiles resolve to typed Pydantic models attached to the AST; Docker and Python generators consume those models (ports, health checks, resources, jobs, etc.) instead of hardcoding production values. `.env.example` documents variables the stack expects.

- **Entity lifecycle hooks** (Stable) — `beforeCreate` / `afterCreate` / etc. on entities are transpiled in the Python service layer (`datrix_codegen_python.generators.service.service_generator` and related templates) and invoked around persistence operations as defined in the DSL.

- **Multi-service NGINX gateway** (Stable) — For applications with more than one service, `datrix_codegen_docker.generators.config.gateway_generator` renders `config/nginx/nginx.conf` via `nginx.conf.j2`: one **upstream** per service, **location** blocks for public REST paths (including each `rest_api` **base_path** prefix), **GraphQL** `graphql_api` base paths (with WebSocket upgrade headers when the API has subscriptions), **health** aliases derived from the primary REST `base_path` plus `service.config.health_check.path` when a primary REST API exists (with `GenerationError` on duplicate external health paths), **403** for versioned paths matching internal REST segments (`INTERNAL_PATH_DENY_REGEX` in the gateway module), **CORS OPTIONS** handling and **proxy timeouts** on proxied locations, and **`client_max_body_size`** on routes for services that declare **storage** blocks. Rate limit zones from `@rateLimit` on endpoints are preserved. If an upstream has **no** matching locations, generation raises `GenerationError` listing that upstream (instead of emitting a broken config). Test-only multi-service fixtures use `attach_config_for_docker` / `ensure_minimal_rest_api_for_multi_service_gateway` in `datrix_codegen_docker.test_helpers` to add minimal `rest_api` stubs when the parsed `.dtrx` omits API blocks.

- **Liveness / readiness / health split** (Planned) — Generated services expose three distinct probes instead of a single conflated `/health`: **`/live`** (process liveness only), **`/ready`** (all `required` dependencies usable — returns 503 when a required dependency is down), and **`/health`** (detailed per-dependency report, including `degraded` optional dependencies). A dependency declared `health = "degraded"` keeps `/ready` green while `/health` reports `degraded`, unless a per-dependency `readyOnDegraded = false` makes it a readiness blocker for guarded rollouts. Deployment probes (Docker healthcheck, K8s liveness/readiness/startup) point at `/ready`; the prior single-`/health` contract is replaced outright, with no backward-compat fields.

### Phase 03 capabilities (Stable) (Python, Docker)

- **GraphQL DataLoaders** (Stable) — `GraphqlResolverGenerator` (`datrix_codegen_python.generators.api.graphql_resolver_generator`) emits Strawberry DataLoader wiring and batch resolvers from DSL definitions so related fields load in grouped queries instead of per-row round-trips.

- **Rate limiting** (Stable) — A unified plan-based system requiring a Redis/Valkey-backed cache block:

  **Plan-based rate limiting** (`RateLimitGenerator` in `datrix_codegen_python.generators.cross_cutting.rate_limit_generator`) — Automatically generated for any service with REST or GraphQL APIs plus a Redis-backed cache. Emits `rate_limit/` package: `rate_limit_config.py` (baked plan tiers: RPM sliding window + daily quota + per-endpoint overrides), `rate_limiter.py` (Redis sorted-set implementation), `rate_limit_dependency.py` (FastAPI dependency `enforce_plan_rate_limit` wired at router level; GraphQL variant `enforce_plan_rate_limit_graphql` called in context getter). Client identification uses JWT `sub` claim → `x-forwarded-for` → IP fallback. Plan ID extracted from JWT claims. Emits standard headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`.

  **Per-endpoint overrides** — When endpoints use `@rateLimit(requests=N, window=S)` in the DSL, the decorator values are collected by `collect_endpoint_rate_limit_overrides` and baked into `ENDPOINT_OVERRIDES` in `rate_limit_config.py`. At runtime, `enforce_plan_rate_limit` checks overrides before applying plan RPM: if the request matches an override, the endpoint-specific requests/window constraint applies instead of the plan RPM (daily quota still applies). All rate limiting flows through a single path using consistent JWT-aware client identification.

  **`DISABLE_RATE_LIMIT` env var** (values `1`, `true`, `yes`) — early return before Redis access, enabling tests to run without Redis infrastructure. Raises 503 when Redis is unavailable and rate limiting is not disabled.

- **RFC 7807 error envelope** (Stable) — `ProjectGenerator._generate_error_modules` renders `api/error_response.py.j2` and `api/error_handlers.py.j2`; `main.py.j2` calls `register_error_handlers(app)` so API errors return a shared `ErrorResponse` / `FieldError` model (Problem Details fields: `type`, `title`, `status`, `detail`, `instance`, optional `errors`).

- **Prometheus application metrics** (Stable) — Before sub-generators run, `PythonGenerator` sets the Jinja global `has_prometheus_metrics` from the resolved observability profile. When true, generated **RDBMS** `connection.py` modules expose `sqlalchemy_pool_*` gauges (pool listeners), **Redis cache** access increments `redis_cache_hits_total` / `redis_cache_misses_total`, and **jobs** `runner.py` records `job_runs_total`, `job_failures_total`, and `job_duration_seconds` (see `metrics_middleware.py.j2` for HTTP counters/histograms as before).

- **Docker monitoring stack** (Stable) — With `observability.metrics` (Prometheus) and `observability.visualization` (Grafana), `datrix-codegen-docker` adds **cAdvisor** next to Prometheus, scrapes it from `prometheus.yml.j2`, writes **per-compose-service Grafana dashboards** plus a **multi-service overview** (`datrix-system-overview.json`) via the shared `DashboardBuilder` in `datrix_codegen_common.dashboards.builder` (delegated through a thin wrapper in `datrix_codegen_docker.generators.infra.dashboard_builder`), and emits **per-service alert files** under `config/prometheus/` (standard rules: `HighErrorRate`, `HighLatency`, optional pool/cache/job rules from service features, plus a **DSL** group when blocks declare alerts). Grafana dashboards require metrics; missing metrics with visualization enabled raises `GenerationError` at generation time. Dashboard panels are organized into row groups (HTTP, RDBMS, Cache, Jobs, Pubsub, CQRS, Storage, DSL Alerts, Container Resources) and include Grafana template variables (`$service`, `$interval`) for runtime filtering. Dashboard row visibility is user-configurable via `visualization.dashboards.rows` in the observability config.

- **Kubernetes Grafana dashboards** (Stable) — With `observability.metrics` (Prometheus) and `observability.visualization` (Grafana), `datrix-codegen-k8s` emits sidecar-discoverable Grafana dashboard **ConfigMaps** with a configurable selector label (default: `grafana_dashboard: "1"`). Dashboard JSON is generated by the shared `DashboardBuilder` in `datrix_codegen_common.dashboards.builder`. K8s dashboards include pod resource panels (CPU, memory, restarts from kubelet/kube-state-metrics) and a `$namespace` template variable. Kubernetes does not deploy Grafana itself — clusters provide Grafana through kube-prometheus-stack or equivalent.

- **AWS CloudWatch dashboards** (Stable) — With `observability.visualization` (`cloudwatch`) and `observability.metrics` (`cloudwatch`), `datrix-codegen-aws` emits `AWS::CloudWatch::Dashboard` CloudFormation resources per service with infrastructure widgets (ECS, RDS, ElastiCache, SQS, SNS, ALB) and application metric widgets from the `Datrix/Application` CloudWatch namespace. Provider pairing is strict: `cloudwatch` visualization requires `cloudwatch` metrics. Managed Grafana (`visualization.managed: true`) provisions an `AWS::Grafana::Workspace` with AMP datasource and Grafana dashboard JSON.

- **Azure Monitor workbooks** (Stable) — With `observability.visualization` (`azure-monitor`) and `observability.metrics` (`azure-monitor`), `datrix-codegen-azure` emits `Microsoft.Insights/workbooks` Bicep resources per service with infrastructure steps (Container Apps, Flexible Server, Redis, Service Bus, Event Hubs) and application metric steps from Azure Monitor. Provider pairing is strict: `azure-monitor` visualization requires `azure-monitor` metrics. Managed Grafana (`visualization.managed: true`) provisions a `Microsoft.Dashboard/grafana` resource with Prometheus-compatible datasource.

### Search engine integration (Stable)

Datrix supports full-text search through two paths: **config-driven** (existing, via `IntegrationsProfileConfig.search`) and **DSL-level** (via `search` blocks in services and shared containers).

**DSL-level `search` block** — Declares search indexes with field mappings, analyzers, boost weights, facet/sortable flags, and entity sync rules directly in `.dtrx` files:

```datrix
service CatalogService {
    rdbms db('config/rdbms.dcfg') {
        entity Product { ... }
    }
    search es('config/search.dcfg') {
        index ProductSearch syncs Product {
            field name : text, boost(3.0), analyzer("standard")
            field description : text, boost(1.0), analyzer("english")
            field category : keyword, facet
            field price : float, sortable
        }
        analyzer autocomplete {
            tokenizer: edge_ngram(minGram: 2, maxGram: 20)
            filter: [lowercase]
        }
    }
}
```

**Multi-platform code generation:**

| Platform | Status | Search Service | Client Library |
|----------|--------|---------------|----------------|
| Docker Compose | Stable | Elasticsearch container + init container | `elasticsearch` / `@elastic/elasticsearch` |
| Kubernetes | Stable | Elasticsearch StatefulSet + headless Service + init Job | `elasticsearch` / `@elastic/elasticsearch` |
| AWS | Stable | Amazon OpenSearch Service domain (CDK) | `elasticsearch` / `@elastic/elasticsearch` (wire-compatible) |
| Azure | Stable | Azure AI Search (Bicep) | `azure-search-documents` / `@azure/search-documents` |

**Platform-variant code generation:** Docker, K8s, and AWS targets are Elasticsearch-compatible and share the same generated client code. Azure AI Search has a different API surface, so the language code generators produce platform-variant search integration code: separate templates for index init, search client, and sync handlers. The variant is selected based on the target platform in `CodegenContext`.

**Azure AI Search type mapping:** Elasticsearch field types, analyzers, and boost weights are translated to Azure AI Search equivalents. `boost` values become scoring profiles (an index-level construct). Language-specific analyzers map to `.lucene` variants (e.g., `"english"` → `"en.lucene"`). The mapping is exhaustive and fails fast on unsupported types.

**`fulltext()` entity modifier** remains for database-native full-text indexes (PostgreSQL GIN / MySQL FULLTEXT). The `search` block targets external search engines with relevance scoring, faceted search, autocomplete, and multi-entity indexes — a different performance tier.

### ArcGIS FeatureServer Integration (Planned)

Datrix supports first-class ArcGIS FeatureServer paged ingestion through the `arcgisFeatureLayer` integration kind. This replaces ad-hoc HTTP API client usage for ArcGIS FeatureServer layers with a target-neutral contract that generates pagination, geometry normalization, checksum computation, and archive handling.

**Config shape (`.dcfg`):**

```dcfg
integrations layerName {
    kind = "arcgisFeatureLayer";
    baseUrl = "https://services2.arcgis.com/.../FeatureServer/0";
    objectIdField = "OBJECTID";
    outSR = 4326;
    pageSize = 1000;
    where = "1=1";
    archiveMode = "changed";
    outFields = ["OBJECTID", "NAME", "STATUS"];
    rateLimit { requestsPerSecond = 2.0; burstAllowed = 5; backoffStrategy = "exponential"; }
    retry { maxAttempts = 3; initialDelayMs = 1000; maxDelayMs = 10000; retryOn = [429, 500, 502, 503, 504]; }
    timeout { connectMs = 10000; readMs = 60000; }
}
```

**Config model:** `ArcGisFeatureLayerIntegrationConfig` in `datrix_common.config.integrations.models` with fields: `kind` (literal `"arcgisFeatureLayer"`), `base_url`, `object_id_field` (optional), `out_sr` (default 4326), `page_size` (optional positive int), `where` (default `"1=1"`), `out_fields` (required non-empty list), `watermark_field` (optional), `archive_mode` (enum: `manifest | changed | full | failureOnly`, default `changed`), `geometry` (default `true`), plus shared `rate_limit`, `retry`, `timeout`, `monitoring`.

**Runtime query contract:** Generated code performs: (1) metadata fetch (`GET {baseUrl}?f=json` for `maxRecordCount` and `objectIdField`), (2) paged `/query` calls with `resultOffset`/`resultRecordCount`, `orderByFields=<objectIdField> ASC`, and explicit field list, (3) stop when no features or `exceededTransferLimit` is false with fewer results than page size, (4) per-feature attribute normalization, geometry conversion (ArcGIS polyline to GeoJSON), SHA-256 checksum computation from canonical JSON, and (5) idempotent upsert of changed features using stable source key.

**Refresh modes:** `incremental` (checksum comparison baseline, optional watermark narrowing) and `reconcile` (full layer scan, stale record detection).

**Archive modes:** `manifest` (run metadata only), `changed` (manifest + changed/failed records, default), `full` (manifest + all fetched pages), `failureOnly` (manifest + failed records on error).

**Multi-language lowering:** Python and TypeScript generators emit target-native ArcGIS client modules under `integrations/` with: httpx/fetch-based HTTP client, retry/rate-limit settings, metadata request, page iteration, geometry normalization, and checksum generation. No ArcGIS SDK dependency — generated code uses standard HTTP clients.

**Failure behavior:** ArcGIS response errors, missing object ID metadata, missing feature arrays, or repeated page cursors fail the ingestion run. Silent partial refresh is invalid.

### Notification Infrastructure Provisioning

Generated services call notification builtins (`Email.send`, `SMS.send`, `Push.send`) and the language generators emit provider-specific helpers; the cloud/runtime generators provision the backing provider resources from the same resolved `integrations` profile — no new application DSL syntax. Provisioning is keyed on the pair `(provider, DeploymentProvider)`, resolved through total frozen dispatch tables in `datrix_common.config.integrations.provisioning`. Each `(channel, provider, DeploymentProvider)` cell resolves to exactly one realization class: `PROVISION` (Datrix owns the resource — SES identity, SNS platform application, ACS, Notification Hub, Mailpit — plus scoped IAM/role and env wiring), `SECRET_REF` (Secrets Manager / Key Vault placeholder reference + env wiring, no provider resource), or `UNSUPPORTED` (generation fails loud with `GenerationError` in the `resolve_infrastructure_configs` stage, before any generator runs). The dispatch-table shape mirrors `PROVIDER_GENERATORS` (single deterministic value per key), not `*_ENGINES_BY_FLAVOR`. Coverage: AWS SES/SNS-SMS/SNS-push, Azure Communication Services (`acs` email/SMS) and Notification Hubs (`azure-notification-hubs` push), and local Mailpit SMTP capture for Docker (any `smtp` service) and Kubernetes (`LOCAL` + `smtp` service). Credential hygiene is centralized on `datrix_common.config.secret_hygiene.looks_like_raw_secret` at config-validation time — raw secret literals are rejected; `env("...")` references and `credentialSecretName` are accepted; no generator emits a raw credential. Full reference: [notification-provisioning.md](../../../../datrix-common/docs/integrations/notification-provisioning.md).

### CDN / Content Delivery (Beta)

Datrix supports CDN configuration through `cdn` blocks in services and shared containers. A `cdn` block declares a CDN distribution with named origins, cache behaviors, and optional custom domains.

**DSL syntax:**

```datrix
service frontend.WebService : version('1.0.0') {
    storage mediaStore('config/storage.dcfg') {
        bucket StaticAssets { ... }
        bucket UserUploads { ... }
    }
    rest_api WebAPI : basePath('/api/v1') { ... }

    cdn WebCDN('config/cdn.dcfg') {
        origin StaticAssets {
            source: mediaStore.StaticAssets
            cacheTtl: 86400
            pathPattern: '/static/*'
        }
        origin UserMedia {
            source: mediaStore.UserUploads
            cacheTtl: 3600
            pathPattern: '/media/*'
        }
        origin API {
            source: WebAPI
            cacheTtl: 60
            pathPattern: '/api/*'
            forwardHeaders: ['Authorization']
            forwardQueryStrings: true
        }
        defaultOrigin: API
        customDomain: 'cdn.example.com'
    }
}
```

**Multi-platform code generation:**

| Platform | Status | CDN Service | Generated Artifacts |
|----------|--------|-------------|---------------------|
| Docker Compose | Stable | Varnish cache proxy (simulates edge caching) | Varnish container + VCL configuration |
| Kubernetes | Stable | Ingress annotations (origin-compatible headers) | CDN-origin Ingress with CORS and cache-control annotations |
| AWS | Stable | CloudFront distribution with OAC | CDK/CloudFormation: distribution, behaviors, OAC, optional ACM certificate |
| Azure | Planned | Azure Front Door profile | Bicep: profile, endpoints, origin groups, routes, cache configuration |

**Cache invalidation utilities:** When CDN is configured on AWS or Azure, language code generators (Python, TypeScript) emit platform-specific cache invalidation helper modules.

**Origin types:** CDN origins can reference `storage` bucket sources (S3, Blob Storage) or `rest_api` endpoints (ALB, Container Apps). Each origin specifies its own cache TTL, path pattern, and header forwarding rules.

**Custom domains and SSL:** When `customDomain` is set in CDN config, the platform generators provision SSL certificates automatically — ACM certificates in `us-east-1` for CloudFront (with DNS validation), or Front Door managed certificates for Azure.

### Serverless Block Code Generation (Stable)

Datrix supports serverless deployment of handler logic through `serverless` blocks declared inside services. A serverless block groups four member types — subscriptions, jobs, endpoints, and enqueue consumers — into independently deployable serverless functions. The serverless block determines deployment target; member types reuse the same AST types as service-level handlers.

**DSL syntax:**

```datrix
service examples.OrderService('config/order-service.dcfg') {
    rdbms db('config/rdbms.dcfg') { ... }
    pubsub mq('config/pubsub.dcfg') { ... }

    serverless eventHandlers {
        subscribe mq.OrderEvents {
            on OrderPlaced(UUID orderId, Decimal amount) { ... }
            on OrderCancelled(UUID orderId) { ... }
        }

        @path('/webhooks/stripe')
        @name('StripeWebhook')
        post(JSON payload) -> Void { ... }
    }

    serverless scheduledTasks {
        job DailyOrderReport { ... }
    }

    serverless queueWorkers {
        enqueue examples.OrderService.ProcessShipment(UUID orderId) { ... }
    }
}
```

**One function per executable handler (D1):** Each executable handler becomes an independently deployable unit with its own timeout, memory, and concurrency settings. Handler identity is normalized to `snake_case` from the handler's name, `@name` decorator, or structural identity. Collision validation rejects duplicate identities within a block (SLS004).

**Two-layer generation (D2):** Application-layer generators produce two artifacts per handler: (a) a platform-agnostic business logic handler module, and (b) a platform-specific entry point adapter (Lambda handler, Azure Functions `__init__.py` + `function.json`, or container runner). The handler module is identical across platforms.

**Generated file layout (Python, `platform=lambda`):**
```
{service_root}/serverless/{block_snake}/
    handlers/
        {handler_snake}.py          # Business logic (platform-agnostic)
    lambda_adapters/
        {handler_snake}.py          # AWS Lambda entry point
```

**Config resolution chain (D3):** Schedule and retry resolve from `service.config.jobs.jobs[job_name]` (shared jobs config). Platform execution settings (timeout, memory, concurrency, plan_sku, runtime_version) resolve from `ServerlessProfileConfig.defaults` plus per-handler overrides in `ServerlessProfileConfig.handlers`. Missing job schedule config fails generation with a diagnostic (SLS006).

**Shared ServerlessBlockPlan (D6):** A frozen `ServerlessBlockPlan` context model in `datrix-codegen-common` is computed once from the resolved `ServerlessBlock` + `ServerlessProfileConfig`. All infrastructure generators consume this plan rather than independently parsing AST + config.

**ServerlessOrchestrator (D9):** `ServerlessOrchestrator(DomainOrchestrator)` owns all handler modules and adapters for members inside `ServerlessBlock`, including jobs. `JobsOrchestrator` handles only service-level/in-process jobs.

**Multi-platform infrastructure generation:**

| Platform | Status | Compute Resource | Trigger Resources |
|----------|--------|-----------------|-------------------|
| AWS | Stable | Lambda functions (CDK) | API Gateway HTTP API, EventBridge Scheduler, SNS/SQS triggers |
| Azure | Stable | Function App (Bicep) | HTTP trigger, Timer trigger, Service Bus/Event Grid triggers |
| Docker Compose | Stable | Separate container services | APScheduler, uvicorn, consumer loops |
| Kubernetes | Stable | CronJob, Deployment + Service | Schedule, consumer process, HTTP server |
| Component | Stable | (support metadata only) | Env vars, README documentation |

**Platform compatibility (D8):** `ServerlessProfileConfig.platform` determines the programming model: `lambda` (AWS only), `functions` (Azure only), `container` (all providers). Incompatible platform/provider combinations fail generation before partial artifacts are rendered.

**Semantic validation rules:**
- SLS004: Handler identity uniqueness across executable handlers within a block
- SLS005: Handler config references validate against actual handler identities
- SLS006: Job inside serverless block requires schedule config entry
- SLS007: Shared-owned serverless blocks are rejected

**Service-owned only (D7):** Serverless blocks are generated only when declared inside a service. Shared containers do not own deployable serverless blocks.

### Replayable Ingestion — Storage-as-System-of-Record (Planned)

Datrix supports an ingestion pattern that decouples *acquiring* records from *loading* them into a database, so a table can be rebuilt at any time without re-fetching from the external source (which may have mutated or disappeared). Normalized record batches are archived to object storage — the **system-of-record** — and the database is filled by consuming **claim-check** events: each event carries a small typed pointer (`StorageRef`) to the archived batch, never the bytes. Rebuild is a generated **replay** operator that re-publishes a topic's archived batches from storage; consumers reprocess and rebuild the database with zero external fetch. Because durability lives in storage, rebuild does not depend on broker retention.

**DSL syntax (storage-backed, replayable topic):**

```datrix
storage catalogArchive {
    folder raw      : path('raw/');         // source payloads
    folder batches  : path('batches/');     // normalized record batches (system-of-record)
}

pubsub feedBus {
    // `source(folder)` binds the backing storage; `replayable` generates the replay operator.
    topic CatalogFeed : source(catalogArchive.batches), replayable {
        publish ProductBatchPublished(
            StorageRef batch,          // typed claim-check pointer (builtin value struct)
            Int recordCount,
            String schemaVersion,
            DateTime sourceUpdatedAt
        );
    }
}
```

**`StorageRef` (builtin value struct):** `{ String folder; String key; Int size; String contentType; String? checksum }` — the only value a claim-check event needs to locate its batch.

**Storage is the system-of-record; Kafka is transport (D39).** The durable artifact is the normalized batch in object storage; the broker carries only pointers and need not retain anything for rebuild.

**Claim-check, not fat events (D40).** Bulk batches exceed sane broker message sizes and would bloat the log; the bytes stay in storage, which is the system-of-record anyway, so there is one copy.

**Topic↔storage binding is declarative (D41).** A replayable topic declares `source(folder)`; generic, generated replay needs to know the backing folder and object→event mapping rather than inferring it.

**Event envelope persisted as object metadata (D42).** The producer stamps the event's fields onto the archived object via `set_metadata`; replay reconstructs events from `get_metadata` — one source of truth, no separate manifest store.

**Consumers of replayable topics must be idempotent (D43).** The dedup key is declared explicitly: the target entity marks its idempotency key with the `replayKey` field modifier (e.g. `String sku : unique, replayKey;`). Enforced at generation — a replayable-topic consumer must `.upsert` into a `replayKey` entity; a `.create()`, or a target entity without `replayKey`, fails generation with a diagnostic. Replay re-delivers, so idempotency is structural and declarative, not a runtime dedup.

**Replay is an operator-triggered endpoint plus optional backfill job (D44).** `replayable` synthesizes a `replay{Topic}(range)` operator endpoint onto the owning service; `replay schedule("…")` additionally synthesizes a cron backfill job. Both are ordinary service nodes, so every platform generator (AWS/Azure/Docker/K8s) deploys them without special-casing. Replay is range-scoped by key prefix and/or timestamp window.

**Schema version is stamped per batch; cross-version replay fails fast (D45).** A consumer replaying an unsupported `schemaVersion` errors rather than coercing old records.

**I/O stays explicit (D46).** `upload`/`download` remain explicit in handler bodies; the framework adds the typed `StorageRef`, the binding, replay synthesis, and the idempotency check — not hidden I/O.

**Accumulate-only; deletion is deliberate and audited (D47).** The store and database never auto-delete and never propagate source deletions — a record the source drops is retained (historical value). The sole deletion path is an explicit operator `purge{Topic}(selector)` — by key, time-range, or full — that deletes the matching DB rows and storage data together, records the purge in a durable exclusion log that **replay honors** (so a purge is never undone by a later replay), and writes an audit record. Erasure is both logical (immediate: DB delete + exclusion entry) and physical (eventual: range/full delete whole objects; key-level compaction rewrites objects to remove the bytes). Storage stays append-only except via this audited purge path.

**Reuses existing primitives:** the ten storage operations (`upload`/`download`/`list`/`exists`/`delete`/`copy`/`move`/`get_metadata`/`set_metadata`), the transactional outbox (`defer_event`/`outbox_active`), consumer DB-session injection, and the jobs/APScheduler path. The only generated additions are the storage-backed producer branch, the replay endpoint/job bodies, and the `StorageRef` schema.

### Managed API Gateway (Stable)

Datrix supports managed API gateway infrastructure through a `gateway` block at the application level and a unified `gateway.yaml` configuration. When `type: managed` (cloud only), the AWS and Azure generators emit cloud-managed API gateway resources with throttling, API keys, usage plans, request validation, response caching, WAF integration, and custom domain/TLS management.

**DSL syntax (application-level `gateway` block):**

```datrix
application ecommerce.Ecommerce {
    gateway : type('managed') {
        throttle(1000, 2000);       // 1000 steady-state, 2000 burst per second

        apiKeys {
            plan BasicPlan : rateLimit(100, 'hour'), quota(1000, 'day');
            plan ProPlan : rateLimit(1000, 'hour'), quota(50000, 'day');
            plan EnterprisePlan : rateLimit(10000, 'hour'), quota(unlimited);
        }

        cache(ttl: 300);            // 300 seconds default TTL
        waf : enabled;
        domain('api.ecommerce-app.com');
    }

    service ecommerce.UserService { ... }
    service ecommerce.OrderService { ... }
}
```

Gateway configuration can also be specified entirely in `gateway.yaml` (profile-based, as with other config files) for users who prefer YAML over DSL-level gateway config. The `type` field in `GatewayProfileConfig` determines the gateway infrastructure: `nginx` (default; the only self-hosted gateway, used by Docker and Kubernetes) or `managed` (cloud-only: AWS API Gateway / Azure APIM).

**Multi-platform code generation:**

| Platform | Status | Gateway Service | Generated Artifacts |
|----------|--------|----------------|---------------------|
| Docker Compose | Stable | NGINX reverse proxy when `type: nginx` (`managed` is cloud-only and rejected) | NGINX container + reverse-proxy config with rate limiting |
| Kubernetes | Stable | NGINX Ingress controller when `type: nginx` (`managed` is cloud-only and rejected) | Annotated Ingress resources |
| AWS | Stable | API Gateway REST API (full-featured) or HTTP API (throttling-only) | CDK/CloudFormation: REST API with usage plans, API keys, caching, VPC Link + NLB for ECS integration |
| Azure | Stable | Azure API Management (APIM) | Bicep: APIM service, per-service APIs, products (usage plans), XML rate-limiting/quota policies |

**AWS auto-selection:** The AWS generator uses REST API when any advanced feature is enabled (`apiKeys`, `cache`, `waf`) and HTTP API otherwise. REST API supports usage plans, API keys, request validation, response caching, and WAF association. HTTP API provides lower latency and cost for simple throttling and routing.

**VPC Link for private integration:** On AWS, API Gateway communicates with ECS services through a VPC Link connected to a Network Load Balancer (NLB). The generator creates an NLB when API Gateway is used: API Gateway → VPC Link → NLB → ECS Target Groups.

**WAF integration:** When `waf.enabled: true`, the AWS generator provisions a WAF Web ACL with `AWSManagedRulesCommonRuleSet` (general protection) and `AWSManagedRulesSQLiRuleSet` (SQL injection) managed rule groups, and associates it with the API Gateway stage.

**Application-level awareness:** When behind a managed gateway, language generators (Python, TypeScript) emit trusted-proxy middleware so services correctly handle `X-Forwarded-For` and API key headers injected by the gateway. Application-level API key validation is omitted when gateway-level API key enforcement is enabled.

**Backward compatibility with NGINX:** When `type: nginx` (or no gateway type specified), the existing NGINX generation path in `datrix-codegen-docker` runs unchanged. The managed gateway is opt-in.

### Geo Spatial Operations (Stable)

Datrix supports spatial types and PostGIS spatial queries through the `geo` extension. The `geo` extension separates concerns across three namespaces: `Geo.*` (standard library coordinate math, always available), `GeoShape.*` (value-level shape operations, extension required), and `GeoSql.*` (SQL query expressions lowered to PostGIS, extension required).

**DSL syntax:**

```datrix
system ecommerce.System : version('1.0.0') {
    use extension geo;
}

service ecommerce.WarehouseService('config/warehouse.dcfg') {
    rdbms db('config/rdbms.dcfg') {
        entity Warehouse {
            Text name
            Geometry boundary
            Geometry centerPoint
        }
    }
    rest_api WarehouseAPI : basePath('/api/v1') {
        get nearbyWarehouses(Number lat, Number lng, Number radiusNm) -> Warehouse[] {
            return Warehouse
                .where(GeoSql.withinDistanceNm(centerPoint, lat, lng, radiusNm))
                .orderBy(GeoSql.distanceNm(centerPoint, lat, lng))
                .all();
        }
    }
}
```

**Key features:**

- **Spatial types:** `Geometry` (WKT) and `Geography` (EWKT) with SRID 4326, mapped to GeoAlchemy2 columns for Python and `geometry`/`geography` DDL for SQL
- **Automatic GiST indexes:** Every `Geometry` / `Geography` entity field receives a `USING GIST` index automatically
- **GeoSql SQL lowering:** `GeoSql.*` predicates and scalar expressions lower to PostGIS functions (`ST_Contains`, `ST_DWithin`, `ST_Distance`, `ST_Area`, `ST_Centroid`) with geodetic semantics
- **GeoShape value-level ops:** `GeoShape.*` provides Shapely-backed (Python) and Turf.js-backed (TypeScript) runtime geometry operations (containsPoint, area, centroid, WKT/GeoJSON conversion)
- **Semantic validation:** `Geometry`, `Geography`, `GeoShape`, and `GeoSql` require `use extension postgis;`; `GeoSql.*` is valid only in entity query expression contexts
- **Per-service dependency detection:** Geo dependencies (GeoAlchemy2, Shapely, PostGIS, Turf.js) are added only to services that actually use geo features
- **OpenAPI format metadata:** `format: wkt` for `Geometry`, `format: ewkt` for `Geography`

See the [PostGIS extension reference](../../../../datrix-extensions/docs/postgis-extension.md) for the full namespace contract, type mappings, and SQL lowering details. For raster/tile operations, see the [geo raster extension reference](../../../../datrix-extensions/docs/geo-raster-extension.md).

### Infrastructure Resource Pooling — Shared Provisioned Resources With Per-Service Isolation (Planned)

Datrix generates **one provisioned managed resource per infrastructure block** on every platform. For systems with many bounded-context services, this multiplies the fixed per-instance base cost — a system with 43 `rdbms` blocks generates 43 provisioned servers; 38 `pubsub` blocks generate 38 namespaces.

**Pooling is opt-in.** Several infra blocks across services can share one provisioned resource while maintaining **logical isolation** — each child block gets its own connection secret, RBAC/IAM scope, migration identity, and observability tags. Blocks without a group declaration continue to use the existing dedicated-per-block path and output is unchanged (byte-for-byte identical on all six generators).

**Explicit group declaration via `.dcfg`:** Pooling is authoring via `serverGroup` / `namespaceGroup` fields on RDBMS and PubSub blocks, plus `serverGroups{}` / `namespaceGroups{}` sizing blocks in the system `.dcfg`:

```dcfg
// Service config
rdbms ordersDb {
    engine = "postgres"
    platform = "rds"
    serverGroup = "orders-pool"
}

// System config
serverGroups {
    orders-pool {
        sku = "db.t3.medium"
        storageGb = 100
    }
}
```

**Platform-neutral contract:** `PooledGroup` / `PooledMember` in `datrix_codegen_common.pooling.models` is consumed identically by Python/TypeScript × Azure/AWS/Docker/K8s. The contract is platform-agnostic and language-agnostic; every generator receives pre-resolved `list[PooledGroup]` and iterates `group.members` for per-child wiring. Cross-reference: [Pooling Contract Reference](../../../../datrix-codegen-common/docs/pooling-contract.md).

**Profile-scoped identity:** `(group_name, profile)` is the shared-resource key; staging and production never share a physical resource. Migration state is target-scoped (`.datrix/rdbms-migrations/<target>/...` per phase-55), and resource identity is resolved per deployment profile during config resolution.

**Per-child isolation is a required output:** Connection secret, RBAC/IAM scope, migration identity, and observability dimensions are emitted by the grouping pre-pass per member, not assumed correct. Validators enforce per-child secret distinctness, per-child RBAC/IAM scope binding, cross-group migration-identity UUID uniqueness, and per-child observability tagging. No shared admin secret; no wildcard grant.

**Docker/K8s reconciliation:** On Docker and Kubernetes, explicit `serverGroup` is authoritative. Ungrouped blocks keep the existing implicit host-based deduplication via `InfraRegistry` (identity unchanged — `InfraIdentity(component_type, engine, host, port)`). Parity is tested: identical resource counts for the same grouped app across Azure/AWS/Docker/K8s (modulo operator-flavor rejection).

**Operator-flavor rejection:** Operator-flavor RDBMS and PubSub blocks cannot join a group (one CR = one single-tenant cluster). Generation raises `GenerationError` naming the offending group and block with a clear message: *"Operator-flavor engine cannot join a server/namespace group; use container flavor or a dedicated (ungrouped) block."*

**Ungrouped byte-identical guarantee (D48):** Ungrouped output is byte-for-byte unchanged on all six generators. The grouping pre-pass is a no-op when no blocks declare a group.

**Design decisions:**
- **D39** — Resource identity is `(group, profile)` — staging and production are separate physical resources
- **D40** — Per-child isolation (secret/RBAC/migration/diagnostics) is a required pre-pass output, validator-backed
- **D41** — Membership is a `.dcfg` field (`serverGroup`, `namespaceGroup`) — configuration is configuration; pooling is opt-in via authoring
- **D42** — Operator-flavor engine in a group is rejected, fail loud (no silent CR fan-out, no fallback)
- **D43** — Explicit group governs grouped blocks; ungrouped blocks keep implicit collapse via `InfraRegistry` (backward-compatible, parity-tested)
- **D48** — Ungrouped output is byte-for-byte unchanged on all six generators
- **Capacity validation** — Cross-platform validator rejects undeclared groups, mismatched member engine/flavor/version, profile-missing-from-identity, and operator-flavor-in-group before generation starts

**Cross-reference:**
- [Config System — serverGroup / namespaceGroup fields](../../../../datrix-common/docs/architecture/config-system.md#servergroup--namespacegroup--infrastructure-resource-pooling-fields)
- [Pooling Contract Reference](../../../../datrix-codegen-common/docs/pooling-contract.md) — canonical model documentation, per-generator consumption patterns, InfraRegistry reconciliation, operator-flavor rejection

---

## Managed Identity Provider Integration (Planned)

> **Not yet implemented.** The design is finalized and absorbed; implementation has not begun.

Applications declare managed identity providers in an `identity {}` block. The pipeline connects provider declarations to generated authentication middleware, per-surface authorization contracts, and platform-specific provisioning artifacts.

### DSL Layer

The parser and transformer produce an `IdentityBlock` AST node containing one `ProviderDecl` per named provider. Each `ProviderDecl` carries:

- Provider name and bound config path (`.dcfg` file)
- Identity fields (typed field declarations that become `Auth.identity.*` accessors at runtime)
- Group-to-role mappings (`group "<local>" as <role>`)

Every externally reachable surface must carry an explicit `auth(...)` modifier (modes: `public`, `required`, `optional`, `service`) or a `verify(...)` modifier. Surfaces with neither fail validation (IDN011). Block-level auth defaults may be declared on `rest_api` and `graphql_api` blocks; surface-level `auth(...)` fully replaces (never merges with) the block default.

**Semantic validators:** IDN001–IDN018 (identity block / surface rules), IDC001–IDC003 (config file rules). See [semantic-validators.md](../../../../datrix-common/docs/architecture/semantic-validators.md#identity-validation-idn001idn018).

### Generator Layer

**Provider plan (OR6):** All generators consume a versioned JSON artifact `config/generated/identity-providers.json` (the "provider plan") emitted by the component generator. The plan binds each provider name to its runtime parameters (issuer, JWKS URL, audience, client ID, algorithm allow-list, secret references). Runtime code resolves a provider by issuer, not by name — each surface validates against the provider whose issuer matches the incoming token.

**Per-platform outputs:**

| Platform | Generator | Key outputs |
|----------|-----------|-------------|
| Python / FastAPI | `datrix-codegen-python` | `identity.py` (PyJWT + `PyJWKClient`), `identity_surface.py` guard, `identity_profile.py` service, WebSocket auth, delegation helper |
| TypeScript / NestJS | `datrix-codegen-typescript` | `identity.ts` (`jose`), `identity-surface.guard.ts`, `identity-profile.service.ts`, WebSocket gateway, delegation helper |
| AWS | `datrix-codegen-aws` | Cognito User Pool + per-service app clients, MFA, custom attributes, groups, hosted UI, OR2 AWS secret wiring |
| Azure | `datrix-codegen-azure` | Entra ID / Entra External ID app registration, audience routing, Bicep extension, OR2 Azure Key Vault secret wiring |
| Docker | `datrix-codegen-docker` | Keycloak + backing DB containers, realm import artifact, OR2 Docker secret wiring |
| Kubernetes | `datrix-codegen-k8s` | Keycloak StatefulSet + DB StatefulSet, realm ConfigMap, OR2 K8s secret wiring |
| Component | `datrix-codegen-component` | Provider plan JSON, public-client metadata, identity documentation artifact |

**System entities (OR11):** `IdentityProfile` and `IdentityLink` are reserved entity names injected by the identity planner. `IdentityProfile` stores projected provider identity fields per-user; `IdentityLink` tracks per-provider credential linkage (sub claim, issuer, linked-at timestamp). User-defined entities with these names fail validation.

**Secret provider matrix (OR2):** Provider secrets (client secrets, JWKS signing keys, webhook secrets) are referenced via `ConfigSecretRef` with a `secretProvider` field. Supported providers: `env`, `aws-secrets-manager`, `aws-ssm`, `azure-key-vault`, `k8s-secret`, `docker-secret`.

**Capability matrix (OR14):** `datrix_common/identity/capability_matrix.py` maps each provider type to its supported capability set (MFA, social providers, custom claims, machine audience, etc.). Generators query this matrix to gate feature emission — unsupported capabilities for a given provider type raise a codegen error rather than silently omitting code.

### Provider Type Routing (Azure, OR3)

Azure provider type is determined by `audience` in the provider config:

| Audience | Provider | Notes |
|----------|----------|-------|
| `customer` | Entra External ID | B2C is legacy and not generated |
| `workforce` | Entra ID | Standard workforce / employee auth |
| `machine` | User-assigned managed identity | No human login; service-to-service only |

### Design Reference

Full design decisions (DN1–DN82) and operationalization resolutions (OR1–OR20) are distributed across:

- [datrix-common/docs/architecture/identity.md](../../../../datrix-common/docs/architecture/identity.md) — AuthContract, provider config schema, provider plan (OR6), system entities, capability matrix, secret reference matrix
- [datrix-language/docs/reference/access-levels.md](../../../../datrix-language/docs/reference/access-levels.md) — full `identity {}` / `auth(...)` / `verify(...)` DSL syntax
- [datrix-common/docs/architecture/semantic-validators.md](../../../../datrix-common/docs/architecture/semantic-validators.md#identity-validation-idn001idn018) — IDN001–IDN018, IDC001–IDC003
- Platform-specific docs in each `datrix-codegen-*` repo under `docs/identity-*.md`
