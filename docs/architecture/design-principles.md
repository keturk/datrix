# Datrix Design Principles

**Last Updated:** April 24, 2026

---

## Core Philosophy

Datrix is built on proven software engineering principles that ensure:
- **Reliable code generation** - Cannot generate broken code
- **Type safety** - Exhaustive type checking and validation
- **Maintainability** - Clear, modular architecture
- **Developer experience** - Fast feedback with helpful errors

---

## Architectural Principles

### 1. Fail Fast, Fail Loud

**Principle:** Errors should be caught at generation time, not runtime.

**Why:**
- Faster feedback loop
- Clear error messages with context
- No broken code reaches users
- Reduces debugging time

**Application:** The codebase raises explicit errors with context (e.g. entity not found with available names and suggestions). No silent fallbacks or `None` returns for lookup failures.

**Example (Alembic initial migration):** `build_initial_migration_context` and related helpers in `datrix_codegen_python.generators.persistence._migration_schema` raise `GenerationError` when an entity has no primary key, when a `belongsTo` target is missing from the block, or when foreign-key dependencies between tables are circular — generation stops with a concrete message instead of emitting broken DDL.

**Example (incremental migration safety):** The shared migration change policy in `datrix_common.migration.change_policy` classifies schema diffs as `safe`, `risky`, or `blocked` before adapter rendering. Destructive changes (field/table removal, rename, type narrowing, enum value removal/rename/reorder) are generation errors — they fail loudly instead of silently generating migrations that could corrupt deployed databases. Missing RDBMS UUID, missing migration state with existing history, and append-only file content changes are also hard errors.

**Example (multi-service NGINX gateway):** `generate_nginx_config` in `datrix_codegen_docker.generators.config.gateway_generator` raises `GenerationError` when any upstream would have no location blocks (for example a service with no `rest_api` / `graphql_api` and no derivable health alias), when two services would publish the same external health path through the gateway, or when a service has no HTTP port in resolved config — rather than emitting an incomplete `nginx.conf`.

**Example (Grafana without metrics):** `generate_dashboards` in `datrix_codegen_docker.generators.infra.dashboard_builder` raises `GenerationError` when visualization is enabled but Prometheus metrics are not — dashboards have no scrape targets to plot.

**Example (rate limit preconditions):** Both rate limiting templates (`middleware_rate_limit.py.j2` for per-route and `rate_limit_dependency.py.j2` for plan-based) raise `HTTPException` **503** when `app.state.redis` is missing and rate limiting is not disabled, and **429** when the limit is exceeded. Both respect `DISABLE_RATE_LIMIT` env var for testing — the only intentional bypass path.

**Example (required-body validation):** `RequiredBodyValidator` in `datrix_common.semantic.validators.required_body` rejects callable declarations (service functions, entity functions, lifecycle hooks, CQRS handlers, job handlers, validate blocks, trait functions) that have no body at compile time with `BODY001` diagnostics — rather than allowing empty bodies to reach code generation and emit runtime `NotImplementedError` / `throw new Error` stubs. REST endpoints and test specs are excluded (empty endpoints return valid default responses; empty tests are placeholders). This validator runs as part of domain validation (semantic analysis phase 13) and guarantees that generated code is fully functional without runtime stubs.

**Example (generated-output stub guard):** A shared guard in `datrix_codegen_common` scans generated file objects for forbidden runtime stub patterns (`raise NotImplementedError`, `throw new Error(…not implemented…)`) before output is accepted. Each language generator entrypoint invokes the guard so stubs cannot reach generated output even if a validation gap exists. Allowlisting is narrow and pattern-specific (e.g., the Windows `except NotImplementedError` signal-handler idiom).

**Example (transpiler identifier resolution):** The transpiler resolves all identifiers through a single-path architecture: a Stage 1-2 pipeline (`NameResolver` → `QueryExpander`) builds a resolution table keyed by AST node ID, and Stage 3 (code emitters) consults that table exclusively. When the table marks an identifier as `"unresolved"`, emit-time raises an explicit error with context instead of silently retrying through fallback lookups. All identifier categories (entities, views, enums, constants, module functions, async API functions, storage blocks, integration clients, service dependencies, cache blocks, builtin categories, entity methods, local variables) must be resolvable through data in `TranspileContext` before the pipeline runs — no silent retry paths exist. This eliminates dual-path bugs where resolution logic could drift between the pipeline and a fallback.

**Example (no silent unknown members):** REST API, CQRS View, and Struct transformers raise `TransformError` for unknown member types instead of silently dropping them. This ensures typos or unsupported syntax are caught immediately with a clear error message listing valid member types for that construct.

