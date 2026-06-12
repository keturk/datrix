# Datrix Architecture Overview

**Version:** 2.0
**Last Updated:** May 2, 2026

---

## Introduction

Datrix is a code generation system that transforms `.dtrx` domain specifications into production-ready applications across multiple languages and platforms.

### Key Features

✅ **Template-Based Generation** - Jinja2 templates with automatic formatting
✅ **Fail-Fast Error Handling** - Errors caught at generation time, not runtime
✅ **Multi-Language Support** - Python, TypeScript, SQL
✅ **Multi-Platform Support** - Docker, Kubernetes, AWS, Azure
✅ **Type-Safe** - Exhaustive type mappings with validation
✅ **Modular Architecture** - 13 installable packages (core toolchain + optional **datrix-extensions**) plus showcase and projects repos
✅ **Specification-Level Testing** - DSL `test` blocks transpile to pytest under `tests/spec/` (Python) and Jest under `test/spec/` (TypeScript); see the [spec testing documentation](../guide/spec-testing.md)
✅ **Event contracts** - `ensure` clauses on `publish` events enforce publisher-side validation before `dispatch`
✅ **External library interfacing** - `extern service` declarations generate typed HTTP clients and deployment wiring for user-built services
✅ **Serverless block code generation** - `serverless` blocks deploy handlers as Lambda functions, Azure Functions, or container processes with platform-specific entry points and infrastructure provisioning
✅ **Centralized runtime config store** - a system-level `configStore` section generates a runtime configuration plane (AWS AppConfig, Azure App Configuration, or self-hosted Consul KV), local JSON defaults, and Python/TypeScript runtime clients for feature flags and operational tuning without rebuilds

---

## Sub-Documents

This overview was split into focused sub-documents for easier navigation. Each sub-document preserves the original section headings.

- **[Pipeline Flow & Capabilities](architecture/pipeline-and-capabilities.md)** — System architecture, pipeline stages, standard library, phase 01/02/03 capabilities, search engine integration, CDN / content delivery, managed API gateway
- **[Repository Architecture & Plugins](architecture/repository-architecture.md)** — 13 packages, plugin system, domain extension system, extern services, application containers, adding a new language
- **[Builtin Traits & Enums](architecture/builtin-traits-enums.md)** — 10 builtin traits, 2 builtin enums, injection mechanism

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
 A --> F[datrix-codegen-sql]
 CGC --> G[datrix-codegen-docker]
 CGC --> H[datrix-codegen-k8s]
 A --> I[datrix-codegen-aws]
 A --> J[datrix-codegen-azure]
 B --> K[datrix-cli]
 A --> K
 CC --> K
 D --> K
 E --> K
 F --> K
 G --> K
 H --> K
 I --> K
 J --> K
