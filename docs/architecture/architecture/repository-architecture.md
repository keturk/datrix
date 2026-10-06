# Repository Architecture & Plugins

> Part of the architecture documentation. See [../architecture-overview.md](../architecture-overview.md) for the full index.

---

## Repository Architecture

The project is split into **nineteen** installable packages (seventeen core toolchain packages, the **datrix-testing** test harness, and optional **datrix-extensions**), plus the **datrix** showcase repo (docs, examples, scripts). This structure provides clear boundaries, independent versioning/releases, selective installation, and per-repo CI/CD pipelines.

> **The datrix showcase repo holds only docs, examples, and scripts — it is not an installable toolchain package and hosts no test suite.** It must never contain a `tests/` pytest suite, product tests, cross-package tests, or language/provider matrix tests. Datrix is a **multi-language, multi-platform generator** (not limited to Python/TypeScript, not limited to Docker/AWS/Azure), so no test that enumerates specific languages or providers belongs in it. Each `datrix-*` package tests only its own surface; genuine repo-level cross-cutting validation lives as **scripts under `datrix/scripts/test/`**, never as `datrix/tests/`.

### Core Repositories (2)

#### 1. datrix-common
**Purpose:** Shared foundation for all Datrix packages — AST model, type system, standard library, config resolution, and plugin and deployment declarations. Semantic analysis is the separate `datrix-semantic` package (#17); the generation framework is the separate `datrix-codegen-kernel` package (#18).

**Responsibilities:**
- **AST and types:** AST model (`Application`, `Entity`, `Service`, **`Shared`**, `RdbmsBlock`, etc.) — the single representation consumed by all generators; type system (`TypeRegistry`, `ScalarType`) and builtin scalar type definitions
- **Standard library:** Ships the stdlib loader, catalog and errors (`datrix_common.stdlib.loader`, `.catalog`, `.errors`) and consumes the seven `.dtrx` module files `datrix-language` ships. Discovery and parsing of stdlib `.dtrx` sources use a `StdlibParserProtocol` injected by `datrix-language` — its `stdlib_module_directory()` names where the files live and its `parse_stdlib_source()` parses each one; `datrix-common` never imports the parser directly. See `datrix_common.protocols.parser`.
- **Config resolution:** parses `.dcfg` ConfigDSL files referenced by AST declarations, selects active profile, validates against schemas, attaches resolved config to blocks
- **Plugin declarations:** plugin protocols (`GeneratorPlugin`, `PlatformPlugin`), the structural Protocols that name generation-framework types without importing them (`plugin/framework_protocols.py`), YAML/JSON document builders, and the `pytest11` feature-tag plugin (`datrix_common.testing.feature_tags`); the shared test harness is the separate `datrix-testing` package. The generator base classes and template rendering are `datrix-codegen-kernel`; **pipeline orchestration** (`GenerationPipeline`) lives in `datrix-cli`.
- **Protocols:** `ParserProtocol`, `StdlibParserProtocol`, `LanguageHooks`, `LanguageRuntimeSpec`, `GeneratorPlugin`, `PlatformPlugin` — all protocol definitions that enable dependency inversion across packages
- **Transpiler:** Staged DSL-to-source pipeline shared across language packages — **`NameResolver`** (Stage 1) and **`QueryExpander`** (Stage 2) in **datrix-common** produce **`ResolutionTable`** / query-annotation side-tables; each **`LanguageTranspiler`** subclass (Stage 3) consumes those tables and returns **`TranspileResult`**. Configuration is a frozen **`TranspileContext`**; per-file sibling-flow state lives in **`FileScope`** / **`PythonFileScope`** / **`TypeScriptFileScope`**. Expression and statement work uses **`ExpressionVisitor`** / **`StatementVisitor`** and **`node.accept()`**; call targets use **`CallTargetEmitter`** and **`dispatch_call()`**. See [datrix-common — Transpiler architecture](../../../../datrix-common/docs/architecture.md#transpiler-architecture-staged-pipeline), [code-generation.md — Consolidated generator infrastructure](../../../../datrix-common/docs/architecture/code-generation.md#consolidated-generator-infrastructure), and [datrix-common-api — Transpiler modules](../../../../datrix-common/docs/datrix-common-api.md#transpiler-modules).
- **Shared:** Rendering utilities, error classes, configuration models, shared utilities
- **Seed builtins:** `Seed` builtin object declaring the framework-maintained reference datasets (countries, subdivisions, currencies, timezones, languages); the datasets and their loader live in `datrix-codegen-kernel` (`datrix_codegen_kernel.seed_data`); SeedDSL AST model classes for parsed seed declarations
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

**Key Insight:** The parser + transformers produce `Application` directly. There is no separate IR layer. The `Application` model and all AST types are defined in `datrix-common`; datrix-language imports them. Standard library `.dtrx` resources live in `datrix-common`; `datrix-language` provides the parser implementation that the stdlib loader calls via protocol injection.

**Dependencies:**
- `datrix-common` (AST model, type system, config resolution, stdlib protocols)
- `datrix-semantic` (the language server runs semantic analysis and converts its diagnostics)

---

### Shared Codegen Intelligence (1)

#### 3. datrix-codegen-common
**Purpose:** Language-agnostic algorithms, context models, profile-driven transpiler, field analysis, and parity checking consumed by language codegen packages.

**Responsibilities:**
- **Profile-driven transpiler:** `LanguageProfile` (nine sub-profiles: syntax, operators, builtins, types, naming, orm, scope, docs, errors), `SharedTranspiler` (final, no subclassing), `SyntaxEmitters` protocol with `CBraceSyntaxEmitters` and `IndentBlockSyntaxEmitters`
- **Algorithms:** `build_*_context()` functions that compute language-agnostic semantic contexts from AST
- **Context models:** Frozen dataclasses (`EntityContext`, `ServiceContext`, `SchemaContext`, etc.) carrying semantic data from algorithms to micro-generators
- **Field analysis:** Reusable entity/field analysis (lookup methods, cascade checks, sortable/filterable classification, lifecycle hooks)
- **Micro-generator pattern:** `MicroGenerator[TContext]` ABC for language-specific rendering from shared context
- **Parity checking:** `validate_profile_completeness()`, `verify_micro_generator_parity()`, `validate_builtin_parity()` — automated cross-language feature verification
- **Seed orchestration:** SeedDSL-backed orchestration across RDBMS, NoSQL, and Storage targets — semantic validation, dependency graph construction, target writer interfaces, and component-scoped seed policy resolution (replaces the obsolete YAML-driven `SeedOrchestrator`)

**Dependencies:**
- `datrix-common` (AST model, type system, configuration)
- `datrix-codegen-kernel` (generator base classes, template rendering, the GenDSL data model, the service-feature vocabulary)
- `datrix-migration` (schema snapshot, diff, change policy, revision ledger and state store the migration orchestrator drives)

See [datrix-codegen-common — Architecture](../../../../datrix-codegen-common/docs/architecture.md).

---

### Code Generators (4)

These are **specialized extensions** of the generation framework in `datrix-codegen-kernel` for specific languages or platform-agnostic artifacts.

The language generators below are the set that ships **today**. Datrix is a multi-language generator by design: this list grows, and nothing in the framework may assume it is closed. Every language generator is a peer — it depends on `datrix-codegen-common` + `datrix-codegen-kernel` + `datrix-common` and never on a sibling language package.

#### 4. datrix-codegen-component
Generates platform-agnostic components: documentation (README, API reference, architecture), configuration (Alembic, pytest, coverage), scripts (entrypoint, dev scripts), and shared templates (Mermaid diagrams)

#### 5. datrix-codegen-python
Generates Python code (FastAPI). Includes SeedDSL-backed seed runner generation with SQLAlchemy Core dialect DML for RDBMS, motor/pymongo for NoSQL, and provider SDK for Storage targets. Extends `PythonBuiltinMethodMapper` with `Seed.*` method mappings.

#### 6. datrix-codegen-typescript
Generates TypeScript code (NestJS on Express). Includes SeedDSL-backed seed runner generation with MikroORM/SQL driver for RDBMS, Mongo driver for NoSQL, and AWS/Azure SDK for Storage targets. Extends `TsBuiltinMethodMapper` with `Seed.*` method mappings.

#### 7. datrix-codegen-sql
Generates SQL DDL (PostgreSQL, MySQL). Seed DML (PostgreSQL `ON CONFLICT ... DO NOTHING/UPDATE`, MySQL `INSERT IGNORE` / `ON DUPLICATE KEY UPDATE`) is built by the kernel's `RdbmsSeedWriter`.

**Dependencies (language generators):**
- `datrix-codegen-common` (shared transpiler, algorithms, context models, field analysis)
- `datrix-codegen-kernel` (generator base classes, template rendering, generation framework)
- `datrix-common` (AST model, type system, configuration)
- `datrix-migration` (schema snapshot, diff and revision ledger their migration adapters render from)
- `jinja2` (for template rendering)
- No language package depends on `datrix-codegen-sql`: the SQL dialect facts their migration adapters render DDL through (dialect protocol and registry, index constants, naming, column derivation, type map) live in `datrix-codegen-kernel` (`datrix_codegen_kernel.sql_facts`). A language package never depends on a sibling language package.

**Dependencies (component, SQL):**
- `datrix-codegen-kernel` (generator base classes, template rendering, generation framework, GenDSL runtime and registrations; component also consumes derived domain declarations, the shared serverless plan and NoSQL connection plans, SQL the migration-adapter contract, its language-agnostic plans and the SQL dialect facts in `sql_facts`)
- `datrix-common` (AST model, type system, configuration)
- `datrix-migration` (SQL only: schema diff, revision ids, live-snapshot reflector contract)
- `jinja2` (for template rendering)

Neither declares `datrix-codegen-common`: the import-boundary scanner forbids them every `datrix_codegen_common` import in `src/`.

Every edge is held equal to the import set by `datrix/scripts/gates/parity/manifest-import-parity-gate.ps1`.

---

### Platform Generators (3)

Generate infrastructure and deployment configurations. Under the [Deployment Target Contract](../architecture-overview.md#decision-6-deployment-target-contract-stable), these generators are classified by their role in the multidimensional deployment model:

- **Runtime generators** (`datrix-codegen-docker`) — owns the deployable artifact shape for the `docker-compose` runtime, and DECLARES (`PlatformCapabilityDeclaration.container_scaffold_runtimes`) the other runtimes it also supplies per-service Dockerfiles for: `ecs-fargate`, `app-runner`, and `azure-app-service-container`. The shared deployment plan asks every installed platform for that declared set rather than consulting a runtime-keyed table
- **Provider generators** (`datrix-codegen-aws`, `datrix-codegen-azure`) — own provider-managed infrastructure, and also own provider-native runtimes (`ecs-fargate`, `app-runner` for AWS; `azure-app-service` for Azure)

Provider generators own the cloud infrastructure for provider-native runtimes. Where the docker platform declares a cloud runtime in its `container_scaffold_runtimes` (`ecs-fargate`, `app-runner`, `azure-app-service-container`), the docker generator supplies the per-service Dockerfiles that runtime packages into images — the provider generator still owns all infrastructure. The `docker-compose` runtime's container artifacts always come from the docker runtime generator regardless of provider: the `local` provider augments nothing, and the `azure-vm` provider (Decision 35, adopted and registered from the Azure platform package) pairs the runtime with cloud-hosted compute — emitting its own infrastructure (VM, managed PostgreSQL/Blob/Service Bus via Bicep) alongside the unchanged Compose output. For `runtime: azure-app-service` (code-based, no containers), the Azure generator produces all infrastructure directly — there is no separate runtime generator and no Dockerfile involvement.

#### 8. datrix-codegen-docker
Generates Dockerfiles and docker-compose.yml, including optional **job worker** services for Python services with jobs, **Elasticsearch** infrastructure plus index-init containers when search integration and searchable fields are present, **Varnish** cache proxy containers when `cdn` blocks are configured (simulates edge caching for local development), **PgBouncer** containers when `connectionPooler.enabled: true` on RDBMS blocks (one PgBouncer container per consolidated database, with health check and dependency wiring), an **NGINX reverse-proxy** gateway container when `gateway.type` is `nginx` (the only self-hosted gateway; `managed` is cloud-only and rejected for Docker), and **seed services** that run profile-gated seed scripts after migration completion (production profiles run reference data only by default)

#### 9. datrix-codegen-aws
Generates AWS infrastructure (CDK, CloudFormation) including VPC, ECS Fargate, RDS, ElastiCache, SNS/SQS, MSK (Kafka), Amazon MQ (RabbitMQ), DynamoDB, Amazon DocumentDB (MongoDB), S3, ALB, Amazon OpenSearch Service domains, CloudFront CDN distributions (with OAC for S3 origins, custom domains, and SSL certificates), RDS Proxy resources when `connectionPooler.enabled: true` on RDBMS blocks, API Gateway (REST API or HTTP API) with usage plans, API keys, response caching, WAF Web ACL, VPC Link + NLB, and custom domains when `gateway.type` is `managed`, and AWS Cloud Map service discovery (private DNS namespace + ECS service registration for internal service-to-service communication)

#### 10. datrix-codegen-azure
Generates Azure infrastructure (Bicep) including App Service (native PaaS runtime for `runtime: azure-app-service`), Azure Functions (serverless handlers from `serverless` blocks), Flexible Server (from `rdbms` blocks), Cosmos DB (from `nosql` blocks), Service Bus or Event Hubs/Kafka (from `pubsub` blocks), Azure Cache for Redis (from `cache` blocks), Blob Storage (from `storage` blocks), Azure AI Search services (from `search` blocks), Azure Front Door CDN profiles (from `cdn` blocks), Azure API Management (from `gateway.type: managed`), built-in PgBouncer server parameters on Flexible Server when `connectionPooler.enabled: true`, and App Service internal service discovery (peer service URL env vars). Service deployment shape is derived from declared DSL blocks; no per-service runtime-flavor selector is used.

**Dependencies:**
- `datrix-common` (AST model, configuration, YAML/JSON builders)
- `datrix-codegen-kernel` (generator base classes, template rendering, the shared route and runtime derivations, the deploy-script machinery, and every language-agnostic platform service: GenDSL runtime, the `platform/` provider library, pooling, dashboards, secrets, seed planning, serverless plans, shared enums). Platform generators do not declare `datrix-codegen-common`; the import-boundary scanner forbids them every `datrix_codegen_common` import in `src/`

> **Language-agnostic provider generators.** All three platform generators obtain language-specific runtime details from the `LanguageRuntimeSpec` protocol via `discover_language_runtime_spec(target_language)` — no `Language`-enum branching, no `language_name == "…"` comparisons in application-wiring code. The protocol carries provider-facing methods alongside the Docker set, including: `container_command(service, package_name)` (the single source of truth for how the HTTP service starts — consumed both as Azure App Service's `startup_command` and as the source every `datrix-codegen-docker` Dockerfile `CMD` is rendered from on both clouds), `hosts_consumers_in_process()` (whether scheduled-job / event-consumer / queue-worker containers run in-process on Compose), and `language_id()` (the language's open-identity `LanguageId`). The IaC language a provider authors infrastructure in (AWS CDK Python, Azure Bicep) is independent of the generated app's language — AWS pins it in one `_CDK_IAC_LANGUAGE` constant. Shared, language-agnostic provider concerns (the `resolve_runtime_spec` discovery helper, the `runtime_stack_token` composer, and the `PlatformInfrastructure` protocol) live in the **`platform/` subpackage of `datrix-codegen-kernel`** (`datrix_codegen_kernel.platform`, a sibling of `gendsl/`, `dashboards/`, `pooling/`, `secrets/`), the target-neutral layer platforms depend on instead of `datrix-codegen-common`. The shared Grafana `DashboardBuilder` already lives in `datrix_codegen_kernel.dashboards` and platforms import it directly (no re-home, no facade). The platform discovery seam is the existing `PlatformGenerator` + `datrix.platforms` group — there is no separate `PlatformAdapter` type; `PlatformInfrastructure` is a property on `PlatformGenerator` subclasses. See [Platform Subpackage](../../../../datrix-codegen-kernel/docs/platform-subpackage.md) and [Decision 12: Language-Agnostic Provider Generators](../architecture-overview.md#decision-12-language-agnostic-provider-generators-adopted).

---

### Frontend Client Generators (2)

#### 11. datrix-codegen-angular
Generates a TypeScript Angular client from the shared frontend client contract: request/response types, enums, and injectable HTTP services built from the same contract-builder every frontend target consumes. An artifact-phase companion generator — activates only when the application declares a `clients { angular { ... } }` config block. Depends on `datrix-common`, `datrix-codegen-kernel` and `datrix-codegen-common` like every other codegen-* target, plus `datrix-codegen-typescript-core` (#19) for the TypeScript transpiler core and web-client mechanics; imports no backend language generator.

#### 12. datrix-codegen-flutter
Generates the Flutter mobile client's API layer in Dart — models, one client class per API, the exception vocabulary, and the route manifest — from the same shared client contract. An artifact-phase `datrix.generators` plugin, not a language plugin: it activates only when an application's `targets` (or the system `clients { flutter { } }` block) names it. Depends on `datrix-common`, `datrix-codegen-kernel` and `datrix-codegen-common`; imports no backend language generator.

---

### CLI (1)

#### 13. datrix-cli
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
- `datrix-common` (AST model, type system, configuration)
- `datrix-codegen-kernel` (generation framework, generator discovery)
- `datrix-semantic` (the `analyze` stage, push device-registry injection, and `datrix validate`)
- `datrix-language` (parser, CST-to-AST transformers, `ParserProtocol` implementation)
- `datrix-migration` (the migrations stage, the migration state transaction, and the `datrix migrations` commands)
- `datrix-codegen-common` (the migration and generator-inspection commands import migration state and render, the migration CQRS algorithm, and GenDSL definitions lazily inside their command bodies)
- Discovers installed generator *plugins* dynamically (datrix-codegen-python, etc.)

---

### Extension packs (optional)

#### 14. datrix-extensions
Optional package of **domain extension** entry points registered under the `datrix.extensions` group. Each pack contributes language-agnostic scalar definitions, builtin objects, and value struct definitions via the **`value_struct_definitions()`** surface on the `DatrixExtension` protocol, database extension names, extra dependency hints, and optional template directories. **Language-specific type mappings** live in `datrix-codegen-python`, `datrix-codegen-typescript-core` (TypeScript's, shared by the backend and every TypeScript frontend target), `datrix-codegen-kernel` (SQL's `sql_facts`), not in the extension pack (split ownership).

**Current extensions:**

| Entry point | Logical name | Purpose |
|-------------|-------------|---------|
| `postgis` | `postgis` | PostGIS spatial types (`Geometry`, `Geography`), `GeoShape.*` value-level ops, `GeoSql.*` SQL expressions, PostGIS database extension, geoalchemy2/shapely/turf dependencies |
| `geo` | `geo` | Database-independent geospatial raster/tile builtins (`GeoTile.*`, `GeoTiff.*`), value structs (`GeoBounds`, `GeoTileSpec`, `GeoElevationGrid`), Python helper implementations |

**Dependencies:**
- `datrix-common` (protocols, types)

**Installation:** Only required when a project's `system.dtrx` declares `use extension <name>;`. Not a hard dependency of `datrix-cli` or the language generators.

---

### Test harness (1)

#### 15. datrix-testing
The shared test harness every package's suite imports: factories that build real AST objects, fixtures (including the fixture client-target and agents-platform plugins and the shared UI-model graph), assertions, `.dtrx` parsing helpers, pipeline and platform-config helpers, the determinism and semantic-baseline harnesses, and Hypothesis strategies. Every package lists it in its `dev` extra only; it is never a runtime dependency, and no module under any package's `src/` imports it. The `pytest11` feature-tag plugin stays in `datrix-common`, because it loads into every pytest session in the shared venv. See [datrix-testing — Architecture](../../../../datrix-testing/docs/architecture.md).

**Dependencies:**
- `datrix-common`
- `datrix-semantic` (the parsing and semantic-baseline harnesses run the analyzer)
- `datrix-codegen-kernel` (the assertion, I/O, pipeline and determinism helpers build and compare `GeneratedFile`/`Generator` values; the kernel takes this package only as a dev extra)

---

### Migration framework (1)

#### 16. datrix-migration
The RDBMS migration machinery every RDBMS-emitting generator shares: the canonical schema snapshot and revision ledger formats, the schema differ and snapshot-to-snapshot differ, the change policy, deterministic revision ids, the rebaseline builder, the live-snapshot artifact contract, and the migration state store. Target adapters (Alembic, MikroORM, versioned SQL) render their own files from its canonical state. `datrix-common` must never import it; the core names the run's state transaction through the `RunScopedStateCommit` Protocol. See [datrix-migration — Architecture](../../../../datrix-migration/docs/architecture.md).

**Dependencies:**
- `datrix-common`

**Consumers (runtime dependency):** `datrix-cli`, `datrix-codegen-common`, `datrix-codegen-python`, `datrix-codegen-typescript`, `datrix-codegen-sql`.

---

### Semantic analysis (1)

#### 17. datrix-semantic
Semantic analysis over the parsed `Application`: `SemanticAnalyzer` and its declared phase pipeline (stdlib symbol registration, symbol collection, import and reference resolution, field typing, storage resolution, inheritance merge, FK synthesis, index resolution, replay synthesis, type checking, code-body checks, and the domain validators), auth-contract lowering, push device-registry injection, and seed-document validation. It collects diagnostics and fails the pipeline when errors remain. `datrix-common` must never import it; a fact both a semantic phase and a code generator read lives in the core (the stamped cross-service contract is read through `datrix_common.cross_service.contract.get_cross_service_contract`). See [datrix-semantic — Architecture](../../../../datrix-semantic/docs/architecture.md).

**Dependencies:**
- `datrix-common`

**Consumers (runtime dependency):** `datrix-language` (the language server), `datrix-cli` (the `analyze` stage and `datrix validate`), and `datrix-testing` (the parsing and semantic-baseline harnesses).

---

### Generation kernel (1)

#### 18. datrix-codegen-kernel
The target-neutral generation framework every generator shares: the `Generator` / `GeneratedFile` base classes, the Jinja2 template engine, entry-point discovery, the sub-generator registry framework, the cross-language `TypeMappingRegistry`, the shared route and runtime-configuration derivations, the deploy-script machinery and its templates, the framework-header and framework-secret contracts, the GenDSL data model and registries, the service-feature vocabulary every feature gate reads, and the Seed reference datasets. It loads no language-layer, generator, parser, semantic or CLI module: its own import-linter contract forbids them (`TYPE_CHECKING` included) and a fresh-subprocess test proves it at runtime. `datrix-common` must never import it. See [datrix-codegen-kernel — Architecture](../../../../datrix-codegen-kernel/docs/architecture.md).

**Dependencies:**
- `datrix-common`

**Consumers (runtime dependency):** `datrix-cli`, `datrix-codegen-common`, `datrix-codegen-typescript-core`, every language, platform and frontend generator, `datrix-codegen-sql`, `datrix-codegen-component`, and `datrix-testing`.

---

### Language cores (1)

#### 19. datrix-codegen-typescript-core
The TypeScript language core: the transpiler core and its visitors, the language profile and its sub-profiles, the scalar type maps and type resolver, the TypeScript naming and path facts the transpiler binds imports with (block-qualified entity names, NoSQL module paths, MikroORM connection maps, storage-service injections, job handler names), the class-validator field decorators, and the web-client mechanics every browser client emitting TypeScript shares. A library with no entry point, split out of the TypeScript backend so a frontend target emitting TypeScript never depends on the backend language package. It imports none of its consumers: its own import-linter contract forbids them (`TYPE_CHECKING` included) and a fresh-subprocess test imports each module first and proves it at runtime. See [datrix-codegen-typescript-core — Architecture](../../../../datrix-codegen-typescript-core/docs/architecture.md).

**Dependencies:**
- `datrix-common`
- `datrix-codegen-kernel`
- `datrix-codegen-common` (the shared transpiler, profile and algorithms the core builds on)

**Consumers (runtime dependency):** `datrix-codegen-typescript` (the backend) and every frontend target that emits TypeScript (`datrix-codegen-angular` today).

---

### Showcase (1)

#### 20. datrix
Public repository with documentation, examples, and scripts.

### Client artifact outside this registry: `datrix-vscode`

One further repository, `datrix-vscode`, exists and is deliberately **not** one of the
nineteen above: it is the thin VS Code client for the Datrix language server, hosts no
framework tests and no framework code, and its packaging CI proves the published `.vsix`
bundles none of the framework packages. Its **source repository is private; the extension
it publishes to the marketplace is public** — a `.vsix` is a readable archive regardless of
the source repo's visibility, so publishing the extension does not require publishing the
repository. It sits inside the `datrix-*` name glob deliberately, which places it under the
customer-domain isolation gate with no registration step, but that is a backstop, not
substitute governance for a repo the rest of this document's tooling assumptions do not
cover. See [Architecture Overview — Decision 41](../architecture-overview.md#decision-41-datrix-language-server--editor-intelligence-over-lsp-adopted).

---

## Plugin Architecture

Generators and domain extensions load through **setuptools entry-point groups** discovered at runtime (see table). Cross-cutting pieces:

- **Protocols** — Code generators implement `GeneratorPlugin`; platform generators implement `PlatformPlugin`. **Language targets subclass `LanguageGenerator`** (`datrix_codegen_common.generation.language_generator`): `generate()` is `@final` in the base class; subclasses implement **ten abstract methods**. See [code-generation.md](../../../../datrix-common/docs/architecture/code-generation.md#consolidated-generator-infrastructure) in datrix-common.
- **`TypeMappingRegistry`** (`datrix_codegen_kernel.generation.type_mapping_registry`) — each registered language maps canonical `TypeRegistry` types (`global_registry.register_language()` at import time).
- **`LanguageHooks` / `LanguageRuntimeSpec`** — reached as facets of each language's `LanguagePlugin` aggregate (registered under `datrix.languages`, not as standalone entry-point groups): post-write formatting and validation hooks, and infrastructure details for Docker (Dockerfile context, health checks, migration commands), respectively.

### Entry Point Groups

| Group | Purpose | Protocol |
|-------|---------|----------|
| `datrix.generators` | Standalone code generators (SQL, component) registered directly, not via a language bundle | `GeneratorPlugin` |
| `datrix.platforms` | Platform generators (Docker, AWS, Azure) | `PlatformPlugin` |
| `datrix.languages` | Aggregate language plugins (Python, TypeScript) bundling generator, hooks, runtime spec, type mappings, transpiler profile, migration adapter, and gendsl behind one registration | `LanguagePlugin` |
| `datrix.extensions` | Domain extension packs (types, builtins, DB extension names, templates) | `DatrixExtension` |

There is no `datrix.language_hooks` or `datrix.language_runtime_spec` entry-point group — both protocols travel as facets of the one `LanguagePlugin` registered per language (Decision 23, [Architecture Overview](../architecture-overview.md#decision-23-generation-pipeline-and-plugin-coherence-adopted)). The plugin protocols are defined in `datrix-common` (see `datrix_common.plugin.protocol`, `datrix_common.plugin.extension`, `datrix_common.plugin.language_plugin`, `datrix_common.plugin.hook_outcome`); the `LanguageRuntimeSpec` protocol is defined in `datrix-codegen-kernel` (`datrix_codegen_kernel.generation.language_runtime_spec`); the language post-generation hooks protocol is defined once, in the core (`datrix_common.plugin.framework_protocols.LanguageHooksProtocol`). The CLI and pipeline discover every plugin kind — generators, platforms, languages, and extensions — through one `PluginRegistry` discovery path, one cache, and one error family. Users only install the generators they need — no unused dependencies. Install **`datrix-extensions`** only when using `use extension` in `system.dtrx`.

---

## Domain extension system

Domain-specific scalars, builtin objects, and infrastructure hints (for example PostGIS) can ship in **extension packs** instead of bloating `datrix-common`. See the [extensions guide](../../../../datrix-extensions/docs/extensions-guide.md) and the [datrix-common extensions overview](../../../../datrix-common/docs/extensions.md).

### Split ownership

| Layer | Owns |
|-------|------|
| Extension pack (`datrix.extensions`) | Language-agnostic scalar defs, builtin object types, `db_extensions()`, `extra_dependencies()`, `template_dirs()` |
| Each language generator (`datrix-codegen-python`, …) | All **language-specific** type mappings for core **and** declared extensions (for example `PYTHON_EXTENSION_MAPS` in `datrix_codegen_python.type_mappings`, merged by the shared `build_type_map`) |

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

**Messaging:** Topics and **`publish`** events live under **`pubsub`** blocks (whether owned by a service or a **`shared`** block). **`subscribe { … }`** is always a **direct child of `service { }`**, not nested inside `pubsub`. Services declare which other containers they depend on with **`uses SharedOrServiceName : modifiers;`**. Infrastructure blocks navigate to their owner via **`block.container()`** (`Service` or `Shared`). See [datrix-language — Service blocks reference](../../../../datrix-language/docs/reference/datrix-service-blocks.md).

### Extern services (external library interfacing)

An `extern service` declares a **contract** for an external HTTP service that Datrix does not generate code for. The user builds and deploys the external service independently (in any language); Datrix generates a **typed HTTP client** in consuming services and wires **deployment infrastructure** (Docker Compose entry, health checks, environment variables).

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
- **Environment wiring** — `{SERVICE}_SERVICE_URL` injected into consuming services

**Config profiles:** Extern services support two deployment modes via config YAML:
- `deployment: container` — colocated container (development, docker-compose). Requires `image` and `port`.
- `deployment: external` — remote URL, no container managed by Datrix (production). Requires `url`.

**Network:** Extern services are internal-only — not routed through the nginx gateway by default. They serve other Datrix-generated services, not end users.

### Pipeline integration

The high-level flow is: **parse** records extension directives on the AST → **registry / type registry** APIs load and validate packs when invoked → **semantic analysis** and **generators** consume the resulting types and maps. Exact call ordering follows the implementation in `GenerationPipeline` and semantic analysis; language generation always receives declared names via `declared_extension_names(app)` (`datrix_codegen_kernel.generation.language_helpers`).

### Adding a New Language

Adding a new target language (e.g., Go, Rust) requires a new `datrix-codegen-{lang}` package that depends on `datrix-common` and `datrix-codegen-common`. Follow the **consolidated checklist**:

1. Create `datrix-codegen-{lang}` package (depends on `datrix-common` and `datrix-codegen-common`).
2. Subclass **`LanguageGenerator`** — implement the ten abstract methods; wire sub-generators and project-level output through the shared `generate()` implementation.
3. Define a **`LanguageProfile`** instance (`datrix_codegen_common.transpiler.profile`) with the nine sub-profiles (Syntax, Operators, Builtins, Types, Naming, ORM, Scope, Docs, Errors). For C-style languages, inherit from `CBraceSyntaxEmitters`.
4. Wire the **`SharedTranspiler`** from `datrix-codegen-common` with the language profile. Implement an ORM-specific entity query module for the language's framework.
5. Implement **micro-generators** (`MicroGenerator[TContext]` from `datrix_codegen_common`) for each domain, using shared context models.
6. Add **`type_mappings.py`** — map every canonical type; register with `global_registry.register_language()`.
7. Implement **`LanguageHooks`** — post-generation formatting and validation.
8. Implement **`LanguageRuntimeSpec`** — Dockerfile context, healthchecks, DB URL schemes, migration commands, job runner commands, plus the three provider-facing methods (`container_command`, `hosts_consumers_in_process`, `project_language`). The parity gate fails onboarding if any method is unimplemented.
9. Register entry points in **`pyproject.toml`** (`datrix.generators`, and hooks/runtime spec as required).
10. Run parity verification: `validate_profile_completeness(LANG_PROFILE)` and `verify_micro_generator_parity(...)` to detect missing builtins, types, or domain generators.

The shared transpiler algorithm, context builders, and field analysis require **zero new code** — they work automatically with the new profile and micro-generators. See [datrix-codegen-common — Adding a New Language](../../../../datrix-codegen-common/docs/architecture.md#adding-a-new-language) for detailed line counts.

#### Repo integration: what you do *not* have to update

Repo tooling **discovers** packages from disk rather than reading a hardcoded list, so a new `datrix-codegen-{lang}` package joins the following automatically and must never be added to a list by hand:

| Surface | Joins as soon as the package has… |
|---|---|
| `test.ps1 -All`, `status-tests.ps1` | a `tests/` directory |
| `mypy.ps1 -All`, the shared-venv install set (`Get-DatrixPackages`), `dependency.ps1`, dead-code `--all` | a `pyproject.toml` |
| `check-import-boundaries.ps1`, `check-generated-file-ratchet.ps1`, the forbidden-patterns audit, all `--all` scanners (ast-grep, libcst, logic-map) | a `src/` tree |
| `projects.ps1`, the metrics `-All` scripts, `git/commit-and-push.ps1`, the dev scripts fed by `Get-DatrixDirectories` | the directory existing at all (a `.git` for commit-and-push) |
| `check-docs-conformance.ps1`'s package/import-name scope tables | the directory existing at all |

If you find yourself editing a package list to make a new language visible, that list is a bug — convert it to discovery instead. This is the [generality-preserving design rule](../design-principles.md); a hardcoded package list silently stops covering every package added after it was written.

#### Repo integration: what you *must* update

Only genuinely curated, human-authored content needs a deliberate edit:

1. **`ARCHITECTURE_DOC_FILES`** in `datrix/scripts/gates/repo-hygiene/lib/check_docs_conformance.py` — add the new package's `docs/architecture.md`. This tuple is a literal by design (a curated doc set, never a glob), so it is the one registry that does not self-update. Update the doc's own stated file count at the same time.
2. **Package catalogs and counts** — this file (the count in [Repository Architecture](#repository-architecture) and the catalog above), [architecture-cheat-sheet.md](../architecture-cheat-sheet.md) (`## Packages (N)` and its table), and [architecture-overview.md](../architecture-overview.md) (the dependency graph and the install list).
3. **[import-boundaries.md](../../../../datrix-common/docs/architecture/import-boundaries.md)** — confirm the new package is covered by the general "language generators must not cross-import siblings" rule. That rule is stated once, over the whole class, precisely so it does not need an O(N²) row per language pair.
4. **The `datrix.languages` entry-point group** in [datrix-common-api.md](../../../../datrix-common/docs/datrix-common-api.md) — list the new plugin.

Platform generators consume `LanguageRuntimeSpec` via protocol dispatch instead of language-specific branching. See [code-generation.md — Consolidated generator infrastructure](../../../../datrix-common/docs/architecture/code-generation.md#consolidated-generator-infrastructure).