**Example (typed inter-service calls):** A cross-service call is a typed RPC against the provider's named `access(Service)` endpoint — `Service.Block.<method>.<name>(args)` or a resource `Service.Block.<db>.<Entity>.<op>(args)` — never a stringly-typed path or a pathless positional list. The cross-service endpoint contract registry is resolved at generation time, so a call to an undeclared dependency, an unknown block, an unresolved endpoint identity, an argument arity/type mismatch, or an endpoint that is not `access(Service)` is a generation error with actionable diagnostics — never a silent fallback to caller-supplied param names or a wrong endpoint. A declared dependency whose contract is missing from the pinned snapshot is reported distinctly ("regenerate the dependency first") rather than masquerading as an absent endpoint, and resolution never binds against a stale provider revision. The provider's return type is decoded into a generated response struct that fails loud on an unexpected missing required field, so a casing mismatch or contract drift surfaces as a hard decode error instead of a silent `null`.

**Example (dependency resilience is declared, never synthesized):** Resilience is a property of the dependency, authored once and applied everywhere — the generator never invents timeout/breaker/bulkhead values and never auto-classifies an operation as safe to degrade. A policy-managed operation, or a `service` dependency that has inter-service calls, left uncovered by both the application-level baseline and any per-service override is a generation error (`RESILIENCE_POLICY_REQUIRED`). Degradation applies only where the author declared it and the operation semantics permit (a cache write degrades only when known post-source-of-truth-commit; a rate-limit counter does not fail open by default).

**Benefits:**
- ✅ Cannot continue with invalid state
- ✅ Error includes helpful suggestions
- ✅ Caught during generation, not deployment

---

### 2. Templates + Formatter for Code Generation

**Principle:** Use Jinja2 templates with ruff format for Python code formatting, and Prettier for TypeScript.

**Why:**
- Templates are readable and look like the output
- After files are written, `GenerationPipeline` runs `LanguageHooks` post-processing (import fix, then ruff format / Prettier when `PipelineConfig.format_output` is true, then semantic checks such as ruff rules) so output stays consistent with project standards
- Easy to maintain and modify
- Reusable template macros

**Application:** Generators use Jinja2 (e.g. `PackageLoader` for templates), render to raw code, and validate syntax before output. Model templates emit a Pydantic model class keyed by entity name, with conditional imports (e.g. UUID when needed) and one field per entity field. Templates should produce well-formatted output; hook formatters normalize what lands on disk. Raw string concatenation is not used. See the codebase for template files (e.g. `model.py.j2` in datrix-codegen-python).

**Example (transpiled job handlers):** `JobsGenerator` (`datrix_codegen_python.generators.messaging.jobs_generator`) combines Jinja2 templates such as `messaging/jobs_scheduler.py.j2` and `messaging/jobs_runner.py.j2` with output from `PythonTranspiler` so each scheduled job’s DSL body becomes real Python inside the generated scheduler/runner modules.

**Example (Grafana dashboard JSON):** `DashboardBuilder` (`datrix_codegen_docker.generators.infra.dashboard_builder`) assembles Grafana **provisioned** dashboard documents in Python (nested dicts), serializes them to JSON under `config/grafana/dashboards/`, and pairs them with Jinja2-rendered Prometheus alert YAML — no ad-hoc string concatenation of panel definitions.

**Key Insight:** Templates should aim for clean output; the pipeline's post-processing passes (import fix, format, validate) catch remaining drift. Which passes run is controlled by `PipelineConfig.validation_level` — see [Validation levels](architecture/pipeline-and-capabilities.md#validation-levels) for the level-to-hook mapping.

**When to Use Each Approach:**

| Approach | When to Use |
|----------|-------------|
| **Jinja2 Templates** | Generating boilerplate code (models, schemas, routes), output structure is well-defined, readability of template matters |
| **AST Builders** | Programmatically transforming existing code, dynamic structure based on complex conditions, need fine-grained control over AST nodes |

**Template Structure:**

- `datrix-codegen-python/src/datrix_codegen_python/templates/` — Jinja2 templates organized into domain subdirectories (`entity/`, `api/`, `service/`, `persistence/`, `messaging/`, `cross_cutting/`, `project/`)
- `generators/` — Generator classes organized into matching domain subdirectories

**Benefits:**
- ✅ Templates are readable and maintainable
- ✅ Consistent formatting via ruff format/Prettier
- ✅ Validation during formatting
- ✅ Reusable template macros

---

### 3. Exhaustive Type Mappings

**Principle:** All type mappings must be explicit. No defaults, no fallbacks.

**Why:**
- Prevents silent bugs
- Forces complete implementation
- Clear error messages
- Easy to add new types

**Application:** Type mappings are exhaustive: every Datrix type has an explicit mapping per target language. Unmapped types raise an error (e.g. `UnmappedTypeError`) with available types listed. No default or fallback to `Any`.

**Example (Problem Details `type` URNs):** `error_handlers.py.j2` assigns a distinct `urn:datrix:error:…` string per handler (`entity-not-found`, `cascade-restriction`, `validation`, `request-validation`, `internal`, etc.) so clients can branch on `type` without guessing from free-text `detail`.