```

**Legend:**
- **datrix-common** (no dependencies) — Foundation and generation framework (AST model, type system, semantic analysis, standard library resources + loader protocols, config resolution, plugin protocols, generation framework). Does **not** import `datrix-language` — parser and stdlib-loader implementations are injected via protocols.
- **datrix-language** (depends on datrix-common) — Parser + CST-to-AST transformers, implements `ParserProtocol` and `StdlibParserProtocol` defined in datrix-common
- **datrix-extensions** (depends on datrix-common) — Optional domain packs; **not** required by `datrix-cli` or generators unless you declare `use extension` and install the pack
- **datrix-codegen-common** (depends on datrix-common) — Shared codegen intelligence: profile-driven transpiler, language-agnostic algorithms, context models, field analysis, parity checking, shared Grafana dashboard builder, GenDSL runtime, serverless/replayable-ingestion plans. Consumed by language codegen packages and by **all four** platform generators for its language-agnostic services.
- **Language Code Generators** (depend on datrix-codegen-common, which depends on datrix-common) — Python, TypeScript
- **Other Code Generators** (depend on datrix-common) — SQL, component
- **Platform Generators** (Docker, Kubernetes, AWS, Azure) — all four depend on **datrix-codegen-common** for its language-agnostic platform services (GenDSL runtime, shared Grafana `DashboardBuilder`, serverless and replayable-ingestion plans, shared enums) as well as datrix-common. They must **not** import the language-specific parts of codegen-common (`transpiler.*`, language-shaped `context_models`/`algorithms`) or any language generator package — see the [platform → codegen-common subtree contract](../../datrix-common/docs/architecture/import-boundaries.md#platform--codegen-common-subtree-contract).
- **datrix-cli** (depends on datrix-common, datrix-language; owns `GenerationPipeline` orchestration; discovers generator plugins dynamically)

> **`datrix_codegen_common/platform/` subpackage.** A `platform/` subpackage lives **inside the existing `datrix-codegen-common`** — a sibling of `gendsl/`, `dashboards/`, `algorithms/`, and `context_models/`. **No new package or repo is created**: the shared provider seam (the `resolve_runtime_spec` / `runtime_stack_token` helpers and the `PlatformInfrastructure` protocol) is language-agnostic platform code, exactly the layer `datrix-codegen-common` already owns. Because the four platform generators already legally import `datrix-codegen-common`, `platform.*` simply joins the closed list of language-agnostic codegen-common subtrees platforms may import (alongside `gendsl.*`, `dashboards.*`, `algorithms.serverless`, `context_models.serverless`, `context_models.replayable_ingestion`, `enums`) — no new graph node and no new boundary edge. The shared Grafana `DashboardBuilder` **stays in `datrix-codegen-common/dashboards/`** and platforms continue to import it directly; there is no re-home and no `ObservabilityIntegration` facade. See [Shared Provider Library](../../datrix-codegen-common/docs/architecture.md#shared-provider-library-platform) and [Decision 12: Language-Agnostic Provider Generators](#decision-12-language-agnostic-provider-generators).

**Import boundary enforcement:** The dependency edges above are enforced by automated tooling — see [Import Boundaries](../../datrix-common/docs/architecture/import-boundaries.md) for the full rule table and scanner usage. The scanner currently reports a known lower-bound caveat: files carrying a UTF-8 BOM are silently skipped (read with `encoding="utf-8"`), so the violation count is a lower bound until the scanner reads with `encoding="utf-8-sig"`. Fixing that is a tracked scanner-robustness follow-up, separate from the boundary-rule reconciliation.

---

## Core Principles

1. **Fail Fast, Fail Loud** — Catch errors at generation time, not runtime. See [Design Principles](./design-principles.md).
2. **Template-Based Generation with Formatters** — Jinja2 templates with ruff format (Python) / Prettier (TypeScript). See [Design Principles](./design-principles.md).
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
- **Prettier** - TypeScript code formatting
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

---

### Decision 3: One Repo Per Platform

**Rationale:**
- Independent versioning
- Independent releases
- Clear ownership
- Plugin architecture

**Result:** Separate repos for Docker, K8s, AWS, Azure

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

**Design reference:** [GenDSL Documentation](../../../datrix-codegen-common/docs/gendsl/overview.md) — Complete specification in datrix-codegen-common/docs/gendsl/

---

### Decision 6: Deployment Target Contract (Stable)

**Rationale:**
- Legacy models conflated runtime packaging shape, infrastructure provider, and cloud-managed targets into a single dimension
- "Docker" and "Kubernetes" are runtime/packaging targets, not cloud providers; "AWS" and "Azure" are providers, not runtimes
- One-dimensional models cannot express combinations like "Kubernetes on Azure (AKS)" or "Docker Compose on Azure VM" without overloading terms
- CLI overrides can create partial deployment states where the command line says one target but resolved config still contains values for another

**Result:**
- An explicit deployment target model replaces the single `hosting` dimension with four orthogonal fields:

```yaml
language: python | typescript

deployment:
  runtime: docker-compose | kubernetes | azure-app-service | ecs-fargate | app-runner
  provider: local | existing | aws | azure
  target: aks | eks | vm | ...        # optional, provider-specific
  registry: acr | ecr | ...           # optional, provider-specific
