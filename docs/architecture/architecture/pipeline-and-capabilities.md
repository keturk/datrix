# Pipeline Flow & Capabilities

> Part of the architecture documentation. See [../architecture-overview.md](../architecture-overview.md) for the full index.

---

## System Architecture

### Pipeline Flow (Illustrative)

```
.dtrx Source Files
 ↓
┌─────────────────────────────────┐
│ Parser (datrix-language) │
│ - Lexical analysis │
│ - Syntax parsing (Tree-sitter) │
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
│ - Parse YAML config files │
│ - Select active profile │
│ - Validate against schemas │
│ - Attach resolved_config to │
│ AST blocks │
└─────────────────────────────────┘
 ↓
┌─────────────────────────────────┐
│ Same Application, config-bound │
│ - YAML resolved per profile │
│ - resolved_config on blocks │
│ - Ready for platform validation │
│ - Generators read-only over AST │
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
```

The `datrix generate` command reads `language` and `deployment` (runtime, provider, target, registry) from resolved config. Deployment-affecting CLI overrides (`--hosting`, `--platform`) are being removed — see [Decision 6: Deployment Target Contract](../architecture-overview.md#decision-6-deployment-target-contract-planned). The pipeline validates deployment dimensions (runtime/provider/target/service-flavor/infrastructure-flavor) before generation starts.

> **Migration note:** During migration, the legacy `--language`, `--hosting`, and `--platform` CLI overrides still run in the `apply_cli_overrides` stage after service and infrastructure YAML are resolved on the AST (and after optional `--service` filtering), and before `platform_validation`.

**Pipeline stages (`GenerationPipeline.run` in `datrix-common`)** align with the diagram above through semantic analysis; afterward the implementation continues with: optional service filter → `apply_cli_overrides` → `normalize_service_memory_limits` → `deployment_validation` (validates runtime/provider/target/service-flavor/infrastructure-flavor combinations) → incremental merge (may early-exit when nothing changed) → `build_deployment_plan` (resolves `DeploymentPlan` with language generators, runtime generators, and provider generators from the deployment config — see [Decision 6: Deployment Target Contract](../architecture-overview.md#decision-6-deployment-target-contract-planned)) → `discover_generators` and `discover_platforms` (receives pre-resolved platform config from the plan) → execute generators → write files → optional migrations stage → `LanguageHooks` post-processing (gated by `validation_level`) → JSON normalization → `snapshot`. Extension **directives** are recorded during parse; **registry** and **type-registry** integration run when the active code path invokes `PluginRegistry` / `TypeRegistry` APIs (see [Domain extension system](repository-architecture.md#domain-extension-system)). Language generators receive declared extension names via `declared_extension_names(app)` and merge per-language maps (for example `build_python_type_map` in `datrix-codegen-python`).

#### Validation levels

`PipelineConfig.validation_level` controls which post-generation hooks run after files are written. The enum `ValidationLevel` lives in `datrix-common` (`datrix_common.generation.validation_level`) so both CLI and pipeline can use it.

| Level | Post-processing behavior |
|---|---|
| `none` | Skip `fix_imports`, `format_files`, and `validate_files`. Parser, config resolution, and semantic analysis still run (they are pre-generation and mandatory). |
| `fast` | Run `fix_imports` and `format_files` (if cheap). Skip `validate_files`. |
| `standard` | Run all three hooks: `fix_imports`, `format_files`, `validate_files`. This is the default. |
| `full` | Run `standard` plus additional checks (e.g. `ruff check` full suite, `pyright`, `tsc --noEmit`) when available via language hooks. |

CLI mapping: `--skip-validation` is shorthand for `--validation-level none`. `--validation-level` and `--skip-validation` cannot both specify a non-none level (a warning is emitted if they conflict, and `--skip-validation` wins).

**What validation levels never bypass:** `.dtrx` parse validation, YAML config loading and model validation, semantic analysis, and platform compatibility validation. These are pre-generation correctness checks, not post-generation quality checks.

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

- **User-facing JWT (gateway apps)** (Stable) — When gateway JWT settings are present in project config, Compose emits `JWT_SECRET`, `JWT_ALGORITHM`, and `JWT_EXPIRY` into service environments (see `datrix_codegen_docker.generators.compose.compose_builder`). Python gateway generation (`datrix_codegen_python.generators.api.gateway_generator`) emits JWT verification aligned with those settings.

- **Config-driven operational settings** (Stable) — Service and project YAML profiles resolve to typed Pydantic models attached to the AST; Docker and Python generators consume those models (ports, health checks, resources, jobs, etc.) instead of hardcoding production values. `.env.example` documents variables the stack expects.

- **Entity lifecycle hooks** (Stable) — `beforeCreate` / `afterCreate` / etc. on entities are transpiled in the Python service layer (`datrix_codegen_python.generators.service.service_generator` and related templates) and invoked around persistence operations as defined in the DSL.

- **Multi-service NGINX gateway** (Stable) — For applications with more than one service, `datrix_codegen_docker.generators.config.gateway_generator` renders `config/nginx/nginx.conf` via `nginx.conf.j2`: one **upstream** per service, **location** blocks for public REST paths (including each `rest_api` **base_path** prefix), **GraphQL** `graphql_api` base paths (with WebSocket upgrade headers when the API has subscriptions), **health** aliases derived from the primary REST `base_path` plus `service.config.health_check.path` when a primary REST API exists (with `GenerationError` on duplicate external health paths), **403** for versioned paths matching internal REST segments (`INTERNAL_PATH_DENY_REGEX` in the gateway module), **CORS OPTIONS** handling and **proxy timeouts** on proxied locations, and **`client_max_body_size`** on routes for services that declare **storage** blocks. Rate limit zones from `@rateLimit` on endpoints are preserved. If an upstream has **no** matching locations, generation raises `GenerationError` listing that upstream (instead of emitting a broken config). Test-only multi-service fixtures use `attach_config_for_docker` / `ensure_minimal_rest_api_for_multi_service_gateway` in `datrix_codegen_docker.test_helpers` to add minimal `rest_api` stubs when the parsed `.dtrx` omits API blocks.

### Phase 03 capabilities (Stable) (Python, Docker)

- **GraphQL DataLoaders** (Stable) — `GraphqlResolverGenerator` (`datrix_codegen_python.generators.api.graphql_resolver_generator`) emits Strawberry DataLoader wiring and batch resolvers from DSL definitions so related fields load in grouped queries instead of per-row round-trips.

- **Rate limiting** (Stable) — A unified plan-based system requiring a Redis/Valkey-backed cache block:

  **Plan-based rate limiting** (`RateLimitGenerator` in `datrix_codegen_python.generators.cross_cutting.rate_limit_generator`) — Automatically generated for any service with REST or GraphQL APIs plus a Redis-backed cache. Emits `rate_limit/` package: `rate_limit_config.py` (baked plan tiers: RPM sliding window + daily quota + per-endpoint overrides), `rate_limiter.py` (Redis sorted-set implementation), `rate_limit_dependency.py` (FastAPI dependency `enforce_plan_rate_limit` wired at router level; GraphQL variant `enforce_plan_rate_limit_graphql` called in context getter). Client identification uses JWT `sub` claim → `x-forwarded-for` → IP fallback. Plan ID extracted from JWT claims. Emits standard headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`.

  **Per-endpoint overrides** — When endpoints use `@rateLimit(requests=N, window=S)` in the DSL, the decorator values are collected by `collect_endpoint_rate_limit_overrides` and baked into `ENDPOINT_OVERRIDES` in `rate_limit_config.py`. At runtime, `enforce_plan_rate_limit` checks overrides before applying plan RPM: if the request matches an override, the endpoint-specific requests/window constraint applies instead of the plan RPM (daily quota still applies). All rate limiting flows through a single path using consistent JWT-aware client identification.

  **`DISABLE_RATE_LIMIT` env var** (values `1`, `true`, `yes`) — early return before Redis access, enabling tests to run without Redis infrastructure. Raises 503 when Redis is unavailable and rate limiting is not disabled.

- **RFC 7807 error envelope** (Stable) — `ProjectGenerator._generate_error_modules` renders `api/error_response.py.j2` and `api/error_handlers.py.j2`; `main.py.j2` calls `register_error_handlers(app)` so API errors return a shared `ErrorResponse` / `FieldError` model (Problem Details fields: `type`, `title`, `status`, `detail`, `instance`, optional `errors`).

- **Prometheus application metrics** (Stable) — Before sub-generators run, `PythonGenerator` sets the Jinja global `has_prometheus_metrics` from the resolved observability profile. When true, generated **RDBMS** `connection.py` modules expose `sqlalchemy_pool_*` gauges (pool listeners), **Redis cache** access increments `redis_cache_hits_total` / `redis_cache_misses_total`, and **jobs** `runner.py` records `job_runs_total`, `job_failures_total`, and `job_duration_seconds` (see `metrics_middleware.py.j2` for HTTP counters/histograms as before).

- **Docker monitoring stack** (Stable) — With `observability.metrics` (Prometheus) and `observability.visualization` (Grafana), `datrix-codegen-docker` adds **cAdvisor** next to Prometheus, scrapes it from `prometheus.yml.j2`, writes **per-compose-service Grafana dashboards** plus a **multi-service overview** (`datrix-system-overview.json`) via `DashboardBuilder` / `generate_dashboards` in `datrix_codegen_docker.generators.infra.dashboard_builder`, and emits **per-service alert files** under `config/prometheus/` (standard rules: `HighErrorRate`, `HighLatency`, optional pool/cache/job rules from service features, plus a **DSL** group when blocks declare alerts). Grafana dashboards require metrics; missing metrics with visualization enabled raises `GenerationError` at generation time.

### Search engine integration (Stable)

Datrix supports full-text search through two paths: **config-driven** (existing, via `IntegrationsProfileConfig.search`) and **DSL-level** (via `search` blocks in services and shared containers).

**DSL-level `search` block** — Declares search indexes with field mappings, analyzers, boost weights, facet/sortable flags, and entity sync rules directly in `.dtrx` files:

```datrix
service CatalogService {
    rdbms db('config/rdbms.yaml') {
        entity Product { ... }
    }
    search es('config/search.yaml') {
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

### CDN / Content Delivery (Beta)

Datrix supports CDN configuration through `cdn` blocks in services and shared containers. A `cdn` block declares a CDN distribution with named origins, cache behaviors, and optional custom domains.

**DSL syntax:**

```datrix
service frontend.WebService : version('1.0.0') {
    storage mediaStore('config/storage.yaml') {
        bucket StaticAssets { ... }
        bucket UserUploads { ... }
    }
    rest_api WebAPI : basePath('/api/v1') { ... }

    cdn WebCDN('config/cdn.yaml') {
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

### Managed API Gateway (Stable)

Datrix supports managed API gateway infrastructure through a `gateway` block at the application level and a unified `gateway.yaml` configuration. When `type: managed` (or `type: kong` / `type: traefik`), platform generators emit cloud-managed or self-hosted API gateway resources with throttling, API keys, usage plans, request validation, response caching, WAF integration, and custom domain/TLS management.

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

Gateway configuration can also be specified entirely in `gateway.yaml` (profile-based, as with other config files) for users who prefer YAML over DSL-level gateway config. The `type` field in `GatewayProfileConfig` determines the gateway infrastructure: `nginx` (default, existing NGINX reverse proxy), `managed` (cloud-native: AWS API Gateway / Azure APIM), `kong` (Kong Gateway for Docker/K8s), or `traefik` (Traefik for K8s).

**Multi-platform code generation:**

| Platform | Status | Gateway Service | Generated Artifacts |
|----------|--------|----------------|---------------------|
| Docker Compose | Stable | Kong Gateway (declarative mode) when `type: managed`/`kong`; NGINX when `type: nginx` | Kong container + `kong.yml` declarative config with rate-limiting, key-auth, and proxy-cache plugins |
| Kubernetes | Stable | Kong Ingress Controller CRDs or Traefik IngressRoute | KongPlugin CRDs (rate-limiting, key-auth) + annotated Ingress resources |
| AWS | Stable | API Gateway REST API (full-featured) or HTTP API (throttling-only) | CDK/CloudFormation: REST API with usage plans, API keys, caching, VPC Link + NLB for ECS integration |
| Azure | Stable | Azure API Management (APIM) | Bicep: APIM service, per-service APIs, products (usage plans), XML rate-limiting/quota policies |

**AWS auto-selection:** The AWS generator uses REST API when any advanced feature is enabled (`apiKeys`, `cache`, `waf`) and HTTP API otherwise. REST API supports usage plans, API keys, request validation, response caching, and WAF association. HTTP API provides lower latency and cost for simple throttling and routing.

**VPC Link for private integration:** On AWS, API Gateway communicates with ECS services through a VPC Link connected to a Network Load Balancer (NLB). The generator creates an NLB when API Gateway is used: API Gateway → VPC Link → NLB → ECS Target Groups.

**WAF integration:** When `waf.enabled: true`, the AWS generator provisions a WAF Web ACL with `AWSManagedRulesCommonRuleSet` (general protection) and `AWSManagedRulesSQLiRuleSet` (SQL injection) managed rule groups, and associates it with the API Gateway stage.

**Application-level awareness:** When behind a managed gateway, language generators (Python, TypeScript) emit trusted-proxy middleware so services correctly handle `X-Forwarded-For` and API key headers injected by the gateway. Application-level API key validation is omitted when gateway-level API key enforcement is enabled.

**Backward compatibility with NGINX:** When `type: nginx` (or no gateway type specified), the existing NGINX generation path in `datrix-codegen-docker` runs unchanged. The managed gateway is opt-in.