**Benefits:**
- ✅ No silent bugs
- ✅ Forces complete implementation
- ✅ Helpful error messages
- ✅ Easy to find missing mappings

---

### 4. Immutability

**Principle:** The Application (AST model) is immutable after creation.

**Why:**
- Thread-safe
- Predictable behavior
- Prevents accidental modifications
- Easier to reason about

**Application:** The Application (AST) model is immutable: AST classes are frozen (Pydantic v2). Modifying a parsed entity or service raises `FrozenInstanceError`. Generators are read-only and iterate over services and blocks without mutating the AST.

**Benefits:**
- ✅ Thread-safe generation
- ✅ No side effects
- ✅ Cacheable results
- ✅ Easy to parallelize

---

### 5. Single Responsibility

**Principle:** Each repository/module has ONE clear purpose.

**Why:**
- Easier to understand
- Easier to test
- Clear ownership
- Independent evolution

**Application:**

**Repository Organization:**
- `datrix-common`: Foundation and code generation framework (AST model, types, errors, config, semantic analysis, plugin protocols, pipeline) - ONE PURPOSE
- `datrix-language`: Parser and CST-to-AST transformers (AST model lives in datrix-common) - ONE PURPOSE
- `datrix-codegen-component`: Platform-agnostic component generation - ONE PURPOSE
- `datrix-codegen-python`: Python code generation - ONE PURPOSE
- `datrix-codegen-docker`: Docker generation - ONE PURPOSE

**Module Organization:** Each package keeps one concern per module (e.g. models, routes, services, tests). One generator class per concern; platform-specific generation (e.g. Docker) lives in a separate package, not mixed with metrics or other concerns.

---

### 6. Dependency Inversion

**Principle:** Depend on abstractions, not concretions.

**Why:**
- Easier to swap implementations
- Better testing (swap real implementations)
- Loose coupling
- Plugin architecture

**Application:** Generators depend on abstractions (e.g. a formatter interface); concrete implementations (Ruff for Python, Prettier for TypeScript) live in the codebase and can be swapped. See `datrix_common` and generator packages for the interfaces.

**Benefits:**
- ✅ Easy to add new formatters
- ✅ Easy to test (swap formatter implementations)
- ✅ User choice of formatter
- ✅ No tight coupling

---

### 7. Explicit Over Implicit

**Principle:** Be explicit about requirements and behavior. No magic.

**Why:**
- Easier to understand
- No surprises
- Better error messages
- Self-documenting

**Application:** Types and configuration are explicit. Fields must declare their type; no inference from names (e.g. `_id` → UUID). Generators receive all required parameters (app, output_dir, versions); no magic defaults. The codebase uses explicit types and constructor arguments throughout.

**Builtin traits are opt-in:** Datrix provides ten builtin traits (Timestampable, Tenantable, SoftDeletable, etc.) that are always available but never automatically applied. Entities must explicitly declare `with TraitName` to receive trait fields. For example, `entity User extends BaseEntity with Tenantable` opts the User entity into tenant isolation — without this declaration, the entity has no `tenantId` field.

**Example (seed reference data):** `SeedGenerator` (`datrix_codegen_python.generators.persistence.seed_generator`) only runs when `config/seed-data.yaml` exists under the service output tree. Entity names, columns, and row shapes must match the AST; unknown columns or missing primary-key values raise `GenerationError` with **Allowed:** lists — reference data is never inferred from the DSL alone.

**Example (runtime configuration):** Docker Compose and generated Python settings models bind operational values to **named environment variables** (for example `JWT_SECRET`, `INTERNAL_API_TOKEN`, database URLs, and ports). Values come from resolved YAML profiles and documented `.env.example` entries — not from undocumented literals in generated service code.

**Example (cross-service exposure is an explicit choice):** A service's internal API surface is the explicit set of `access(Service)` endpoints, not an implicit consequence of naming or routing. An endpoint becomes cross-service-callable only by being marked `access(Service)` (and, for custom endpoints, named); a peer can never invoke a `public`/`access(authenticated)` endpoint as an RPC. Endpoint identity (`(method, name)`) is the stable contract callers bind to, decoupled from the `@path`/URL, which is a deployment detail. Likewise, the resilience posture of a `service` dependency is declared explicitly — the recommended values ship as a named config template opted into at the application level, so the numbers are always visible in config rather than silently inherited, and retry is enabled only on endpoints explicitly marked `idempotent`.

---

### 8. Block-Qualified Storage Entity Identity

**Principle:** Storage entities have canonical block-qualified identity. No service-wide fallbacks.

**Why:**
- Stable behavior when adding new storage blocks
- Clear ownership and boundaries
- Prevents ambiguity in multi-block services
- Makes generator logic deterministic

**The canonical identity for storage entities:**

```
service → storage block → entity
```