```

- `language` selects the generated application implementation
- `deployment.runtime` selects the deployable artifact shape (Compose, Kubernetes manifests, Azure App Service, etc.)
- `deployment.provider` selects the infrastructure provider or substrate owner
- `deployment.target` and `deployment.registry` are optional provider-specific refinements
- `host` remains a network endpoint concept only — never used to mean AWS, Azure, Docker, or Kubernetes

> **Note:** `runtime: azure-container-apps` is **retired**. Use `runtime: azure-app-service` for the native Azure PaaS runtime, or `runtime: kubernetes, target: aks` for a container mesh on AKS. Specifying the retired value raises a generation error with migration guidance.

**Construct-mapped realization:** Once a deployment target is resolved, each DSL block maps to the target platform's native primitive. Service deployment shape is derived entirely from declared blocks — no separate per-service runtime selector is needed. See [Design Principles — Construct-Mapped Platform Realization](./design-principles.md#11-construct-mapped-platform-realization-stable) for the full mapping table and rationale.

**Concept matrix:**

| Concept | Examples | Owns |
| --- | --- | --- |
| Language | `python`, `typescript` | Application source code, framework/runtime adapters, language package/dependency files |
| Runtime | `docker-compose`, `kubernetes`, `azure-app-service`, `ecs-fargate` | Deployable artifact shape and process model |
| Provider | `local`, `existing`, `aws`, `azure` | Provider-managed substrate, registry, identity, networking, managed services |
| Infrastructure flavor | `container`, `external`, `rds`, `flexible-server`, `event-hubs` | Per-block provisioning choice (RDBMS, cache, pubsub, etc.) |
| Host | `db.example.com`, `api.example.com`, `localhost` | Network endpoint |

**Deployment examples:**

```yaml
# Local Docker Compose
language: python
deployment:
  runtime: docker-compose
  provider: local

# Kubernetes on Azure (AKS)
language: python
deployment:
  runtime: kubernetes
  provider: azure
  target: aks
  registry: acr

# Azure App Service (native PaaS)
language: python
deployment:
  runtime: azure-app-service
  provider: azure
  registry: acr

# AWS ECS Fargate
language: python
deployment:
  runtime: ecs-fargate
  provider: aws
  registry: ecr
