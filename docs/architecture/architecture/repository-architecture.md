# Repository Architecture & Plugins

> Part of the architecture documentation. See [../architecture-overview.md](../architecture-overview.md) for the full index.

---

## Repository Architecture

The project is split into **thirteen** installable packages (twelve core toolchain packages plus optional **datrix-extensions**), plus the **datrix** showcase repo (docs, examples, scripts) and **datrix-projects** repo (private production projects). This structure provides clear boundaries, independent versioning/releases, selective installation, and per-repo CI/CD pipelines.

### Core Repositories (2)

#### 1. datrix-common
**Purpose:** Shared foundation and code generation framework for all Datrix packages — AST model, type system, semantic analysis, standard library, config resolution, and generator infrastructure.

**Responsibilities:**
- **AST and types:** AST model (`Application`, `Entity`, `Service`, **`Shared`**, `RdbmsBlock`, etc.) — the single representation consumed by all generators; type system (`TypeRegistry`, `ScalarType`) and builtin scalar type definitions
- **Semantic analysis:** ordered passes in `SemanticAnalyzer.analyze` (`datrix_common.semantic.analyzer`) — stdlib symbol registration, symbol collection, import and reference resolution, field typing, inheritance merge, FK synthesis, index resolution, type checking, and domain validators (collects diagnostics; fails the pipeline when errors remain)
- **Standard library:** Ships `.dtrx` stdlib modules (`datrix_common.stdlib`) and the stdlib loader. Parsing of stdlib `.dtrx` sources uses a `StdlibParserProtocol` injected by `datrix-language` — `datrix-common` never imports the parser directly. See `datrix_common.stdlib.protocols`.
- **Config resolution:** parses `.dcfg` ConfigDSL files referenced by AST declarations, selects active profile, validates against schemas, attaches resolved config to blocks
- **Generation framework:** Generator base classes, plugin protocols (`GeneratorPlugin`, `PlatformPlugin`), template rendering (Jinja2), YAML/JSON document builders, file coordination, code formatting integration, testing utilities for generator packages. **Pipeline orchestration** (`GenerationPipeline`) lives in `datrix-cli`, not here — `datrix-common` provides the framework; `datrix-cli` owns the orchestrator.
- **Protocols:** `ParserProtocol`, `StdlibParserProtocol`, `LanguageHooks`, `LanguageRuntimeSpec`, `GeneratorPlugin`, `PlatformPlugin` — all protocol definitions that enable dependency inversion across packages
- **Transpiler:** Staged DSL-to-source pipeline shared across language packages — **`NameResolver`** (Stage 1) and **`QueryExpander`** (Stage 2) in **datrix-common** produce **`ResolutionTable`** / query-annotation side-tables; each **`LanguageTranspiler`** subclass (Stage 3) consumes those tables and returns **`TranspileResult`**. Configuration is a frozen **`TranspileContext`**; per-file sibling-flow state lives in **`FileScope`** / **`PythonFileScope`** / **`TypeScriptFileScope`**. Expression and statement work uses **`ExpressionVisitor`** / **`StatementVisitor`** and **`node.accept()`**; call targets use **`CallTargetEmitter`** and **`dispatch_call()`**. See [datrix-common — Transpiler architecture](../../../../datrix-common/docs/architecture.md#transpiler-architecture-staged-pipeline), [code-generation.md — Consolidated generator infrastructure](../../../../datrix-common/docs/architecture/code-generation.md#consolidated-generator-infrastructure), and [datrix-common-api — Transpiler modules](../../../../datrix-common/docs/datrix-common-api.md#transpiler-modules).
- **Shared:** Rendering utilities, error classes, configuration models, shared utilities
- **Seed builtins:** `Seed` builtin object with framework-maintained reference datasets (countries, subdivisions, currencies, timezones, languages); canonical data in `builtins/data/` as JSON; SeedDSL AST model classes for parsed seed declarations
- **Seed config:** ConfigDSL schema extensions for component-scoped seed policy (category enablement, tenant distribution, hash policy)

**Dependencies:** None (zero dependencies on other Datrix packages). All parser and stdlib-loader functionality is injected via protocols at runtime.

---

#### 2. datrix-language
**Purpose:** Parser and CST-to-AST transformers for .dtrx, .dcfg, and .dseed files

**Responsibilities:**
- Parsing .dtrx files (Tree-sitter grammar, lexer, parser)
- Parsing .dseed files (SeedDSL — seed declarations, tabular data, registry, `@ref`/`@lookup`/`@uuid`/`@hash`/`@json`/`@geo` constructs)
- Implements `ParserProtocol` and `StdlibParserProtocol` (defined in `datrix-common`) — provides the concrete `TreeSitterParser` used by CLI and stdlib loader
- Shipped **builtins** `.dtrx` definitions under `src/datrix_language/builtins/` (injected at parse time)
- CST-to-AST transformers that produce `Application` objects (defined in `datrix-common`)
- **Server-managed fields** via the **`server`** field modifier (for example `UUID id : primaryKey, server = uuid();`, `DateTime createdAt : server = DateTime.now();`) — not a `@` prefix on the type
- **Custom exception catalogs** via `exceptions { … }` blocks on `module` and `service`
- **User-defined scalars** via `scalar Name : BaseType { … }` on `module` and `service` (constrained aliases; distinct from extension-pack scalars — see [language reference](../../reference/language-reference.md#custom-scalar-types))

**Key Insight:** The parser + transformers produce `Application` directly. There is no separate IR layer. The `Application` model and all AST types are defined in `datrix-common`; datrix-language imports them. Standard library `.dtrx` resources live in `datrix-common` (the semantic layer); `datrix-language` provides the parser implementation that the stdlib loader calls via protocol injection.

**Dependencies:**
- `datrix-common` (AST model, type system, semantic analysis, config resolution, stdlib protocols)

---

### Shared Codegen Intelligence (1)

#### 3. datrix-codegen-common
**Purpose:** Language-agnostic algorithms, context models, profile-driven transpiler, field analysis, and parity checking consumed by language codegen packages.

**Responsibilities:**
- **Profile-driven transpiler:** `LanguageProfile` (7 sub-profiles), `SharedTranspiler` (final, no subclassing), `SyntaxEmitters` protocol with `CBraceSyntaxEmitters` and `PythonIndentSyntaxEmitters`
- **Algorithms:** `build_*_context()` functions that compute language-agnostic semantic contexts from AST
- **Context models:** Frozen dataclasses (`EntityContext`, `ServiceContext`, `SchemaContext`, etc.) carrying semantic data from algorithms to micro-generators
- **Field analysis:** Reusable entity/field analysis (lookup methods, cascade checks, sortable/filterable classification, lifecycle hooks)
- **Micro-generator pattern:** `MicroGenerator[TContext]` ABC for language-specific rendering from shared context
- **Parity checking:** `validate_profile_completeness()`, `verify_micro_generator_parity()`, `validate_builtin_parity()` — automated cross-language feature verification
- **Seed orchestration:** SeedDSL-backed orchestration across RDBMS, NoSQL, and Storage targets — semantic validation, dependency graph construction, target writer interfaces, and component-scoped seed policy resolution (replaces the obsolete YAML-driven `SeedOrchestrator`)

**Dependencies:**
- `datrix-common` (AST model, type system, transpiler base, generation framework)

See [datrix-codegen-common — Architecture](../../../../datrix-codegen-common/docs/architecture.md).

---

### Code Generators (4)

These are **specialized extensions** of the generation framework in `datrix-common` for specific languages or platform-agnostic artifacts.

#### 4. datrix-codegen-component
Generates platform-agnostic components: documentation (README, API reference, architecture), configuration (Alembic, pytest, coverage), scripts (entrypoint, dev scripts), and shared templates (Mermaid diagrams)

#### 5. datrix-codegen-python
Generates Python code (FastAPI, Django, Flask). Includes SeedDSL-backed seed runner generation with SQLAlchemy Core dialect DML for RDBMS, motor/pymongo for NoSQL, and provider SDK for Storage targets. Extends `PythonBuiltinMethodMapper` with `Seed.*` method mappings.

#### 6. datrix-codegen-typescript
Generates TypeScript code (Express, NestJS, Next.js). Includes SeedDSL-backed seed runner generation with MikroORM/SQL driver for RDBMS, Mongo driver for NoSQL, and AWS/Azure SDK for Storage targets. Extends `TsBuiltinMethodMapper` with `Seed.*` method mappings.

#### 7. datrix-codegen-sql
Generates SQL DDL (PostgreSQL, MySQL). Extends `SQLDialect` protocol with seed-specific DML primitives (`seed_upsert_sql()`) for multi-engine upsert semantics: PostgreSQL `ON CONFLICT ... DO NOTHING/UPDATE`, MySQL `INSERT IGNORE` / `ON DUPLICATE KEY UPDATE`.

**Dependencies (language generators):**
- `datrix-codegen-common` (shared transpiler, algorithms, context models, field analysis)
- `datrix-common` (AST model, type system, template rendering, generation framework)
- `jinja2` (for template rendering)

**Dependencies (component, SQL):**
- `datrix-common` (AST model, type system, template rendering, generation framework)
- `jinja2` (for template rendering)

---

### Platform Generators (4)

Generate infrastructure and deployment configurations. Under the [Deployment Target Contract](../architecture-overview.md#decision-6-deployment-target-contract-planned) (Planned), these generators are re-classified by their role in the multidimensional deployment model:

- **Runtime generators** (`datrix-codegen-docker`, `datrix-codegen-k8s`) — own the deployable artifact shape for `docker-compose` and `kubernetes` runtimes respectively
- **Provider generators** (`datrix-codegen-aws`, `datrix-codegen-azure`) — own provider-managed infrastructure, and also own provider-native runtimes (`ecs-fargate`, `app-runner` for AWS; `azure-container-apps`, `azure-app-service` for Azure)

Provider generators augment runtime output when selected alongside Docker or Kubernetes. For `runtime: kubernetes, provider: azure`, the K8s generator still produces Kubernetes manifests; the Azure generator adds AKS/ACR/identity/networking/managed-service integration.

#### 8. datrix-codegen-docker
Generates Dockerfiles and docker-compose.yml, including optional **job worker** services for Python services with jobs, **Elasticsearch** infrastructure plus index-init containers when search integration and searchable fields are present, **Varnish** cache proxy containers when `cdn` blocks are configured (simulates edge caching for local development), **PgBouncer** containers when `connectionPooler.enabled: true` on RDBMS blocks (one PgBouncer container per consolidated database, with health check and dependency wiring), **Kong Gateway** containers with declarative config when `gateway.type` is `managed` or `kong` (rate-limiting, key-auth, and proxy-cache plugins), and **seed services** that run profile-gated seed scripts after migration completion (production profiles run reference data only by default)

#### 9. datrix-codegen-k8s
Generates Kubernetes manifests (Deployment, Service, etc.) including Elasticsearch StatefulSets, headless Services, and search index init Jobs when `search` blocks are present, PgBouncer Deployment + ClusterIP Service + ConfigMap when `connectionPooler.enabled: true` on RDBMS blocks, Kong Ingress Controller CRDs (KongPlugin resources for rate-limiting, key-auth) with annotated Ingress when `gateway.type` is `managed` or `kong`, and **seed Jobs** that run profile-gated seed scripts after schema initialization and migrations (alongside existing Kafka/RabbitMQ/search init Jobs)

#### 10. datrix-codegen-aws
Generates AWS infrastructure (CDK, CloudFormation) including VPC, ECS Fargate, RDS, ElastiCache, SNS/SQS, MSK (Kafka), Amazon MQ (RabbitMQ), DynamoDB, Amazon DocumentDB (MongoDB), S3, ALB, Amazon OpenSearch Service domains, CloudFront CDN distributions (with OAC for S3 origins, custom domains, and SSL certificates), RDS Proxy resources when `connectionPooler.enabled: true` on RDBMS blocks, API Gateway (REST API or HTTP API) with usage plans, API keys, response caching, WAF Web ACL, VPC Link + NLB, and custom domains when `gateway.type` is `managed`, and AWS Cloud Map service discovery (private DNS namespace + ECS service registration for internal service-to-service communication)

#### 11. datrix-codegen-azure
Generates Azure infrastructure (Bicep, ARM templates) including Container Apps, Flexible Server, Cosmos DB, Service Bus, Event Hubs (Kafka), Azure Cache for Redis, Blob Storage, Azure AI Search services, Azure Front Door CDN profiles (with origin groups, routes, and cache configuration), built-in PgBouncer server parameters on Flexible Server when `connectionPooler.enabled: true` on RDBMS blocks, Azure API Management (APIM) with per-service APIs, products (usage plans), and XML rate-limiting/quota policies when `gateway.type` is `managed`, and Container Apps internal service discovery (peer traffic encryption, internal/external ingress, and peer service URL env vars)

**Dependencies:**
- `datrix-common` (AST model, configuration, generation framework, YAML/JSON builders)

---

### CLI (1)

#### 12. datrix-cli
Command-line interface for code generation and seed management

**Responsibilities:**
- **Pipeline orchestration** — owns `GenerationPipeline` (parse → analyze → generate → format → write), the full end-to-end orchestrator that coordinates parsing, semantic analysis, config resolution, generator execution, file writing, and post-processing hooks. Constructs `TreeSitterParser` and stdlib loader from `datrix-language` and injects them into the pipeline stages.
- **Seed execution** — `datrix seed` command family: `--profile`, `--category`, `--dry-run`, `--reset` (non-prod), `--warm-cache`, `--rebuild-views`. Production safety: `datrix seed --profile prod` runs only reference data by default; baseline and volume categories are rejected unless overridden with `--force`.
- **Seed capture** — `datrix seed capture` reverse-engineers existing database state into `.dseed` declarations with tenant-scoped introspection, secret redaction, and natural-key inference.
- Plugin discovery
- Linting and formatting
- Progress reporting
- User interaction

**Dependencies:**
- `datrix-common` (AST model, type system, configuration, semantic analysis, generation framework, generator discovery)
- `datrix-language` (parser, CST-to-AST transformers, `ParserProtocol` implementation)
- Discovers installed generator *plugins* dynamically (datrix-codegen-python, etc.)

---

### Extension packs (optional)

#### 13. datrix-extensions
Optional package of **domain extension** entry points registered under the `datrix.extensions` group. Each pack contributes language-agnostic scalar definitions, builtin objects, database extension names (for example PostGIS), extra dependency hints, and optional template directories. **Language-specific type mappings** live in `datrix-codegen-python`, `datrix-codegen-typescript`, `datrix-codegen-sql`, not in the extension pack (split ownership).

**Dependencies:**
- `datrix-common` (protocols, types)

**Installation:** Only required when a project's `system.dtrx` declares `use extension <name>;`. Not a hard dependency of `datrix-cli` or the language generators.

---

### Showcase (1)

#### 14. datrix
Public repository with documentation, examples, and scripts.

---

## Plugin Architecture

Generators and domain extensions load through **setuptools entry-point groups** discovered at runtime (see table). Cross-cutting pieces:

- **Protocols** — Code generators implement `GeneratorPlugin`; platform generators implement `PlatformPlugin`. **Language targets subclass `LanguageGenerator`** (`datrix_common.generation.language_generator`): `generate()` is `@final` in the base class; subclasses implement **nine abstract methods**. See [code-generation.md](../../../../datrix-common/docs/architecture/code-generation.md#consolidated-generator-infrastructure) in datrix-common.
- **`TypeMappingRegistry`** (`datrix_common.generation.type_mapping_registry`) — each registered language maps canonical `TypeRegistry` types (`global_registry.register_language()` at import time).
- **`LanguageHooks` / `LanguageRuntimeSpec`** — post-write formatting and validation hooks, and infrastructure details for Docker/K8s (Dockerfile context, health checks, migration commands), respectively.

### Entry Point Groups

| Group | Purpose | Protocol |
|-------|---------|----------|
| `datrix.generators` | Code generators (Python, TypeScript, SQL, component) | `GeneratorPlugin` |
| `datrix.platforms` | Platform generators (Docker, K8s, AWS, Azure) | `PlatformPlugin` |
| `datrix.language_hooks` | Post-generation hooks (formatting, validation) | `LanguageHooks` |
| `datrix.language_runtime_spec` | Infrastructure details (Dockerfiles, healthchecks, migrations) | `LanguageRuntimeSpec` |
| `datrix.extensions` | Domain extension packs (types, builtins, DB extension names, templates) | `DatrixExtension` |

All protocols are defined in `datrix-common` (see `datrix_common.plugin.protocol`, `datrix_common.plugin.extension`, `datrix_common.generation.language_hooks`, `datrix_common.generation.language_runtime_spec`). The CLI and pipeline discover installed plugins at runtime. Users only install the generators they need — no unused dependencies. Install **`datrix-extensions`** only when using `use extension` in `system.dtrx`.

---

## Domain extension system

Domain-specific scalars, builtin objects, and infrastructure hints (for example PostGIS) can ship in **extension packs** instead of bloating `datrix-common`. See the [extensions guide](../../../../datrix-extensions/docs/extensions-guide.md) and the [datrix-common extensions overview](../../../../datrix-common/docs/extensions.md).

### Split ownership

| Layer | Owns |
|-------|------|
| Extension pack (`datrix.extensions`) | Language-agnostic scalar defs, builtin object types, `db_extensions()`, `extra_dependencies()`, `template_dirs()` |
| Each language generator (`datrix-codegen-python`, …) | All **language-specific** type mappings for core **and** declared extensions (for example `PYTHON_EXTENSION_MAPS` + `build_python_type_map` in `datrix_codegen_python.type_mappings`) |

Adding a new target language updates **one** codegen package with core maps plus whichever extension keys it supports. Adding a new extension updates the extension pack **and** each language generator that should support it.

### Discovery and types

- **`PluginRegistry.discover_extensions()`** — loads classes from the `datrix.extensions` entry-point group (`datrix_common.plugin.registry`).
- **`PluginRegistry.load_declared_extensions(declared)`** — resolves names from `app.extension_directives` to `DatrixExtension` instances; raises **`ExtensionNotFoundError`** with install hints when a name is missing.
- **`TypeRegistry.load_extensions(extensions)`** — registers extension scalar definitions into the shared type registry when callers supply loaded instances (`datrix_common.types.registry`).

### DSL

Projects enable packs in **`system.dtrx`** with:

```datrix
use extension geo;
```

(`use extension` must appear inside the `system { }` block; see `datrix_language` transformer validation.)

### Application containers

A `.dtrx` application is built from **five** top-level container kinds (plus `include` / `import`):

| Container | Purpose | Typical members |
|-----------|---------|-----------------|
| **`system { }`** | Application metadata | `config`, `discovery`, `use extension` |
| **`module { }`** | Shared types and functions | `entity`, `enum`, `trait`, `struct`, `scalar`, `const`, `fn`, `exceptions`, `import` |
| **`service { }`** | Deployable microservice | Everything in **module** scope **plus** infrastructure (`rdbms`, `nosql`, `cache`, `pubsub`, `storage`, `queues`, `search`, `cdn`), APIs, jobs, CQRS, **`subscribe`** (service-level), **`uses`**, `enqueue`, `test`, service `config` / `discovery` |
| **`shared { }`** | **Cross-service infrastructure** | `rdbms`, `nosql`, `cache`, `pubsub`, `storage`, `queues`, `search`, `cdn` only — **no** APIs, jobs, CQRS, or `subscribe` |
| **`extern service { }`** | **External library/tool contract** | `struct`, `enum`, `rest_api` (signature-only endpoints), `errors`, `auth`, `health` — **no** infrastructure blocks, no implementation bodies |

**Messaging:** Topics and **`publish`** events live under **`pubsub`** blocks (whether owned by a service or a **`shared`** block). **`subscribe { … }`** is always a **direct child of `service { }`**, not nested inside `pubsub`. Services declare which other containers they depend on with **`uses SharedOrServiceName : modifiers;`**. Infrastructure blocks navigate to their owner via **`block.container()`** (`Service` or `Shared`). See [datrix-language — Service blocks reference](../../../../datrix-language/docs/reference/datrix-service-blocks.md) and [design/shared-block.md](../../../../design/shared-block.md).

### Extern services (external library interfacing)

An `extern service` declares a **contract** for an external HTTP service that Datrix does not generate code for. The user builds and deploys the external service independently (in any language); Datrix generates a **typed HTTP client** in consuming services and wires **deployment infrastructure** (Docker Compose entry, K8s manifests, health checks, environment variables).

**Why HTTP services instead of in-process dependencies:**
- No language lock-in — user writes external service in any language
- Completely isolated dependency graph — no conflicts with Datrix-managed packages
- No user code inside the generated project — re-generation is always safe
- Clean deployment separation — one container per concern, independent scaling

**DSL syntax:**

```dtrx
extern service pricing.PricingEngine('config/pricing-engine.dcfg') : version('1.0.0') {
    struct PricingRequest { String productId; Integer quantity; String currency; }
    struct PricingResponse { Decimal price; Decimal tax; String currency; }
    errors { NotFound(String message); ValidationError(String field, String reason); }
    auth : apiKey(header: 'X-API-Key');
    health : path('/health');
    rest_api PricingAPI : basePath('/api/v1') {
        post calculatePrice(PricingRequest request) -> PricingResponse {
            ensure request.quantity > 0;
            ensure request.currency.length == 3;
        }
    }
}
```

**Constraints:** An `extern service` may only contain `struct`, `enum`, `rest_api` (signature-only), `errors`, `auth`, and `health` declarations. Infrastructure blocks (`rdbms`, `cache`, `pubsub`, etc.), entity definitions, implementation bodies, and `discovery` blocks are not allowed.

**Consumption:** A generated service uses an extern service via the same `uses` declaration used for inter-service dependencies:

```dtrx
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    uses PricingEngine;
    // Generated code receives a typed HTTP client for PricingEngine
}
```

**What Datrix generates:**
- **Typed HTTP client** — client class with methods matching each endpoint, auth header injection, error mapping to typed exceptions
- **Contract validation** — `ensure` clauses run before HTTP dispatch (raises `ContractViolationError`)
- **Client DTOs** — request/response models from the extern service's struct definitions
- **Docker Compose entry** — container with user-provided image (no build context), health check, `depends_on` wiring
- **K8s manifests** — Deployment, Service, Secret for colocated extern services
- **Environment wiring** — `{SERVICE}_SERVICE_URL` injected into consuming services

**Config profiles:** Extern services support two deployment modes via config YAML:
- `deployment: container` — colocated container (development, docker-compose). Requires `image` and `port`.
- `deployment: external` — remote URL, no container managed by Datrix (production). Requires `url`.

**Network:** Extern services are internal-only — not routed through the nginx gateway by default. They serve other Datrix-generated services, not end users.

### Pipeline integration

The high-level flow is: **parse** records extension directives on the AST → **registry / type registry** APIs load and validate packs when invoked → **semantic analysis** and **generators** consume the resulting types and maps. Exact call ordering follows the implementation in `GenerationPipeline` and semantic analysis; language generation always receives declared names via `declared_extension_names(app)` (`datrix_common.generation.language_helpers`).

### Adding a New Language

Adding a new target language (e.g., Go, Rust, Java) requires a new `datrix-codegen-{lang}` package that depends on `datrix-common` and `datrix-codegen-common`. Follow the **consolidated checklist**:

1. Create `datrix-codegen-{lang}` package (depends on `datrix-common` and `datrix-codegen-common`).
2. Subclass **`LanguageGenerator`** — implement the nine abstract methods; wire sub-generators and project-level output through the shared `generate()` implementation.
3. Define a **`LanguageProfile`** instance (`datrix_codegen_common.transpiler.profile`) with the 7 sub-profiles (Syntax, Operators, Builtins, Types, Naming, ORM, Scope). For C-style languages, inherit from `CBraceSyntaxEmitters`.
4. Wire the **`SharedTranspiler`** from `datrix-codegen-common` with the language profile. Implement an ORM-specific entity query module for the language's framework.
5. Implement **micro-generators** (`MicroGenerator[TContext]` from `datrix_codegen_common`) for each domain, using shared context models.
6. Add **`type_mappings.py`** — map every canonical type; register with `global_registry.register_language()`.
7. Implement **`LanguageHooks`** — post-generation formatting and validation.
8. Implement **`LanguageRuntimeSpec`** — Dockerfile context, healthchecks, DB URL schemes, migration commands, job runner commands.
9. Register entry points in **`pyproject.toml`** (`datrix.generators`, and hooks/runtime spec as required).
10. Run parity verification: `validate_profile_completeness(LANG_PROFILE)` and `verify_micro_generator_parity(...)` to detect missing builtins, types, or domain generators.

The shared transpiler algorithm, context builders, and field analysis require **zero new code** — they work automatically with the new profile and micro-generators. See [datrix-codegen-common — Adding a New Language](../../../../datrix-codegen-common/docs/architecture.md#adding-a-new-language) for detailed line counts.

Platform generators consume `LanguageRuntimeSpec` via protocol dispatch instead of language-specific branching. See [code-generation.md — Consolidated generator infrastructure](../../../../datrix-common/docs/architecture/code-generation.md#consolidated-generator-infrastructure).