Storage blocks are `rdbms` and `nosql`. Each entity belongs to exactly one storage block. The entity's identity is the triple `(service_name, block_name, entity_name)`.

**Resolution contract:**

1. **Explicit `block.Entity` always wins** — `memberDb.Member` unambiguously refers to `memberDb.Member`
2. **API storage defaults provide bare-name resolution** — `rest_api` and `graphql_api` may declare `rdbms(blockName)` and/or `nosql(blockName)` to resolve bare entity references like `Member` inside that API
3. **No service-wide fallbacks** — Generators must NOT infer a storage block from:
   - Service block count (e.g., "the only RDBMS block")
   - Service iteration order (e.g., "the first RDBMS block")
   - Service-wide entity-name uniqueness (e.g., "Member exists in only one block, so use that")
   - Callable parameter types (e.g., "first entity parameter defines the block")

**Application:**

- REST and GraphQL APIs declare explicit storage defaults via `rdbms(blockName)` or `nosql(blockName)` attributes
- API defaults define how bare entity references (e.g., `Member`) resolve inside that API block
- Semantic analysis attaches `StorageEntityBinding` directly to AST nodes during validation
- Generators consume attached semantic bindings; they do not resolve or infer storage blocks

**Benefits:**
- ✅ Adding a second storage block does not change existing API behavior
- ✅ No "first block" or "only block" guessing in generators
- ✅ Clear error messages when defaults are missing
- ✅ Explicit migration path for services with multiple storage blocks

**Example (stable resolution):**

```dtrx
service MemberService {
    rdbms memberDb {
        entity Member {
            id: UUID primaryKey
        }
    }

    // This API works because of the rdbms(memberDb) default
    rest_api MemberAPI : basePath("/members"), rdbms(memberDb) {
        get(UUID id) -> Member {
            return Member.findOne({ id: id });
        }
    }
}
```

Adding a second storage block does not break the API:

```dtrx
    rdbms auditDb {
        entity AuditEntry {
            id: UUID primaryKey
        }
    }

    // MemberAPI still resolves Member to memberDb.Member (not ambiguous)
```

---

## Language Design Principles

### 0. Uniform Language Consistency

**Principle:** Datrix DSL is a full-fledged language with uniform scoping rules. If a construct (enum, alert, hook, index, validation) is valid in one block, it should be valid in all analogous blocks unless there is a concrete technical reason to exclude it.

**Why:**
- Predictable learning curve — features work the same way everywhere
- Avoids accidental asymmetry from isolated implementation
- Enables composition patterns (traits contribute indexes/validations/hooks regardless of storage backend)
- Treats all infrastructure blocks uniformly

**Application:**
- **Hooks:** Traits and entities use the same lifecycle hook syntax (`beforeCreate`, `afterCreate`, etc.)
- **Indexes and validations:** Traits can declare indexes and validation blocks that compose into entities
- **Enums:** All infrastructure blocks support block-scoped enum declarations with qualified cross-block access
- **Alerts:** All infrastructure blocks support alert declarations via `AlertableMixin`
- **Audit modifiers:** All data/stateful blocks (rdbms, nosql, cache, pubsub, storage, queues, cdn, jobs) support block-level audit syntax
- **NoSQL parity:** NoSQL blocks support `entity`, `abstract_entity`, `trait`, `enum`, `alert` — same as RDBMS

**Example:**
```datrix
trait Searchable {
    String(500) description;
    String(50) category;

    index(category);  // Trait indexes compose into entities
    index(category, description);

    validate {
        if (description.length < 10)
            ValidationError("Description too short");
    }
}

nosql analytics('config.dcfg') {
    // NoSQL supports traits, abstract entities, enums — same as RDBMS
    trait Timestamped {
        DateTime createdAt = DateTime.now();
        beforeCreate { this.createdAt = DateTime.now(); }
    }

    entity UserActivity with Timestamped, Searchable {
        UUID userId : index;
        JSON payload;
    }
}
```

### Contextual keywords and server-managed fields

**Server-managed fields** are marked with the **`server`** modifier in the field's modifier list (for example `UUID id : primaryKey, server = uuid();`). The old **`@Type fieldName`** form for system-populated fields was **removed**; there is no parallel syntax or deprecation period. See the [language reference](../reference/language-reference.md#decorators-and-modifiers).

**REST endpoint decorators** (`@retry`, `@rateLimit`, `@cache`, …) are unrelated: they stay **`@`-prefixed** on endpoints inside `rest_api` blocks.

**Contextual keywords:** Identifiers such as `server`, `unique`, and `indexed` are recognized in **modifier position** after `:` on a field (and similar grammatical slots), not as a large set of global reserved words. This keeps the grammar readable while avoiding arbitrary name shadowing outside those positions.

### 1. Platform Independence

**Principle:** DSL code should be platform-agnostic.