```

**Generator orchestration** becomes multidimensional:

| Deployment | Language generators | Runtime generators | Provider generators |
| --- | --- | --- | --- |
| Python Docker Compose local | `component`, `python`, `sql` | `docker` | none |
| TypeScript Docker Compose local | `component`, `typescript`, `sql`, `python_http_contract_overlay` | `docker` | none |
| Python Kubernetes existing | `component`, `python`, `sql` | `k8s` | none |
| Python Kubernetes on Azure (AKS) | `component`, `python`, `sql` | `k8s` | `azure` AKS/ACR/networking |
| Python Azure App Service | `component`, `python`, `sql` | none (PaaS, no K8s manifests) | `azure` App Service + managed infra |
| Python ECS Fargate | `component`, `python`, `sql` | none (PaaS) | `aws` ECS/Fargate/managed infra |

Provider generators augment runtime output unless the runtime is provider-native. For `runtime: kubernetes, provider: azure`, Azure support adds AKS/ACR/identity/networking/managed-service integration without replacing Kubernetes manifests. For `runtime: azure-app-service`, the Azure generator produces all infrastructure Bicep — there is no separate runtime generator.

**Explicit config rule:** Defaults are an anti-pattern for deployment generation. Every deployment-relevant field must come from resolved config. Missing required fields must produce explicit errors naming the config path and expected field. Invalid combinations must produce validation errors rather than being corrected silently. No generator may override a user-provided config value.

**Validation rules:** Provider values are scoped by runtime:

| Runtime | Valid providers |
| --- | --- |
| `docker-compose` | `local`, `aws`, `azure` |
| `kubernetes` | `existing`, `aws`, `azure` |
| `azure-app-service` | `azure` |
| `ecs-fargate` | `aws` |
| `app-runner` | `aws` |

**CLI contract:** Deployment-affecting values are not accepted as one-off CLI overrides. `datrix generate` reads `language` and `deployment` from resolved config. `--hosting` and `--platform` generation-time overrides are removed. Users who need to change deployment target edit config files (or use a `datrix config set-deployment` helper command that writes config explicitly).

**Output path contract:** Generated output paths include language, runtime, and provider:

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
- **Target-language adapter protocol** — `RdbmsMigrationAdapter` in `datrix-codegen-common` defines the contract. Python/Alembic, TypeScript/MikroORM, and SQL are adapters that render target-native migration files from shared canonical state
- **Shared-owned RDBMS migrations** — Shared RDBMS blocks generate migration files under `SharedPaths.rdbms_dir`, not under a consuming service. Platform generators create one migration apply unit per shared `rdbms_id`

**State ownership:** The migration orchestrator owns snapshot/ledger lifecycle. Adapters render target-native files from `MigrationState` but do not load, write, or allocate revision IDs. Canonical state (`schema.json`, `ledger.json`) lives under the application source folder and is target-language/platform/engine agnostic.

**Reference:** [RDBMS Migration Decisions (D1-D23)](rdbms-migration-decisions.md) | [Migration API](../../../datrix-common/docs/architecture/migration.md) | [Adapter Protocol](../../../datrix-codegen-common/docs/migration-adapter.md)

---

### Decision 9: Centralized Runtime Config Store

**Rationale:**
- ConfigDSL (`.dcfg`) resolves configuration at generation/deploy time and bakes it into generated code, env vars, Compose files, K8s manifests, and cloud infrastructure. That cannot support operational changes that must happen without rebuilding and redeploying an image: feature flags and kill switches, rate-limit/TTL/retry/timeout tuning, per-environment overrides of the same artifact, and secret-rotation coordination
- Datrix needs to generate the runtime config-store infrastructure, initial values, access permissions, and language-specific runtime clients while preserving the existing static ConfigDSL pipeline
- A runtime config plane must not become a backdoor for secrets — it stores only non-sensitive values and *references* to secrets, never secret values

**Result:**
- A system-level `configStore` section is added to existing **system** ConfigDSL. No application DSL grammar change is introduced — the runtime plane is purely an infrastructure + generated-client capability. The resolved object attaches to `app.system.config.config_store` via `SystemConfigProfileConfig.config_store` (`ConfigStoreConfig | None`)
- `configStore` is **additive and gated**: services receive a generated runtime client only when `configStore` is present; apps without it produce byte-equivalent output (no client files, no new env vars, no config-store infrastructure). It does **not** replace service/system `.dcfg` — ConfigDSL remains the source for generation-time and deploy-time configuration. The config store adds runtime-mutable keys only
- **Supported engines (initial set):** AWS AppConfig (`engine: appconfig`, `platform: managed`), Azure App Configuration (`engine: app-configuration`, `platform: managed`), and self-hosted Consul KV for Docker/Kubernetes (`engine: consul`, `platform: container` or `external`). Parameter Store and etcd are future extensions
- **Centralized compatibility validation:** engine/platform/provider combinations are validated in `datrix-common` during system config resolution, using the resolved deployment runtime/provider plus config-store engine/platform. Unsupported combinations fail loud with diagnostics naming runtime, provider, engine, and platform. Generator-side `GenerationError` guards remain as a defensive backstop. There is no silent fallback from cloud config to local JSON — local defaults are client startup data, not an infrastructure substitute
- **Generated clients** (Python and TypeScript) share one conceptual API: `start/stop/refresh`, typed scalar accessors (`get_bool/get_int/get_float/get_string`), `get_namespace`, and `get_secret_ref`. The dynamic API is the public contract; generators also emit typed namespace/key constants (Python frozen constants, TypeScript `as const` + literal types) but no per-key accessor methods. Behavior: cache seeded from generated defaults, remote values merged over defaults profile-by-profile, unknown namespace/key access raises, single background poll task per process, and explicit fail-open (log-and-continue) vs fail-closed (fail startup / raise on refresh) semantics
- **Secrets boundary:** keys may declare a `secretRef` (provider + name/path + optional version) — a non-sensitive pointer. Scalar accessors raise for `secretRef` keys; only `get_secret_ref` returns reference metadata. Actual secret values resolve through generated secret-manager access code (Vault, Azure Key Vault, AWS Secrets Manager, env). Secret-manager read permissions are generated from declared secret references, not from arbitrary runtime values. Raw secret-looking defaults are rejected using the same placeholder/secret hygiene as extern-service config
- **Feature-flag profiles** (`kind: featureFlag`) may contain only `Boolean` keys and render to provider-native feature-flag shapes (AppConfig feature flags, Azure feature-management content type); non-Boolean runtime values use `kind: freeform`

**Engine compatibility matrix:**

| Deployment target | appconfig managed | app-configuration managed | consul container | consul external |
| --- | --- | --- | --- | --- |
| Docker/local | invalid | invalid | supported | supported |
| Kubernetes/local | invalid | invalid | supported | supported |
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

**Rationale:**
- Provider generators (AWS, Azure) were coupled to the target language in a way runtime generators (Docker, K8s) were not: Docker/K8s discover the language via the `LanguageRuntimeSpec` protocol and ask it for language-appropriate commands, while AWS branched on the `Language` enum inline and hardcoded Python idioms (CDK stack language, scheduled-job command), and Azure hardcoded the App Service `gunicorn … uvicorn` startup command and `PYTHON|…` `linuxFxVersion`
- Consequence: a new target language required editing every provider generator independently, and a new provider had to re-derive language handling from scratch instead of inheriting it
- There was no shared home for provider-level, language-agnostic concerns (config resolution, observability integration, networking/auth/managed-service provisioning), so each provider re-implemented them

**Result:**
- **Language is discovered, never branched.** Every platform generator obtains language-specific runtime details from `LanguageRuntimeSpec` via `discover_language_runtime_spec(target_language)`, exactly as Docker/K8s do. Zero `Language`-enum branches and zero `language_name == "…"` string comparisons remain in any platform package's application-wiring code (Docker, K8s, AWS, Azure)
- **The `LanguageRuntimeSpec` protocol gains exactly three language-agnostic methods** (default-free abstract declarations, implemented in `datrix-codegen-python` and `datrix-codegen-typescript`, covered by the Design 014 parity gate): `container_command(service, package_name) -> list[str]` (the explicit HTTP-service start command; sole consumer is Azure App Service — AWS inherits its container `ENTRYPOINT` from the built Docker image and needs no wiring), `hosts_consumers_in_process() -> bool` (whether the language runs scheduled-job / event-consumer / queue-worker containers in-process on Compose/K8s), and `project_language() -> ProjectLanguage` (the language's own `ProjectLanguage` member, replacing a silent string→enum fallback). `health_check_endpoint` is **not** added — the readiness path is the shared, language-neutral `HTTP_HEALTH_CHECK_PATH = "/ready"` constant
- **IaC language ≠ application language.** The language a provider authors its infrastructure artifacts in (AWS CDK Python, Azure Bicep) is independent of the generated application's language. A TypeScript app deployed via AWS still gets Python CDK stacks; the CDK references a TypeScript container command obtained from the runtime spec. AWS collapses its three Python-IaC string constants into one named `_CDK_IAC_LANGUAGE` constant documenting this invariant
- **The `datrix_codegen_common/platform/` subpackage** (inside the existing `datrix-codegen-common`, a sibling of `gendsl/`, `dashboards/`, `algorithms/`, `context_models/` — **not a new package**) is the shared home for provider-level concerns that are language-agnostic and shared by ≥2 platforms: the `resolve_runtime_spec(context)` discovery helper (raises `GenerationError`, never falls back to Python), the `runtime_stack_token(lang_spec, runtime_version)` `LANG|VERSION` composer, and the `PlatformInfrastructure` protocol. The shared Grafana `DashboardBuilder` already lives in `datrix_codegen_common/dashboards/` and platforms import it directly — no re-home, no facade
- **`PlatformInfrastructure` protocol** (`@runtime_checkable`, in `datrix_codegen_common/platform/`) expresses provider-level infrastructure surfaces — `network_topology(app)`, `service_to_service_auth(app)`, and `provision_managed_service(block, block_kind, service)` — exposed as a `platform_infrastructure` property on each `PlatformGenerator` subclass. Every platform implements the **full** protocol: clouds fully; Docker/K8s return explicit no-op value objects (`NetworkTopology.none()`, empty `ManagedServicePlan`) — honest "no VPC/IAM" facts, never silent stubs. Value objects (`NetworkTopology`, `ServiceAuthModel`, `ManagedServicePlan`) are frozen Pydantic models in `datrix_codegen_common/platform/`, keeping provider concepts out of the AST model
- **The platform seam is the existing `PlatformGenerator` + `datrix.platforms` entry-point group** — discovered via `discover_platforms`. No new `PlatformAdapter` type is introduced. `PlatformInfrastructure` and the shared `DashboardBuilder` are *consumed by* `PlatformGenerator` subclasses, never a competing discovery contract. A new provider implements a `PlatformGenerator` subclass + a `PlatformInfrastructure` implementation, and *consumes* the shared `DashboardBuilder` (`datrix_codegen_common.dashboards`) and `LanguageRuntimeSpec` — language support is free

**Reference:** [Repository Architecture — Platform Generators](architecture/repository-architecture.md#platform-generators-4) | [Import Boundaries — Platform → codegen-common subtree contract](../../datrix-common/docs/architecture/import-boundaries.md#platform--codegen-common-subtree-contract)

---

### Decision 13: Managed Identity Provider Integration

**Rationale:**
- Every production application needs authentication, but Datrix previously generated only self-managed JWT validation (a static configured public key) plus role-based `access(role)` checks. Users had to hand-build the rest: a `User` entity with `passwordHash`, password hashing, login/register endpoints, token minting, refresh tokens, and MFA — error-prone, insecure by default, and repeated in every project.
- The generated auth path had concrete foot-guns: a static public key instead of a JWKS endpoint (no key rotation), a transitive `ROLE_HIERARCHY` that implicitly widened authorization, and self-minted tokens — all properties of the local-auth model rather than a managed identity provider.
- Authentication ("who are you") belongs to a managed identity provider (Cognito, Microsoft Entra, Keycloak); the application should validate provider-issued tokens, not own credentials, sessions, or token issuance.

**Result — managed identity replaces manual authentication (no backward compatibility):**

- **DSL is semantic, config is operational.** An `identity { provider <name> config('<path>') { … } }` block declares logical provider names, application-visible identity fields (type-first, e.g. `String company;`), and `group "<provider-local>" as <datrixRole>` mappings. Operational settings (MFA, password policy, social login, token lifetime, callback/logout URLs, tenant/realm/pool, claim paths) live only in the referenced provider `.dcfg` file. The provider *type* lives in config, not `.dtrx`.
- **Unified `auth(...)` protected-surface contract.** Every externally reachable REST/GraphQL/WebSocket/webhook/externally-invokable-serverless surface resolves exactly one effective `AuthContract`. Forms: `auth(public)`, `auth(required, providers: […])`, `auth(optional, providers: […])`, `auth(required, providers: […], roles: […])`, `auth(service, providers: […])`. `providers: [...]` is a **set** (issuer selects the provider; no fallback order); `roles: [...]` is **any-of** with **no transitive hierarchy**. Non-public modes require an explicit provider list — there is no application default provider and no implicit public default.
- **`AuthContract` replaces `AccessLevel` + `Endpoint.required_roles`/`Endpoint.access_level`.** The legacy `AccessLevel` enum, the `Endpoint.access_level`/`Endpoint.required_roles` fields, and the `is_public`/`is_service_facing`/`is_authorized()` predicates in `datrix-common` are **deleted, not adapted**. The transformer's modifier-string + `@authorize`-decorator access handling lowers to a frozen `AuthContract` (`mode`, `providers`, `roles`, `principalTypes`, `surfaceId`, `delegation`, `profile`, `verify`). The generated auth code drops `ROLE_HIERARCHY`/`_expand_roles` — a deliberate forward-only break: a token previously passing a check only via transitive role inclusion no longer passes unless it carries the literal role.
- **Provider is the source of truth; Datrix projects a local profile.** Datrix never mints primary tokens. It validates provider tokens via issuer/audience/client/JWKS, and for human providers projects a local `IdentityProfile` (+ `IdentityLink` keyed `(providerName, providerSubject)`) into a bound relational store on first successful auth. These are Datrix-managed system entities users cannot redefine. Account linking is explicit and verified; weak email-only linking is forbidden.
- **Opinionated per-target providers.** Docker/K8s → Keycloak (provisioned with realm import, clients, groups, social providers); AWS → Cognito User Pool (app-level, per-service app client); Azure customer → Microsoft Entra External ID, Azure workforce → Microsoft Entra ID, Azure machine → user-assigned managed identity (app registration via the Microsoft Graph Bicep extension, never a `deploy-identity.sh` stub). `provider self` (`ProviderPlanEntry.mode="self"`) is a Datrix-managed Keycloak issuer realizable on **all four targets** — Docker/K8s reuse existing Keycloak provisioning; AWS and Azure get managed-container + backing-DB + realm-import provisioning — so "managed" includes "Datrix-managed self-hosted," not external-only. `mode: external` consumes issuer/JWKS/audience/client and provisions nothing. A capability matrix in `datrix-common` is the authoritative source for supported `(providerType, target, feature)` combinations; unsupported combinations fail loud.
- **Structured versioned provider plan.** A `config/generated/identity-providers.json` artifact (schema owned by `datrix-common`, one per application+environment) carries providers, surfaces, role/attribute mappings, revocation mode, and `*_SECRET_REF` names. Runtime guards resolve provider per surface by issuer from `plan.surfaces[surfaceId]` — never a hardcoded provider name. A non-secret public-client metadata artifact (`identity-client-<provider>.<env>.json`) is the only supported input for frontend login config. Secrets are `ConfigSecretRef` references only (reusing the existing structured secret model + raw-secret hygiene), wired to platform-native secret stores; raw secrets never appear in source, manifests, logs, or docs.
- **Security-sensitive defaults fail closed.** Auth/JWKS-refresh failures, authorization-bearing cache reads/deletes (revocation, role mappings, identity links), and revocation checks reuse the existing `dependencyPolicy` model with `onFailure="raise"`/`"deny"` only (the model has no `fallback`). Error bodies are opaque (RFC 7807) and never leak issuer/audience/client/role/claim detail; structured reason codes go to logs only. WebSocket auth uses fixed close codes (4401 auth-failed/expired, 4403 forbidden) and clears membership/`Auth.*` state on expiry.

**Enforcement (managed-only):** Authentication issuance is provider-owned, end to end. The `Auth` issuance builtin (`generateToken`/`verifyToken`/`hashPassword`/`verifyPassword`/`generateOtp`/`generateApiKey`/…) is **removed wholesale** — the only recognized authentication is a provider-issued token validated through `auth(...)`, and a provider (external *or* `provider self`) owns issuance. The Decision-13 `Auth.*` context views (`Auth.isAuthenticated`/`subject`/`identity.*`) are generated runtime, not that builtin, and stay. Non-authentication cryptography (signing, hashing, HMAC, secure random, opaque keys) belongs to the pre-existing `Crypto` builtin — the sanctioned non-auth surface, which produces signed/hashed data and never confers an `Auth.*` principal. Enforcement extends the existing `LegacyAuthConflictValidator` + `IdentityValidator` (removed-issuance-builtin diagnostics, dangling-provider checks, a best-effort hand-rolled-auth heuristic) — no new validator class. The Python first-party local-validation short-circuit (`_validate_local_issuer_token`, the `iss == JWT_ISSUER` path) is removed; `provider self` tokens validate through the standard provider-plan/JWKS path like any provider (TypeScript never had such a path).

**Runtime libraries (defaults, behavior is the contract):** Python (FastAPI) uses `pyjwt[crypto]` + `PyJWKClient` + `httpx`; TypeScript (NestJS) uses `jose` (`createRemoteJWKSet` + `jwtVerify`). The current Python template already uses PyJWT, so the change is JWKS-based validation with `kid` rotation, not a library swap. Symmetric algorithms and `alg: none` are always rejected.

**External-product caveats (verify before implementing):** Microsoft Entra External ID being the forward consumer-identity path and the Microsoft Graph Bicep extension's availability/API, the provider claim paths (Cognito `cognito:groups`, Keycloak `realm_access.roles`, Entra `roles`), runtime library maintenance/API surface, the WebSocket private-use close-code range, and platform handshake-header capabilities rest on external product knowledge as of the 2026 cutoff and are not verifiable from the Datrix repo.

**Cross-design boundaries:** The WebSocket design depends on this design for protected-handshake identity and consumes the shared identity plan (it owns transport/routing/rooms). The Config Store (`ConfigSecretRef`) and resilience (`dependencyPolicy`) subsystems are reused, not owned here.

**Reference:** [API Auth Contracts](../../../datrix-language/docs/reference/access-levels.md) | [Semantic Validators — Identity](../../../datrix-common/docs/architecture/semantic-validators.md)

---

## Installation

```bash
# Minimal (CLI only)
pip install datrix-cli

