# Datrix Architecture Overview

**Version:** 2.1
**Last Updated:** June 23, 2026

---

## Introduction

Datrix is a code generation system that transforms `.dtrx` domain specifications into production-ready applications across multiple languages and platforms.

### Key Features

✅ **Template-Based Generation** - Jinja2 templates with automatic formatting
✅ **Fail-Fast Error Handling** - Errors caught at generation time, not runtime
✅ **Multi-Language Support** - Python, TypeScript, SQL, .NET, Java — the language set is open
✅ **Multi-Platform Support** - Docker, AWS, Azure
✅ **Type-Safe** - Exhaustive type mappings with validation
✅ **Modular Architecture** - 14 installable packages (13 core toolchain + optional **datrix-extensions**) plus showcase and projects repos
✅ **Specification-Level Testing** - DSL `test` blocks transpile to pytest under `tests/spec/` (Python) and Jest under `test/spec/` (TypeScript); see the [spec testing documentation](../guide/spec-testing.md)
✅ **Event contracts** - `ensure` clauses on `publish` events enforce publisher-side validation before `dispatch`
✅ **External library interfacing** - `extern service` declarations generate typed HTTP clients and deployment wiring for user-built services
✅ **Serverless block code generation** - `serverless` blocks deploy handlers as Lambda functions, Azure Functions, or container processes with platform-specific entry points and infrastructure provisioning
✅ **Centralized runtime config store** - a system-level `configStore` section generates a runtime configuration plane (AWS AppConfig, Azure App Configuration, or self-hosted Consul KV), local JSON defaults, and Python/TypeScript runtime clients for feature flags and operational tuning without rebuilds
✅ **Zero-environment runtime** - generated services read zero environment variables; all deployment-static values (config-store endpoint, secrets-backend URL, region, credential kind) are baked as literal constants at generation time (see [Decision 14](#decision-14-runtime-configuration--secrets--zero-environment-architecture))

---

## Sub-Documents

This overview was split into focused sub-documents for easier navigation. Each sub-document preserves the original section headings.

- **[Pipeline Flow & Capabilities](architecture/pipeline-and-capabilities.md)** — System architecture, pipeline stages, standard library, phase 01/02/03 capabilities, search engine integration, CDN / content delivery, managed API gateway
- **[Repository Architecture & Plugins](architecture/repository-architecture.md)** — 15 repos (14 installable packages + the showcase repo), plugin system, domain extension system, extern services, application containers, adding a new language
- **[Builtin Traits & Enums](architecture/builtin-traits-enums.md)** — 10 builtin traits, 2 builtin enums, injection mechanism

Related:

- **[Generated Output Stability](generated-output-stability.md)** — the reference-example parity gate: the repo's proof that generated output does not change unintentionally, how to read a failure, and the re-bless command

### Moved section anchors

The following anchors previously lived in this file and are now in sub-documents. Update links accordingly:

| Old anchor in this file | New location |
|------------------------|--------------|
| `#system-architecture` | [pipeline-and-capabilities.md#system-architecture](architecture/pipeline-and-capabilities.md#system-architecture) |
| `#pipeline-flow` | [pipeline-and-capabilities.md#pipeline-flow](architecture/pipeline-and-capabilities.md#pipeline-flow) |
| `#standard-library` | [pipeline-and-capabilities.md#standard-library](architecture/pipeline-and-capabilities.md#standard-library) |
| `#phase-01-capabilities-python-and-docker` | [pipeline-and-capabilities.md#phase-01-capabilities-python-and-docker](architecture/pipeline-and-capabilities.md#phase-01-capabilities-python-and-docker) |
| `#phase-02-capabilities-python-docker-docs` | [pipeline-and-capabilities.md#phase-02-capabilities-python-docker-docs](architecture/pipeline-and-capabilities.md#phase-02-capabilities-python-docker-docs) |
| `#phase-03-capabilities-python-docker` | [pipeline-and-capabilities.md#phase-03-capabilities-python-docker](architecture/pipeline-and-capabilities.md#phase-03-capabilities-python-docker) |
| `#search-engine-integration` | [pipeline-and-capabilities.md#search-engine-integration](architecture/pipeline-and-capabilities.md#search-engine-integration) |
| `#cdn--content-delivery` | [pipeline-and-capabilities.md#cdn--content-delivery](architecture/pipeline-and-capabilities.md#cdn--content-delivery) |
| `#managed-api-gateway` | [pipeline-and-capabilities.md#managed-api-gateway](architecture/pipeline-and-capabilities.md#managed-api-gateway) |
| `#repository-architecture` | [repository-architecture.md#repository-architecture](architecture/repository-architecture.md#repository-architecture) |
| `#plugin-architecture` | [repository-architecture.md#plugin-architecture](architecture/repository-architecture.md#plugin-architecture) |
| `#domain-extension-system` | [repository-architecture.md#domain-extension-system](architecture/repository-architecture.md#domain-extension-system) |
| `#application-containers` | [repository-architecture.md#application-containers](architecture/repository-architecture.md#application-containers) |
| `#extern-services-external-library-interfacing` | [repository-architecture.md#extern-services-external-library-interfacing](architecture/repository-architecture.md#extern-services-external-library-interfacing) |
| `#adding-a-new-language` | [repository-architecture.md#adding-a-new-language](architecture/repository-architecture.md#adding-a-new-language) |
| `#builtin-traits-and-enums` | [builtin-traits-enums.md#builtin-traits-and-enums](architecture/builtin-traits-enums.md#builtin-traits-and-enums) |

---

## Dependency Graph

```mermaid
graph TD
 A[datrix-common]
 B[datrix-language] --> A
 L[datrix-extensions] --> A
 A --> CC[datrix-codegen-component]
 A --> CGC[datrix-codegen-common]
 CGC --> D[datrix-codegen-python]
 CGC --> E[datrix-codegen-typescript]
 CGC --> M[datrix-codegen-dotnet]
 CGC --> N[datrix-codegen-java]
 A --> F[datrix-codegen-sql]
 CGC --> G[datrix-codegen-docker]
 A --> I[datrix-codegen-aws]
 A --> J[datrix-codegen-azure]
 B --> K[datrix-cli]
 A --> K
 CC --> K
 D --> K
 E --> K
 M --> K
 N --> K
 F --> K
 G --> K
 I --> K
 J --> K
```

**Legend:**
- **datrix-common** (no dependencies) — Foundation and generation framework (AST model, type system, semantic analysis, standard library resources + loader protocols, config resolution, plugin protocols, generation framework). Does **not** import `datrix-language` — parser and stdlib-loader implementations are injected via protocols.
- **datrix-language** (depends on datrix-common) — Parser + CST-to-AST transformers, implements `ParserProtocol` and `StdlibParserProtocol` defined in datrix-common
- **datrix-extensions** (depends on datrix-common) — Optional domain packs; **not** required by `datrix-cli` or generators unless you declare `use extension` and install the pack
- **datrix-codegen-common** (depends on datrix-common) — Shared codegen intelligence: profile-driven transpiler, language-agnostic algorithms, context models, field analysis, parity checking, shared Grafana dashboard builder, GenDSL runtime, serverless/replayable-ingestion plans. Consumed by language codegen packages and by **all three** platform generators for its language-agnostic services.
- **Language Code Generators** (depend on datrix-codegen-common, which depends on datrix-common) — Python, TypeScript, .NET, and Java. The set is open: each new target language is one more peer package here, and a language generator never depends on a sibling language package.
- **Other Code Generators** (depend on datrix-common) — SQL, component
- **Platform Generators** (Docker, AWS, Azure) — all three depend on **datrix-codegen-common** for its language-agnostic platform services (GenDSL runtime, shared Grafana `DashboardBuilder`, serverless and replayable-ingestion plans, shared enums) as well as datrix-common. They must **not** import the language-specific parts of codegen-common (`transpiler.*`, language-shaped `context_models`/`algorithms`) or any language generator package — see the [platform → codegen-common subtree contract](../../datrix-common/docs/architecture/import-boundaries.md#platform--codegen-common-subtree-contract).
- **datrix-cli** (depends on datrix-common, datrix-language; owns `GenerationPipeline` orchestration; discovers generator plugins dynamically)

> **`datrix_codegen_common/platform/` subpackage.** A `platform/` subpackage lives **inside the existing `datrix-codegen-common`** — a sibling of `gendsl/`, `dashboards/`, `algorithms/`, and `context_models/`. **No new package or repo is created**: the shared provider seam (the `resolve_runtime_spec` / `runtime_stack_token` helpers and the `PlatformInfrastructure` protocol) is language-agnostic platform code, exactly the layer `datrix-codegen-common` already owns. Because the three platform generators already legally import `datrix-codegen-common`, `platform.*` simply joins the closed list of language-agnostic codegen-common subtrees platforms may import (alongside `gendsl.*`, `dashboards.*`, `algorithms.serverless`, `context_models.serverless`, `context_models.replayable_ingestion`, `enums`) — no new graph node and no new boundary edge. The shared Grafana `DashboardBuilder` **stays in `datrix-codegen-common/src/datrix_codegen_common/dashboards/`** and platforms continue to import it directly; there is no re-home and no `ObservabilityIntegration` facade. See [Shared Provider Library](../../datrix-codegen-common/docs/architecture.md#shared-provider-library-platform) and [Decision 12: Language-Agnostic Provider Generators](#decision-12-language-agnostic-provider-generators).

**Import boundary enforcement:** The dependency edges above are enforced by automated tooling — see [Import Boundaries](../../datrix-common/docs/architecture/import-boundaries.md) for the full rule table and scanner usage. The scanner currently reports a known lower-bound caveat: files carrying a UTF-8 BOM are silently skipped (read with `encoding="utf-8"`), so the violation count is a lower bound until the scanner reads with `encoding="utf-8-sig"`. Fixing that is a tracked scanner-robustness follow-up, separate from the boundary-rule reconciliation.

---

## Core Principles

1. **Fail Fast, Fail Loud** — Catch errors at generation time, not runtime. See [Design Principles](./design-principles.md).
2. **Template-Based Generation with Formatters** — Jinja2 templates with ruff format (Python) / CSharpier (.NET) / google-java-format (Java); TypeScript templates emit pre-formatted output validated via `tsc --noEmit`, no separate formatter. See [Design Principles](./design-principles.md).
3. **Exhaustive Type Mappings** — All type mappings must be explicit; fail if unmapped. See [Design Principles](./design-principles.md).
4. **Immutable AST Model** — The Application model cannot be modified after creation (thread-safe, predictable). See [Design Principles](./design-principles.md).
5. **Single Responsibility** — Each repository has ONE clear purpose (`datrix-common`: AST + framework; `datrix-language`: parser; each codegen: one language/platform).

---

## Technology Stack

### Languages & Frameworks
- **Python 3.11+** - All implementations
- **Tree-sitter** - Parser generation
- **Pydantic v2** - Data validation

### Code Generation
- **Jinja2** - Template-based code generation
- **ruff format** - Python code formatting
- **CSharpier** - .NET code formatting
- **google-java-format** - Java code formatting
- **tsc --noEmit** - TypeScript compile validation (templates emit pre-formatted output; no separate formatter)
- **ruamel.yaml** - YAML generation
- **Transpiler** — `StagePipeline` + `TranspileContext` + `TranspileResult` + visitor protocols (`datrix_common.transpiler`, `datrix_common.datrix_model.visitor_protocols`); see [datrix-common-api — Transpiler modules](../../../datrix-common/docs/datrix-common-api.md#transpiler-modules)

### Code Quality
- **ruff** - Python linting and formatting
- **mypy** - Type checking (strict mode)
- **pytest** - Testing

### CLI
- **Typer/Click** - CLI framework
- **Rich** - Terminal UI

---

## Key Architectural Decisions

### Decision 1: No Separate IR Layer

**Rationale:**
- The parser produces the Application (AST model) directly
- There is no IR layer; the AST model is the single representation
- Fewer transformations means fewer bugs

**Result:** The AST model (`Application`, `Entity`, `Service`, etc.) lives in `datrix-common`. The parser in `datrix-language` produces `Application` objects but the type is defined in `datrix-common`, making the AST available to all packages without depending on the parser.

---

### Decision 2: `datrix-codegen-*` Naming

**Rationale:**
- Shows family relationship (all codegen)
- They extend/specialize `datrix-common`
- User mental model: "codegen for Python"

**Result:**
- `datrix-codegen-python` (not `datrix-generator-python`)
- `datrix-codegen-typescript`
- `datrix-codegen-sql`
- Every new target language joins under the same convention — e.g. `datrix-codegen-dotnet` and `datrix-codegen-java`, both now real generators

---

### Decision 3: One Repo Per Platform

**Rationale:**
- Independent versioning
- Independent releases
- Clear ownership
- Plugin architecture

**Result:** Separate repos for Docker, AWS, Azure

---

### Decision 4: One DateTime Type, Always Timezone-Aware

**Rationale:**
- A timezone-aware datetime and a UTC datetime are the same *type* with different *values* for the timezone component — UTC is just one timezone
- Having separate `UDateTime` / `UDate` / `UTime` types implies UTC is structurally different from other timezones, which it isn't
- Naive datetimes (no timezone info) are almost always a bug in server code
- The Python ecosystem is moving away from naive datetimes; JavaScript's `Date` is always aware

**Result:**
- **`DateTime`** is always timezone-aware. There is no naive datetime in the DSL.
- **`Timezone`** is a builtin object that specifies which timezone. `Timezone.UTC` is the default; `Timezone.of("America/New_York")` for arbitrary IANA timezones.
- **`DateTime.now()`** defaults to UTC (no argument needed). `DateTime.now(Timezone.of("US/Eastern"))` for other timezones.
- `UDateTime`, `UDate`, `UTime` and all aliases (`UTCDateTime`, `DateTimeUTC`, `Instant`, `UTCDate`, `UTCTime`) are removed.
- `DateTime.utcNow()` is removed — it's just `DateTime.now()`.
- `Date` and `Time` remain timezone-unaware (calendar dates and wall-clock times don't carry timezone semantics).

---

### Decision 5: Generator Definition DSL (Implemented)

**Rationale:**
- Generator implementations encode structure (file declarations, iteration patterns, feature gates, semantic requirements) as imperative Python — registries, class constructors, context builders, and template rendering paths
- The same structural information is split across multiple locations, making it hard to answer "what does this generator produce?"
- Feature gates are repeated and sometimes implicit; semantic contracts are not declared adjacent to file emission; context dictionaries are often untyped
- Platform generators cannot reuse the language-generator registry model

**Result:**
- A constrained generator-definition DSL (genDSL) embedded in Python docstrings declares generator structure: identity, domains, feature gates, semantic requirements, iteration scopes, context models, file declarations, and cross-domain contributions
- The genDSL compiles in memory at import time into Python IR objects (`GeneratorDefinition`, `DomainDefinition`, `FileDefinition`, etc.) consumed by the existing generator runtime — no generated source files, no checked-in artifacts
- Python remains the implementation language for context builders, type resolvers, transpilers, and complex algorithms; the genDSL declares structure, Python implements computation
- IR foundation types live in `datrix-common`; the parser, validator, and runtime live in `datrix-codegen-common`; each generator package embeds its own genDSL definitions
- When a generator migrates to genDSL, the entire registry moves at once — no partial migration, no mixed sources, no backward compatibility wrappers
- **GenDSL 2 hardening (adopted and complete, 2026-07-08):** compilation closed — `where`/`when` resolve against typed context models and builder references resolve eagerly at registration, so an unknown property or reference is a load-time error instead of a silent `False`; a `FeatureCatalog` derived from AST block presence and plugin capability declarations replaced the hardcoded `_app_feature_*` executor predicates; declared-file rendering became the only render path, with the `render_declared_files` escape hatch removed and each consumer's hand-coded iteration loop deleted; and parity collapsed to a single derived mechanism (`parity/generated_parity_table.py`), retiring the hand-maintained exemptions, feature-gate, and per-package declaration lists.

**Design reference:** [GenDSL Documentation](../../../datrix-codegen-common/docs/gendsl/overview.md) — Complete specification in datrix-codegen-common/docs/gendsl/. GenDSL 2 hardening: [Design Decisions 14–17](../../../datrix-codegen-common/docs/gendsl/design-decisions.md#decision-14-closed-compilation--typed-context-validation-and-eager-reference-resolution) and [Migration Guide Phase 8](../../../datrix-codegen-common/docs/gendsl/migration-guide.md#phase-8-gendsl-2--closed-compilation-declared-rendering-single-parity).

---

### Decision 6: Deployment Target Contract (Stable)

> **Partially superseded by Decision 15 (Multi-Target Plugin Architecture, adopted) and Decision 044 (Language as a Generation Target, adopted):** `deployment.provider` is no longer a closed enum value set — it is an open, plugin-registry-validated identifier (`ProviderId`; see [datrix-common API — Open identity](../../../datrix-common/docs/datrix-common-api.md#open-identity-languageid--providerid)), and the "Generator orchestration" table below is no longer a fixed lineup — each generator declares a phase and optional `runs_after` names, and the CLI topologically sorts them (`datrix_common.generation.generator_lineup`). `deployment.runtime` is an open, plugin-declared identifier too (`RuntimeId`; each platform declares the runtimes it realizes). Runtime/provider orthogonality is preserved by construction — the two are independently resolved dimensions, and neither resolver takes the other as a parameter. `language` is no longer a config field at all: it is a required generation parameter (`--language`/`-L`) resolved against the registered `datrix.languages` set (`LanguageId`, via `resolve_language_id`) — see Decision 6 below, as amended. The YAML shape and concept matrix below are otherwise unchanged, minus the removed `language` config key.

**Rationale:**
- Legacy models conflated runtime packaging shape, infrastructure provider, and cloud-managed targets into a single dimension
- "Docker Compose" and "ECS Fargate" are runtime/packaging targets, not cloud providers; "AWS" and "Azure" are providers, not runtimes
- One-dimensional models cannot express combinations like "ECS Fargate on AWS" or "Azure App Service on Azure" without overloading terms
- CLI overrides can create partial deployment states where the command line says one target but resolved config still contains values for another

**Result:**
- An explicit deployment target model replaces the single `hosting` dimension with three orthogonal fields:

```yaml
deployment:
  runtime: docker-compose | azure-app-service | azure-app-service-container | ecs-fargate | app-runner
  provider: local | existing | aws | azure
  registry: acr | ecr | ...           # optional, provider-specific
```

- `language` is not part of this config model — it is a required generation parameter (`--language`/`-L`), resolved against the registered `datrix.languages` set via `resolve_language_id`; it selects the generated application implementation. A `language` key in `config/system.dcfg` (base or profile) is a fail-loud error. See the CLI contract below.
- `deployment.runtime` selects the deployable artifact shape (Compose, Azure App Service, ECS Fargate, etc.)
- `deployment.provider` selects the infrastructure provider or substrate owner
- `deployment.registry` is an optional provider-specific refinement
- There is no `target` dimension; cloud deployments use only native runtimes (`ecs-fargate`/`app-runner` for AWS, `azure-app-service`/`azure-app-service-container` for Azure)
- `host` remains a network endpoint concept only — never used to mean AWS, Azure, or Docker

> **Note:** `runtime: azure-container-apps` is **retired**. Use `runtime: azure-app-service` for the native Azure PaaS runtime. Specifying the retired value raises a generation error with migration guidance.

**Construct-mapped realization:** Once a deployment target is resolved, each DSL block maps to the target platform's native primitive. Service deployment shape is derived entirely from declared blocks — no separate per-service runtime selector is needed. See [Design Principles — Construct-Mapped Platform Realization](./design-principles.md#11-construct-mapped-platform-realization-stable) for the full mapping table and rationale.

**Concept matrix:**

| Concept | Examples | Owns |
| --- | --- | --- |
| Language | `python`, `typescript` | Application source code, framework/runtime adapters, language package/dependency files — resolved from the required `--language`/`-L` CLI flag, not deployment config |
| Runtime | `docker-compose`, `azure-app-service`, `azure-app-service-container`, `ecs-fargate`, `app-runner` | Deployable artifact shape and process model |
| Provider | `local`, `existing`, `aws`, `azure` | Provider-managed substrate, registry, identity, networking, managed services |
| Infrastructure flavor | `container`, `external`, `rds`, `flexible-server`, `event-hubs` | Per-block provisioning choice (RDBMS, cache, pubsub, etc.) |
| Host | `db.example.com`, `api.example.com`, `localhost` | Network endpoint |

**Deployment examples:**

```yaml
# Local Docker Compose
deployment:
  runtime: docker-compose
  provider: local

# AWS App Runner
deployment:
  runtime: app-runner
  provider: aws
  registry: ecr

# Azure App Service (native PaaS)
deployment:
  runtime: azure-app-service
  provider: azure
  registry: acr

# AWS ECS Fargate
deployment:
  runtime: ecs-fargate
  provider: aws
  registry: ecr
```

Each example above pairs with a required `--language`/`-L` flag on the `datrix generate` command; language is never read from these config blocks.

**Generator orchestration** becomes multidimensional:

| Deployment | Language generators | Runtime generators | Provider generators |
| --- | --- | --- | --- |
| Python Docker Compose local | `component`, `python`, `sql` | `docker` | none |
| TypeScript Docker Compose local | `component`, `typescript`, `sql`, `python_http_contract_overlay` | `docker` | none |
| Python Azure App Service (code-based) | `component`, `python`, `sql` | none (PaaS, no containers) | `azure` App Service + managed infra |
| Python Azure App Service Container | `component`, `python`, `sql` | `docker` (custom-container delivery) | `azure` App Service + managed infra |
| Python ECS Fargate | `component`, `python`, `sql` | `docker` (containers need Dockerfiles) | `aws` ECS/Fargate/managed infra |
| Python App Runner | `component`, `python`, `sql` | `docker` (image-based PaaS pulls an ECR image) | `aws` App Runner + managed infra |

Provider-native runtimes are produced by their provider generator plus, where the runtime is container-based, the shared `docker` runtime generator supplying Dockerfiles. Container artifacts for the `docker-compose` runtime always come from the `docker` runtime generator, whichever provider is selected: the platform set for a run is the sum of the runtime axis and the provider axis, so the two compose independently. Paired with `local`, no provider generator augments the Compose output, because `local` provisions nothing. Decision 35 adds a second pairing — `azure-vm`, cloud-hosted compute — where the provider emits its own infrastructure alongside unchanged Compose output. For `runtime: azure-app-service` (code-based delivery), the Azure generator produces all infrastructure Bicep and there is no separate runtime generator — no containers are involved. For `runtime: azure-app-service-container`, the Azure generator produces the infrastructure Bicep and the `docker` runtime generator supplies the Dockerfile for the custom-container delivery mode. For `runtime: ecs-fargate`, the AWS generator produces the infrastructure and the `docker` runtime generator supplies per-service Dockerfiles. For `runtime: app-runner`, the AWS generator produces the infrastructure; App Runner's own generated stack pulls an ECR image, so it likewise requires the `docker` runtime generator to supply that image's Dockerfile — App Runner is image-based PaaS, not containerless.

**Explicit config rule:** Defaults are an anti-pattern for deployment generation. Every deployment-relevant field must come from resolved config. Missing required fields must produce explicit errors naming the config path and expected field. Invalid combinations must produce validation errors rather than being corrected silently. No generator may override a user-provided config value.

**Validation rules:** Provider values are scoped by runtime:

| Runtime | Valid providers |
| --- | --- |
| `docker-compose` | `local`; `azure-vm` (Decision 35) |
| `azure-app-service` | `azure` |
| `azure-app-service-container` | `azure` |
| `ecs-fargate` | `aws` |
| `app-runner` | `aws` |

**CLI contract:** Deployment-affecting values are not accepted as one-off CLI overrides. `datrix generate` requires `--language`/`-L` (resolved via `resolve_language_id` against the registered `datrix.languages` set) and reads `deployment` from resolved config. `--hosting` and `--platform` generation-time overrides are removed. Users who need to change deployment target edit config files (or use a `datrix config set-deployment` helper command that writes config explicitly).

**Output path contract:** Generated output paths include language (from the required `--language` flag), runtime, and provider (from resolved deployment config):

```text
.projects/<app>/<language>/<runtime>/<provider>/
```

---

### Decision 7: Extension Naming — PostGIS Split

**Rationale:**
- The current `geo` extension is semantically a PostGIS pack: it owns `Geometry`, `Geography`, `GeoSql`, PostGIS database extension validation, PostGIS migration templates, and PostGIS/geometry runtime dependencies
- Raster helpers (tile grid calculation, GeoTIFF parsing) are database-independent operations that should not inherit PostGIS infrastructure or dependency behavior
- A single `geo` name conflates two distinct concerns: PostGIS-coupled spatial types and database-independent geospatial computation

**Result:**
- The existing PostGIS-backed extension is renamed from `geo` to **`postgis`** with no backward compatibility alias
- The `geo` name is reclaimed for a new generic, database-independent geospatial extension providing raster and tile helpers (`GeoTile`, `GeoTiff`)
- Existing DSL projects that declare `use extension geo;` for PostGIS behavior must update to `use extension postgis;`
- The `DatrixExtension` protocol gains a **`value_struct_definitions()`** surface so extensions can contribute named struct types (e.g., `GeoBounds`, `GeoTileSpec`, `GeoElevationGrid`) in addition to scalars and builtin objects

**Extension ownership after split:**

| Extension | DSL declaration | Provides |
| --- | --- | --- |
| `postgis` | `use extension postgis;` | `Geometry`, `Geography` spatial types, `GeoShape.*` value-level ops, `GeoSql.*` SQL expressions, PostGIS database extension, geoalchemy2/shapely/turf dependencies |
| `geo` | `use extension geo;` | `GeoTile.*` tile grid operations, `GeoTiff.*` raster parsing, `GeoBounds`/`GeoTileSpec`/`GeoElevationGrid` value structs (Python helpers only in Phase 1; TypeScript fails loudly until helper support is added) |

**Core `Geo.*` stdlib** (distance, tile coordinate math) remains unaffected — it is always available without any extension declaration.

---

### Decision 8: Incremental RDBMS Schema Migrations

**Rationale:**
- Generated services with RDBMS entities are deployed with an initial schema migration applied. If a later regeneration rewrites that initial migration to include newly added fields, the live database does not change because migration engines track applied revision IDs, not changed file contents
- Generated application code can then reference columns that do not exist in the deployed database
- Python/Alembic and TypeScript/MikroORM both exhibit this gap: a fixed initial migration file is overwritten on each generation, but once applied, no new migration identity is created for schema changes

**Result:**
- **Canonical schema snapshots** — Language-neutral JSON files (`schema.json`) under `{app_dir}/.datrix/rdbms-migrations/{rdbms_id}/` record the deployed database contract
- **Revision ledger** — An append-only JSON file (`ledger.json`) in the same directory records ordered Datrix revision IDs and database-agnostic canonical migration operations
- **RDBMS UUID identity** — Every `RdbmsConfig` in ConfigDSL requires an `id: UUID` field. This UUID is the canonical migration identity, independent of service name, block alias, profile, engine, platform, or output directory
- **Immutable migration history** — Once generated, a migration revision file is append-only. Later generations append new revisions; they never rewrite previous revisions
- **Append-only file retention** — `GeneratedFile` gains a `retention` field (`"normal"` or `"append_only"`). `FileWriter` and manifest logic preserve append-only files across regenerations and reject content changes
- **Shared diff and safety policy** — Schema changes are classified as `safe`, `risky`, or `blocked` before adapter rendering. Destructive changes (field/table removal, rename, type narrowing, enum removal) are generation errors — no ConfigDSL or CLI override converts them to automatic migrations
- **Target-language adapter protocol** — `RdbmsMigrationAdapter` in `datrix-codegen-common` defines the contract. Python/Alembic, TypeScript/MikroORM, Java/Liquibase, dotnet/FluentMigrator, and SQL are adapters that render target-native migration files from shared canonical state
- **Shared-owned RDBMS migrations** — Shared RDBMS blocks generate migration files under `SharedPaths.rdbms_dir`, not under a consuming service. Platform generators create one migration apply unit per shared `rdbms_id`

**State ownership:** The migration orchestrator owns snapshot/ledger lifecycle. Adapters render target-native files from `MigrationState` but do not load, write, or allocate revision IDs. Canonical state (`schema.json`, `ledger.json`) lives under the application source folder and is target-language/platform/engine agnostic.

**Reference:** [RDBMS Migration Decisions (D1-D23)](rdbms-migration-decisions.md) | [Migration API](../../../datrix-common/docs/architecture/migration.md) | [Adapter Protocol](../../../datrix-codegen-common/docs/migration-adapter.md)

---

### Decision 9: Centralized Runtime Config Store

**Rationale:**
- ConfigDSL (`.dcfg`) resolves configuration at generation/deploy time and bakes it into generated code, env vars, Compose files, and cloud infrastructure. That cannot support operational changes that must happen without rebuilding and redeploying an image: feature flags and kill switches, rate-limit/TTL/retry/timeout tuning, per-environment overrides of the same artifact, and secret-rotation coordination
- Datrix needs to generate the runtime config-store infrastructure, initial values, access permissions, and language-specific runtime clients while preserving the existing static ConfigDSL pipeline
- A runtime config plane must not become a backdoor for secrets — it stores only non-sensitive values and *references* to secrets, never secret values

**Result:**
- A system-level `configStore` section is added to existing **system** ConfigDSL. No application DSL grammar change is introduced — the runtime plane is purely an infrastructure + generated-client capability. The resolved object attaches to `app.system.config.config_store` via `SystemConfigProfileConfig.config_store` (`ConfigStoreConfig | None`)
- `configStore` is **additive and gated**: services receive a generated runtime client only when `configStore` is present; apps without it produce byte-equivalent output (no client files, no new env vars, no config-store infrastructure). It does **not** replace service/system `.dcfg` — ConfigDSL remains the source for generation-time and deploy-time configuration. The config store adds runtime-mutable keys only
- **Supported engines (initial set):** AWS AppConfig (`engine: aws-managed`, `platform: managed`), Azure App Configuration (`engine: azure-managed`, `platform: managed`), and self-hosted Consul KV for Docker (`engine: consul`, `platform: container` or `external`). Parameter Store and etcd are future extensions
- **Centralized compatibility validation:** engine/platform/provider combinations are validated in `datrix-common` during system config resolution, using the resolved deployment runtime/provider plus config-store engine/platform. Unsupported combinations fail loud with diagnostics naming runtime, provider, engine, and platform. Generator-side `GenerationError` guards remain as a defensive backstop. There is no silent fallback from cloud config to local JSON — local defaults are client startup data, not an infrastructure substitute
- **Generated clients** (Python and TypeScript) share one conceptual API: `start/stop/refresh`, typed scalar accessors (`get_bool/get_int/get_float/get_string`), `get_namespace`, and `get_secret_ref`. The dynamic API is the public contract; generators also emit typed namespace/key constants (Python frozen constants, TypeScript `as const` + literal types) but no per-key accessor methods. Behavior: cache seeded from generated defaults, remote values merged over defaults profile-by-profile, unknown namespace/key access raises, single background poll task per process, and explicit fail-open (log-and-continue) vs fail-closed (fail startup / raise on refresh) semantics
- **Secrets boundary:** keys may declare a `secretRef` (provider + name/path + optional version) — a non-sensitive pointer. Scalar accessors raise for `secretRef` keys; only `get_secret_ref` returns reference metadata. Actual secret values resolve through generated secret-manager access code (Vault, Azure Key Vault, AWS Secrets Manager, env). Secret-manager read permissions are generated from declared secret references, not from arbitrary runtime values. Raw secret-looking defaults are rejected using the same placeholder/secret hygiene as extern-service config
- **Feature-flag profiles** (`kind: featureFlag`) may contain only `Boolean` keys and render to provider-native feature-flag shapes (AppConfig feature flags, Azure feature-management content type); non-Boolean runtime values use `kind: freeform`

**Engine compatibility matrix:**

| Deployment target | aws-managed (AWS AppConfig) | azure-managed (Azure App Configuration) | consul container | consul external |
| --- | --- | --- | --- | --- |
| Docker/local | invalid | invalid | supported | supported |
| AWS provider | supported | invalid | invalid | supported |
| Azure provider | invalid | supported | invalid | supported |

**Reference:** [Config Store Schema](../../../datrix-common/docs/config-store.md) — `ConfigStoreConfig` schema and validation rules

---

### Decision 10: Database Drift Detection & Reconciliation

**Rationale:**
- The migration engine is purely source-driven and offline: every revision diffs a **recorded** baseline (`schema.json`) against a **desired** snapshot built from the AST. It never consults the live database — deliberate, so generation runs in CI without DB access, but it leaves the engine blind to the actual deployed schema
- When a database is changed out-of-band (manual hotfix during troubleshooting, restored backup, partially-applied migration, parallel environment), the recorded baseline `R`, the live schema `L`, and the desired schema `D` diverge silently. The engine plans `R → D` and applies it against a database already at `L`, colliding with the out-of-band edits
- This is a generic framework gap, not a per-project problem: any Datrix project whose database drifts from the recorded baseline hits it

**Result:**
- **Live snapshot is a third source of `RdbmsSchemaSnapshot`** — an environment-side exporter (where the DB is reachable) reflects the live catalog into a portable, hash-verified `live-schema-snapshot.json`. Datrix imports the artifact offline; the entire existing diff → classify → allocate → ledger pipeline is reused unchanged
- **Datrix never connects to a live database** — generation and the new `drift`/`reconcile` commands accept only `--live-snapshot <path>`; credentials, connection strings, and reachability stay in the deployment environment
- **Shared canonicalization** normalizes both source-built and imported live snapshots (implicit/backing indexes, PK-derived constraints, default-literal formatting, type aliasing, identifier casing, index column ordering) so equivalent schemas canonicalize to zero drift
- **Read-only drift detection** — `datrix migrations drift --live-snapshot` reports `diff(recorded R, live L)` classified, exits non-zero when drift exists (CI-guard friendly), and never writes the ledger or DB
- **Append-only reconciliation** — `reconcile --adopt` appends an `adopted` revision whose after-state is `L`, sets `R := L`, and records live-snapshot alignment separately (a sibling of the `adapter-alignment.json` precedent), running no DDL; `reconcile --to-desired` emits `diff(L, D)` as a reconciliation revision with destructive entries `blocked` exactly as in source-driven generation — no override flag
- **Adopt records reality; converge generates DDL** — adopting an observed dropped column documents fact (safe); regenerating one away is gated by `change_policy` (blocked). The ledger gains an `"adopted"` classification and an explicit non-DDL `adopt_live_schema` operation (schema version bumped)
- **Policy split** — a per-environment selector (default off) makes production treat drift as a guard (detect & refuse, never auto-reconcile) while pre-prod gains the reconcile loop. First reflector scope: Postgres, MySQL, MariaDB (MariaDB routes through the MySQL-family reflector, matching the existing dialect mapping)

**Reference:** [RDBMS Migration Decisions D24–D29](rdbms-migration-decisions.md#database-drift-detection--reconciliation-d24d29) | [Migration API](../../../datrix-common/docs/architecture/migration.md)

---

### Decision 11: Typed Inter-Service Calls & Dependency Resilience Policy

**Rationale:**
- A cross-service call is an RPC against another service's endpoint contract — the network is where type safety matters most — yet the call surface carried the provider's HTTP **path as a string argument** (or, worse, no route at all), so a typo, stale path, or wrong-typed value became a runtime 404/422/500 instead of a generation error, and a pathless positional call could silently resolve to the wrong endpoint
- Cross-service responses were untyped `JSON`, so every consumer hand-wrote shape validators against the same peer shapes
- Resilience was keyed on the dependency/path rather than the endpoint operation it actually invokes, and was either mechanically tied to the call or expressible only as per-service config repetition — there was no operation-level policy (a failed cache write could fail a route whose source of truth already committed; a rate-limit counter could fail open)
- A single `/health` endpoint conflated process liveness, readiness, and degraded-but-serving states, so deployment probes could not distinguish them

**Result — two coupled pillars that land together:**

**Pillar A — Typed, named inter-service call surface.** Cross-service callability is bound to the explicit internal-API boundary:
- A custom endpoint is cross-service-callable **if and only if** it is marked `access(Service)`. A service-facing custom endpoint **must** carry a name (placed after the HTTP method, like a function name); external-facing endpoints (`public`, `access(authenticated)`, role-gated) carry no cross-service name and are unreachable as RPCs. Exposing an endpoint to peers is the deliberate act of marking it `access(Service)`, never a side effect of naming — so a peer can never invoke a user-facing endpoint and bypass its end-user authorization context
- The cross-service identity is `(HTTP method, name)`. Callers invoke a custom endpoint as `Service.Block.<method>.<name>(args)` and a resource (auto-CRUD) endpoint as `Service.Block.<db>.<Entity>.<op>(args)`, with typed arguments (positional then named) and **no route string**. Endpoint identity is a stable contract; the `@path`/URL is a deployment detail that can change without breaking callers
- The string-path, interpolated-path, and pathless positional forms are removed outright (no backward-compatible alias)
- A named call's static type is the provider's declared return type, surfaced in the caller as a generated, validated **response struct** (transitive type closure; only `-> JSON` endpoints stay untyped), eliminating hand-written boundary validators

**Contract registry.** A cross-service endpoint contract registry — keyed by endpoint identity, not route — is built at generation time as a **complete, consistent, content-pinned snapshot** of every transitive dependency, and is consumed identically by validation and codegen. A missing dependency contract is a distinct, actionable diagnostic (regenerate the dependency first), never confused with a genuinely-absent endpoint; resolution never binds against a stale provider revision.

**Pillar B — Application-level dependency resilience policy.** Resilience is a property of the dependency, declared once and applied everywhere; the generator never synthesizes values and never auto-classifies operations:
- A `dependencyPolicy` section under `resilience` declares per-dependency-kind (`cache`, `rdbms`, `pubsub`, `objectStorage`, `service`, `extern`) availability, health severity, and operation-level `onFailure` behavior. A safe baseline is authored **once at the application level** (a `defaults` block every dependency of that kind inherits); an individual dependency overrides only where it differs
- A policy-managed operation, or a `service` dependency that has inter-service calls, left uncovered at every level is a generation error (`RESILIENCE_POLICY_REQUIRED`) — nothing is invented to fill the gap. Degradation applies only where the author declared it and the operation semantics permit (e.g. a cache write may degrade only when known to run after the source-of-truth commit)
- Every typed inter-service call routes through a generated **per-dependency resilient client** driven by that policy. Timeout, circuit breaker, and bulkhead are non-amplifying and stay on; **retry is off by default** and enabled only when the provider endpoint is marked `idempotent` (HTTP `GET` is not a safe proxy for idempotency), and even then is bounded by a retry budget and suppressed while the breaker is open
- Generated services expose `/live` (process liveness), `/ready` (required dependencies), and `/health` (detailed, including degraded optional dependencies) with distinct semantics; deployment probes point at `/ready`. The prior single-`/health` contract is replaced outright

**Reference:** [Pipeline & Capabilities — Inter-service typed calls and dependency resilience](architecture/pipeline-and-capabilities.md#phase-02-capabilities-python-docker-docs) | [Design Principles — Explicit Over Implicit / Configuration Boundary](./design-principles.md#7-explicit-over-implicit)

---

### Decision 12: Language-Agnostic Provider Generators

> **Widened by Decision 15 (Multi-Target Plugin Architecture, adopted):** the language-agnostic `LanguageRuntimeSpec` consumption pattern described below is now one part of a full `PlatformPlugin` aggregate — bundling descriptor, generator, infrastructure, `PlatformCapabilityDeclaration`, and the new symmetric `PlatformRuntimeSpec`, which lets language generators consume platform-declared runtime facts (trigger bindings, secrets access, startup execution) instead of hardcoding provider branches. The `LanguageRuntimeSpec`/`PlatformInfrastructure` contract described below is unchanged and remains accurate.

**Rationale:**
- Provider generators (AWS, Azure) were coupled to the target language in a way runtime generators (Docker) were not: Docker discover the language via the `LanguageRuntimeSpec` protocol and ask it for language-appropriate commands, while AWS branched on the `Language` enum inline and hardcoded Python idioms (CDK stack language, scheduled-job command), and Azure hardcoded the App Service `gunicorn … uvicorn` startup command and `PYTHON|…` `linuxFxVersion`
- Consequence: a new target language required editing every provider generator independently, and a new provider had to re-derive language handling from scratch instead of inheriting it
- There was no shared home for provider-level, language-agnostic concerns (config resolution, observability integration, networking/auth/managed-service provisioning), so each provider re-implemented them

**Result:**
- **Language is discovered, never branched.** Every platform generator obtains language-specific runtime details from `LanguageRuntimeSpec` via `discover_language_runtime_spec(target_language)`, exactly as Docker do. Zero `Language`-enum branches and zero `language_name == "…"` string comparisons remain in any platform package's application-wiring code (Docker, AWS, Azure)
- **The `LanguageRuntimeSpec` protocol gains language-agnostic methods** (default-free abstract declarations, implemented in `datrix-codegen-python` and `datrix-codegen-typescript`, covered by the parity gate), including: `container_command(service, package_name) -> list[str]` (the single source of truth for how the HTTP service starts — consumed both as Azure App Service's `startup_command` and as the source every `datrix-codegen-docker` Dockerfile `CMD` is rendered from on both clouds, so the same service starts identically regardless of hosting mode), `hosts_consumers_in_process() -> bool` (whether the language runs scheduled-job / event-consumer / queue-worker containers in-process on Compose), and `language_id() -> LanguageId` (the language's own open-identity `LanguageId`, replacing a silent string→enum fallback). `health_check_endpoint` is **not** added — the readiness path is the shared, language-neutral `HTTP_HEALTH_CHECK_PATH = "/ready"` constant
- **IaC language ≠ application language.** The language a provider authors its infrastructure artifacts in (AWS CDK Python, Azure Bicep) is independent of the generated application's language. A TypeScript app deployed via AWS still gets Python CDK stacks; the CDK references a TypeScript container command obtained from the runtime spec. AWS collapses its three Python-IaC string constants into one named `_CDK_IAC_LANGUAGE` constant documenting this invariant
- **The `datrix_codegen_common/platform/` subpackage** (inside the existing `datrix-codegen-common`, a sibling of `gendsl/`, `dashboards/`, `algorithms/`, `context_models/` — **not a new package**) is the shared home for provider-level concerns that are language-agnostic and shared by ≥2 platforms: the `resolve_runtime_spec(context)` discovery helper (raises `GenerationError`, never falls back to Python), the `runtime_stack_token(lang_spec, runtime_version)` `LANG|VERSION` composer, and the `PlatformInfrastructure` protocol. The shared Grafana `DashboardBuilder` already lives in `datrix_codegen_common/dashboards/` and platforms import it directly — no re-home, no facade
- **`PlatformInfrastructure` protocol** (`@runtime_checkable`, in `datrix_codegen_common/platform/`) expresses provider-level infrastructure surfaces — `network_topology(app)`, `service_to_service_auth(app)`, and `provision_managed_service(block, block_kind, service)` — exposed as a `platform_infrastructure` property on each `PlatformGenerator` subclass. Every platform implements the **full** protocol: clouds fully; Docker return explicit no-op value objects (`NetworkTopology.none()`, empty `ManagedServicePlan`) — honest "no VPC/IAM" facts, never silent stubs. Value objects (`NetworkTopology`, `ServiceAuthModel`, `ManagedServicePlan`) are frozen Pydantic models in `datrix_codegen_common/platform/`, keeping provider concepts out of the AST model
- **The platform seam is the existing `PlatformGenerator` + `datrix.platforms` entry-point group** — discovered via `discover_platforms`. No new `PlatformAdapter` type is introduced. `PlatformInfrastructure` and the shared `DashboardBuilder` are *consumed by* `PlatformGenerator` subclasses, never a competing discovery contract. A new provider implements a `PlatformGenerator` subclass + a `PlatformInfrastructure` implementation, and *consumes* the shared `DashboardBuilder` (`datrix_codegen_common.dashboards`) and `LanguageRuntimeSpec` — language support is free

**Reference:** [Repository Architecture — Platform Generators](architecture/repository-architecture.md#platform-generators-3) | [Import Boundaries — Platform → codegen-common subtree contract](../../datrix-common/docs/architecture/import-boundaries.md#platform--codegen-common-subtree-contract)

---

### Decision 13: Managed Identity Provider Integration

**Rationale:**
- Every production application needs authentication, but Datrix previously generated only self-managed JWT validation (a static configured public key) plus role-based `access(role)` checks. Users had to hand-build the rest: a `User` entity with `passwordHash`, password hashing, login/register endpoints, token minting, refresh tokens, and MFA — error-prone, insecure by default, and repeated in every project.
- The generated auth path had concrete foot-guns: a static public key instead of a JWKS endpoint (no key rotation), a transitive `ROLE_HIERARCHY` that implicitly widened authorization, and self-minted tokens — all properties of the local-auth model rather than a managed identity provider.
- Authentication ("who are you") belongs to a managed identity provider (Cognito, Microsoft Entra, Zitadel); the application should validate provider-issued tokens, not own credentials, sessions, or token issuance.

**Result — managed identity replaces manual authentication (no backward compatibility):**

- **DSL is semantic, config is operational.** An `identity { provider <name> config('<path>') { … } }` block declares logical provider names, application-visible identity fields (type-first, e.g. `String company;`), and `group "<provider-local>" as <datrixRole>` mappings. Operational settings (MFA, password policy, social login, token lifetime, callback/logout URLs, tenant/realm/pool, claim paths) live only in the referenced provider `.dcfg` file. The provider *type* lives in config, not `.dtrx`.
- **Unified `auth(...)` protected-surface contract.** Every externally reachable REST/GraphQL/WebSocket/webhook/externally-invokable-serverless surface resolves exactly one effective `AuthContract`. Forms: `auth(public)`, `auth(required, providers: […])`, `auth(optional, providers: […])`, `auth(required, providers: […], roles: […])`, `auth(service, providers: […])`, `auth(webhook)`. `providers: [...]` is a **set** (issuer selects the provider; no fallback order); `roles: [...]` is **any-of** with **no transitive hierarchy**. Non-public, non-webhook modes require an explicit provider list — there is no application default provider and no implicit public default. `auth(webhook)` instead requires a mandatory `verify(...)` contract whose scheme authenticates the external sender: a generic `hmac` scheme covers arbitrary senders, with a provider registry retained as a convenience for well-known signature formats (e.g. Stripe, GitHub, Slack).
- **`AuthContract` replaces `AccessLevel` + `Endpoint.required_roles`/`Endpoint.access_level`.** The legacy `AccessLevel` enum, the `Endpoint.access_level`/`Endpoint.required_roles` fields, and the `is_public`/`is_service_facing`/`is_authorized()` predicates in `datrix-common` are **deleted, not adapted**. The transformer's modifier-string + `@authorize`-decorator access handling lowers to a frozen `AuthContract` (`mode`, `providers`, `roles`, `principalTypes`, `surfaceId`, `delegation`, `profile`, `verify`). The generated auth code drops `ROLE_HIERARCHY`/`_expand_roles` — a deliberate forward-only break: a token previously passing a check only via transitive role inclusion no longer passes unless it carries the literal role.
- **Provider is the source of truth; the stable local id is deterministic by default.** Datrix never mints primary tokens. It validates provider tokens via issuer/audience/client/JWKS. The stable local user id is resolved by an explicit per-provider `localIdentity` strategy carried in the plan: the **default `deterministicUuid5`** computes `userId = uuidv5(c9a255a1-350b-4414-beb9-7f06f7dfd92d, "<provider>:<sub>")` — stateless, uniform across services, UUID-shaped, no tables and no first-auth upsert. The frozen namespace is defined once in `datrix-common` and read from the plan by both codegens (never redeclared). Server-side profile attributes + cross-IdP account linking are an **opt-in** feature: declaring `profileProjection { enabled = true; profileStore = <service>; }` selects `localIdentity = projected` **unless every field the block declares is `owner = "app"`** — such an all-app-owned block stays on its normal local-identity mode (`deterministicUuid5` for a human/customer realm) and injects no `IdentityProfile`/`IdentityLink`. A block with any `owner = "provider"` field, or an enabled block with no fields, resolves to `projected` as before, injecting the Datrix-managed `IdentityProfile` (+ `IdentityLink` keyed `(providerName, providerSubject)`) into the single **explicitly declared** store and upserting on first auth. Store resolution is fail-loud — a `projected` resolution with an unresolvable `profileStore` is a generation error, never a silent runtime disable. **Decision-13 amendment (write-back):** app-owned fields (`owner = "app"`, `syncOnAuth`) instead write the application's values into the provider's user metadata, which the provider re-surfaces as a token claim on the next authentication. Providers on the default path inject no identity tables; per-request attributes come from validated token claims (with `required` identityFields enforced 401-at-the-edge), and tenancy is app-owned via onboarding. Account linking is explicit and verified; weak email-only linking is forbidden.
- **Opinionated per-target providers.** Docker → Zitadel (provisioned with project/organization import, clients, groups/roles, social providers — Google, GitHub, generic-OIDC); AWS → Cognito User Pool (app-level, per-service app client); Azure customer → Microsoft Entra External ID, Azure workforce → Microsoft Entra ID, Azure machine → user-assigned managed identity (app registration via the Microsoft Graph Bicep extension, never a `deploy-identity.sh` stub). `provider self` (`ProviderPlanEntry.mode="self"`) is a Datrix-managed Zitadel issuer realizable on Docker targets — Docker reuses existing Zitadel provisioning; a self-host Zitadel instance on a cloud target (AWS/Azure) raises a `GenerationError` (external mode must be used to consume a remotely-hosted Zitadel). `mode: external` consumes issuer/JWKS/audience/client and provisions nothing. A capability matrix in `datrix-common` is the authoritative source for supported `(providerType, target, feature)` combinations; unsupported combinations fail loud.
- **Structured versioned provider plan.** A `config/generated/identity-providers.json` artifact (schema owned by `datrix-common`, one per application+environment) carries providers, surfaces, role/attribute mappings, revocation mode, and `*_SECRET_REF` names. Runtime guards resolve provider per surface by issuer from `plan.surfaces[surfaceId]` — never a hardcoded provider name. A non-secret public-client metadata artifact (`identity-client-<provider>.<env>.json`) is the only supported input for frontend login config. Secrets are logical secret-handle references only (reusing the declared `secrets` table + raw-secret hygiene), wired to platform-native secret stores; raw secrets never appear in source, manifests, logs, or docs.
- **Security-sensitive defaults fail closed.** Auth/JWKS-refresh failures, authorization-bearing cache reads/deletes (revocation, role mappings, identity links), and revocation checks reuse the existing `dependencyPolicy` model with `onFailure="raise"`/`"deny"` only (the model has no `fallback`). Error bodies are opaque (RFC 7807) and never leak issuer/audience/client/role/claim detail; structured reason codes go to logs only. WebSocket auth uses fixed close codes (4401 auth-failed/expired, 4403 forbidden) and clears membership/`Auth.*` state on expiry.

**Enforcement (managed-only):** Authentication issuance is provider-owned, end to end. The `Auth` issuance builtin (`generateToken`/`verifyToken`/`hashPassword`/`verifyPassword`/`generateOtp`/`generateApiKey`/…) is **removed wholesale** — the only recognized authentication is a provider-issued token validated through `auth(...)`, and a provider (external *or* `provider self`) owns issuance. The Decision-13 `Auth.*` context views (`Auth.isAuthenticated`/`subject`/`identity.*`) are generated runtime, not that builtin, and stay. Non-authentication cryptography (signing, hashing, HMAC, secure random, opaque keys) belongs to the pre-existing `Crypto` builtin — the sanctioned non-auth surface, which produces signed/hashed data and never confers an `Auth.*` principal. Enforcement extends the existing legacy-auth-conflict and identity validators (`LegacyAuthManagedOnlyValidator`, `IdentityDanglingProviderValidator`, etc. — removed-issuance-builtin diagnostics, dangling-provider checks, a best-effort hand-rolled-auth heuristic) — no new validator class. The Python first-party local-validation short-circuit (`_validate_local_issuer_token`, the `iss == JWT_ISSUER` path) is removed; `provider self` tokens validate through the standard provider-plan/JWKS path like any provider (TypeScript never had such a path).

**Runtime libraries (defaults, behavior is the contract):** Python (FastAPI) uses `pyjwt[crypto]` + `PyJWKClient` + `httpx`; TypeScript (NestJS) uses `jose` (`createRemoteJWKSet` + `jwtVerify`). The current Python template already uses PyJWT, so the change is JWKS-based validation with `kid` rotation, not a library swap. Symmetric algorithms and `alg: none` are always rejected.

**External-product caveats (verify before implementing):** Microsoft Entra External ID being the forward consumer-identity path and the Microsoft Graph Bicep extension's availability/API, the provider claim paths (Cognito `cognito:groups`, Zitadel `urn:zitadel:iam:org:project:roles`, Entra `roles`), runtime library maintenance/API surface, the WebSocket private-use close-code range, and platform handshake-header capabilities rest on external product knowledge as of the 2026 cutoff and are not verifiable from the Datrix repo.

**Cross-design boundaries:** The WebSocket design depends on this design for protected-handshake identity and consumes the shared identity plan (it owns transport/routing/rooms). The Config Store (its `secretRef` handle references) and resilience (`dependencyPolicy`) subsystems are reused, not owned here.

**Licensing note (Docker IdP — Zitadel):** Zitadel v3 is licensed under AGPLv3, whereas its predecessor (Keycloak) was Apache-2.0. Datrix deploys Zitadel as an unmodified, standalone server consumed only over standard network protocols (OIDC/OAuth2). AGPLv3's copyleft obligation attaches to *modifications of the Zitadel source code* that are conveyed or served over a network — it does not reach into the separate generated application that merely consumes Zitadel's network API. Because Datrix neither modifies Zitadel nor distributes its source, no copyleft obligation propagates into generated application code. Operators who fork and modify Zitadel itself take on AGPLv3 obligations for their fork; that is outside the scope of Datrix-generated apps.

**Reference:** [API Auth Contracts](../../../datrix-language/docs/reference/access-levels.md) | [Semantic Validators — Identity](../../../datrix-common/docs/architecture/semantic-validators.md)

---

### Decision 14: Runtime Configuration & Secrets — Zero-Environment Architecture

**Rationale:**
- Prior generated services read runtime connection parameters and secret-backend endpoints from environment variables (`DATRIX_CONFIG_STORE_ENDPOINT`, `AZURE_KEY_VAULT_URL`, `AWS_REGION`, `ENVIRONMENT`, `AWS_SECRET_PREFIX`, etc.), creating an implicit contract that endpoints, regions, and credential mechanisms were supplied by the deployment orchestrator at container start.
- Earlier config/secret hardening addressed `.dcfg` path-containment and secret-ref allowlist hygiene at generation time, but assumed this env-injection contract for runtime endpoint delivery.
- Env-based endpoint injection is fragile: a misconfigured env var silently falls back to library defaults (boto3 reads `AWS_REGION`; `DefaultAzureCredential` walks the full credential chain including environment credentials), the deployment manifest and the application code have no shared schema, and environment variable injection cannot be statically verified at generation time.

**Result — generated services read ZERO environment variables:**

- **Bootstrap constants (`config/_bootstrap.py`)** are baked at generation time as `typing.Final` literals. They encode every deployment-static value the service needs to reach its config and secrets backends:

  | Constant | Kind | Purpose |
  |---|---|---|
  | `PROVIDER` | `str` | `"LOCAL"` / `"AZURE"` / `"AWS"` |
  | `CREDENTIAL_KIND` | `str` | `"azure-managed-identity"` / `"aws-instance-role"` / `"mounted-file"` |
  | `ENVIRONMENT` | `str` | Deployment environment label |
  | `REGION` | `str \| None` | Cloud region / location; `None` for LOCAL |
  | `CONFIG_STORE_ENDPOINT` | `str \| None` | Azure App Configuration URL or Consul endpoint; `None` for AWS / LOCAL |
  | `SECRETS_STORE_ENDPOINT` | `str \| None` | Azure Key Vault URL; `None` for AWS / LOCAL |
  | `SECRET_PREFIX` | `str` | Prefix applied to logical secret handles |
  | `CONFIG_FILE_PATH` | `str \| None` | Mounted JSON config file path (LOCAL only) |
  | `SECRETS_DIR_PATH` | `str \| None` | Mounted secrets directory path (LOCAL only) |
  | `CREDENTIAL_FILE_PATH` | `str \| None` | Mounted credential file path (LOCAL only) |

  None of these are read from environment variables at service startup. The module imports only `typing`.

- **No-environment credential provider (`config/_credentials.py`)** selects the credential mechanism via the baked `CREDENTIAL_KIND` constant and constructs credentials without consulting any environment variable:
  - `"azure-managed-identity"` → `ManagedIdentityCredential(exclude_environment_credential=True)` — never walks the `DefaultAzureCredential` chain; IMDS only.
  - `"aws-instance-role"` → `boto3.client(service, region_name=REGION)` — always passes the baked region; never reads `AWS_REGION` or `AWS_DEFAULT_REGION`.
  - `"mounted-file"` → reads the baked `CREDENTIAL_FILE_PATH` constant; no env lookup.

- **Config store (`connections` namespace + optional application profiles)** is the runtime source for non-secret scalars (host, port, database name, broker addresses, peer-service base URLs). The backend is selected from `PROVIDER` / `CONFIG_STORE_ENDPOINT`:
  - LOCAL: `FileConfigBackend` reads the baked `CONFIG_FILE_PATH`.
  - Azure: `AzureAppConfigBackend` authenticates via the managed-identity credential and contacts the baked `CONFIG_STORE_ENDPOINT`.
  - AWS: `AppConfigBackend` uses the instance-role boto3 client with the baked `REGION`.
  - Cloud backends receive provisioned config values — including managed-backend hosts assigned at deploy time — via the config store rather than via environment variables. LOCAL deployments receive these values from the mounted config JSON file baked at `CONFIG_FILE_PATH`.

- **Secrets backend (Key Vault / Secrets Manager / file)** resolves credentials by logical handle. The backend, endpoint, and naming policy are baked constants in `config/secrets_resolver.py`:
  - Azure: Azure Key Vault via `SECRETS_STORE_ENDPOINT` + managed-identity credential.
  - AWS: Secrets Manager via the instance-role boto3 client + baked `REGION`. (The `aws-ssm` value no longer exists as a `SecretBackend` member.)
  - LOCAL: file backend reads from `SECRETS_DIR_PATH`; no network, no credentials.
  - The `env` backend is realizable only on the Docker/local platform (declared in that platform's `supported_secret_backends`, rendered as compose `.env` substitution); it is not a member of the AWS or Azure platform's supported backends, so selecting it there **fails at generation time**.
  - Generated services emit exactly **one** secret API — the canonical `config/secrets_resolver.py`. The obsolete `secrets_manager` package (and any provider-specific runtime secret-manager modules) is not emitted; all generated consumers call the canonical resolver directly.

- **`AppSettings` (frozen at startup)** is assembled once during the lifespan `startup` phase by `assemble_settings(config_client, secrets_resolver)`. It composes connection strings from the config-store `connections` namespace (non-secret parts) plus `SecretsResolver` (credential parts). No connection string, endpoint URL, or secret value is baked at generation time; all are composed at startup from the two runtime sources. `get_settings()` raises `RuntimeError` if called before `assemble_settings()` completes — there is no silent default or fallback.

**Canonical resolution stack (from baked constants to running service):**

```
Generation time
  └─ RuntimeBootstrap baked into config/_bootstrap.py (Final literals; no env)

Service startup
  1. _bootstrap.py constants — available at import time; no action required
  2. Config client start — connects to backend using baked PROVIDER / CONFIG_STORE_ENDPOINT
  3. Secrets resolver — backend / endpoint / naming policy baked; no startup fetch
  4. assemble_settings() — reads connections namespace + resolves credential secrets
  5. Engine / client init — uses composed AppSettings fields (URLs already have secrets embedded)
```

**Single planning pipeline (one plan, many renderers).** The deployment-static decisions that feed generation are computed **once** from the resolved ConfigDSL model into an immutable `ResolvedRuntimePlan`, and every renderer translates that plan into target syntax — no renderer decides what is secret, reclassifies config keys, or re-derives secret names:

```
.dcfg ConfigDSL + deployment profile
        └─ ResolvedRuntimePlan  (immutable; built once)
             ├─ SecretReferenceManifest  → Python runtime constants, AWS/Azure/Docker provisioning, IAM/RBAC scopes
             ├─ ConfigSeedPlan           → AWS AppConfig, Azure App Configuration, local config-store artifact
             ├─ RuntimeBootstrap         → baked bootstrap constants + credential factories
             └─ InfraSettingsPlan        → target-specific non-secret infrastructure settings
```

- **`SecretReferenceManifest`** is the single generated list of logical handles and their rendered backend references. Each `SecretReference` carries `logical_handle`, `backend`, `rendered_name`, `runtime_ref`, `provision_ref`, `required`, and value-free `consumer_paths` — and **never** a `value`/`secret_value`/`default`/`example`/`sample`/`plaintext` field. The backend name is built once (handle + deployment policy prefix/separator, composed per service); renderers and IAM/RBAC scopes consume the same reference. For Python it is emitted as data-only constants in `config/_secret_manifest.py` (no I/O, no env reads).
- **`ConfigSeedPlan`** is the single source of truth for what may be written to a config store. Each key is classified once — `ConfigScalarSeed` (non-secret static), `FeatureFlagSeed`, `ConfigSecretMetadata` (points to a handle, no value), `DeploymentExpressionSeed` (resolved by target infra at deploy time), or `OmittedConfigSeed` (no safe generation-time value, with an explicit reason). Renderers must not reclassify; an unrecognized seed type **fails generation**. Config stores carry non-secret values and secret metadata only — never secret values.
- **`InfraSettingsPlan`** holds non-secret infrastructure settings a target platform needs outside the application config model (service name, App Configuration endpoint app setting, Key Vault reference strings, platform routing flags) — distinct from application config, and never an application secret/config source.
- **Generation fails closed** on: an `env` secret backend for service runtime; service-level `secretsStore` runtime-placement fields (non-secret naming/layout belongs in the deployment-profile `SecretBackendPolicy`, not per-service); a missing required handle that cannot be rendered; and an unknown seed/reference type.

**Supersede note:** This supersedes the earlier env-injection contract and the prior `service-config` docs that assumed env-var delivery of endpoints and regions. The generation-time hardening that contract came with (`.dcfg` path-containment, secret-ref allowlist, fail-open default hardening) is unaffected and still holds. The zero-env runtime model — now with a single planning pipeline feeding all renderers — is the canonical Datrix architecture from this point forward.

**Reference:** [Deployment and Runtime Bootstrap](../../../datrix-common/docs/deployment-runtime-bootstrap.md) | [Secret Backend Policy](../../../datrix-common/docs/secret-backend-policy.md) | [Runtime Bootstrap — Python](../../../datrix-codegen-python/docs/runtime-bootstrap.md) | [AppSettings and Startup Assembly](../../../datrix-codegen-python/docs/app-settings.md) | [SecretsResolver](../../../datrix-codegen-python/docs/secrets-resolver.md) | [Config Store Schema](../../../datrix-common/docs/config-store.md)

---

### Decision 15: Multi-Target Plugin Architecture — Open-World Targets, Derived Conformance (Adopted)

**Rationale:**
- Datrix already had the skeleton of an open architecture (entry-point discovery, protocol contracts) but closed-world identity and policy undermined it: target identity lived in central enums (`Language`, `ProjectLanguage`, `DeploymentProvider`) and target policy lived in hand-maintained tables and if-chains across the shared layers — adding a language touched 11 packages, adding a platform touched 8 mandatory shared-layer files before the new package existed
- Language↔platform abstraction was asymmetric: platforms consumed languages through a protocol (`LanguageRuntimeSpec`), so adding a language never touched platform packages, but languages consumed platforms through hardcoded provider branches, so adding a platform edited every language package
- Decision logic ("what to emit") was re-decided per target and duplicated, policed only by hand-authored conformance that had already drifted — structural parity checks silently skipped TypeScript's jobs/cqrs output, and no cross-provider realization conformance existed at all

**Result:**
- One self-describing `LanguagePlugin` aggregate per language, registered once under `datrix.languages`; the five formerly-separate language entry-point groups and every central language registry (`GENERATORS_BY_LANGUAGE`, both `_TARGET_KIND_MAP`s, `_KNOWN_DEFINITION_MODULES`, the CLI migration-adapter factory) are derived from the discovered plugin set and their hardcoded forms deleted. See [datrix-common API — LanguagePlugin](../../../datrix-common/docs/datrix-common-api.md#languageplugin)
- One `PlatformPlugin` aggregate per platform under `datrix.platforms` (the existing group, widened), bundling descriptor, generator, infrastructure, `PlatformRuntimeSpec`, and `PlatformCapabilityDeclaration`
- **Open identity:** `Language`/`ProjectLanguage`/`DeploymentProvider` enums are deleted, replaced by validated `LanguageId`/`ProviderId` resolved against the discovered plugin registry (`datrix_common.plugin.identity`); an unknown target fails loud, listing installed plugins
- **Declared ordering:** each generator declares a phase and optional `runs_after` names on its descriptor; the CLI topologically sorts (`datrix_common.generation.generator_lineup`), replacing the hardcoded lineup tuples; companion generators (e.g. `python_http_contract_overlay`) declare an activation predicate instead of membership in another target's tuple
- **Capability declarations replace every central policy table:** `PlatformCapabilityDeclaration` (`datrix_common.plugin.capability`) replaces the default-secret-backend table, the valid-runtimes-by-provider table, the serverless-compute-model table, the notification-realization table, and the aws/azure flavor-gate twins — each platform owns its column; one generic validator in `datrix-common` asks the selected platform plugin for its realization
- **Symmetric platform contract:** `PlatformRuntimeSpec` (`datrix_common.plugin.platform_runtime_spec`, implemented per platform, consumed by language generators) exposes named capability negotiation, so language packages no longer hardcode provider branches for trigger bindings, secrets access, and startup execution
- **Decision/rendering split completed:** "what to emit" computation lives in `datrix-codegen-common` as data-driven engines over AST + plugin declarations; leaf packages own syntax only; the import-boundary allowlist (`import-boundary-allowlist.toml`) is empty
- **Conformance derived, never hand-authored:** the hand-authored `DomainContract`/`DOMAIN_CONTRACTS` registry is deleted; conformance is derived from per-plugin declarations instead — an absent declaration is an error, and a per-package self-consistency gate verifies declaration ↔ registration ↔ fixture output (see [datrix-codegen-common architecture — Derived Domain Parity Table](../../../datrix-codegen-common/docs/architecture.md#derived-domain-parity-table-structural-verification)); platform `block_realizations` are validated the same way, giving cross-provider drift detection that did not exist before
- The conformance kit ships as `datrix_codegen_common.testkit` behind a `[testkit]` extra, consumed by every target package as a dev-dependency; a target package is "integrated" when the kit passes in its own repo
- `datrix-codegen-sql` is an independent artifact plugin activated by the presence of declared `rdbms` blocks regardless of target language; `python_http_contract_overlay` has its own activation predicate under the same activation-by-declared-need pattern
- Repo topology is unchanged — the 12-repo split stays; shared-layer changes affecting multiple packages remain coordinated multi-repo trains under the existing cross-surface impact rule

The design's seven end-state invariants (I1–I7) hold today as executable gates — see [Architecture Cheat Sheet — Multi-Target Plugin Architecture](architecture-cheat-sheet.md#multi-target-plugin-architecture) for the invariant table and the exact check commands.

**Reference:** [datrix-common API — LanguagePlugin, Open identity, PlatformCapabilityDeclaration, PlatformRuntimeSpec](../../../datrix-common/docs/datrix-common-api.md#languageplugin) | [Import Boundaries](../../../datrix-common/docs/architecture/import-boundaries.md) | [datrix-codegen-common architecture — Derived Domain Parity Table](../../../datrix-codegen-common/docs/architecture.md#derived-domain-parity-table-structural-verification)

---

### Decision 16: Declaration-Driven Service Ingress (Adopted)

**Rationale:**
- A service's network exposure (public / gateway-fronted / internal / none) was decided by per-platform heuristics, not declarations: Azure force-classified any service whose name contained "ingestion" as internal, overriding an explicit per-service `gateway {}` declaration; Docker decided whether a gateway existed at all from `len(app.services) > 1` and host-published every service unconditionally; AWS published every serverless `@path` handler on its own ad-hoc public API regardless of any declaration
- The declaration this exposure needs already exists one layer down: every REST and serverless HTTP endpoint carries a mandatory, explicit `auth(...)` contract, and `auth(service)` already means "reachable exclusively via the authenticated inter-service call surface, never as an end-user HTTP request" — so exposure is a derivable fact, never a new config key. Exposure is also profile-invariant (a public API is public in every environment), ruling out a `.dcfg` key as the right layer

**Result:**
- **Ingress exposure is DERIVED, never declared, name-inferred, or count-inferred.** A service's network exposure — public, gateway-fronted, internal, or none — is derived from the per-endpoint `auth(...)` contracts on its HTTP surface plus the presence of the system `gateway {}` declaration
- **The classification.** `auth(service)` is the sole east-west (machine-only) mode; `auth(public)`, `auth(optional)`, `auth(required)`, and the new `auth(webhook)` are external-caller (north-south) surfaces. A service whose HTTP surface is entirely `auth(service)` derives `internal`; any external-caller endpoint (or a `graphql_api`) makes it `gateway`-fronted when the system declares a `gateway {}`, else its own `public` edge; a service with no HTTP/GraphQL surface at all derives `none`
- **Resolution-attached, single read path.** The `ServiceIngressExposure` classification is homed in `datrix_common/datrix_model/ingress.py` and attached as `Service.resolved_ingress` during config resolution — the same resolution-attached-derived-attribute pattern as `resolved_tracing_level` — and every platform generator reads `resolved_ingress` and nothing else, replacing Azure's name-based classifier, Docker's service-count heuristic, and AWS's unconditional per-handler public API

**Reference:** [Service Ingress Exposure — concept reference](../../../datrix-common/docs/reference/service-ingress-exposure.md) | [Access Levels — `webhook` mode and `verify(...)`](../../../datrix-language/docs/reference/access-levels.md#mode-webhook) | Per-platform realization: [Azure](../../../datrix-codegen-azure/docs/architecture.md) (§ Derived Service Ingress) | [Docker](../../../datrix-codegen-docker/docs/docker-compose.md) | [AWS](../../../datrix-codegen-aws/docs/aws-generator-api.md)

---

### Decision 17: Documentation Conformance Gate (Adopted)

**Rationale:**
- Architecture documentation accumulates repo-relative path references (to source files, other docs, scripts) that silently rot as the tree is refactored; nothing previously re-verified those references stayed resolvable, so broken documentation links could ship indefinitely unnoticed

**Result:**
- **Documentation conformance is an executable gate.** A repo-level validation script — of the same class as the other repo-level gate scripts under `datrix/scripts/test/` — extracts repo-path references from the permanent architecture documentation trees and fails when a reference no longer resolves, checked against a committed exceptions baseline for references that are intentionally external or not yet resolvable

---

### Decision 18: Platform Decision-Engine Consolidation and RealizationDSL (Adopted)

**Rationale:**
- Eight decision families were reimplemented per platform package: provisioning dispatch, capability/flavor tables, secret renderers, preflight/runtime-requirements wiring, baseline alarms/alerts, dashboards, zero-environment provisioning context, and pooling. Each platform's dispatch ladder (`if block_kind == "rdbms"/"cache"/"pubsub"/"nosql"/"storage"`, ending in a hard error) was a second, hand-kept copy of the very capability table the platform already declared, so adding a resource type or policy meant editing the same logic by hand in two or three packages, kept in sync only by review discipline
- Roughly half of the platform packages' code sat in a handful of mega-modules: naming, SKU tables, role types, and runtime resolution flattened into single files well past a reviewable single-concern size, and one platform's capability declaration was embedded inside its general-purpose context-bag generator instead of living with its own type
- Two `language_id.value == "python"/"typescript"` branches survived in the Azure platform package (App Service runtime-stack selection, server-side-build requirement) even though the same decisions were already expressed the right way — as capability queries — by the Docker platform package via `LanguageRuntimeSpec`; the branch-free path already existed and simply hadn't been generalized to every platform
- Infrastructure-as-code authoring had drifted into three different styles across the platform packages: untyped Python source rendered through Jinja templates, a typed builder facade over declarative templates, and a hand-indented YAML template — despite the same package already building the equivalent structure natively elsewhere. Nothing constrained which style a future platform would adopt

**Result:**
- **RealizationDSL: capability cells drive provisioning dispatch.** Each platform's `(block_type, flavor)` capability cell — built on the existing typed `PlatformCapabilityDeclaration`/`BlockRealization` types, which continue to live one layer below in `datrix-common` and are consumed, never owned, by the platform layer — gains a plan-builder binding. One generic dispatcher in `datrix_codegen_common/platform/` replaces every platform's `if block_kind ==` ladder; an undeclared cell fails loud with that platform's own declared reason string, and bindings resolve and signature-check at plugin registration, so compilation stays closed. RealizationDSL is a typed-data mini-DSL, not a textual grammar — its authoring unit is a table cell, so no new parser or grammar is introduced; the loader and dispatcher live in `platform/`, one layer above the base cell types they consume
- **The eight duplicated decision families become provider-parameterized engines** in `datrix_codegen_common/platform/`: provisioning dispatch, capability tables, secret renderers, preflight/runtime-requirements wiring, baseline alarms/alerts, dashboards, zero-environment provisioning context, and pooling each collapse into one engine that every platform parameterizes with its own tables (SKU/engine maps, resource-type strings, metric names and thresholds, backend enums) and templates — never with re-derived scaffolding. This follows the standing rule that shared layers ask and target plugins answer
- **Zero language-name branches survive in any platform package.** Two new parity-gated `LanguageRuntimeSpec` capabilities — an App Service runtime-stack composer and a server-side-build-requirement query — are implemented by every language plugin, so a platform package asks the language plugin instead of branching on a language name
- **Mega-modules are decomposed along the domain taxonomy generator definitions already use** (managed database, cache, pub/sub, document store, storage, observability, identity, pooling, gateway), and each platform's capability declaration moves to live with its own type instead of inside a general-purpose context-bag module
- **Infrastructure-as-code authoring converges on one style: declarative modules behind a typed builder facade.** Azure's existing `BicepBuilder` pattern — typed `build_*` call sites over declarative per-resource templates — becomes the target for every platform. AWS migrates its CDK stacks off untyped Python-source-through-Jinja to typed data serialized into CDK Python source, with the generated project's `cdk bootstrap && cdk deploy` deploy contract left unchanged; Docker's compose file switches from a hand-indented Jinja template to structured YAML serialization of the dict it already builds. No future platform may introduce another authoring style
- **Rejected alternatives:** keeping the per-platform dispatch ladders as a "defensive backstop" once capability cells drive dispatch was rejected — two copies of one truth is the defect being fixed, not a safety net. A textual realization grammar for RealizationDSL was rejected because the authoring unit is a table cell, not free text; a validating loader over typed data gives the same closed-compilation guarantee with far less surface. Platform-side per-language lookup tables were rejected in favor of the two new `LanguageRuntimeSpec` capabilities, because language facts belong with the language plugin, not the platform layer. A new shared package for the eight consolidated engines was rejected because the platform layer already owns language-agnostic provider concerns and every platform package already imports it legally. For the AWS migration specifically, dropping the CDK toolkit in favor of an in-process, typed CloudFormation object model was rejected: it would change the generated project's visible deploy contract and would require building a typed CloudFormation object model that does not exist anywhere in the codebase today — the existing deploy contract was treated as a hard constraint, so the migration changes only how the CDK source is produced (typed data serialized to source, replacing template-driven source generation), never the deploy step itself

---

### Decision 19: Language Decision-Engine Consolidation and EmitDSL (Adopted)

**Rationale:**
- Each language package reimplements the same decision logic in its Stage-3 transpiler tree — dozens of structurally identical functions (builtin-category preference, entity-query dispatch, special-call classification, NoSQL-chain parsing, statement/control-flow dispatch) differing only in type-name literals — because the transpiler skeleton lives entirely inside each language package instead of a shared, data-parameterized layer; the one place this was already fixed (endpoint orchestration collapsed onto a shared orchestrator for one language package while the other still re-implements it locally at nearly eight times the line count) proves the shared-skeleton pattern works everywhere it hasn't been applied yet
- Provider knowledge — which notification/search/other provider maps to which template, dependency list, or field-type schema — is embedded as name conditionals inside the language packages instead of being queried from the platform plugin that actually provisions the resource, so the same cloud-SDK schema (a search service's field-type map, for example) ends up hand-duplicated across multiple packages with an in-source comment admitting it "mirrors" the real owner
- The shared transpiler seam types lie about their own neutrality: the shared result type carries a language-specific type field and boolean flags shaped for one language's runtime primitives, and the shared context type carries fields named for one specific cache backend — so every future language package inherits dead, wrongly-shaped fields, and a shared visitor skeleton cannot be built honestly on a seam that still names one language's runtime
- Templates duplicate the same structural blocks — import banners, guard clauses, pagination and error envelopes — inline across hundreds of per-language templates with almost no shared macro library, and a large slice of the identically-named generator-file pairs across the language packages are per-domain test generators reimplementing the same decision logic once per language

**Result:**
- **One shared Stage-3 transpiler visitor/dispatch skeleton, N emit-table sets.** The shared traversal and decision core — call classification, builtin-category preference, entity/NoSQL-chain parsing and dispatch selection, gateway-profile dispatch, statement/expression walking — moves into `datrix_codegen_common/transpiler/`, parameterized by the existing `LanguageProfile` plus EmitDSL's emit tables. A language package supplies emit-string tables, a type-name adapter, ORM call shapes, and import synthesis — and no `visit_*` control flow of its own. Import boundaries are unaffected: platform packages remain barred from `transpiler.*`
- **EmitDSL: typed per-language emit-table declarations.** The per-language builtin/operator emit decisions the skeleton consumes — which builtin category, which chain step, which emit function — are declared as typed data validated against the closed builtin registry at plugin registration, extending the existing language-profile/builtin-mapping declarative seam with the family discipline: closed compilation (an unmapped builtin or a dangling emit reference fails at registration, never at generation time) and declarations drive execution. EmitDSL is a typed-data mini-DSL, not a textual grammar — its authoring unit is a table row
- **Language-neutral transpiler seams.** The shared transpile-result type loses its language-specific type field and boolean runtime flags in favor of a generic artifact-flags mapping that each language plugin declares and populates, merged through the existing artifact-merge machinery; the shared transpile-context type gains a generic context-extension slot that a language plugin populates with its own per-language extension state (a cache extension, for example) instead of the shared type carrying another language's fields by name. Neither shared seam type may carry a field shaped for one language's runtime or one backend's naming — the shared types become true to their contract before the skeleton is built on them
- **Provider knowledge exits the language packages.** Every provider-name conditional in a language package is replaced by a query to the resolved platform plugin through the existing platform-capability/realization-context seam: notification-provider choice drives template and dependency selection, search-index context, secrets-access shape, and trigger bindings as platform-provided data that language templates consume — never a provider-name branch inside a language package. A cloud-SDK schema such as a search service's field-type map gets exactly one owner: the platform package that provisions that resource, never re-derived inside a language package
- **Shared test-generator generators and a shared macro library.** The parallel per-domain `*_test_generator` pairs collapse into shared generators in `datrix-codegen-common` — decision logic lives once, the template stays per language. A shared Jinja macro library (import banners, comment headers, guard clauses, pagination and error envelopes) starts absorbing the inline template conditionals, and outsized templates split along the same domain lines as their generators. Template *bodies* stay per-language — this is factoring, not sharing
- **Rejected alternatives:** a per-language visitor base-class hierarchy was rejected — inheritance re-creates the exact drift this consolidation fixes; data parameterization matches the already-landed `LanguageProfile` pattern instead. A textual emit grammar for EmitDSL was rejected — the authoring unit is a table row, not free text, and typed data is mypy-checked and diff-friendly in a way a grammar would not be. A shared "integrations" package owning provider maps was rejected — the platform plugin that provisions a resource owns its facts, the same standing division of ownership every platform package already follows. Sharing template bodies across language packages was rejected — bodies are genuinely language-specific; only their decision logic and structural macros are shared

---

### Decision 20: Sealed, Generated AST Model (Adopted)

**Rationale:**
- The AST model is documented as immutable ("frozen (Pydantic v2), generators are read-only") but `Node` is a plain mutable class wired via `setattr`, with no `__slots__`, `__setattr__` guard, or freeze step; semantic analysis mutates the tree in place (owner wiring, FK synthesis, inheritance merge, replay synthesis) with no boundary marking when mutation must stop. The result is no defense against accidental generator-side mutation, silent phase-ordering bugs, and hashing/caching that cannot be trusted
- Node classes are generated at runtime through `_meta.py`'s `model_class(...)` factory and `@model` decorator machinery, checked only because a hand-maintained `mypy_plugin.py` re-implements the generated `__init__`/`add_*`/`get_*` signatures as a second, manually-synced source of truth; every model module additionally duplicates `if TYPE_CHECKING` stub classes for the same generated shapes, degrading IDE navigation and refactoring across the node graph
- `Service` is a god object — accessors, a dozen-plus `add_*` mutators, a dozen `_merge_*` methods, and hashing all on one class — and the package carries hundreds of function-level imports (concentrated in the same container module) and hundreds of `TYPE_CHECKING` blocks used as circular-import workarounds that obscure the real dependency graph

**Result:**
- **Build-then-sealed AST (D1).** Parse/transform and semantic analysis operate on a mutable build view of the tree; `SemanticAnalyzer.analyze()` ends by **sealing** it through a recursive `__setattr__` guard on `Node` (cheap — one flag check per assignment). Every generator receives a sealed `Application`, and any post-seal mutation raises immediately — a hard error from the start, not a warning, since every surfaced mutation site is a latent phase-ordering bug being fixed rather than a case to relax the guard for. The documented principle changes from "frozen Pydantic v2" (false) to the seal contract (true and enforced); see [Design Principles — Immutability](design-principles.md#4-immutability-adopted-build-then-sealed)
- **Checked-in generated node classes retire runtime metaprogramming (D2).** The `_meta.py` spec declarations become inputs to a code generator whose output — real, readable node-class source carrying the seal guard — is committed to the tree, checked by `mypy --strict` directly. A regenerate-and-diff drift gate, the same staleness-detection pattern already used for the tree-sitter grammar hash, keeps the committed source and the spec in lockstep and fails any hand edit. `mypy_plugin.py` and every `if TYPE_CHECKING` stub duplication in the model package are deleted
- **Container god-object decomposition (D3).** `Service` splits into a thin data node holding block collections, a `ServiceMerger` owning the `_merge_*` methods (multi-file service merging is an assembly concern, not a node concern), and a query/lookup facade for the accessor surface; `Application` receives the same treatment where its own method surface warrants it
- **Structural layering fails CI on regression (D4).** Once D2/D3 land, the intra-package layering (types → `datrix_model` → semantic → config → generation/transpiler) is encoded in the existing import-linter contract, and the deferred function-level imports move back to module top under a ratchet: a frozen baseline that may only monotonically decrease, the same pattern already used for the provider-conditional-literal baseline
- **Rejected alternatives:** full frozen-dataclass reconstruction was rejected — it would rewrite every semantic phase to get the same enforced guarantee the seal gets far more cheaply. Documenting the model as mutable instead of fixing it was rejected — immutability past analysis is the property the whole generation layer relies on. Keeping runtime metaprogramming and improving the mypy plugin was rejected — the dual source of truth is the defect, not the plugin's fidelity; tooling should check real code. A one-shot cycle refactor across the whole package was rejected in favor of the import ratchet, which lets each area migrate with the work that already touches it

**Reference:** [Design Principles — Immutability](design-principles.md#4-immutability-adopted-build-then-sealed) | [datrix-common architecture — AST Parent Containment](../../../datrix-common/docs/architecture/ast-parent-containment.md) | [datrix-common architecture — Import Boundaries](../../../datrix-common/docs/architecture/import-boundaries.md)

---

### Decision 21: Declarative Semantic Pipeline (Adopted)

**Rationale:**
- `SemanticAnalyzer.analyze()` ran roughly 20 analysis phases (register stdlib symbols → collect symbols → resolve imports → resolve references → field types → storage → inheritance → FK synthesis → replay synthesis → type check → code bodies → domain validators → annotate calls) as a hardcoded call sequence. Ordering was implicit in source order: no phase declared its prerequisites, prerequisites could not be introspected or tested, and adding a phase meant finding the right line to insert it
- Domain validators sat in a fixed positional list whose correctness depended on comment-documented order; reordering could silently break an inter-validator dependency, and a validator's prerequisites could not be verified in isolation
- The orchestrator reached into one validator's private method to build the cross-service contract registry and hand it to later consumers — a hidden side product of one validator rather than a declared artifact of the pipeline
- The largest domain validators had grown size-imbalanced and low-cohesion, well past a reviewable single-concern size
- Generator ordering had already been migrated from a hardcoded lineup to declared phases plus `runs_after` with a topological sort (Decision 15's "Declared ordering," `datrix_common.generation.generator_lineup`); the semantic pipeline had the identical shape of problem with no equivalent fix

**Result:**
- **Phases declare `requires`/`produces`; order is derived.** Each analysis phase becomes a registered phase object declaring the artifacts it requires and the artifacts it produces — the symbol table, resolution tables, storage bindings, the inheritance closure, the cross-service contract registry, and the other intermediate structures the phases already pass today. A topological sort derives execution order — the same mechanism as the landed generator topo-sort (Decision 15) — and a missing producer or a dependency cycle is a load-time error naming the phases involved, never a silently wrong order
- **A typed, keyed artifact store carries the intermediate structures between phases.** Phases read and write declared artifacts through the store instead of passing them ad hoc; in test mode the store gates reads by declaration, so a phase reading an artifact it never declared as a requirement fails the test rather than silently working because of accidental ordering
- **Per-validator declarations replace the positional `_VALIDATORS` list.** Each domain validator declares its required artifacts, plus `runs_after` only where a genuine validator-to-validator ordering exists. Registration order is derived from the declarations, and comment-encoded ordering is deleted
- **The cross-service contract registry becomes a declared phase artifact.** It is built by its own phase and consumed by validators and later stages through the artifact store; the orchestrator no longer reaches into a validator's private method to obtain it
- **God validators split along their declared artifacts.** The largest validator modules decompose into per-concern validators, each with its own declaration. Splitting follows the declared artifact graph, not line count
- **Non-goals:** no change to diagnostics shape, validator semantics, or analysis results — this is a structural migration of ordering and artifact flow, not a behavior change. Parallel execution becomes possible once every phase declares its artifacts explicitly, but this decision does not turn it on
- **Rejected alternatives:** keeping the imperative call sequence with better comments was rejected — comments are already the mechanism this replaces, and they are untestable. A numbered priority field per validator was rejected — a number re-encodes position without stating *why* a validator must run where it does; a declared dependency states the reason. Promoting the private registry-building method to a public validator method was rejected — building the cross-service contract registry is not validation, it is producing an artifact, and the artifact store is where produced artifacts belong. Splitting the god validators by line count alone was rejected — cohesion follows the declared artifact graph, not file size

**Reference:** [datrix-common architecture — Semantic Validators: Declarative Semantic Pipeline](../../../datrix-common/docs/architecture/semantic-validators.md#declarative-semantic-pipeline-adopted)

---

### Decision 22: Open-World Identity Providers and Infrastructure Flavors (Adopted)

**Rationale:**
- The open-identity migration landed for languages and providers, but the identity subsystem, the six infrastructure `*Flavor` value sets, and the deployment-runtime axis remained closed-world: central enums plus a hand-maintained capability matrix indexed by `(provider type, deployment target)`, so adding a target, identity provider, flavor, or runtime meant editing foundation-package enums and a central table — exactly the add-a-target-touches-shared-layers coupling the plugin migration removed everywhere else
- Two contradictory target-modeling philosophies lived in one package, so every contributor had to learn which pattern applied where

**Result:**
- Identity capability moves into each platform's capability declaration (a declared `(identity provider type, feature)` support set — its own section, not forced into the block-realization cell shape); one generic validator asks the selected platform plugin, and the central `CAPABILITY_MATRIX`/`_MATRIX_INDEX`/`_SET_FEATURES` table and the hardcoded self-host-IdP-on-cloud special case are deleted (that rule becomes an ordinary undeclared cell with a reason string)
- `ProviderType`, `DeploymentTarget`, the six `*Flavor` enums, and the deployment runtime become registry-validated open identifiers resolved against the installed plugin set (the language/provider identifier pattern); a deployment target is derived from the resolved provider, and unknown values fail loud listing installed plugins and their declared support. The identity planner consumes declarations and identifiers instead of enum-keyed tables and decomposes along provider-plan concerns
- Language/platform separation is preserved: the closed `.dcfg` identity-config enums are unchanged (a non-goal), with their translators retyped only at the boundary where they meet the now-open capability types
- **Rejected alternatives:** a dedicated identity-capability registry separate from platform declarations (re-fragments the established mechanism); generating the enums from plugins at build time (still a central artifact that regenerates on install); per-kind flavor registries (the cells already exist in the platform declarations — one source)

---

### Decision 23: Generation Pipeline and Plugin Coherence (Adopted)

**Rationale:**
- The generation pipeline's `run()` threaded a mutable result through stages of which only a subset ran through the uniform timing/error harness; six logically-equal stages ran inline with three different termination shapes, stage names were scattered string literals, and one registered stage was a timed, logged no-op
- The orchestrator pulled private attributes off generators with `getattr` (an untyped contract invisible to type-checking and plugin authors), plugin discovery ran through two separate paths with two caches and two error families, and correctness-dense god modules (manifest/retention writes, a multi-subcommand migrations module, a dual adapter/legacy migration orchestrator) concentrated the highest-risk logic

**Result:**
- The pipeline becomes an ordered registry of `Stage` objects with uniform timing, error wrapping, and declared skip conditions; `run()` reduces to walking the registry; the three termination semantics collapse to raise-or-complete plus one typed `EarlyExit` outcome; the no-op stage is deleted
- Generators return a typed `GeneratorOutput` carrying what the side-channels smuggled (migration artifacts, prune prefixes, audit tracker, bootstrap consumption); the `getattr` probes are deleted and the contract appears in the plugin protocol. All plugin groups discover through one registry with one cache and one error family; the dead language-hooks entry group, the CLI-local scanner, and the descriptor-less platform default are removed (every platform plugin carries a real descriptor)
- The retention/manifest logic extracts into a dedicated subsystem with its own unit suite landed before the move; the multi-subcommand modules split per subcommand; the migration orchestrator's legacy non-adapter paths are deleted once an audit confirms the adapter path is total, and it splits along its state/render/policy seams — no generation-layer module over 1,000 lines
- **Rejected alternatives:** refactoring `run()` into smaller private methods (keeps string-literal stages and three termination shapes); documenting the `getattr` names as a convention (still invisible to type-checking); keeping the CLI-local scanner for locality (two caches is the defect); indefinite dual-path migration retention

---

### Decision 24: Parser Dispatch Registry and Transformer Decomposition (Adopted)

**Rationale:**
- The language front-end solved CST-node-to-handler dispatch three different ways in one package (pre-filled handler dicts, name-based reflection the code itself flagged as an anti-pattern, and large if/elif ladders including a near-duplicate service/shared member ladder), with no executable contract tying a grammar rule to a transformer handler
- The transformers were god modules that also carried semantic lowering (auth/HMAC/verify/webhook resolution, a removed-temporal-type policy) belonging to analysis; state was fanned out through closures poking private attributes; an exported validator was never called in the parse pipeline yet locked in by tests; and a ~59k-line generated parser artifact was committed, burying every grammar review

**Result:**
- One declarative `node.type → handler` registry replaces all three mechanisms, checked bidirectionally against the grammar's node types (a named node with no handler or a handler for a nonexistent node fails); the duplicate member ladders merge into one registry-driven dispatch with a per-container allowed-member set stated as data
- The god transformers split by block family behind the registry (no transformer module over 800 lines); semantic lowering relocates to the semantic layer (behavior-preserving — diagnostics keep their codes, messages, and locations), consolidating a previously three-way-duplicated invariant into one owner; state passes through an immutable transform context; the one bare-exception swallow narrows to typed errors and the dead validator is removed
- The generated parser artifacts leave version control and build from the grammar source through the existing build machinery (in wheel packaging and the local autobuild path — not via hosted CI actions), with a suite-level staleness hash gate replacing the committed files
- **Rejected alternatives:** unifying on the reflection dispatcher (name-based reflection is the silent-failure shape being removed everywhere); splitting transformers by file size rather than family (family boundaries match the registry keys); keeping lowering in the syntax layer (semantic rules there are unreachable by semantic-phase tooling); committing the generated artifacts with only a hash gate (large diffs bury real grammar review)

---

### Decision 25: .NET / ASP.NET Core Language Generator (Approved — Implementation In Progress)

**Rationale:**
- Datrix ships Python (FastAPI) and TypeScript (NestJS) as language generators today, with the language set explicitly open; .NET/ASP.NET Core is a top-tier enterprise server target that started from an empty repo (`datrix-codegen-dotnet` held only LICENSE + README at the time of this decision — see Status below for what has since landed)
- "At feature parity with `datrix-codegen-python`" is a large, enumerable surface (~50 GenDSL domains, ~277 templates, a full Stage-3 transpiler, an incremental migration adapter, a conformance-gated plugin aggregate); every genuine ecosystem constraint — in particular EF Core 10's runtime migration-guard behavior and the state of MariaDB support among EF Core providers — is resolved up front rather than discovered mid-implementation

**Result:**
- A third language generator, `datrix-codegen-dotnet`, targets parity with `datrix-codegen-python`. Like every `datrix-*` package it is itself a Python 3.11 package (generators, transpiler, Jinja2 templates); its *output* is C#
- **Language id is `dotnet`, not `csharp`** — the runtime/platform is the deployment identity (runtime specs, docker images, platform tokens), C# is only the emitted syntax; mirrors naming `python`/`typescript` by runtime ecosystem rather than output syntax
- **Runtime stack:** .NET 10 (LTS, support to Nov 2028); attribute-routed MVC controllers + `[ApiController]`, not minimal APIs, because generated services carry per-route auth policies, filters, validation, and RFC 7807 wiring — the same structural reason NestJS controllers are used on the TypeScript side. OpenAPI via the first-party `Microsoft.AspNetCore.OpenApi`; builds are SDK-style `.csproj`
- **The ORM does not own schema.** EF Core 10 handles data access (POCO entities + explicit generated `IEntityTypeConfiguration<T>` fluent configuration; no `EnsureCreated`, no runtime model diffing); schema is owned by **FluentMigrator**, rendered from Datrix's own canonical migration ledger
- **Engine boundary:** PostgreSQL (Npgsql) and MySQL (Oracle's `MySql.EntityFrameworkCore`, the only EF Core 10-ready MySQL provider today) are supported. **MariaDB fails loud in v1** — the only EF Core 10 MariaDB path is an unreleased Pomelo line, and claiming support on an unverified provider would violate the no-silent-fallback rule; a deliberate, documented sub-par capability, un-gated when Pomelo ships a stable EF Core 10 line
- **Other stack decisions:** Quartz.NET for jobs (the APScheduler role); a generated CQRS bus (Datrix generates its own bus in every language); CSharpier for formatting (the ruff-format role — TypeScript ships no formatter, only pre-formatted templates validated via `tsc --noEmit`); `prometheus-net` for direct Prometheus exposition with OpenTelemetry retained for tracing; SignalR for the identity websocket; a self-probe `--datrix-run healthcheck` mode because the `mcr.microsoft.com/dotnet/aspnet` base image ships neither wget nor curl
- **Single-image runtime dispatch:** generated `Program.cs` inspects `--datrix-run <mode>` before building the web host (migrate / seed / search-init / job-runner / healthcheck; default = web service); `hosts_consumers_in_process()` is `True` (separate worker containers, the Python pattern)
- **The increment 7/8 stack:** cache: `StackExchange.Redis` (Redis/Valkey) + `EnyimMemcachedCore` (Memcached); NoSQL: `MongoDB.Driver` + `AWSSDK.DynamoDBv2` for the document model, mirroring python's `persistence/nosql_*` module family; storage: `AWSSDK.S3` + `Azure.Storage.Blobs` + local filesystem, one client per provider as python already splits it; search: `Elastic.Clients.Elasticsearch` + `Azure.Search.Documents`, adding a `search-init` bootstrap dispatch mode to the `Program.cs` `--datrix-run` switch that already carries `elasticsearch_init_command`; remote config: four backends — file, Consul (a raw typed `HttpClient`, no SDK), AWS AppConfig, Azure App Configuration — behind one `IRemoteConfigBackend` seam so the generated client stays backend-agnostic; secrets: a resolver plus generation-time manifest reconciliation, fail-closed with no opt-out on an initial cache miss (design principle 15); resilient clients: `IHttpClientFactory` + `Microsoft.Extensions.Http.Resilience` (first-party Polly v8) for inter-service and extern typed clients, and the substrate the `@retry` decorator lowers onto; observability: `prometheus-net` for direct Prometheus exposition (par with python's `prometheus_client`, not an OpenTelemetry-metrics substitute), OpenTelemetry for tracing only, and the built-in `AddJsonConsole` for structured logging; GraphQL: Hot Chocolate **16.5.0** (v15 was superseded 2026-05-11, after the original figure was written); identity websocket: SignalR, which ships inside the ASP.NET Core shared framework and needs no package; geo: `NetTopologySuite` + `NetTopologySuite.IO.GeoJSON4STJ`, with hand-rolled `Geo`/`GeoTile`/`GeoTiff` helpers ported line-for-line from python's pure-stdlib implementations
- **Rejected alternatives:** EF-native migrations (EF Core 9+ makes runtime `Migrate()` throw on pending model changes vs. the migrations' `ModelSnapshot`, which would force Datrix to render and perpetually synchronize a `ModelSnapshot` or suppress the guard — a workaround by definition); DbUp (no down/rollback execution, below the Alembic/MikroORM downgrade bar); Hangfire (storage/dashboard assumptions Quartz.NET doesn't need); MediatR (2025 commercial relicensing disqualifies it as a generated-code default); `dotnet format` (full-project analysis per run, not project-context-free like CSharpier)
- **Rejected alternatives (increments 7-8):** OpenTelemetry-metrics-only instead of `prometheus-net` — python (the reference generator) ships direct Prometheus exposition, and matching the reference generator's shape is the parity bar, not adopting a different observability philosophy for one language; `NetTopologySuite.IO.GeoJSON` (the Newtonsoft-based sibling of `.GeoJSON4STJ`) — would introduce a second JSON library where the STJ variant already matches dotnet's canonical JSON type; a GDAL/raster binding for the geo helpers — a heavyweight native-binding dependency for a handful of call sites when the reference implementations are pure-stdlib; a community Consul .NET SDK — the reference generator uses a plain typed HTTP client for Consul's KV/health API, so dotnet does the same; per-provider SMS/push SDKs (Twilio/Vonage/FCM) — N provider SDKs would carry N independent version risks for what are plain authenticated REST APIs, and the observable contract is the provider interface, not the HTTP library beneath it

**Status:** Approved — Implementation In Progress. Increments 0-3 (scaffold/transpiler/entities/REST) and increments 4-6 (persistence & migrations, identity & auth, messaging & workers) have landed and are proven: full suite 1347/0/0, docker 1650 + cli 1207 pass unchanged, all G1-G8 conformance checks green. Increments 7-8 (data & integrations, GraphQL/websockets/geo) have also **landed**. dotnet is now a real generator for persistence, migrations, seeds, identity/JWT-JWKS/auth, gateway, trusted-caller, webhook, rate-limit, tenancy, pubsub, queue, CQRS, jobs, and data & integrations (cache/nosql/storage/search/remote-config/secrets/resilience/inter-service HTTP clients) plus GraphQL/websockets/geo — joining python, typescript, and java in the supported-languages table and package count. Increments 9-10 (test generation, package docs, serverless cloud wiring) have also **landed**: `TestSpecGenerator` renders xUnit specs from DSL `test(...)` blocks, `readme.md.j2` renders package docs, and the Lambda (`_lambda_adapter.py`), Azure Functions (`_azure_functions_adapter.py`), and container (`_container_broker_entrypoints.py`, `_container_http_entrypoint.py`) serverless adapters wire cloud hosting. One gap remains: serverless handler bodies (subscribe/job/enqueue) are transpiled only for the **CONTAINER** platform — **LAMBDA** and **FUNCTIONS** wire the hosting call and platform flag but do not yet transpile the handler body itself. The container-hosting platform work (Azure Container Apps / ECS Fargate best-native targets) is a separate, language-agnostic effort; it does not own dotnet's serverless authoring.

**End-state invariants (G1–G10)** the implementation must satisfy: type-map exhaustiveness, builtin-group obligations, migration parity, worker containers, and cross-surface safety across every touched package. The best-native worker/job execution model is realized language-side by the dotnet generator and per-cloud by the language-agnostic container-hosting platform work (Azure Container Apps / ECS Fargate) — that work owns platform realization only, not any language generator's serverless authoring.

---

### Decision 26: Best-Native Worker/Job Execution (Adopted)

**Rationale:**
- Worker, consumer, and scheduled-job execution needs both a runtime shape every language can implement uniformly and a schedule/scale mechanism that varies legitimately by deployment target (local Compose vs. Azure vs. AWS); collapsing these into one cross-language scheduler would force either a lowest-common-denominator dependency in every generated service or a platform-specific runtime baked into language code
- Python already established the pattern (APScheduler locally, cloud-native scheduling in deployed environments); dotnet needed the same split, making this a general cross-language/cross-platform architectural pattern rather than a dotnet-local detail

**Result:**
- **Language-owned:** each language generator contributes the job handler, the consumer `BackgroundService` (or language-equivalent long-running consumer loop), and a one-shot scheduler-invocable entrypoint (`--datrix-run job-runner` / equivalent dispatch mode). This is best-native per platform — no cross-language scheduling library is imposed on generated code
- **Platform-owned:** the deployment platform owns schedule and scale, not the language runtime. Quartz.NET is dotnet's local/Compose scheduler and the fallback where no cloud scheduler is present; Azure Container Apps Jobs and AWS EventBridge Scheduler own cloud-native scheduling; KEDA (Azure) and SQS-depth-based scaling (AWS) own cloud-native scaling. The cloud realization of this split belongs to the companion container-hosting platform work, not to the language generator

**Status:** Adopted. Language-side realization landed for python (APScheduler) and dotnet (Quartz.NET — job handler, `BackgroundService` consumers, `job-runner` dispatch, Quartz.NET registration; the worker container itself is the G7 conformance obligation). Cloud-side realization (ACA Jobs/EventBridge Scheduler/KEDA/SQS-depth scaling) belongs to the container-hosting platform work and remains future.

---

### Decision 27: Native-Only Observability Providers per Target Platform (Adopted)

**Rationale:**
- Every deployment target has a first-class native observability stack — LOCAL/docker: self-hosted Prometheus/Jaeger/Loki/Grafana/Alertmanager; AWS: CloudWatch (+ X-Ray); Azure: Azure Monitor + Application Insights. The former cross-platform portable overlay (AWS/Azure Managed Grafana over managed-Prometheus) duplicated the native stack and only worked when metrics were Prometheus.
- With the deployment-target axis open (Decision 22), a non-native provider on a cloud (e.g. `metrics.provider = prometheus` or `visualization.provider = grafana` on AWS/Azure) had no boundary rejection — it was silently accepted with nothing native to render it.

**Result:**
- **Native-only rule:** each platform emits only its platform-native observability providers; the portable Managed-Grafana overlay is removed from the AWS and Azure generators. LOCAL/docker keeps its self-hosted stack — the native option for a provider-less deployment.
- **Plugin-declared allow-list:** each platform declares its own native provider set (metrics / tracing / logging / visualization / alerting) on `PlatformCapabilityDeclaration.native_observability_providers` — never a shared `{target -> providers}` table, which would trip the I1 target-literal ratchet.
- **Generic boundary validator:** one shared validator asks the resolved platform's declaration at the `validate_deployment` stage and raises `GenerationError` for any non-native provider — mirroring `unrealizable_surfaces` / `native_notification_vendors` (Decision 22; design principle 10, "Shared Layers Ask, Target Plugins Answer").
- **Language-agnostic:** the rule is enforced at the platform boundary in `datrix-common`, independent of target language (Python / TypeScript / Java / .NET). Per-language native-provider *instrumentation* coverage stays each language generator's own concern.
- **Dead `datadog` metrics provider removed** — non-native on every platform and unreferenced by any generator.
- **Rejected alternatives:** a hardcoded per-platform allow-list matrix in `datrix-common` (it references the deleted `DeploymentProvider`/`DeploymentRuntime` enums and violates principle 10 / the I1 gate); silently dropping non-native providers on a cloud (fail-loud is required).

**Reference:** [datrix-common API — PlatformCapabilityDeclaration.native_observability_providers](../../../datrix-common/docs/datrix-common-api.md#platformcapabilitydeclaration) | [datrix-common — Observability: Native provider resolution](../../../datrix-common/docs/observability.md#native-provider-resolution-platform-boundary) | [AWS architecture — CloudWatch Dashboards](../../../datrix-codegen-aws/docs/architecture.md#cloudwatch-dashboards) | [Azure architecture — Azure Monitor Workbooks](../../../datrix-codegen-azure/docs/architecture.md#azure-monitor-workbooks); implemented in phase 41.

---

### Decision 28: Cross-Target Parity Enforcement — Derived Gates and Declared Capability Holes (Adopted)

**Rationale:**
- Language-target and platform-target discrepancies were being caught only when a person happened to notice them: the byte-baseline matrix carries far more ungenerated pairs than blessed ones, no repo-level check compares platform capability declarations against each other, and builtin-claim equality rests on independently hand-maintained per-language literals instead of derivation.
- Hand-authored gate inventories already exclude newly registered languages by construction, and a parked example with no baseline is skipped without even attempting generation, so a fixed defect has no way to announce itself.

**Result:**
- **Every discrepancy class becomes a red check.** Each class of language-target and platform-target drift is closed by a gate that fails in the drifting package or at the repo level, rather than depending on a reviewer noticing.
- **New repo-level gates follow one house pattern.** Target sets are enumerated from entry points at runtime rather than hardcoded; every gate carries a built-in non-vacuity self-test (a synthetic pass and a synthetic forced failure) on each invocation; and no gate is permitted to pass vacuously against fewer than two targets.
- **Gate inventories derive from registration, never hand lists.** Where a gate previously iterated a literal module or package tuple, it instead derives its target set from the same plugin registration every other target-agnostic mechanism already reads.
- **Known gaps land as typed, reviewed exemptions, never silence.** A gate that would be red today against a catalogued capability hole lands anyway, backed by an exemption file whose entries each carry coordinates and a reason and whose total count is pinned; remediation work removes an entry and decrements the pinned count in the same change. A gate is never blocked on its own remediation, and a hole is never silent.
- **New gate concepts:** platform block-realization/capability parity (the first repo-level consumer of the platform capability declaration), builtin-claims parity (derived comparison of claimed builtin groups across every registered language), cross-language artifact-role parity (presence of each domain role compared across languages, derived from blessed baseline manifests at zero additional generation cost — complementing, not replacing, the byte-baseline gate that pins content), example-universe registry consistency, a grow-only blessed-coverage ratchet, a parked-pair generation probe (a parked, baseline-less pair is attempted at check time, so a fixed defect surfaces as "unpark me" instead of staying parked indefinitely), and a standing committed conformance-spec corpus so a design-acceptance negative check outlives the change that landed it.

**Status:** Landed. `block-realization-parity-gate.ps1` (D1) passes with zero unexempted gaps across all 5 registered platforms (aws/azure/azure-vm/docker/local); `standing-conformance-gate.ps1` (D10) passes all 8 committed specs. See `datrix/scripts/test/quick-reference.md` for the full gate roster and mechanics.

---

### Decision 29: Language-Target Capability Parity to the Reference Surface (Approved — Implementation In Progress)

**Rationale:**
- Python is the most complete language surface Datrix generates from, and every other registered language had accumulated its own untracked capability gaps against it — some visible only as a language silently emitting nothing for a construct another language realizes, the same emit-nothing-report-success defect class as a silent narrowing rather than a fail-loud boundary that would at least be noticed.
- Claimed builtin groups, extension type-map coverage, and provider-name handling had each drifted per language with nothing forcing them back into agreement.

**Result:**
- **Python is the reference surface; every other registered language is brought to it** for each catalogued capability gap — python's own capability surface does not change as part of this work.
- **The messaging builtin group becomes claimed by every registered language**, with its full method-by-provider matrix mapped per language rather than left partially wired against runtime clients that already ship.
- **Extension type-map keys become exhaustive.** Every installed extension pack gets a corresponding type-map key in every registered language, closing the defect class where an extension generates on some languages and is rejected before generation on others.
- **Provider-name string literals leave the language packages.** Facts that used to live as string comparisons against a provider name move onto the platform and realization seams that already declare those facts, so a language package asks a declaration instead of branching on a provider's name.
- **The parity baseline matrix is driven to total coverage.** Every swept example-by-language pair ends this work either blessed or parked with a recorded reason — no pair is left silently ungenerated.

---

### Decision 30: Platform-Target Validation Floor and Realization Parity (Adopted)

**Rationale:**
- The registered platform targets had drifted along three independent lines: pre-generation validation ran on some platforms and not others, config surfaces existed that no platform actually consumed, and capabilities realized on one platform were silently absent on the others with no record of whether the absence was a genuine impossibility or an oversight.

**Result:**
- **A uniform pre-generation validation floor runs on every registered platform.** Every silent skip becomes either fail-loud or realized, and the same validation gates run regardless of target — a config accepted on one platform and silently dropped on another is the defect class being closed.
- **Config surfaces no platform consumes are deleted, not deprecated.** Dead configuration that still parses is a lie to the person who wrote it; there is no backward-compatibility shim. Reintroducing a deleted surface is reserved for a future design that ships together with a real consumer.
- **A capability realized on one platform is realized on the others or declared unsupported with a reason.** Genuine platform impossibilities become explicit declarations carrying a reason, never silence — the same declare-or-realize discipline the capability declaration already establishes for block realization.
- **Provider-shaped facts move onto platform declarations.** Gateway type, TLS termination posture, and injected test identity providers become facts each platform declares and that generic shared validators consult, so no provider name enters a shared layer to express what used to be a per-platform special case.

**Status:** Landed across `datrix-common`, `datrix-language`, and the aws/azure/docker platform packages. `platform-capability-holes.json` carries zero exemptions. `block-realization-parity-gate.ps1`'s `block_realizations` surface — the declare-or-realize bar this decision established — is green across all 5 registered platforms (`aws`, `azure`, `azure-vm`, `docker`, `local`) with nothing catalogued as an outstanding hole. The gate's own completeness self-check had been raising an assertion before any comparison ran, because four fields added to `PlatformCapabilityDeclaration` after this decision landed (`rdbms_login_principal_is_per_service`, `published_host_ports`, `edge_origin_host_port`, `edge_path_routed_origins`) were never triaged into its field buckets; fixing that crash surfaced 20 real gaps on two scalar surfaces (those four fields plus `platform_allowed_host_patterns`) that the crash had been masking. All 20 are now closed — each by a real declaration or a `declared_capability_reasons` entry naming the specific technical fact, none by an exemption entry — and the gate passes with zero unexempted gaps across every surface. The dead-surface deletions (`network {}`, `serviceDiscovery {}`, `gateway.port`, `gateway.circuitBreaker`, `TracingProvider.ZIPKIN`, `SecretBackend.AWS_SSM`) are each pinned by a committed spec in `standing-conformance-gate.ps1`, which passes all 8. Two surfaces investigated as dead proved to have real consumers and were deliberately kept rather than deleted: `gateway.transform` (realized in-service by the language generators' gateway transform rendering, not by platform infrastructure) and `SecretBackend.ENV` (declared supported by the local docker target, realized as Compose `.env` substitution).

---

### Decision 31: Mini-DSL Consolidation — Declared Surfaces Replace Imperative Bypasses (Adopted)

**Rationale:**
- Repeated parity drift traces back to a structural cause: per-target behavior is hand-written once per language or platform instead of declared once and realized generically, so the same behavior can silently diverge every time a target is added or a branch is edited on only one side.
- The existing mini-DSL layers already prevent this class of drift wherever they are actually used — the surfaces where they are bypassed by imperative branches are exactly where drift keeps recurring, so the structural cause is attacked directly rather than patched per instance again.

**Result:**
- **The emit-table schema gains typed predicate columns** — receiver shape, arity, literal-argument, receiver-type restriction, and a flag guard resolved against a closed per-language flag registry — so declared rows can replace imperative branches they previously had no way to express, with validation staying closed at construction time.
- **Shared test-generator emission plans cover every test kind**, leaving each language's per-kind file as a thin naming/path/template/render adapter over one shared decision surface instead of a second, independently drifting implementation.
- **The seed surface becomes a real, closed pipeline surface.** Seed documents load into the application and are validated once during semantic analysis, before any generator runs, with one deterministic-identifier implementation and shared plan writers consumed by every language; the parallel, untyped YAML seed path is deleted.
- **Declared-file coverage plus a shared emission-path gate make the declaration the only emission path** in every language package, so an output path can no longer be produced by an undeclared imperative site alongside its declared one.
- **Queue and serverless block realization join normal table dispatch**, and provisioning-artifact patterns move onto the realization declaration itself, so the declaration and the conformance check that verifies it can no longer drift apart.
- **Non-goal:** template bodies are never shared across languages. Decision logic and structure are what get consolidated; each language's rendered output stays that language's own.

**Status:** Landed across `datrix-codegen-common` and the python/typescript/java/dotnet language packages.
1. Emit-table typed predicate columns — held by a documented **non-zero floor**, not a zero: `EmitDecl`'s typed predicate fields (`receiver_shape`, `arity`, `literal_arg`, `restrict_to`, `flag_guard`) let `emit_tables.py`'s declared rows replace imperative branches wherever the routing decision is single-step (python's `Arity`-guarded `instance_call` rows and its `builtin_category_preference` table are declared today), but what a row cannot yet express is not zero — it sits on the `visit_*` floor `visit_adapter_ratchet.py` pins per language (python 62, typescript 60, dotnet 61, java 66), a floor that gate itself documents as a MONOTONIC ratchet over a justified non-zero terminal count, never a countdown to zero.
2. Shared test-generator emission plans — held by a documented **non-zero floor**: `test_generator_orchestrator.py`'s module docstring records real residual divergence — five kinds (`enum`, `gateway`, `integration`, `jobs`, `lifecycle_hook`) with a suspected unintentional cross-language feature gap, explicitly pending a human reconciliation decision rather than folded; seven more (`api`, `entity`, `deployment`, `computed_field`, `entity_function`, `module_function`, `struct`) with a legitimately per-language-owned decision input. Adoption is gated per language package; python's own `test_adapter_conformance_gates.py` currently confirms at least 15 of its 21 per-kind adapters have adopted a shared plan — not literally every kind, and not claimed as such here.
3. The seed surface becoming a closed pipeline surface — held by a documented **zero**: `SeedGeneratorHooks`/`DefaultSeedHooks` and the untyped YAML seed path are deleted, leaving no surviving consumer in any package's source or tests.
4. Declared-file coverage plus a shared emission-path gate — held by a documented **zero** on the invariant this bullet names: the shared `emission_path` testkit gate is wired into all four shipping language packages' own suites (`test_python_satisfies_the_shared_emission_path_gate.py` and its typescript/java/dotnet equivalents) and enforces that every domain is declared or F2-exempt with a named reason — there is no third "not migrated yet" bucket for any of them.
5. Queue and serverless block realization joining normal table dispatch — held by a documented **zero** on the surface this bullet names: `block-realization-parity-gate.ps1`'s `block_realizations` surface (the union of every `block_type:flavor` coordinate, including queue and serverless) reports zero unexempted gaps across all 5 registered platforms (`aws`, `azure`, `azure-vm`, `docker`, `local`). The gate as a whole also passes: the 20 gaps it briefly reported on two unrelated scalar surfaces, once a crashing completeness self-check stopped masking them, are closed (see Decision 30's Status); none of them ever touched `block_realizations`.
6. The template-body non-goal — a stated **boundary, not a gap**: nothing measures this because there is nothing to close. Shared plan modules consolidate decision logic; each language's rendered template output stays that language's own by design.

---

### Decision 32: Portable Telemetry-Volume and Platform-Diagnostics Contracts, with Realization Conformance (Adopted)

**Rationale:**
- Three telemetry-cost defects were each closed as a point patch inside a single language or platform package. `observability.tracing.samplingRate` was accepted by the DSL but never realized for AWS/X-Ray until a reviewer noticed and patched it. The identical defect then recurred on Azure/Application Insights and cost a pilot environment $94.56 of Log Analytics ingestion — 56% of that environment's running cost, roughly $1.05 per uptime-hour — before a human reading a bill caught it. A third live instance surfaced on the dotnet target during an unrelated investigation: its tracing generator never receives the tracing config at all, so both the declared provider and `samplingRate` are inert, and unlike python and typescript, dotnet does not fail loud either — it silently emits unconditional OTLP.
- Each patch was correct at the target it touched but sat at the wrong altitude: it realized a portable concept inside one target, leaving every other registered target free to keep the same defect and every future target free to reintroduce it. The defect class is recurrence, not any one bug — two of the three instances were caught only by a human reading a bill or a docstring, the third by an investigation aimed at something else entirely. Nothing in the repo would have caught a fourth.
- Point-patching also produced a structurally incomplete fix: bounding the trace signal alone leaves the log and metric exporters running at 100%, so the log stream becomes the new dominant cost term. The trace patch could not finish the job because the portable model had nowhere to express the other two signals.

**Result:**

- **D1 — Portable telemetry-volume contract (`datrix-common`).** Export volume for every OpenTelemetry signal is modeled at the portable layer, so no target has to invent it and no signal is unreachable from the DSL:

```
observability {
  tracing { provider = "..."; samplingRate = 0.1; }
  logging { provider = "..."; level = "info"; exportLevel = "warning"; }
  metrics { provider = "..."; exportIntervalSeconds = 60; }
}
```

  - `samplingRate` stays exactly where it is on the tracing config — already portable and realized by five targets today; relocating it would be churn with no gain.
  - `logging.exportLevel` is the severity floor for records shipped to the aggregation backend, distinct from `level` (what the application emits). It is meaningful on every backend — Log Analytics, CloudWatch Logs, Loki.
  - `metrics.exportIntervalSeconds` is the portable spelling of metric export cadence.
  - Every new field defaults to today's effective behavior, so no existing profile changes a single generated byte. Verified state behind those defaults: no target has any log-export severity filter today, so the emit floor is the export floor; and every application-side metrics path is a pull-based scrape endpoint, so cadence lives on the scraper today (the LOCAL Prometheus scrape interval and the AWS CloudWatch-agent sidecar interval are generation-time literals). The defaults are therefore "no export floor" and "the target's current cadence" — the mechanism ships, the cost decision stays with the config owner.

- **D2 — Portable platform-diagnostics contract (`datrix-common`).** One shared model for platform-collected telemetry, distinct from D1's application-emitted telemetry, projected by each platform package onto its native mechanism. It lands on the shared platform-config base so a newly added platform package inherits the surface rather than inventing one:

```
platforms {
  <target> {
    diagnostics { verbosity = "all"; retentionDays = 30; dailyBudgetGb = 5; }
  }
}
```

  | Field | azure projection | aws projection | local/docker projection |
  | --- | --- | --- | --- |
  | `verbosity` (`all`\|`audit`\|`none`) | diagnostic-settings category group / empty log selection | log-collection scope on the emitted CloudWatch surface | projects onto the emitted log-shipping pipeline, or is declared unsupported with a reason |
  | `retentionDays` | Log Analytics workspace retention | log-group retention | same |
  | `dailyBudgetGb` | workspace daily-quota capping | declared unsupported with a reason | same |

  Consequences, each resolving an open defect rather than adding surface:
  - The azure-only log-selection field a prior point patch added becomes the projection of the portable `verbosity`, not its own field.
  - The AWS platform config's log-retention field folds into `diagnostics.retentionDays` as a straight rename — the old field is deleted outright, not kept alongside the new one.
  - The azure diagnostics retention field stops being accept-and-ignore. Verified current state: it is validated fail-loud and threaded into the render context, but the diagnostic-settings template never emits it — Azure rejects per-setting retention policies on new diagnostic settings, and workspace retention is actually fed from a second, separately named Application Insights retention field. Two names for one concept, one of which is validated and discarded. The portable `diagnostics.retentionDays` becomes the single feed for workspace retention, and the duplicate Application Insights retention field is removed.
  - Every registered platform is in scope: a platform either projects each field onto its native mechanism or declares it unsupported with a reason. Both are honest; accepting and ignoring is not.

- **D3 — Realization conformance: no knob may be silently inert.** A knob is realized when perturbing it changes the emitted artifact in a functional position, checked mechanically at two tiers:
  - **Tier 1 — inert field.** Perturb one field, regenerate, diff. Byte-identical output means the knob is dead.
  - **Tier 2 — cosmetic-only.** Output changed, but only inside comments or strings, so the value reached the text and not the behavior — exactly the Azure sampling defect, where the declared rate appeared in a docstring and a log line while export ran at 100%. Tier 1 cannot see it, and neither can a substring assertion.
  - Home is per-package, not a repo-level sweep: each generator package asserts realization for the config surface it consumes, honoring the rule that each package tests only its own surface and avoiding a full-pipeline run per field across every package at once. The conformance surface per package is the platform configuration model that package receives plus the portable observability profile configuration.
  - Mechanics: perturbation is derived from the models, never hand-listed — the config models expose annotation, default, and constraint metadata, are frozen, and support producing a perturbed copy. Emission uses each package's existing whole-output seam. The perturb/diff engine is shared in the codegen-common conformance kit; each package supplies only its own significant-text normalizer (which spans are comments and strings in the language it emits) — the one genuinely per-target piece, and it lives in the owning package. Legitimately-inert fields go in a hand-reviewed exemption baseline owned by the package, each entry carrying a written reason, with a pinned expected count enforced so an entry cannot be added or removed without updating the count in the same change. A non-vacuity self-test runs every time: feed the comparator a knob known to be realized (must pass) and a deliberately severed one (must fail).

- **D4 — Provider × target realization matrix.** Generalizes the fail-loud gate python and typescript already implement, and makes the matrix a single queryable fact instead of divergent per-package literals.
  - Each target declares the provider set it realizes, per observability category, covering the same five categories the platform capability declaration already uses — metrics, tracing, logging, visualization, alerting. The specifics stay in the package that owns the knowledge; a category a target declares empty means it realizes none.
  - The matrix is assembled from the registered targets at runtime via the language and platform entry-point groups — never a hardcoded literal — so a newly added generator package is covered with no edit to shared code.
  - Declaring a provider the resolved target does not realize is a loud config error, raised uniformly on every target.
  - The matrix is what D3's conformance iterates, so "declared supported" and "actually realized" cannot drift: claiming support obliges passing realization.
  - **The declaration is two axes, not one, and they are not policed identically.** Visualization, alerting, and logging-*provider* are realized by the resolved PLATFORM's infrastructure (a shipped Grafana container, an Alertmanager service, a Loki/CloudWatch Logs/Log Analytics backend) — no language generator branches on them. Every language declares those three categories empty for exactly that reason, and the LANGUAGE-axis validator must skip them rather than reject a provider the PLATFORM natively realizes; only metrics and tracing (where the language emits provider-specific exporter/SDK wiring) stay policed on both axes. This was not obvious from the platform-axis precedent alone and cost two live defects to learn: an early language declaration realized every logging provider ("log-shipping destination is a platform-layer concern") while other languages declared none of the identical fact ("backend routing is a platform-axis concern") — the same portable config generated cleanly on one language and failed generation on another — and a first cut of the language-axis validator policed all five categories uniformly, which rejected `visualization.provider = "grafana"` (a platform-provisioned, framework-example-blessed config) on every language. Both are now fixed; the cross-target discovery in the next bullet is what proved it and is what keeps it fixed.

**Invariant table:**

| # | Invariant | Enforcement mechanism (planned) |
| --- | --- | --- |
| 1 | Every OpenTelemetry signal has a portable export-volume field | Volume fields on the portable observability models; a profile declaring each one produces a functionally different artifact on every target that realizes it |
| 2 | Adopting the new fields changes no existing generated byte | Every new field defaults to today's effective behavior |
| 3 | No platform package defines its own retention or verbosity field | A scan of the platform configs finds the portable `diagnostics` block and zero surviving per-platform retention/log-selection declarations |
| 4 | A knob a target accepts is a knob it realizes | Per-package perturb/regenerate/diff conformance, Tier 1 (inert) and Tier 2 (cosmetic-only) |
| 5 | A legitimately-inert field is a reviewed exemption with a pinned count, never silence | Package-owned exemption baseline; the count is enforced against the entry list |
| 6 | The conformance gate proves its own non-vacuity every run | A known-realized knob must pass and a deliberately severed one must fail, checked before the real comparison |
| 7 | (provider × target) realization is one fact assembled from the registered target set | Per-target declarations folded into a matrix derived from entry points; every pair marked supported must pass the realization check; declaring an unsupported pair is a loud validation error on every target |
| 8 | The language axis and the platform axis agree about which of the two realizes a given observability category | Repo-level cross-target parity gate: every registered language declares the empty set for every platform-only category, and every provider a registered platform declares native validates cleanly against every registered language — target sets from entry points, non-vacuity self-test every run |

**Scope boundaries:** Not a change to any provider's semantics or to which providers exist. Not a new telemetry backend, dashboard, or alerting surface beyond the log-collection scope `verbosity` requires on AWS. Not a value choice — this ships mechanisms with behavior-preserving defaults; what a deployment sets stays the config owner's call. It does not attempt to detect a hardcoded constant that should have been a knob, which is not mechanically decidable and stays a design and review concern — stated so the conformance work is not credited with coverage it lacks.

**Builds on and overlaps with** [Decision 27](#decision-27-native-only-observability-providers-per-target-platform-adopted) (native-only observability providers per target platform) and the cross-target parity program spanning [Decision 28](#decision-28-cross-target-parity-enforcement--derived-gates-and-declared-capability-holes-adopted) through [Decision 31](#decision-31-mini-dsl-consolidation--declared-surfaces-replace-imperative-bypasses-adopted). This decision's conformance engine and derived matrix are the first concrete instances of that program's house pattern — runtime target discovery from entry points, a mandatory non-vacuity self-test, pinned-count exemption files, "declared cannot diverge from realized" — seeding the pattern rather than duplicating it. The axis differs, though: the parity program addresses capability-presence parity between targets, while this decision addresses field-level realization within a target.

**Status:** Adopted. `logging.exportLevel`, `metrics.exportIntervalSeconds`, and the `diagnostics` platform block are live on the portable config models; the perturb/diff conformance kit (`datrix_codegen_common.testkit.gates.config_realization`) is landed and every consuming package (aws, azure, docker, python, typescript, java, dotnet, component) carries its own exemption baseline and passing conformance suite — see [datrix-codegen-common architecture — Config-Realization Conformance Engine](../../../datrix-codegen-common/docs/architecture.md#config-realization-conformance-engine). The provider × target realization matrix is assembled from the registered `datrix.languages`/`datrix.platforms` entry points — see [datrix-common API — LanguageCapabilityDeclaration](../../../datrix-common/docs/datrix-common-api.md#languagecapabilitydeclaration) — and invariant 8's cross-target gate is `datrix/scripts/test/observability-axis-parity-gate.ps1`.

---

### Decision 33: Self-Hosted Compute with Managed State on the Compose Target (Adopted)

**Rationale:**
- The docker-compose target realizes an infrastructure block one of two ways: as a container it provisions, or as an `external` flavor it connects to without provisioning. Two flavors naming a cloud-managed service — object storage as blob storage, and pub/sub as a managed broker — are declared unsupported there, with the reason that a cloud-managed service cannot be provisioned on a self-hosted host.
- That reason conflates two separate questions: *can this target provision the resource*, and *can this target realize a block that consumes it*. The already-supported `rdbms/external` and `storage/minio-external` cells answer them separately — the target connects and does not provision — so the compose target already has the shape; only these two cells are missing it.
- The consequence is a deployment topology the generator cannot express at all: containers on a single self-hosted host, with the three stateful components that dominate disk and memory — relational storage, object storage, message broker — held by managed services the host reaches using its platform-assigned workload identity, with no connection strings or account keys authored anywhere. Running those three as containers is what forces a large host; running the whole stack on a cloud provider's managed compute is what makes an always-on environment expensive. The hybrid sits between the two and is unreachable today.
- The gap is a single platform package's realization, not a missing capability. The language-side clients for both flavors already exist and are exercised by the cloud platform target, dispatching on engine and provider rather than on deployment platform; nothing in the language layer needs to change.

**Result:**

- **D1 — Both cells become supported connect-don't-provision realizations** on the compose target, carrying the same structural pattern as the existing external cells. The generic `(block_type, flavor)` capability gate stops rejecting them, and the platform's managed-realization dispatch returns the same empty provisioning plan every other locally-realizable cell returns: the target realizes the block, just not as a resource it creates.

- **D2 — The container-suppression predicate is local to the platform package.** The shared skip-provisioning set is left unchanged. It is defined as the complement of cloud-managed provisioning, so adding a cloud-managed flavor to it would switch that same flavor's provisioning *off* on the cloud platforms that do provision it — a cross-target regression from an edit that looks local. Per design principle 16, "does this target provision a container for this block" is the target's own question to answer in its own package, alongside the existing storage-side predicate that already answers it for the external object-storage flavor.

- **D3 — Connection values come from authored configuration, never from a resolved container.** A managed pub/sub block takes the same connection branch as an external one, so the authored broker endpoint carries the namespace FQDN the generated client consumes; a blob-storage block's account URL is seeded from its authored endpoint. A key that is neither authored nor provisioned stays unseeded, and the local preflight fails loud naming it rather than emitting an empty placeholder. (Decision 35 supersedes this rule for its own provider only, where the value is resolved from provisioned infrastructure instead of authored configuration; it still governs the compose target's own `local` realization.)

- **D4 — Suppression is total across the emitted tree, not just the compose file.** For a block realized as managed state the target emits: no container, no init container, no init or bootstrap script, no host-gateway extra-host, no `depends_on` edge to a container that is not emitted, and no credential environment or secret surface for a client that authenticates by workload identity. Each of those is a separate emission site and each is a separate check — a suppression that covers the compose file while an init script survives in the generated script tree is a half-realized cell.

**Invariant table:**

| # | Invariant | Enforcement mechanism (planned) |
| --- | --- | --- |
| 1 | A cloud-managed flavor a target can connect to is supported there, not rejected for being unprovisionable | The two cells are declared supported; the capability gate admits them and the flavor-gate test proves the pair no longer raises |
| 2 | Marking a flavor non-provisioning on one target never changes provisioning on another | The shared skip-provisioning set is untouched; suppression lives in the platform package, and the cloud platforms' own cells are unchanged |
| 3 | Every supported cell has a fixture that exercises it | The package's existing kit-CI check already fails loud, naming any supported cell with no fixture service |
| 4 | Suppression covers every emission site, not just the compose file | One check per site — container, init container, init script, extra-host, `depends_on`, credential surface — over real generated output |
| 5 | A connection value is authored or the preflight refuses to start | Unseeded required keys fail loud naming the key; no empty placeholder is ever seeded |

**Scope boundaries:** These two boundaries held for the compose target's own realization cells and have since been superseded by Decision 35: the compose target itself still emits no cloud infrastructure templates for these resources and still provisions them out of band, and the topology described here is still a set of realization cells on the existing target rather than a new one — but Decision 35 introduces a distinct provider that does emit infrastructure-as-code for the equivalent resources on cloud-hosted compute. Not a change to any other target's cells, to the language-side clients, or to which flavors exist. Realization ships on the Python language target; other language targets are unchanged and may declare the same shape independently.

**Status:** Adopted. Both cells are declared supported and registered on the compose target, the platform-local suppression predicate exists, and the realization is exercised by the package's own integration and unit tests covering managed-state generation, managed pub/sub realization, managed storage wiring, and docker validation.

---

### Decision 34: Codegen Shared-Layer Consolidation — Target-Agnostic Logic Leaves the Language Packages (Adopted)

**Rationale:**
- The four language generator packages carry 4,216 physical lines of exactly-duplicated code — 3,767 in duplicated function bodies and 449 in duplicated module-level constant tables. None of it is language-specific emission: it is AST/contract analysis, config-driven predicates, fail-loud AST lookups, and DSL vocabulary tables. Four independent copies of one fact drift at four independent rates, and because cross-language parity tests are prohibited by design, a divergence produces wrong generated code rather than a red suite.
- The packages already know they are copying and cite the import boundary as the reason — a language package may depend only on `datrix-common` and `datrix-codegen-common`, never a sibling. That boundary is real; the conclusion drawn from it is not. `datrix-codegen-common` exists for exactly this, and all four language packages already declare it as a runtime dependency, so every hoist is a relocation with no new edge in the dependency graph.
- The pattern has already shipped a defect. One language package's response-struct generator hand-rolls a service-body walk that omits CQRS, serverless, service-level enqueue, test, and entity-`validate` bodies; another package's twin of that file was repaired to consume the canonical enumerator and the first was not. The consequence is generated code that imports a response module the generator then declines to materialize.
- It is a regression against a decision already taken. The shared enum module was created to centralise DSL string literals that had been scattered across language packages; two packages have since re-scattered the exact literals it holds, and one shared vocabulary has zero consumers while a package hardcodes its members.
- The shared layer's own surfaces block the next language. The struct-slice builder is a closed union of exactly three shipped languages with an `isinstance` ladder over it, and the fourth language's slice lives outside the shared package *because it could not join that union* — invariant I2 ("add-a-language = one package") failing in practice.

**Result:**

- **D1 — Target-agnostic logic lives at the most target-agnostic layer that can own it, parameterized by value.** A helper whose body reads only `datrix-common` AST/config models and `datrix-codegen-common` primitives belongs in `datrix-codegen-common`. Where copies differ, the difference is passed in as an argument (a provider-language identifier, a casing callable) — never a `dict[language, policy]` and never an `if target == X` in the shared layer.

- **D2 — A pure AST accessor belongs in `datrix-common`, not `datrix-codegen-common`.** A helper that only walks the AST and carries no codegen concept is placed alongside the other service accessors; `datrix-common` has zero Datrix dependencies, so nothing is inverted by that placement.

- **D3 — Each DSL vocabulary has exactly one definition, in the shared enum module.** A language package may not redeclare a member set that module already declares, and a vocabulary duplicated across two or more packages with no canonical home gains one there. Cross-language contracts — the DSL exception-to-HTTP-status mapping and the alert metric-name sets — are covered: an HTTP status and a metric name must agree across targets, and a taxonomy guaranteed by independent copies is guaranteed by nothing.

- **D4 — No type, field, or type alias in the shared codegen package carries a target name.** An AST scan found 76 such declarations across 12 files, of which 71 are genuine: the struct context models (21), the CQRS context models (34), the GraphQL context models (10), and six singles. The struct-slice closed union and its `isinstance` ladder become a Protocol plus an emit-slot key supplied by the language's hooks, with each language owning its own slice dataclass. The CQRS models are the systemic case — they carry paired per-language field sets written when only two generators existed, so the later two already write their own content into fields named for other languages; those pairs are re-modelled as single fields keyed by language id, since merely dropping the suffix would re-create the closed set under new names. **One** declaration becomes a reviewed exemption with a written reason rather than a rename: a genuine target name that the out-of-scope docker package consumes in production, which therefore needs a follow-up design. The four `sql`-substring identifiers considered while specifying this decision are **not** exemptions — the ratchet derives its vocabulary from the registered language set, `sql` is not a registered language, and so they never match; the ratchet's self-test proves each as a non-match rather than baselining it. A vocabulary rule and a hand-counted exemption list can disagree, and when they do the vocabulary rule governs: an exemption entry that can never be reached is a silent hole, not a review.

- **D5 — The canonical service-body enumerator is the only enumeration of a service's DSL bodies.** No package hand-rolls a body walk. The accessor's own docstring already declares this and records that every hand-rolled copy has drifted, each omitting a different body kind.

- **D6 — Scope fence.** The SQL and component codegen packages are out: neither shares a duplicated body with a language package and neither depends on `datrix-codegen-common` at runtime. No part of this decision adds that dependency.

- **D7 — The thin delegating micro-generator classes are deliberately not consolidated.** Their bodies are a dependency tuple, a constructor that stores its arguments, and a `render` that forwards. The variation in constructor arity and forwarded keyword arguments means a shared factory would have to model that variation, plausibly costing more than the boilerplate it removes. This is an explicit exclusion, not an unexamined gap.

- **D8 — Guards land before the migrations they police.** Two ratchets ship first with baselines pinned at current counts, so nothing new can be added while existing entries are removed; each migration decrements its baseline in the same change, reaching zero at the end. This follows the existing ratchet-plus-baseline precedent and the pinned-count exemption model.

**Invariant table:**

| # | Invariant | Enforcement mechanism |
| --- | --- | --- |
| 1 | Exactly one definition of each hoisted helper exists across the language packages | Duplicate-body scan reports zero exact-duplicate groups for the consolidated symbol set; the only surviving per-package definitions are pure pre-binding adapters — a docstring and a single `return` delegating to the shared builder — not duplicated bodies |
| 2 | No language package redeclares a shared-enum member set | Shared-vocabulary ratchet passes at a zero baseline; each package's own suites exercise the imported enum |
| 3 | No symbol in the shared codegen package carries a target name | Shared-layer target-name ratchet passes at a baseline holding exactly one reviewed exemption, 70 genuine declarations fixed (down from 76 matched, of which the four `sql`-substring identifiers are provably outside the ratchet's language-derived vocabulary); the closed-world drill's fixture language plugin supplies a struct slice and builds a struct context with no edit to the shared package |
| 4 | No package hand-rolls a service-body walk | Zero private body-enumeration helpers survive in the language packages; a regression test proves a typed cross-service call inside a CQRS handler materializes its response module — written first and observed red against the shipped defect |
| 5 | Every hoist is behavior-preserving | Each affected package's targeted suites pass unchanged; no generated-output diff on the hoisted paths |
| 6 | The scope fence holds | The SQL and component packages' runtime dependencies still exclude `datrix-codegen-common` |

**Scope boundaries:** Not a merge of language-specific emission — type maps, extension maps, per-language capability declarations, genDSL domain declarations, per-target realization declarations, and the language hook bodies all stay where they are. Not a consolidation of the delegating micro-generator classes (D7). Not a change to the SQL, component, docker, AWS, or Azure packages (D6). Not a removal of target-named declarations from the foundation or CLI packages: those are platform config-schema models, whose relocation into the platform packages is a Decision-22-shaped question of its own, and documented canonical-import API whose renaming is a breaking change to a published surface — so the new target-name ratchet is scoped to the shared codegen package. It also matches registered *language* names only, because one registered platform name is a common English word and including platforms returns hundreds of spurious hits; widening the ratchet requires solving that collision first. Not a cross-language parity or matrix test: each package tests its own surface, and the cross-cutting checks are repo-level scripts, never a test suite in the showcase repo. Not an endpoint-handler body-method parity change — two same-named constants encode genuinely different concepts (a cross-service call body versus request parameter binding), and the capability question that separates them belongs to the Cross-Target Parity Program.

**Status:** Adopted. Both ratchets ship in the import-boundary checker with frozen decrease-only baselines and their own non-vacuity self-tests; the named helper clusters are hoisted; the shared codegen package's target-named surfaces are down to a single reviewed exemption; and the shipped body-walk defect is fixed with a regression test that was observed red first.

Three things surfaced during implementation that the approved shape did not anticipate, and each is recorded above rather than quietly absorbed: the exemption count is one rather than five (a language-derived vocabulary cannot match `sql`); a fourth copy of the replay-plan resolvers existed in a package the duplication measurement had not attributed them to, and it carried a fail-loud guard the shared copies lacked, so consolidation was resolved as a union rather than a deletion; and language-named fields written with an abbreviation rather than the registered name are invisible to an identifier ratchet whose vocabulary is the registered set — those were found by review, not by the guard, and the packages that did not emit them had been filling them with silent-default placeholders.

---

### Decision 35: The azure-vm Provider — Azure-Hosted Containers with Provider-Emitted Infrastructure (Adopted)

**Rationale:**
- A container stack running on a cloud VM, backed by cloud-managed state and authenticated by a platform-assigned workload identity, has no truthful provider identity today. It is declared `local`, which means self-hosted infrastructure the generator neither provisions nor knows the shape of — and which is also the identity assumed when no deployment is declared at all. Calling a cloud-hosted deployment `local` forces every cloud resource out of band and leaves the generator unable to state anything true about the target.
- Widening `local` is not available. `local` is the no-declaration default; it declares `owns_provider_platform_generator = False`, which is the fact the shared deployment plan reads to decide whether a provider-owned generator runs at all; and its capability declaration is shared verbatim with the container runtime generator. A `local` that sometimes provisions cloud infrastructure means nothing, and leaves no name for the equivalent on other clouds.
- The framework already composes the two axes independently. The platform set for a run is the sum of the runtime axis (which platform contributes container scaffolding for this runtime) and the provider axis (which provider owns a generator). The pairing of a container runtime with a cloud provider is therefore a supported composition, not a special case — per-platform configs are already built per platform name, so the container runtime generator receives its own config even when the primary provider config belongs to a cloud provider.

**Result:**

- **D1 — A distinct provider identity, not a widened one.** The provider is registered under the platform entry-point group from the Azure platform package, declares the container runtime as its only supported runtime, and declares that it owns a provider platform generator. The container runtime generator is unchanged and continues to own all container artifacts.

- **D2 — Its capability declaration is its own, derived from the self-hosted target's.** Values mirror the self-hosted container target — container-secret backend, password RDBMS connection identity, nginx gateway with no TLS termination, container serverless model, the file-backed config store set — and diverge only where the topology genuinely differs. It declares its own runtime spec rather than importing the container target's, so the two can diverge later without coupling the packages.

- **D3 — Managed state is provisioned, not merely connected.** Under this provider the managed relational, object-storage and messaging flavors are supported AND provisioned by emitted infrastructure templates, rather than connect-only. Container flavors remain supported for what genuinely stays self-hosted on the VM.

- **D4 — Connection values are resolved from provisioned infrastructure at deploy time.** The emitted infrastructure declares its endpoints as outputs; the deploy path resolves them into each service's config store, not the container environment file — the generated runtime config client is file-backed and performs no environment reads, so a value written only to the environment file is consumed by nothing. The environment file remains the destination for a value a third-party container image's compose entry interpolates; everything the generated application itself reads goes to the config store. This supersedes the compose target's authored-configuration rule for this provider only.

- **D5 — The declaration stays inside the existing coordinate union.** A repo-level parity gate unions every capability surface across all installed platforms and fails when any platform has no opinion on a coordinate a peer declares; the reviewed-holes file stands at zero. A new provider that introduces a novel coordinate breaks not only that gate but the per-package capability tests of every peer, which resolve their required set against the live registry. The new declaration is therefore constrained to coordinates the union already carries, or it adds the peer exclusions in the same change.

**Invariant table:**

| # | Invariant | Enforcement mechanism (planned) |
| --- | --- | --- |
| 1 | A cloud-hosted container deployment has a provider identity that truthfully states what it provisions | The provider is registered and resolvable; the no-declaration default is unchanged |
| 2 | Pairing the container runtime with this provider selects both the container scaffolding generator and the provider's own generator | Asserted directly on the resolved platform set for that runtime/provider pair |
| 3 | Every capability field is a declared fact with a written reason where excluded | The declaration's own construction rejects a set-shaped surface with undeclared, unexcluded coordinates |
| 4 | Adding this provider leaves every peer platform's suite green | The repo-level parity gate and each peer package's capability test pass unchanged |
| 5 | Emitted infrastructure authors no connection string or account key | A negative check over the emitted infrastructure templates |

**Scope boundaries:** Confined to one provider on one cloud; the equivalent on other clouds is deliberately unbuilt but not designed out. The container runtime generator is unchanged. The per-profile platform configuration block gains one field for this provider rather than becoming an open plugin-keyed map — that larger refactor is explicitly out of scope. Does not change any other provider's cells, the language-side clients, or which flavors exist.

**Status:** Adopted. The provider is registered in the tree: the plugin class, capability declaration, platform config model, and infrastructure template for the compute resource all ship.

---

### Decision 36: One Fact, One Home — Residual Duplication and Standard-Library Adoption (Adopted)

**Rationale:**
- Decision 34 hoisted the exactly-duplicated bodies out of the four language packages and shipped two ratchets. A fresh measurement on top of it finds the sharpest remaining class: **shared code already exists, and a package keeps a private copy of it anyway.** A language package's cache generator restates ~311 lines the shared cache-method-spec algorithm already owns; the NoSQL DSL-concept table is declared in the shared codegen package and redeclared verbatim in two language packages; the GraphQL string-scalar set is declared shared and redeclared in two more. The DSL-concept table is the worked example in the prohibited-patterns catalogue, whose stated failure mode is generated NoSQL repositories silently using one engine's terminology for another — three copies means adding a fifth engine can produce exactly that, on one language only.
- **The shared-vocabulary ratchet cannot see any of them, by construction.** It fires only when a language package redeclares a member set already declared in the shared *enum* module. Every table above lives in the shared package's `algorithms` subtree, outside that vocabulary. The ratchet is passing at zero and is correct to; its scope is narrower than the rule it enforces, which also covers a vocabulary duplicated across two or more packages with no canonical home. Nothing checks that half.
- **The exact-duplicate metric goes quiet exactly as the problem gets worse.** 123 function names are defined in precisely the four language packages and nowhere else; only 18 still have a byte-identical pair, and 105 have already drifted apart. Four identical copies are cheap to fix and harmless today; four drifted copies are expensive to fix and already wrong on at least three targets. A scan keyed on identical bodies is blindest where the risk is highest — the divergence Decision 34's own rationale identifies as the failure mode.
- **A parallel emission layer survives in one language package.** Production generation routes the GraphQL, function, and integration domains through their micro-generators, but the older generator classes remain: two are referenced by no production module at all and are kept green solely by their own tests, and a third survives only so one method can be called. Tests that prove things about a path production no longer runs are worse than absent — they are false confidence.
- **Six hand-written Kahn topological sorts and four hand-written cycle detectors exist across five packages, while `graphlib` is imported zero times.** It has been in the standard library since 3.9 and every package declares a 3.11 floor. Each site re-derives in-degree bookkeeping and infers a cycle from a length comparison rather than reporting which nodes form it.
- **Three declared runtime dependencies are never imported**, and a property-based testing library sits in a foundation package's runtime dependency list, so every install of that package — and transitively every generated-project toolchain install — pulls it for one module consumed only by that package's own tests.

**Result:**

- **D1 — A private copy of code that already has a shared home is deleted, not reconciled.** Every consuming package already declares the shared codegen package as a runtime dependency, so each removal is deletion, not relocation, and adds no edge to the dependency graph. A shared symbol that consumers must import is public: a private name cannot be a shared vocabulary. The credential-position classification lands first — it decides whether an integration value position is treated as credential material, and its canonical declaration carries a written promise that the classifications will not diverge which a third uncoordinated copy already breaks.

- **D2 — Duplicate-vocabulary detection stops being source-keyed.** A new ratchet asks "is this member set declared in two or more packages?" rather than "does this duplicate a designated source module?". That subsumes both halves of the rule — a table with a shared home and a language copy is a duplicate group, and so is a homeless table with three copies — and needs no notion of which copy is canonical. It carries a decrease-only baseline and a non-vacuity self-test that plants a duplicate, sees the exact count delta, reverts, and sees it clear. The existing enum-scoped ratchet is untouched at its hard zero: it enforces something strictly stronger on a narrower surface, and folding it into a baselined form would weaken it. **A duplicate a design *requires* is a baseline entry with a written reason, never silence** — the per-platform capability declarations, the per-target realized-provider sets, and the per-adapter migration-operation sets are all of that kind. A container assembled entirely from a shared enum's members is consumption, not duplication, and is exempt in both ratchets.

- **D3 — The standard library owns topological ordering; the hand-rolled bookkeeping goes.** `graphlib` is stdlib, so this adds no dependency to the zero-dependency foundation or to any shared layer. The swap is **not** the obvious one: the group-based ready-set loop is not equivalent to a loop that re-sorts its ready list after every single pop, because a node freed by the current pop can jump ahead of an already-ready node with a later key. The sorter is therefore driven one node at a time with the caller's own tie-break key preserved. **Order equivalence is proven by a test authored against the current implementation and observed green first, then the implementation changes beneath it** — one site pins its diagnostics to byte-identical output, so any reordering there is observable. The seed dependency graph migrates its ordering half only: it returns a partial order plus *all* cycles and deliberately continues past one, which a stdlib exception that reports a single cycle and aborts cannot express.

- **D4 — Two identical GraphQL type sorts become one, and a reference cycle fails loud.** The shared and language copies share algorithm, name, tie-break, and an O(V²) inner rescan that no reverse-edge index avoids; they differ only in cycle handling. One raises with the involved types named and a remediation hint; the other logs at ERROR, appends the unordered remainder, and emits code its own docstring says may fail at runtime. Emitting knowingly-broken output with a log line is the silent-fallback shape principle 1 forbids: generation fails instead. Only cycle inputs change behaviour, so no valid-input byte moves.

- **D5 — A parallel emission layer is removed, coverage first.** The declared surface is the only emission path for the concern it owns; a residual imperative path emitting the same artifacts is a bypass to be closed. Because most of the behaviour proven against the dead classes has no equivalent assertion against the live micro-generators, **coverage migrates before deletion, in the same change** — deleting a module and its tests together silently deletes whatever those tests were the only proof of. The structural guard is a package-owned check that no generator module is reachable only from tests, landed with a pinned baseline ahead of the deletions it polices so the next instance cannot appear silently.

- **D6 — Intra-package consolidation needs no boundary decision and is ranked by duplicated lines per unit of coordination.** It reaches surfaces nothing else will: the SQL package is fenced out of Decision 34 and gains no shared-codegen dependency, so package-local extraction is the only lever that will ever apply to its two dialect reflectors. Where two packages independently grew the same internal duplication between the same pair of concerns, that is evidence the missing abstraction belongs in the shared layer rather than being fixed locally three times — and only decisions and structure move there, never template bodies.

- **D7 — One implementation per fact in the foundation layer, and no new third-party dependency to get there.** A dependency added to the zero-dependency foundation is paid for by every package and every generated-toolchain install, so the bar is correspondingly high: deep-merge, duration parsing, and semantic-version validation are consolidated in place rather than delegated to a library. Duration is the sharpest case — the accepted unit set is currently two different facts, so whether a configuration value may say `"1d"` is answered differently depending on which code path reads it. Version validation adopts the official published grammar as a named, sourced constant rather than a hand-written approximation that accepts a trailing prerelease separator as valid. The C-style string escaper is deliberately **not** replaced by a JSON serializer: it escapes the two Unicode line separators that are statement terminators in one target language, making it more correct than the library, and a marker in the source already records that intent.

- **D8 — A declared dependency that is never imported is deleted, and a test-only library leaves the runtime list.** A dead dependency is also a false signal that the capability it implies exists. A testing library moves to an optional extra mirroring the existing testkit-extra pattern; because the environment bootstrap installs base dependencies only and then each package's declared dev specs, the extra must be named in that package's own dev list to remain installed.

- **D9 — What is deliberately not consolidated is recorded, with the invariant that requires it.** Per-platform capability declarations and per-target realized-provider sets are near-identical *because* their governing decisions require each target to declare its own column and forbid a shared table; merging them would delete the invariant. Per-adapter expressible-operation sets stay independent — but where one adapter's comment asserts a rule its code cannot enforce ("must never widen" the orchestrator's policy), the rule gains a check: the orchestrator declares the policy set once and validates every registered adapter against it. Also excluded: the thin pre-binding adapters Decision 34 already names as the consolidated state; four naming conventions that share a spelling rule today but would become a breaking edit if merged; a deliberate two-form API already delegating to shared code; and a duplicate whose own docstring records the import cycle it exists to avoid.

- **D10 — The drift measurement is replaced with one that does not go quiet as drift sets in, and it now serves two axes with one scanner.** `parallel_implementation_drift.py` (`D:\datrix\datrix\scripts\library\test\parallel_implementation_drift.py`) takes an `--axis languages|platforms` parameter, and its gate wrapper `parallel-implementation-drift-gate.ps1` (`D:\datrix\datrix\scripts\test\parallel-implementation-drift-gate.ps1`) takes `-Axis`; a second scanner inside the tool that exists to find second implementations would be self-refuting. **The comparison unit is the package, not the registered target name.** On the platform axis five registered names resolve to three packages (`azure` and `azure-vm` both live in `datrix_codegen_azure`; `docker` and `local` both in `datrix_codegen_docker`); keying by registered name would compare a package's `src` tree against itself and report every function in it as a parallel implementation of itself, so names sharing a package fold into one entry labelled with both (`azure+azure-vm`). On the 1:1 language axis the fold is a no-op, which is why the language report is unchanged before and after. Exclusion is axis-relative: on the platform axis the language packages are part of the exclusion set and vice versa, so a name shared between a language and a platform package is reported by neither (`parallel_implementation_drift.py:493-494`). It remains a **report with a decrease-only count baseline, not a pass/fail gate on individual names** — a name-keyed check cannot distinguish an intentional per-language emission difference from an unreconciled fix, and a gate that cannot make that distinction gets turned off — but there are now **two separate baselines, never a shared ratchet**: `D:\datrix\datrix\scripts\config\parallel-implementation-drift-baseline.json` for languages and `D:\datrix\datrix\scripts\config\platform-implementation-drift-baseline.json` for platforms; `-UpdateBaseline` writes only the axis it was invoked with. Every drifted group is classified once — intentional adaptation with a written reason, or a divergence to fix — with zero unclassified as the bar. A symbol carrying one registered language's name inside another language's package is a target-name leak the shared-layer ratchet cannot see, because that ratchet is scoped to the shared codegen package; such symbols are renamed. Every run proves its own non-vacuity with nine self-test assertions, including that two names sharing one package fold into one labelled entry, that an axis whose every registered name shares ONE package is refused as vacuous even with two registered names, and that the entry-point module root the scanner resolves packages by equals the resolved plugin class's module root for every registered language.

**Invariant table:**

| # | Invariant | Enforcement mechanism |
| --- | --- | --- |
| 1 | A member set declared in two or more packages is a baseline entry with a written reason, never silence | Cross-package duplicate-vocabulary ratchet (`check-import-boundaries.ps1 -CheckCrossPackageVocabulary`), decrease-only baseline, with a plant/observe/revert non-vacuity self-test; the enum-scoped ratchet (`-CheckSharedVocabulary`) stays at its hard zero |
| 2 | Code that has a shared home has exactly one definition | Per-symbol negative check that the private declaration is gone from every consuming package, plus a positive test that the shared value drives behaviour — required especially where the deleted copy had no test at all |
| 3 | A topological order is preserved across the migration to the standard library | Per-site order test authored against the current implementation and observed green BEFORE the swap, asserting full sequences rather than index inequalities; a cycle then reports its members instead of being inferred from a length comparison |
| 4 | A reference cycle fails generation rather than emitting code that breaks at runtime | One shared sort; a cycle fixture raises on every consuming target, with the degrade path's test rewritten red-first |
| 5 | A generator module is never reachable only from tests | Package-owned reachability check with a pinned decrease-only baseline, landed before the deletions it polices and decremented to zero by them |
| 6 | Consolidation is behaviour-preserving unless it is declared otherwise | Duplicate-block count strictly dropped per package (before/after pasted) and generated output is byte-identical; the single intended exception (azure's pooled-group hash) is declared and re-blessed as a diff, never reported as a no-op |
| 7 | One implementation per fact in the foundation, with no new third-party dependency | Negative grep for the second implementation, plus a test proving the union of previously-divergent accepted inputs now resolves through one path |
| 8 | A declared dependency is an imported dependency | Absent from the manifest; a clean editable install of each affected package succeeds and the moved test-only library still resolves in the shared environment |
| 9 | An adapter cannot widen an orchestrator-owned policy set | `MigrationOrchestrator` validates every registered adapter against the declared policy and fails loud on a widening; both per-adapter sets survive independently |
| 10 | Parallel implementations across language packages, and separately across platform packages, are measured by a signal that survives divergence | Name-keyed report (`parallel_implementation_drift.py --axis languages\|platforms`, gate wrapper `parallel-implementation-drift-gate.ps1 -Axis`) with a runtime-derived, package-folded target set per axis, two separate decrease-only count baselines (never a shared ratchet), and zero unclassified groups |

**Scope boundaries:** No item adds an edge to the dependency graph, and Decision 34's scope fence holds — the SQL and component packages gained no shared-codegen runtime dependency; their consolidation stayed package-local. No new third-party dependency was taken anywhere, and specifically not in the foundation layer: the merge, version, duration, email-validation, retry, quantity-parsing, and case-conversion libraries were each considered against a named site and each rejected. The two hand-written DSL parsers were not replaced — their error messages carry the source-location data the fail-fast contract depends on. The cron dialect translators, which translate between vendor dialects rather than validating a single one, were not touched, nor was the fixed-size batching primitive that landed in a Python release above the declared floor. No cross-language parity or matrix test was added: each package tests its own surface, and the two repo-level items here are scripts, never a test suite in the showcase repo. The C-style string escaper was deliberately left unreplaced.

**Status:** Adopted. All ten invariants hold today as executable gates: the cross-package vocabulary ratchet ships and passes; every private copy of shared code is gone; `graphlib` drives topological ordering at every migrated site with order-equivalence tests proven against the prior implementation first; the two GraphQL sorts are one, and a reference cycle fails generation instead of emitting code that breaks at runtime; the residual generator layer is gone with its coverage migrated first and a reachability guard landed to catch the next instance; intra-package duplication dropped in every targeted package; the foundation layer's hygiene set landed with no new third-party dependency; the three dead dependencies are gone and the test-only library moved to an extra; the migration-adapter policy set is enforced by the orchestrator rather than asserted in a comment; and the parallel-implementation drift report is live with every classified group accounted for.

Two things surfaced during implementation that the approved shape did not anticipate. First, the live drifted population the scanner reported was roughly five times the design-time estimate (626 groups, not the ~105 estimated), because the scanner correctly counts class methods as well as module-level functions — several of the design's own named review candidates are class methods. The broader population was adjudicated design-faithful rather than the scanner narrowed to match the estimate, and reviewing it at full scope found 25 real production bugs an exact-duplicate scan could never have surfaced — among them a batch-lookup optimization that silently never fired on one target (an unconditional `return None` stub with no call site), a missing type-unwrap producing a reachable runtime `TypeError` on nullable Decimal fields, and a cache-engine mapping gap that would have failed real generation outright. This is the direct empirical confirmation of this decision's own rationale: an exact-duplicate metric goes quiet exactly where the risk is highest. Second, one function-level-import ratchet baseline needed a reviewed increase of one, in a file that already carried four deferred imports dodging the same documented package-init cycle; the new site is a fifth instance of that same reviewed pattern, not a new class of debt, and the alternative — restructuring the foundation package's root import order — was judged out of this decision's scope.

---

### Decision 37: Zero-Inbound VM Deployment and the Deploy-Time Binding Invariant (Approved — Implementation In Progress)

**Rationale:**
- A provider that emits infrastructure must also own deploying it. When the runtime axis (containers) and the provider axis (cloud infrastructure) each emit their own artifacts and neither owns the deployment step, the generated tree's entrypoint assumes infrastructure that nothing in the tree ever creates.
- Values that only become knowable at deploy time are a recurring defect class of their own: one artifact produces a value, another consumes a different value for the same fact, and nothing compares them. A resolved endpoint, a generated key, a derived port — each needs exactly one producer, a consumer that reads the same value the producer wrote, and a check that catches the case where either side is silent or where both sides disagree.

**Result:**

- **D1 — Two deploy scripts, two owners.** The runtime generator owns the on-machine container deploy script — build images, bring the stack up — and needs no cloud knowledge to do it. The provider generator owns an outer deployment CLI that creates the resource group, deploys the infrastructure, uploads the generated tree, and triggers the inner script. Neither generator overwrites the other's file.

- **D2 — Deployment opens no inbound port.** Artifacts travel to blob storage; execution happens through the cloud's managed run-command channel using the VM's system-assigned identity; output streams back through append blobs. Shell access is break-glass, never the deploy path, and the generator authors no inbound SSH rule.

- **D3 — Deploy-resolved values land where the consumer reads them.** For a file-backed config store that performs no environment reads, that is the config store, not an environment file — the same binding this decision's Decision 35 correction states for that provider.

- **D4 — Every deploy-resolved key has exactly one producer.** A key produced by nothing is a hole; a key produced by two artifacts is a race between whichever wrote last.

- **D5 — A deploy-resolved key carries no compile-time default.** A plausible-looking wrong value is worse than an absent one: the absent one fails loud at first read, and the plausible one runs quietly against the wrong target.

- **D6 — No generated value equals the config key that holds it.** Emitting a key's own name as its value is a silent fallback wearing the shape of a real one; a generator that cannot resolve a value raises instead of writing a placeholder.

- **D7 — Every network-security allow rule's port is a port some artifact actually publishes.** The rule set is derived from the real port bindings the generated tree publishes, never authored as a constant alongside them.

- **D8 — A managed edge may terminate TLS in front of a self-hosted gateway without becoming the gateway.** Routing, CORS, and rate limiting stay with the self-hosted gateway; the platform's declared supported gateway types are unchanged by the presence of a TLS edge in front of one. Origin restriction pins the edge's own deploy-time public address, because the cloud's service tag for that managed service does not contain any one instance's egress address.

**Invariant table:**

| # | Invariant | Enforcement mechanism |
| --- | --- | --- |
| 1 | The runtime generator's deploy script and the provider generator's deploy script never collide | The two generators emit different file paths; each package's own tests assert its script's contents |
| 2 | Deployment opens no inbound shell port | No inbound rule for the shell port is emitted; an acceptance check asserts the emitted rule set contains no wildcard/Internet source and no shell port |
| 3 | A deploy-resolved value is written to the config store its consumer actually reads | A generation-time binding check running after every generator has produced its files and before anything is written to disk — the one point with complete cross-target content — fails generation on a mismatch |
| 4 | Every deploy-resolved key has exactly one producer, no compile-time default, and no value equal to its own key name | The same binding check |
| 5 | Every emitted allow rule's port is a real published binding | The rule set is derived from the published port bindings; the binding check compares them |
| 6 | A managed TLS edge does not change the platform's declared gateway capability | The platform capability declaration's supported gateway types stay unchanged, and its written exclusion entry states what the managed edge does and does not realize |

**Scope boundaries:** Confined to the deployment path this provider's infrastructure requires; does not change the runtime generator's container artifacts or any other provider's deployment mechanics. Does not introduce a new managed gateway type — the TLS edge fronts the existing self-hosted gateway rather than replacing it.

**Status:** Approved — Implementation In Progress.

---

### Decision 38: Lowering the Declarative Floor on Both Axes — Collapsibility Classification and Declared Dependency Tables (Adopted)

**Rationale:**
- Decision 36's per-name drift classification records whether a divergence is *legitimate* — intentional or tracked — with a written reason. It does not record whether the pair is *collapsible, and by what mechanism*, and the two questions come apart badly: a large fraction of the written intentional reasons already name the parameter that would collapse the pair. One is a shared statement-walk whose two copies differ only in which casing convention each language's generated identifier space uses; another is an identical loop body whose only duplicated part is a per-class dict-accumulation wrapper. Both reasons are legitimate. Neither divergence is irreducible.
- The platform axis had no measurement instrument at all until the two-axis scanner landed — no baseline, no ratchet, and no worklist for platform-dependent code existed to classify in the first place.
- "Which packages does this feature require, in this language, at what scope" is a distinct decision family with no declarative home today: it is hand-written per language across roughly forty sites, and it has already shipped a reachable defect — a TypeScript service declaring a memcached cache block gets no memcached client package in its generated manifest, because the live selection path emits one hardcoded package name regardless of the declared engine.

**Result:**

- **D1 — Both axes carry a collapsibility classification alongside the existing legitimacy classification.** Each classification entry carries a `mechanism` field naming which collapsing mechanism would remove the divergence, or `none`; a `none` entry carries a one-line reason distinct from the existing legitimacy reason, so "legitimate and irreducible" becomes a stated claim rather than an inference from "legitimate."
- **D2 — Classification completeness is a checked invariant, not a comment.** No such check exists before this decision — the requirement that every drifted group be classified lived only as a comment inside the classification file. Each axis's classification entry count must equal that axis's live drifted count, with zero entries unclassified on either field, verified by an executable check run alongside the drift gate.
- **D3 — The largest mechanically-collapsible families are collapsed with mechanisms that already exist, before any new surface is designed.** The casing family is served by the already-declared `LanguageProfile.naming` casers (`identifier_caser`, `type_name_caser`, `constant_caser`); inventing a casing surface to collapse it would be a second home for a declaration that already exists. A mechanism label is a hypothesis about the code, not a fact about it: a per-body read of every name labelled collapsible-by-casing found roughly half carried a divergence beyond casing — an absent branch, a different return arity, a missing parameter — and reclassified those to their real mechanism before any hoist touched them, so the eventual casing pass worked from a worklist that was right before it started. One name (`event_block_directory_caser`) remains labelled but unreached: two of its four legs need a role `NamingProfile` doesn't declare (snake_case for build-tool package segments, kebab-case for directory names) — collapsing it would mean inventing a declaration, which this same decision forbids without a decision family to justify it.
- **D4 — A new declarative surface is added only where a decision family has no declarative home.** The mini-DSL family clauses govern this directly: they forbid folding a new concern into an existing surface, and forbid a new surface where a declaration already exists.
- **D5 — Pure predicates over the sealed model live once, in the shared layer, not once per platform.** The shared home is `D:\datrix\datrix-codegen-common\src\datrix_codegen_common\generation\service_predicates.py`; a predicate carrying no target specificity gets exactly one definition. Where a predicate genuinely differs per platform, the difference becomes a declared per-platform set read by one shared predicate — the same "shared layers ask, target plugins answer" move already made for provisioning dispatch — never a per-platform copy of the algorithm. Applying this move to Azure's own `_service_has_deployable_block` surfaced a live defect, not just duplication: Azure's predicate omitted `enqueue_consumers` from its counted deployable-construct set even though three sites in Azure's own generators realize it, so a service whose only deployable block was an enqueue consumer was rejected at Azure validation despite Azure being able to generate it. The declared set now includes `enqueue_consumers` for Azure — a deliberate behavioural correction, re-blessed as a diff rather than landed silently, per D7.
- **D6 — Both drift ratchets move monotonically down, per workstream, with the decrease pinned in the same change as the hoist.** A hoist that does not move the number did not remove a parallel implementation.
- **D7 — Behaviour preservation is proven by byte-identical generated output, not by a green suite alone.** A deliberate behavioural change is re-blessed as a diff, never landed silently.
- **D8 — The one new declarative surface, per-language dependency tables, carries no version constraint.** Versions already have a declarative home — the dependency catalog (`D:\datrix\datrix-common\src\datrix_common\config\project\catalog.py`, fed from each generator's `defaults.yaml` and `.dcfg` project dependencies) — so a row carrying its own version would create a second home for versions on day one. A row is shaped as feature (plus a typed qualifier) → package name + scope, and the version resolves through the existing catalog. The feature key alone cannot express every selection: a language may select between two client packages by infrastructure engine or flavor, and engines/flavors are open, registry-validated identifiers belonging to no closed catalog, so the schema carries a typed predicate qualifier column validated against the registered flavor declarations — never free text.
- **D9 — Feature keys validate against the union of two closed vocabularies, not one.** The app-level presence catalog at `D:\datrix\datrix-common\src\datrix_common\generation\feature_catalog.py` (13 entries, raising with the full valid list on an unknown name) and the service-level feature getters on `ServiceOrchestrator` at `D:\datrix\datrix-common\src\datrix_common\generation\orchestrator.py:204-246` (19 keys) are both closed and both importable; a dependency table validates against their union and raises on an unknown key from either side.
- **D10 — Schema, homes, and the sole-source rule.** The schema and validating loader live at `D:\datrix\datrix-codegen-common\src\datrix_codegen_common\generation\dependency_dsl.py`, mirroring the emit-table module's adopted mechanics — frozen typed rows, validation in constructors at module import (which is plugin-registration time), closed compilation, and a mutation gate in each language package's own suite. It belongs under `generation/`, not `transpiler/`: emit tables sit in the transpiler because Stage-3 emitters consume them, while dependency selection is a generation-manifest concern. Rows live per language at `D:\datrix\datrix-codegen-<lang>\src\datrix_codegen_<lang>\generation\dependency_tables.py`, mirroring the existing per-language emit-table modules. The authoring unit is a table row; no grammar is added — text is earned, and this does not earn it. The declaration is the only source of a generated manifest's dependency set: no language package computes a dependency name set outside its table.
- **D11 — Shared raise sites are parameterized by the caller's own already-raised exception class, never a new declared-exception-type hook.** The original sketch for this family was a language-plugin hook a shared body would read to pick its exception type. That hook was never built, and none was needed: every collapsed name has exactly one production call site per package, so the raised class is supplied there, beside the table or vocabulary it belongs to — the same shape `NoSqlFilterSyntax.error_type` already used for the NoSQL filter skeleton. The classes are deliberately not unified where a caller's choice is load-bearing: python's `transpile_where_comparison` raises a bare `ValueError` because python's own entity-query chain catches that exact class to trigger a pattern-fallback; forcing it to a shared exception type would silently change which fallback runs. Shared homes: `datrix_codegen_common.algorithms.declared_table_lookup` (lookup-or-raise over a caller's own table — the `_geosql_spec` and `_hmac_digest_name` family), `datrix_codegen_common.algorithms.entity_query_chain.transpile_where_comparison` (the `field.lt(value)`-shaped `where()` comparison body, parameterized by the caller's own cased receiver), `datrix_codegen_common.transpiler.skeleton.nosql_dispatch.nosql_sort_direction` (folded out of every target's own `orderBy(...)` sort builder, reading `NoSqlFilterSyntax.error_type` the same way the filter skeleton does), and `datrix_codegen_common.generation.raise_site_guards.reject_unrealizable_gateway_fields` (the platform-axis analogue: aws/azure/docker each declare which gateway rate-limit fields they cannot realize and what to write instead, read by one shared raise site).
- **D12 — A classification entry cannot claim `intentional` while its own reason describes a capability or emission gap.** An exhaustive per-entry read of the language-axis classification file found five entries shaped exactly that way — soft-delete cascade gating on a trait instead of the DSL's declared `onSoftDelete` cascade, `Entity.update()` silently bypassing lifecycle hooks, a statement-position stub, a cache-pooling placeholder that silently realized every declared config unpooled, and a spec-placeholder gap that could violate a field's own regex constraint. Each was ruled a defect, not a capability difference, with a reference target naming the language that already does it correctly, and fixed at the source rather than reclassified to `tracked` and left. The premise behind the cache-pooling fix — that every language is meant to support pooled cache connections — was resolved affirmatively: pooled-cache realization now ships across every registered language and platform, not just declared unsupported. The shared test-generator orchestrator's docstring heading that had called this class "suspected unintentional feature gaps, pending reconciliation by the repo owner" was itself stale — the kinds it named were already reconciled onto shared plans in every language package — and was rewritten to a historical record in the same change. The collapsibility-classification gate now rejects `mechanism: capability-gap-defect` paired with `status: intentional` outright, so this class cannot recur silently.

**Invariant table:**

| # | Invariant | Enforcement mechanism |
| --- | --- | --- |
| 1 | Both axes carry a collapsibility classification, so "how much target-dependent code is left, and what would remove it" is a query rather than an investigation | Each classification entry carries a `mechanism` field (which collapsing mechanism would remove it, or `none`), and for `none` a one-line reason distinct from the existing legitimacy reason |
| 2 | Each axis's classification entry count equals that axis's live drifted count, with zero entries unclassified on either field | An executable check over both classification files, run alongside the drift gate — no such check existed before this decision; the requirement lived only as a comment inside the classification file |
| 3 | The largest mechanically-collapsible families are collapsed with mechanisms that already exist, before any new surface is designed | The casing family is served by the already-declared `LanguageProfile.naming` casers (`identifier_caser`, `type_name_caser`, `constant_caser`) |
| 4 | A new declarative surface is added only where a decision family has no declarative home | The mini-DSL family clauses, which forbid folding a new concern into an existing surface and forbid a surface where a declaration already exists |
| 5 | Pure predicates over the sealed model live once in the shared layer, not once per platform | Shared home `service_predicates.py`; a predicate carrying no target specificity has exactly one definition; where it genuinely differs per platform, the difference is a declared per-platform set read by one shared predicate, never a per-platform copy of the algorithm |
| 6 | Both drift ratchets move monotonically down, per workstream, with the decrease pinned in the same change as the hoist | The baseline decrease is reviewed alongside the hoist that produced it; a hoist that does not move the number is not accepted as a hoist |
| 7 | Behaviour preservation is proven by byte-identical generated output, not by a green suite alone | Generated output compared byte-identical before/after; a deliberate behavioural change is re-blessed as a diff, never landed silently |
| 8 | Shared raise sites are parameterized by the caller's own exception class, never forced onto a new declared-exception-type hook | `datrix_codegen_common.algorithms.declared_table_lookup`, `.entity_query_chain.transpile_where_comparison`, `transpiler.skeleton.nosql_dispatch.nosql_sort_direction`, and `generation.raise_site_guards.reject_unrealizable_gateway_fields` each take the exception class as a parameter; a per-body read confirmed no caller could be unified without changing which exception a caller-side `except` clause catches |
| 9 | No classification entry claims `status: intentional` while its own written reason describes a capability or emission gap | The collapsibility-classification gate hard-rejects `mechanism: capability-gap-defect` paired with `status: intentional`; the five entries this class was ever true for are fixed, each against a named reference target |

**Scope boundaries:** Not inventing a surface where a declaration already exists — the casing family is served by `LanguageProfile.naming`, not a new casing table. Not sharing template bodies across languages: only decision logic and structure move to the shared layer. Not driving either floor to zero; the visit-floor is a documented, audited non-zero terminal floor. Not folding multi-step lowering into predicated rows — their consolidation path is shared plan modules. Not merging coincidental name collisions: unrelated functions that happen to share a name are metric overcount, and the correct response is a rename, not a fold.

**Status:** Adopted.

Landed: the two-axis measurement instrument and both count baselines; the collapsibility field on **both** axes, populated on every entry, with its own enforcement check and unclassified-count ratchets; the platform-axis classification file; the shared-predicate hoists (D5), including the declared per-platform deployable-block set that replaced the divergent per-platform predicate (and closed the Azure `enqueue_consumers` gap it exposed) and the adoption of the shared endpoint enumerator in place of a hand-rolled service/api/endpoint walk; the dependency-table surface (D8-D10) — schema, per-language row modules in all four language packages, and the out-of-table decision-site ratchet at zero; the casing family's collapse onto the already-declared `LanguageProfile.naming` casers (D3), reclassifying the mislabelled names to their real mechanism first; the shared raise sites (D11), parameterized by each caller's own exception class rather than a new plugin hook; and the capability-gap-defect reclassification (D12), with the stale orchestrator heading it depended on rewritten in the same change. Both drift ratchets hold at their decreased counts, and every classification entry on both axes is fully collapsibility-classified.

One name remains labelled collapsible-by-casing but unreached, by design rather than oversight: `event_block_directory_caser` needs a `NamingProfile` role for path-segment/kebab-case conventions the profile does not declare, and D4 forbids inventing that declaration without a decision family to justify it. `NamingProfile.structural_rule` itself is still populated as identity by every language, so the same boundary applies to any future structural-rather-than-case-based convention (a leading-underscore private-field prefix, a reserved-word escape).

---

## Installation

```bash
# Minimal (CLI only)
pip install datrix-cli

# Python + Docker
pip install datrix-cli datrix-codegen-python datrix-codegen-docker

# Full stack
pip install datrix-cli \
 datrix-codegen-python datrix-codegen-typescript datrix-codegen-sql datrix-codegen-java \
 datrix-codegen-docker datrix-codegen-aws datrix-codegen-azure

# Additional language generators
pip install datrix-cli datrix-codegen-dotnet datrix-codegen-java
```

**Note:** The CLI automatically discovers installed generators. You only need to install the generators you plan to use.

---

## Usage

Use the CLI to validate and generate:
```bash
# Validate a file or directory of .dtrx files
datrix validate system.dtrx
datrix validate examples/02-features/01-core-data-modeling/rest-api

# Generate (defaults: profile test; deployment from ConfigDSL for that profile; --language is required)
datrix generate --source system.dtrx --output ./generated --language python

# Generate for a specific profile
datrix generate --source system.dtrx --output ./generated --profile production --language python

# Short flag
datrix generate --source system.dtrx --output ./generated -L typescript
```

**Config-driven generation:** `language` is a required generation parameter — pass `--language`/`-L`, resolved against the registered `datrix.languages` set via `resolve_language_id`; there is no config fallback and no silent default. `deployment` (runtime, provider, target, registry) is the source of truth in `config/system.dcfg`. Infrastructure flavor for individual blocks (e.g. `flexible-server`, `event-hubs`, `blob-storage`) is set in each block's `.dcfg` config file. Generation reads deployment settings from resolved config — there are no deployment-affecting CLI overrides. See [Decision 6: Deployment Target Contract](#decision-6-deployment-target-contract-stable) for the full deployment model.

> **Note:** The `--hosting` and `--platform` CLI overrides have been removed. Deployment target is configured in ConfigDSL files, not CLI flags. `--language`/`-L` is required and is the sole source for the language target — a `language` key in ConfigDSL is a fail-loud error at generation time.

---

## Next Steps

- Read [Design Principles](./design-principles.md) to understand core principles
- Read [Language Reference](../reference/language-reference.md) to learn how to write `.dtrx` files
- See [Getting Started](../getting-started/first-project.md) and the runnable trees under [`examples/`](../../examples/)