**Application:**
```datrix
// Same DSL works for all platforms (excerpt from examples/01-foundation/book-service-base.dtrx)
service library.BookService : version('1.0.0') {
 rdbms db('config/book-service/datasources.dcfg') {
 abstract entity BaseEntity {
 UUID id : primaryKey, server = uuid();
 DateTime createdAt : server = DateTime.now();
 DateTime updatedAt : server = DateTime.now();
 }
 entity Book extends BaseEntity {
 String(200) title;
 String(20) isbn;
 String(100) author;
 Int publicationYear;
 }
 }
}

// Platform selection via config (system .dcfg: language, deployment), not CLI flags:
// Set deployment.runtime and deployment.provider in the active profile, then:
// datrix generate --source system.dtrx --output ./generated
//
// See architecture-overview.md Decision 6: Deployment Target Contract for the full
// deployment model (runtime, provider, target, registry).
```

**Generated Differences:**
- Docker: Creates Dockerfile + docker-compose.yml
- Kubernetes: Creates Deployment + Service manifests
- AWS: Creates ECS task definitions
- **Business logic: Identical across all platforms**

---

### 2. DRY (Don't Repeat Yourself)

**Principle:** Define once, use everywhere.

**Application:**

**Inheritance:** (inside an rdbms block; see [examples/01-foundation](../../examples/01-foundation/))
```datrix
abstract entity BaseEntity {
 UUID id : primaryKey, server = uuid();
 DateTime createdAt : server = DateTime.now();
 DateTime updatedAt : server = DateTime.now();
}

// Inherit everywhere - no repetition
entity User extends BaseEntity { }
entity Order extends BaseEntity { }
entity Product extends BaseEntity { }
```

**Struct Reuse:** (structs and entities inside service blocks; see [examples/02-features/02-service-architecture/modules-imports](../../examples/02-features/02-service-architecture/modules-imports/))
```datrix
struct Address {
 String street;
 String city;
 String state;
 String zipCode;
}

entity User extends BaseEntity {
 Address shippingAddress; // Reuse
 Address billingAddress; // Reuse
}
```

---

### 3. Service as Unit of Deployment

**Principle:** Each service owns its infrastructure and business logic. The DSL makes service boundaries explicit.

**Application:**
- Each service declares its own data stores via named blocks: `rdbms db('path')`, `cache redis('path')`, `nosql docdb('path')`, `storage store('path')`, `pubsub mq('path')`, `search es('path')`
- Config is externalized and profile-based (YAML/JSON). Top-level keys are profile names (`development`, `production`); the generator selects the key from the system profile
- One statement per concern: registration, resilience, and each integration type are separate config statements; deployment-related settings (replicas, resources, healthCheck) live in service-config YAML, not in the DSL

---

### 4. Named Data Blocks and Block-Qualified Access

**Principle:** All data blocks require a user-chosen block name, enabling block-qualified access from outside the block.

**Named Block Syntax:**
```datrix
rdbms db('config/datasources.dcfg') { ... }
nosql docdb('config/nosql.dcfg') { ... }
cache redis('config/cache.dcfg') { ... }
storage store('config/storage.dcfg') { ... }
pubsub mq('config/pubsub.dcfg') { ... }
search es('config/search.dcfg') { ... }
```

**Access Rules:**
- **Inside the same block:** Bare names (e.g., `belongsTo Author`, `extends BaseEntity`)
- **Outside the block:** Use `blockname.Thing` (e.g., `resource db.Book`, `db.User.findOrFail(id)`, `redis.SessionCache.set(...)`)
- **Service-level enums, structs, constants:** Live directly inside `service { }`, always bare names
- **Block-level enums:** Enums declared inside a block are block-scoped — visible by bare name only within that block. Cross-block usage requires qualified name (`blockName.EnumName`). Same enum name in different blocks is valid (different scopes, no collision).
- **Transactions:** Explicitly name the block they scope: `transaction(db) { ... }`

---

### 5. Progressive Disclosure

**Principle:** Simple things should be simple, complex things should be possible.

**Application:**

**Simple entity (minimal syntax; inside rdbms block):**
```datrix
entity User extends BaseEntity {
 String(100) name;
 Email email;
}
```

**Complex entity (when needed; see [examples/02-features/01-core-data-modeling/authentication/book-service.dtrx](../../examples/02-features/01-core-data-modeling/authentication/book-service.dtrx) for User with Auth.hashPassword in beforeCreate):**
```datrix
entity User extends BaseEntity {
 Email email : unique;
 Password passwordHash;
 String(100) firstName;
 String(100) lastName;
 UserRole role = UserRole.Customer;

 String fullName := "{firstName} {lastName}";

 validate {
 if (firstName.trim().isEmpty())
 ValidationError("First name is required");
 }

 beforeCreate {
 passwordHash = Auth.hashPassword(passwordHash);
 }

 afterCreate {
 dispatch UserRegistered(id, email);
 }
}
```

---