# Python + Docker
pip install datrix-cli datrix-codegen-python datrix-codegen-docker

# Full stack
pip install datrix-cli \
 datrix-codegen-python datrix-codegen-typescript datrix-codegen-sql \
 datrix-codegen-docker datrix-codegen-k8s datrix-codegen-aws datrix-codegen-azure
```

**Note:** The CLI automatically discovers installed generators. You only need to install the generators you plan to use.

---

## Usage

Use the CLI to validate and generate:
```bash
# Validate a file or directory of .dtrx files
datrix validate system.dtrx
datrix validate examples/02-features/01-core-data-modeling/rest-api

# Generate (defaults: profile test; language and deployment from ConfigDSL for that profile)
datrix generate --source system.dtrx --output ./generated

# Generate for a specific profile
datrix generate --source system.dtrx --output ./generated --profile production

# Override language for testing only (optional short flag)
datrix generate --source system.dtrx --output ./generated --language typescript
datrix generate --source system.dtrx --output ./generated -L python
```

**Config-driven generation:** The source of truth is ConfigDSL: `language` and `deployment` (runtime, provider, target, registry) in `config/system.dcfg`. Infrastructure flavor for individual blocks (e.g. `flexible-server`, `event-hubs`, `blob-storage`) is set in each block's `.dcfg` config file. Generation reads deployment settings from resolved config — there are no deployment-affecting CLI overrides. See [Decision 6: Deployment Target Contract](#decision-6-deployment-target-contract-stable) for the full deployment model.

> **Note:** The `--hosting` and `--platform` CLI overrides have been removed. Deployment target is configured in ConfigDSL files, not CLI flags.

---

## Next Steps

- Read [Design Principles](./design-principles.md) to understand core principles
- Read [Language Reference](../reference/language-reference.md) to learn how to write `.dtrx` files
- See [Getting Started](../getting-started/first-project.md) and the runnable trees under [`examples/`](../../examples/)
