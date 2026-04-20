# Datrix Design Principles

**Last Updated:** April 12, 2026

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

**Example (multi-service NGINX gateway):** `generate_nginx_config` in `datrix_codegen_docker.generators.config.gateway_generator` raises `GenerationError` when any upstream would have no location blocks (for example a service with no `rest_api` / `graphql_api` and no derivable health alias), when two services would publish the same external health path through the gateway, or when a service has no HTTP port in resolved config — rather than emitting an incomplete `nginx.conf`.

**Example (Grafana without metrics):** `generate_dashboards` in `datrix_codegen_docker.generators.infra.dashboard_builder` raises `GenerationError` when visualization is enabled but Prometheus metrics are not — dashboards have no scrape targets to plot.

**Example (rate limit preconditions):** `middleware_rate_limit.py.j2` raises `HTTPException` **503** when `app.state.redis` is missing (rate limiting cannot run), and **429** when the sliding window is exceeded — no silent bypass.

**Benefits:**
- ✅ Cannot continue with invalid state
- ✅ Error includes helpful suggestions
- ✅ Caught during generation, not deployment

---

### 2. Templates + Formatter for Code Generation

**Principle:** Use Jinja2 templates with ruff format for Python code formatting, and Prettier for TypeScript.

**Why:**
- Templates are readable and look like the output
- ruff format (Python) and Prettier (TypeScript) check formatting consistency
- Generated code is no longer auto-formatted; formatting is checked and warnings are surfaced instead
- Easy to maintain and modify
- Reusable template macros

**Application:** Generators use Jinja2 (e.g. `PackageLoader` for templates), render to raw code, and validate syntax before output. Model templates emit a Pydantic model class keyed by entity name, with conditional imports (e.g. UUID when needed) and one field per entity field. Templates should produce well-formatted output; ruff format / Prettier check formatting. Raw string concatenation is not used. See the codebase for template files (e.g. `model.py.j2` in datrix-codegen-python).

**Example (transpiled job handlers):** `JobsGenerator` (`datrix_codegen_python.generators.messaging.jobs_generator`) combines Jinja2 templates such as `messaging/jobs_scheduler.py.j2` and `messaging/jobs_runner.py.j2` with output from `PythonTranspiler` so each scheduled job’s DSL body becomes real Python inside the generated scheduler/runner modules.

**Example (Grafana dashboard JSON):** `DashboardBuilder` (`datrix_codegen_docker.generators.infra.dashboard_builder`) assembles Grafana **provisioned** dashboard documents in Python (nested dicts), serializes them to JSON under `config/grafana/dashboards/`, and pairs them with Jinja2-rendered Prometheus alert YAML — no ad-hoc string concatenation of panel definitions.

**Key Insight:** Templates should produce well-formatted output; ruff format --check catches formatting issues.

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

---

## Language Design Principles

### 1. Platform Independence

**Principle:** DSL code should be platform-agnostic.

**Application:**
```datrix
// Same DSL works for all platforms (excerpt from examples/01-foundation/book-service-base.dtrx)
service library.BookService : version('1.0.0') {
 rdbms db('config/book-service/datasources.yaml') {
 abstract entity BaseEntity {
 @UUID id : primaryKey = uuid();
 @UDateTime createdAt = utcNow();
 @UDateTime updatedAt = utcNow();
 }
 entity Book extends BaseEntity {
 String(200) title;
 String(20) isbn;
 String(100) author;
 Int publicationYear;
 }
 }
}

// Platform selection via config (system-config.yaml: language, hosting), not CLI flags:
// Set hosting: docker | kubernetes | aws | azure in the active profile, then:
// datrix generate --source system.dtrx --output ./generated
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
 @UUID id : primaryKey = uuid();
 @UDateTime createdAt = utcNow();
 @UDateTime updatedAt = utcNow();
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
- Each service declares its own data stores via named blocks: `rdbms db('path')`, `cache redis('path')`, `nosql docdb('path')`, `storage store('path')`, `pubsub mq('path')`
- Config is externalized and profile-based (YAML/JSON). Top-level keys are profile names (`development`, `production`); the generator selects the key from the system profile
- One statement per concern: registration, resilience, and each integration type are separate config statements; deployment-related settings (replicas, resources, healthCheck) live in service-config YAML, not in the DSL

---

### 4. Named Data Blocks and Block-Qualified Access

**Principle:** All data blocks require a user-chosen block name, enabling block-qualified access from outside the block.

**Named Block Syntax:**
```datrix
rdbms db('config/datasources.yaml') { ... }
nosql docdb('config/nosql.yaml') { ... }
cache redis('config/cache.yaml') { ... }
storage store('config/storage.yaml') { ... }
pubsub mq('config/pubsub.yaml') { ... }
```

**Access Rules:**
- **Inside the same block:** Bare names (e.g., `belongsTo Author`, `extends BaseEntity`)
- **Outside the block:** Use `blockname.Thing` (e.g., `resource db.Book`, `db.User.findOrFail(id)`, `redis.SessionCache.set(...)`)
- **Enums, structs, constants:** Live at service level (directly inside `service { }`), always bare names
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
 emit UserRegistered(id, email);
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

**Enforcement:** The parser rejects environmental data in the DSL at parse time. `SERVICE_ATTR_IDENTIFIERS` in `contextual_keywords.py` restricts service attributes to `version` and `description` — writing `port(8000)` in a `.dtrx` file produces an error listing the allowed attributes.

**See also:** [Config System — DSL/YAML Boundary](../../../datrix-common/docs/architecture/config-system.md#dslyaml-boundary) for the full taxonomy and enforcement details.

---

## Code Generation Principles

### Specification-level verification

**Principle:** Business rules declared in the DSL can be exercised with service-level tests that share the same imperative syntax as handlers and jobs.

**Application:** `test("description") { ... }` members on a service compile to async pytest cases or Jest specs. Statements use real entity APIs (`catalog.Book.create`, `save`, field assignments) plus `assert`, `throws`, and `emitted`. Generated tests sit beside other service tests (`tests/spec/` in Python, `test/spec/` in TypeScript) and reuse database and messaging fixtures—verification targets real behavior, not stubs.

---

### 1. Generate Idiomatic Code

**Principle:** Generated code should follow language best practices.

**Application:** Generated Python uses type hints, Pydantic models, and async/await where appropriate (e.g. FastAPI). Generated TypeScript uses interfaces, async/await, and framework conventions (e.g. NestJS decorators). The generators produce idiomatic code per language and framework.

---

### 2. No Dead Code

**Principle:** Only generate code that will be used.

**Application:** Only code that is used is generated. Utilities (e.g. case conversion) are emitted only when the Application requires them. The codebase does not generate unused helpers "just in case."

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

## Summary

Datrix design principles ensure:

1. **Reliability** - Fail fast, no broken code
2. **Type Safety** - Exhaustive mappings, no implicit conversions
3. **Maintainability** - Template-based generation, single responsibility, immutable AST model
4. **Developer Experience** - Clear errors, readable code, helpful messages
5. **Language Quality** - Platform-independent, DRY, progressive disclosure, configuration boundary
6. **Code Quality** - Idiomatic, no dead code, readable output

These principles guide all architectural and implementation decisions in the Datrix project.

---

**Last Updated:** April 13, 2026