### 6. Configuration Boundary

**Principle:** DSL defines *what the system does* (behavioral policy, same in every environment). YAML defines *where it runs and how much* (environmental, changes between dev/staging/prod). No value should appear in both places.

**Why:**
- Single source of truth — no conflicting definitions
- Clear ownership — developers know where to change each concern
- Environment isolation — behavioral code never drifts between environments

**Application:**

| Behavioral (DSL) | Environmental (YAML) |
|---|---|
| Cache TTL (`@cache(ttl: 300)`) | Connection strings (`${DB_URL}`) |
| Rate limits (`@rateLimit(limit: 100, window: 60)`) | Service port (`port: 8000`) |
| Service version (`version('1.0.0')`) | CPU/memory limits, replica count |
| Entity lifecycle hooks, validation rules | CORS origins, JWT secrets |
| Service topology (`discovery { }`) | Job schedules, retry/timeout defaults |
| Computed fields | Provider credentials |
| Extern service contract (`extern service { rest_api ... }`) | Extern service deployment mode, image, URL, auth secrets |
| Gateway type and usage plan structure (`gateway : type('managed') { apiKeys { ... } }`) | Gateway throttle limits, cache TTL, WAF toggle, custom domain, certificate ARN |

**Enforcement:** The parser rejects environmental data in the DSL at parse time. `SERVICE_ATTR_IDENTIFIERS` in `contextual_keywords.py` restricts service attributes to `version` and `description` — writing `port(8000)` in a `.dtrx` file produces an error listing the allowed attributes.

**See also:** [Config System — DSL/YAML Boundary](../../../datrix-common/docs/architecture/config-system.md#dslyaml-boundary) for the full taxonomy and enforcement details.

---

### 7. Domain extensions and core boundary

**Principle:** Domain-specific types, builtin functions, and database extension requirements that need **special infrastructure or runtime dependencies** belong in **optional extension packs** (`datrix.extensions`), not in `datrix-common`. Declaring a pack is a **behavioral** choice and belongs in the DSL.

**Why:**
- Keeps the core type system and generators maintainable as domains diverge (geo, timeseries, fintech, etc.)
- Avoids forcing every language generator to map types a given project never uses
- Preserves clear ownership: packs ship language-agnostic definitions; each **language generator** owns all mappings for core **and** supported extensions (split ownership)

**Application:**

| Concern | Owner |
|---------|--------|
| Scalar defs, builtin objects, `db_extensions()`, extra deps, templates | Extension pack implementing `DatrixExtension` |
| Python / TypeScript / SQL type and ORM mappings | `datrix-codegen-python`, `datrix-codegen-typescript`, `datrix-codegen-sql` |

Enable packs in **`system.dtrx`** with `use extension <name>;` (not YAML). Exhaustive mapping rules still apply: unknown extension keys or unmapped types **fail at generation time** with explicit errors (for example `ExtensionNotSupportedError` from `build_python_type_map` when Python has no map for a declared extension).

**See also:** [Extensions guide](../../../datrix-extensions/docs/extensions-guide.md) and [Architecture Overview — Domain extension system](./architecture/repository-architecture.md#domain-extension-system).

---

### 9. Baseline Observability From Provisioned Resources

**Principle:** Baseline alarms, alerts, and recording rules are derived from infrastructure the target generator actually provisions. They are separate from user-declared DSL alert declarations and must not require users to manually define basic availability and saturation alerts.

**Why:**
- Users should not need to manually declare every CPU, memory, and queue-depth alarm
- Baseline observability must track what is actually provisioned, not what might be provisioned
- User-declared alerts remain distinct (custom thresholds, custom metrics) and must not collide with baseline alerts in names or tags

**Application:** Each infrastructure generator (AWS, Azure, K8s) inspects the resource plans it produces and emits a baseline set of alarms/alerts/recording rules for provisioned resources. Baseline alerts use conservative default thresholds defined in source constants. User-declared `AlertDeclaration`s from the DSL remain a separate codepath with distinct naming.

---

### 10. Hardening Defaults Must Be Explicit

**Principle:** Network policies, PDBs, DLQs, retries, alarms, and baseline probes that can change deployment behavior must be generated from explicit, documented defaults with opt-out or override hooks where the platform already has a configuration surface.

**Why:**
- Silent deployment-behavior changes break existing workflows
- Explicit defaults are discoverable and auditable
- Override hooks allow teams to tune without forking generators

**Application:** When a generator adds a new behavior-changing resource (e.g., Docker network segmentation, K8s PodDisruptionBudget, EventBridge DLQ), the default values are defined as named constants in source code and documented in the package architecture docs. Where the platform config model already has a relevant field, the default flows through that config surface so users can override it.

---

### 11. Construct-Mapped Platform Realization (Stable)

**Principle:** Each DSL construct maps to the target platform's native primitive. Service deployment shape is derived from the constructs declared in the service — not from a separate realization-flavor selector.

**The three-layer model:**

| Layer | Where | Owns |
|-------|-------|------|
| Platform-agnostic logic | `.dtrx` | Service definitions, block structure, entity schema, business logic |
| Deployment target | `.dcfg` | Runtime, provider, target, sizing — chosen once per profile |
| Realization | Generator | Maps each construct to the target platform's native primitive |

**How shape is derived:**

The set of infrastructure resources a service receives is the union of its declared blocks, mapped by the active platform generator. No separate "service flavor" field routes the mapping — block kind plus platform determines the primitive.

Example mapping on Azure (`runtime: azure-app-service, provider: azure`):

| DSL block | Azure primitive |
|-----------|----------------|
| service (HTTP surface: `rest_api`, `graphql_api`) | Azure App Service |
| `serverless` block | Azure Functions (Function App) |
| `rdbms` block | Azure Flexible Server |
| `cache` block | Azure Cache for Redis |
| `nosql` block | Azure Cosmos DB |
| `pubsub` block | Azure Service Bus or Event Hubs (by engine) |
| `storage` block | Azure Blob Storage |
| `cdn` block | Azure Front Door |
| `gateway` block (`type: managed`) | Azure API Management |
| `search` block | Azure AI Search |

The same construct-to-primitive mapping applies on other platforms (AWS: App Service → App Runner/ECS + Fargate; Kubernetes: service → Deployment/Service/Ingress, job → CronJob; Docker Compose: services → containers).

**No silent ignore:**

When a deployment target is resolved, the generator either emits the correct primitive for each construct or raises a `GenerationError` with an actionable message. Unrecognised runtime/provider/target combinations fail loudly — see [Decision 6: Deployment Target Contract](architecture-overview.md#decision-6-deployment-target-contract-stable). No construct is silently omitted and no unsupported combination is silently corrected.

**No defaults:**

Every deployment-relevant choice is explicit in the `.dcfg` profile. A missing required field (runtime, provider, SKU for cloud-managed blocks) is a generation error that names the missing config path, the expected field, and the valid options. Generators never invent deployment values.

**Infrastructure-flavor is per-block, not per-service:**

`RdbmsFlavor`, `CacheFlavor`, `PubsubFlavor`, and similar enums express how a single block is provisioned (`container`, `flexible-server`, `elasticache`, `event-hubs`, etc.). They are block-level infrastructure choices, not a service-level runtime selector. Service deployment shape still derives from which blocks are declared, not from a service-flavor enum.

**Retired path:**

`azure-container-apps` as a `runtime` value is retired. Specifying it raises `GenerationError` with guidance to use `runtime: azure-app-service` for the native Azure PaaS runtime or `runtime: kubernetes, target: aks` for a container mesh on AKS.

**Why:**
- One representation removes the duplication where `.dtrx` described the logical structure and a separate flavor described the runtime shape — they were always derivable from each other
- Generators can be verified exhaustively: every construct kind must have a mapping for every supported platform
- No defaults means authors are always aware of their deployment choices; generation does not silently assume a platform

**Benefits:**
- Block structure drives infra shape — adding a block adds the right resources; removing one removes them
- Platform generators are auditable: one mapping table per construct kind
- Authors see every deployment choice in config; nothing is hidden in defaults

---

## Code Generation Principles

### No Derived Artifacts (Planned)

**Principle:** Generator definitions must not create a second editable artifact. The genDSL docstring is source; the compiled IR is runtime state only.

**Why:**
- Prevents AI agents and humans from patching a derived file instead of editing the source declaration
- Eliminates stale-cache and regeneration-ordering bugs
- Single source of truth for generator structure

**Application:**

| Forbidden | Allowed |
|-----------|---------|
| Checked-in generated Python registry files | Embedded generator-definition docstrings |
| Checked-in generated generator classes | Hand-written Python context builders, hooks, algorithms |
| Generated manifest or metadata files | Templates |
| Generated cache or build-output tables | Tests that compile definitions in memory |
| | CLI/runtime introspection over in-memory IR |

If a genDSL compiler needs intermediate structures, they stay in process memory and are rebuilt every run.

---

### Staged transpilation and explicit state

**Principle:** Imperative DSL bodies are lowered to target source through **explicit stages and data classes**, not implicit mutable transpiler fields.

**Application:** **datrix-common** owns **`TranspileContext`** (frozen per-service configuration), **`FileScope`** variants (mutable per-file sibling-flow state), **`TranspileResult`** (frozen per-visit code + imports + capability flags), **`StagePipeline`** (**`NameResolver`** → **`QueryExpander`** → configure **`LanguageTranspiler`**), and **`ResolutionTable`** keyed by `id(ast_node)` so the AST stays frozen. **`ExpressionVisitor`** / **`StatementVisitor`** plus **`node.accept()`** replace large `isinstance` trees for expressions and statements; **`CallTargetEmitter`** + **`dispatch_call()`** specialize call targets. Rationale and history: [`design/transpiler-improvement.md`](../../../design/transpiler-improvement.md). API summary: [datrix-common-api.md — Transpiler modules](../../datrix-common/docs/datrix-common-api.md#transpiler-modules).

---

### Specification-level verification

**Principle:** Business rules declared in the DSL can be exercised with service-level tests that share the same imperative syntax as handlers and jobs.

**Application:** `test("description") { ... }` members on a service compile to async pytest cases or Jest specs. Statements use real entity APIs (`catalog.Book.create`, `save`, field assignments) plus `assert`, `throws`, and `emitted`. Generated tests sit beside other service tests (`tests/spec/` in Python, `test/spec/` in TypeScript) and reuse database and messaging fixtures—verification targets real behavior, not stubs.

---

### 1. Generate Idiomatic Code

**Principle:** Generated code should follow language best practices.

**Application:** Generated Python uses type hints, Pydantic models, and async/await where appropriate (e.g. FastAPI). Generated TypeScript uses interfaces, async/await, and framework conventions (e.g. NestJS decorators). The generators produce idiomatic code per language and framework.

---

### 2. No Dead Code, No Runtime Stubs

**Principle:** Only generate code that will be used. Generated code must be fully functional — never emit `raise NotImplementedError` or `throw new Error("...not implemented")` stubs.

**Application:** Only code that is used is generated. Utilities (e.g. case conversion) are emitted only when the Application requires them. The codebase does not generate unused helpers "just in case." Callable declarations that require an implementation body (service functions, entity functions, lifecycle hooks, CQRS handlers, job handlers, validate blocks) are validated at compile time; empty bodies produce `BODY001` errors. Generator fallback paths use internal assertions (indicating a framework bug) rather than user-facing runtime stubs. A shared generated-output guard scans all generated files before output is accepted, ensuring no runtime stub patterns slip through.

---

### 3. Readable Generated Code

**Principle:** Generated code should be readable by humans.

**Application:** Generated code is structured for readability: docstrings, type hints, clear names, and consistent formatting. Models and routes follow a logical structure. The generators enforce these via templates and formatting checks.

**Features:**
- ✅ Docstrings
- ✅ Type hints
- ✅ Clear variable names
- ✅ Proper formatting
- ✅ Logical structure

---

## Documentation Standards

### Capability status labels

Every capability described in documentation must include one of these status labels so readers know what is implemented, what is planned, and what is illustrative:

| Label | Meaning |
|-------|---------|
| **Stable** | Supported by normal CLI generation and tested. |
| **Beta** | Implemented but coverage or UX may change. |
| **Experimental** | Available behind a flag or partial path. |
| **Planned** | Design intent, not yet implemented. |
| **Illustrative** | Example only, not a support claim. |

Place the label near the heading of the capability section (e.g., `### Feature Name (Stable)`).

### Docs synchronization checklist

When changing any of the following, update the corresponding documentation:

1. **CLI options** — Update `datrix-cli/docs/commands/generate.md` and any docs containing CLI examples (e.g., `configuration-guide.md`, `first-project.md`, `architecture-overview.md`).
2. **Semantic analysis phases** — Update the ordered phase list in `architecture/pipeline-and-capabilities.md` to match `SemanticAnalyzer.analyze()`.
3. **Config models** — Update `configuration-guide.md` and any config schema docs.
4. **Generator support** — Update capability sections in `pipeline-and-capabilities.md` with correct status labels.

### Canonical CLI examples

Documentation examples must use current flag syntax. The canonical `datrix generate` invocation is:

```bash
datrix generate --source examples/03-domains/ecommerce/system.dtrx --output generated
```

The target language and deployment settings (runtime, provider, target, registry) are read from resolved config in the selected system `.dcfg` profile. There are no deployment-affecting CLI overrides — see [architecture-overview.md Decision 6: Deployment Target Contract](architecture-overview.md#decision-6-deployment-target-contract-stable). `--profile` selects the config profile to use.

> **Migration note:** The `--hosting` / `-H` and `--platform` / `-P` flags are being removed. The `--language` / `-L` flag remains for development convenience but deployment dimensions come exclusively from config.

---

## Summary

Datrix design principles ensure:

1. **Reliability** - Fail fast, no broken code
2. **Type Safety** - Exhaustive mappings, no implicit conversions
3. **Maintainability** - Template-based generation, single responsibility, immutable AST model
4. **Developer Experience** - Clear errors, readable code, helpful messages
5. **Language Quality** - Platform-independent, DRY, progressive disclosure, configuration boundary, domain extension boundary
6. **Code Quality** - Idiomatic, no dead code, readable output
7. **Deployment clarity** - Construct-mapped platform realization: blocks drive infra shape, targets are explicit, no silent defaults

These principles guide all architectural and implementation decisions in the Datrix project.
