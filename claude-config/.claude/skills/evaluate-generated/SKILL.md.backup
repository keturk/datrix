# Evaluate Generated Code Skill

Compare a `.dtrx` application source against its generated output to produce a deployment-readiness evaluation report. The skill reads the DSL to understand what was defined (services, entities, APIs, blocks, features), cross-references against what was actually generated (using manifests and filesystem inspection), and identifies gaps, missing artifacts, deployment blockers, **dead code** — generated artifacts that should not exist given the DSL source and target platform (e.g., AWS code when the platform is Docker, cache modules when no cache block is defined, unused dependencies), and **semantic correctness issues** — transpiled DSL expressions, computed fields, lifecycle hooks, and validation blocks that do not correctly implement the DSL semantics.

**This skill produces a report.** It does not fix issues or regenerate code. It evaluates completeness, deployment readiness, and semantic correctness.

## When to Use

- User asks to "evaluate", "assess", or "check" generated output against its source
- User wants to know if a generated project is deployment-ready
- User asks "what's missing" from a generated project
- User wants a completeness comparison between DSL source and generated code
- User asks about deployment readiness or blockers for a generated project
- User asks about "dead code", "unnecessary code", or "extra/stale artifacts" in generated output
- User reports seeing platform-specific code (e.g., AWS files) when the target platform is different

## How to Invoke

Primary invocation with both paths:
```
/evaluate-generated

SOURCE: D:\datrix\datrix\examples\02-domains\ecommerce\system.dtrx
GENERATED: D:\datrix\.generated\python\docker\02-domains\ecommerce
```

Example project invocation:
```
/evaluate-generated

SOURCE: D:\datrix\datrix\examples\02-domains\ecommerce\system.dtrx
GENERATED: D:\datrix\.generated\python\docker\02-domains\ecommerce
```

Alternative natural language:
```
"Evaluate generated output for the ecommerce example"
"Check deployment readiness of the ecommerce example"
"Compare ecommerce source against its generated code"
```

When only one path is given, the skill **must ask for the other**. Both SOURCE and GENERATED are required.

## Mandatory Reading (BEFORE any evaluation)

Before doing ANY work, read these documents in full:

1. **`d:\datrix\.claude\CLAUDE.md`** -- Project instructions and coding standards
2. **`d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md`** -- Full contributing rules (index with links to sub-documents under `ai-agent-rules/`)
3. **`d:\datrix\datrix\docs\architecture\architecture-overview.md`** -- System architecture and pipeline (index with links to sub-documents under `architecture/`)
4. **`d:\datrix\datrix\docs\architecture\design-principles.md`** -- Design principles

**DO NOT skip these.** Skipping = rejected report.

### Project Structure (DYNAMIC — read from generated file)

Before evaluating, read the project structure file for the codegen package(s) relevant to the generated output:

- **`d:\datrix\{package-name}\.project-structure.md`**

Where `{package-name}` is determined from the generated output language (e.g., `datrix-codegen-python` for Python, `datrix-codegen-typescript` for TypeScript). Also read `datrix-codegen-docker` and `datrix-codegen-component` if Docker/component artifacts are being evaluated.

If the file is missing or stale, regenerate it:
```bash
powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}
```

## Inputs

1. **SOURCE** -- Path to `system.dtrx` file (the root DSL file that may include other .dtrx files)
2. **GENERATED** -- Path to the generated output directory (the root containing service dirs, docker-compose.yml, etc.)

## Workflow -- Phased with Confidence Checks

**This workflow is broken into phases. At the end of each phase, assess your confidence. If confident in findings, proceed to the next phase (include a brief status note). If NOT confident, STOP and present findings to the user and WAIT for their go-ahead.**

---

### Phase 1: Read and Analyze the DSL Source

**Goal:** Build a complete inventory of what the DSL defines.

#### 1a: Read system.dtrx and Resolve Includes

1. Read `system.dtrx` -- identify the system name, version, and config references (config, registry, gateway, observability)
2. Find all `include` statements and read each included `.dtrx` file
3. Find all `from ... import ...` statements and trace cross-service imports
4. Read config YAML files referenced in the DSL blocks (datasources, pubsub, cache, resilience, registration, observability, gateway, jobs, etc.) -- these are relative to the source directory

#### 1b: Extract DSL Features per Service

For each service defined in the .dtrx files, catalog:

- **Service identity:** qualified name (e.g., `ecommerce.OrderService`), version, description
- **Config statements:** config, registration, resilience, discovery dependencies
- **RDBMS blocks:** block name, config path, entities (name, fields, relationships via hasMany/belongsTo/hasOne/manyToMany, abstract vs concrete, traits used, lifecycle hooks, validate blocks, functions, computed fields, indexes, audit flag), enums, structs
- **Cache blocks:** block name, config path, hash/counter/sorted-set/list/queue definitions
- **PubSub blocks:** block name, config path, topics (with publish events), subscriptions (with event handlers)
- **CQRS blocks:** views, commands, queries
- **REST APIs:** name, basePath, endpoints (method, path, parameters, return type, internal flag, rate limits, alerts)
- **GraphQL APIs:** name, base path, type definitions, queries, mutations, subscriptions
- **Jobs blocks:** config path, job definitions
- **Storage blocks:** block name, config path
- **NoSQL blocks:** block name, config path, document definitions
- **Service dependencies:** discovery block entries

#### 1c: Extract System-Level Features

- System config references (system-config.yaml)
- Registry config
- Gateway config (nginx routing implications)
- Observability config (metrics, tracing, visualization)

**End-of-phase output:** A structured inventory of every DSL-defined feature. This becomes the "expected" checklist.

**If confident** (clear DSL, all includes resolved, configs readable) -- proceed to Phase 2.
**If NOT confident** (missing includes, unreadable configs, ambiguous DSL) -- **STOP and report what could not be resolved.**

---

### Phase 2: Scan the Generated Output

**Goal:** Build a complete inventory of what was actually generated.

#### 2a: Auto-detect Language and Platform

Determine the target language and platform from the generated output:

- **Python:** Look for `pyproject.toml`, `requirements.txt`, `src/` with Python packages, `main.py`
- **TypeScript:** Look for `package.json`, `tsconfig.json`, `src/` with `.ts` files, `app.module.ts`
- **Docker:** Look for `docker-compose.yml`, `Dockerfile`
- **Kubernetes:** Look for `k8s/` directory with manifests

#### 2b: Read Manifests

Read all JSON files under `{GENERATED}/.datrix/manifests/`:
- `python.json` or `typescript.json` -- language-specific generated files
- `docker.json` -- Docker-specific generated files
- `component.json` -- platform-agnostic component files
- `sql.json` -- SQL DDL files

Each manifest has: `{ "target": "...", "generated_at": "...", "files": [...], "user_files": [...] }`

The `files` array is the authoritative list of what the generation pipeline produced. Cross-reference every entry against the filesystem to verify the files actually exist.

#### 2c: Scan Filesystem per Service

For each service directory in the generated output, catalog what exists. Use the language-specific reference tables at the end of this document to know what to look for.

**End-of-phase output:** A structured inventory of every generated artifact, organized by service.

---

### Phase 3: Cross-Reference Source vs Generated

**Goal:** Identify gaps, missing items, and unexpected artifacts.

#### 3a: Service-Level Matching

For each service defined in the DSL:
1. Verify a corresponding service directory exists in the generated output
2. Verify the service directory name follows the convention: `{namespace}_{service_name_snake_case}` (e.g., `ecommerce.OrderService` -> `ecommerce_order_service`)

#### 3b: Per-Block Feature Verification

For each block type within each service, verify the expected generated artifacts exist:

**RDBMS block (`rdbms blockName('config/...')`):**
- [ ] Database connection module
- [ ] Session management
- [ ] Base model
- [ ] Health check
- [ ] One ORM model file per non-abstract entity
- [ ] One Pydantic schema / DTO file per non-abstract entity
- [ ] One service file per non-abstract entity
- [ ] Migration config + initial schema referencing ALL entities in this block
- [ ] SQL DDL file in sql.json manifest

**Cache block (`cache blockName('config/...')`):**
- [ ] Cache client/config module
- [ ] Cache access helpers
- [ ] Cache decorators (if applicable)

**PubSub block (`pubsub blockName('config/...')`):**
- [ ] Message broker config/connection
- [ ] Producer module
- [ ] Consumer module with handlers for each subscription
- [ ] Event schemas

**REST API block (`rest_api Name : basePath('/...')`):**
- [ ] Routes/controller file with handlers for each endpoint
- [ ] Internal endpoints marked with appropriate auth

**GraphQL API block:**
- [ ] GraphQL schema/types
- [ ] Resolvers
- [ ] DataLoader wiring (if relationships present)

**Jobs block:**
- [ ] Scheduler module
- [ ] Runner module
- [ ] Job config
- [ ] Docker worker service in docker-compose (for Docker platform)

**CQRS block:**
- [ ] Command handlers
- [ ] Query handlers
- [ ] View definitions

**Storage block:**
- [ ] Storage client module
- [ ] Storage bucket init script (in Docker output)

**NoSQL block:**
- [ ] NoSQL client module
- [ ] Document models
- [ ] Repository modules
- [ ] Health check

#### 3c: Entity Completeness Check

For each non-abstract entity in each RDBMS block:
- [ ] ORM model exists with all fields from DSL
- [ ] Schema/DTO exists
- [ ] Service exists (if entity exposed via API)
- [ ] Relationships (hasMany, belongsTo, hasOne, manyToMany) present in model
- [ ] Computed fields present (existence check only — semantic verification in Phase 3.5)
- [ ] Lifecycle hooks (beforeCreate, afterCreate, etc.) present (existence check only — semantic verification in Phase 3.5)
- [ ] Validation blocks present (existence check only — semantic verification in Phase 3.5)
- [ ] Entity referenced in initial migration

#### 3d: Project-Level Verification

- [ ] docker-compose.yml exists and includes all service + infrastructure containers
- [ ] .env.example exists with required environment variables
- [ ] Database init scripts present for all RDBMS blocks
- [ ] PubSub topic init scripts present for all PubSub blocks
- [ ] NGINX config present (for multi-service apps with gateway config)
- [ ] Prometheus config present (if observability.metrics enabled)
- [ ] Grafana dashboards present (if observability.visualization enabled)
- [ ] Deploy test exists
- [ ] README exists

#### 3e: Manifest Integrity Check

- [ ] Every file listed in manifests actually exists on disk
- [ ] Note any significant files on disk that do not appear in a manifest

#### 3f: Dead Code Detection

Identify generated artifacts that should NOT exist given the DSL source. Dead code is code that was generated but has no corresponding DSL definition or is irrelevant to the target platform/configuration. This is the inverse of gap analysis — instead of "what's missing?", ask "what shouldn't be here?"

**Platform Mismatch Detection:**

Determine the intended deployment platform from the DSL system config and the generated output. Then flag code for platforms that are NOT the target:

| Target Platform | Should NOT exist |
|-----------------|-----------------|
| Docker only | Any `aws/`, `azure/`, `k8s/` directories or files; AWS CDK constructs; Azure Bicep/ARM templates; Kubernetes manifests; Terraform modules; cloud-specific IAM/policy files |
| Kubernetes | AWS/Azure-specific service wrappers; cloud-native database configurations (RDS, Aurora, CosmosDB); cloud IAM policies |
| AWS | Azure-specific files; GCP files; on-prem-only configurations |
| Azure | AWS-specific files; GCP files; on-prem-only configurations |

Check for platform-specific code by scanning:
- Directory names: `aws/`, `azure/`, `k8s/`, `terraform/`, `cdk/`, `bicep/`, `arm/`
- File patterns: `*.tf`, `*.bicep`, `cdk.json`, `serverless.yml`, `*-stack.ts`
- Import patterns in source files: cloud SDK imports (`@aws-sdk/*`, `@azure/*`, `boto3`, `azure-*`)
- Docker-compose services referencing cloud-only infrastructure (e.g., LocalStack, Azurite) when not needed
- Manifest entries for platform generators that shouldn't have run (e.g., `aws.json` manifest when platform is Docker)

**Unused Feature Module Detection:**

For each feature module type, verify there is a corresponding DSL block. Flag modules that exist without a DSL definition:

| Generated Module | Required DSL Block |
|-----------------|--------------------|
| `redis/`, `cache/` directories | `cache` block in service |
| `mq/`, `pubsub/`, `messaging/` directories | `pubsub` block in service |
| `jobs/` directory | `jobs` block in service |
| `store/` directory | `storage` block in service |
| `docdb/`, `nosql/` directories | `nosql` block in service |
| `cqrs/` directory | `cqrs` block in service |
| `graphql/` directory | `graphql_api` block in service |
| `clients/` with inter-service client files | `discovery` block referencing that service |
| `observability/` directory | `observability` in system config |

**Orphaned Entity Artifacts:**

For each entity-level file (model, schema/DTO, service, migration reference), verify the entity exists in the DSL:
- Model/entity files with no matching DSL entity definition
- Schema/DTO files with no matching DSL entity
- Service files with no matching DSL entity
- Migration references to tables with no DSL entity

**Stale Infrastructure in docker-compose.yml:**

Cross-reference every service defined in `docker-compose.yml` against the DSL:
- Database containers for RDBMS engines not used by any service
- Cache containers when no service has a cache block
- Broker containers when no service has a pubsub block
- NoSQL containers when no service has a nosql block
- Storage containers when no service has a storage block
- Observability containers (Prometheus, Grafana, Jaeger, Loki) when observability is not configured
- Migration containers for blocks that don't exist
- Worker containers for services without jobs blocks
- Init containers (topic init, storage init) for blocks that don't exist

**Unused Dependencies:**

Check `requirements.txt` / `package.json` for libraries that correspond to unused features:
- Database drivers (e.g., `asyncpg`, `aiomysql`, `pg`, `mysql2`) when no RDBMS block uses that engine
- Cache libraries (`redis`, `aioredis`, `ioredis`) when no cache block exists
- Broker libraries (`aiokafka`, `aio-pika`, `kafkajs`, `amqplib`) when no pubsub block exists
- Cloud SDK packages (`boto3`, `@aws-sdk/*`, `azure-*`) when platform is not that cloud
- Observability libraries (`prometheus-client`, `opentelemetry-*`, `prom-client`) when observability is not configured
- Storage libraries (`boto3`/`minio`, `@aws-sdk/client-s3`) when no storage block exists
- NoSQL drivers (`motor`, `pymongo`, `mongodb`) when no nosql block exists

**End-of-phase output:** A structured comparison showing: matched items (present in both DSL and generated), missing items (in DSL but not generated), dead items (in generated but not justified by DSL or platform config), extra items (in generated but not clearly mapped to DSL).

**If confident** -- proceed to Phase 3.5.
**If NOT confident** -- **STOP and present findings, WAIT for user direction.**

---

### Phase 3.5: Semantic Verification of Transpiled Code

**Goal:** Verify that transpiled DSL expressions, computed fields, lifecycle hooks, and validation blocks correctly implement the DSL semantics.

**IMPORTANT:** This phase focuses on **semantic correctness**, not just structural completeness. Read generated code line-by-line and compare against DSL source to verify the transpilation logic is correct.

#### 3.5a: Computed Fields Verification

For each entity with computed fields:

1. **Read the DSL source** for each computed field definition
2. **Read the generated Python/TypeScript code** for the corresponding `@property` method or getter
3. **Verify semantic correctness:**
   - String interpolation expressions transpile correctly (e.g., `#"{title} ({publicationYear})"` → `f"{self.title} ({self.publication_year})"`)
   - Built-in function calls map correctly (e.g., `toLowerCase()` → `.lower()`)
   - Field references use correct Python/TypeScript naming (camelCase → snake_case in Python)
   - Type conversions are correct (e.g., `toString()` → `str()`)
   - Null/None handling is correct
   - Conditional expressions transpile correctly (`condition ? true : false` → `true_value if condition else false_value`)
   - Arithmetic/comparison operators work as expected

**Example DSL:**
```
String displayTitle := #"{title} ({publicationYear})";
```

**Expected Python:**
```python
@property
def display_title(self) -> str:
    return f"{self.title} ({self.publication_year})"
```

**Check:**
- ✅ String interpolation syntax correct
- ✅ Field names converted to snake_case
- ✅ Return type annotation correct

#### 3.5b: Lifecycle Hooks Verification

For each entity with lifecycle hooks:

1. **Read the DSL source** for each hook definition (beforeCreate, afterCreate, beforeUpdate, afterUpdate, beforeDelete, afterDelete)
2. **Read the generated Python/TypeScript code** for the corresponding lifecycle hook method
3. **Verify semantic correctness:**
   - Built-in function calls work correctly (e.g., `Auth.hashPassword(field)`)
   - Field assignments transpile correctly
   - Conditional logic in hooks transpiles correctly
   - Error handling/validation logic is correct
   - Async/await handling is correct (for async operations)
   - Database session/transaction handling is correct

**Example DSL:**
```
beforeCreate {
    passwordHash := Auth.hashPassword(password);
}
```

**Expected Python:**
```python
def before_create(self) -> None:
    from library_book_service.auth import hash_password
    self.password_hash = hash_password(self.password)
```

**Check:**
- ✅ Built-in function call transpiled correctly
- ✅ Import statement added for the function
- ✅ Field assignment uses correct Python naming
- ✅ Method signature correct

#### 3.5c: Validation Blocks Verification

For each entity with validation blocks:

1. **Read the DSL source** for each validation rule
2. **Read the generated Pydantic validator or validation method**
3. **Verify semantic correctness:**
   - Validation expressions transpile correctly
   - Error messages match DSL
   - Validator decorators correct (`@field_validator`, `@model_validator`)
   - Validation logic matches DSL semantics
   - Conditional validations work correctly
   - Cross-field validations reference correct fields

**Example DSL:**
```
validate {
    if (publicationYear > currentYear()) {
        error "Publication year cannot be in the future";
    }
}
```

**Expected Python:**
```python
@model_validator(mode="after")
def validate_publication_year(self) -> "Book":
    from datetime import datetime
    if self.publication_year > datetime.now().year:
        raise ValueError("Publication year cannot be in the future")
    return self
```

**Check:**
- ✅ Built-in function `currentYear()` transpiled to `datetime.now().year`
- ✅ Error message matches DSL
- ✅ Validator decorator correct
- ✅ Return type correct

#### 3.5d: REST API Endpoint Logic Verification

For each REST API endpoint with custom logic (not CRUD):

1. **Read the DSL source** for endpoint implementation
2. **Read the generated route handler code**
3. **Verify semantic correctness:**
   - Request parameter extraction correct
   - Business logic transpiled correctly
   - Response construction matches DSL
   - Error handling matches DSL
   - Database queries match DSL semantics
   - Inter-service calls transpile correctly

#### 3.5e: Event Handler Logic Verification

For PubSub event handlers with custom logic:

1. **Read the DSL source** for event handler implementation
2. **Read the generated consumer/handler code**
3. **Verify semantic correctness:**
   - Event payload deserialization correct
   - Handler logic matches DSL
   - Database operations match DSL
   - Error handling/retries match configuration
   - Event publishing (if any) transpiles correctly

#### 3.5f: Documentation of Semantic Issues

For each semantic issue found, document:

- **DSL Source:** The original DSL code (file, line number, entity/block/field name)
- **Generated Code:** The transpiled code (file, line number)
- **Issue:** What is semantically incorrect (missing logic, wrong operator, incorrect function call, etc.)
- **Expected:** What the correct transpilation should be
- **Impact:** Runtime error, incorrect behavior, data corruption, etc.
- **Severity:** Critical (causes crash/data loss), Major (incorrect behavior), Minor (cosmetic/optimization)

**End-of-phase output:** A structured list of semantic correctness issues organized by severity, with references to both DSL source and generated code.

**If confident** -- proceed to Phase 4.
**If NOT confident** (many complex expressions, uncertain about transpilation rules) -- **STOP and present findings, WAIT for user direction.**

---

### Phase 4: Deployment Readiness Assessment

**Goal:** Determine if the generated output can be deployed and run.

#### 4a: Container Readiness (Docker)
- [ ] Every service has a Dockerfile
- [ ] docker-compose.yml has a service entry for every DSL service
- [ ] Infrastructure services present (see Docker Infrastructure Mapping table below)
- [ ] Health checks configured for all service containers
- [ ] Correct depends_on relationships (services depend on infrastructure, migration containers)
- [ ] Port assignments unique
- [ ] Network configuration present
- [ ] Volume mounts for data persistence

#### 4b: Database Readiness
- [ ] Alembic/migration config exists per RDBMS block
- [ ] Initial migration exists and references all entities
- [ ] Database init SQL script creates required databases
- [ ] Migration container defined in docker-compose for each RDBMS block

#### 4c: Environment Variables
- [ ] .env.example documents all required variables
- [ ] Database URLs present for each RDBMS block
- [ ] Redis URLs present (if cache blocks exist)
- [ ] Broker URLs present (if pubsub blocks exist)
- [ ] JWT secrets present (if gateway JWT configured)
- [ ] Internal API tokens present (if internal endpoints exist across services)
- [ ] Storage credentials present (if storage blocks exist)
- [ ] NoSQL URIs present (if nosql blocks exist)
- [ ] Observability endpoints present (if observability configured)

#### 4d: Dependency Completeness
- [ ] requirements.txt / package.json includes all needed libraries
- [ ] Database drivers present (asyncpg for PostgreSQL, aiomysql for MySQL)
- [ ] Cache libraries present (redis/aioredis)
- [ ] Broker libraries present (aiokafka, aio-pika, etc.)
- [ ] HTTP client libraries present (httpx for inter-service calls)
- [ ] Observability libraries present (prometheus-client, opentelemetry)

#### 4e: Potential Runtime Issues
- [ ] No circular service dependencies
- [ ] All inter-service client modules reference correct base URLs
- [ ] Health check paths match what the service exposes
- [ ] NGINX upstream names match docker-compose service names (if gateway present)

**End-of-phase output:** A deployment readiness assessment with specific blockers listed.

---

### Phase 5: Generate the Report

**Goal:** Write a structured evaluation report to `d:\datrix\eval\`.

#### 5a: Create Report Directory

Create `d:\datrix\eval\` if it does not exist.

#### 5b: Report Filename

```
d:\datrix\eval\{YYYY-MM-DD}-eval-{project-slug}-{language}.md
```

Where:
- `{project-slug}` is derived from the system name (e.g., `ecommerce`, `library`)
- `{language}` is the detected target language (`python` or `typescript`)

If a report with the same name already exists, append a sequence number: `-01`, `-02`, etc.

#### 5c: Report Template

```markdown
# Deployment Readiness Evaluation

**Project:** {system name}
**Date:** {YYYY-MM-DD HH:MM}
**Source:** `{source path}`
**Generated:** `{generated path}`
**Language:** {Python/TypeScript}
**Platform:** {Docker/Kubernetes/AWS/Azure}
**Generated At:** {timestamp from manifests}

---

## Executive Summary

**Overall Readiness:** {READY / NOT READY -- {N} blockers}
**Completeness Score:** {X}/{Y} expected artifacts generated ({percentage}%)
**Deployment Blockers:** {count}
**Warnings:** {count}
**Dead Code Items:** {count}
**Semantic Issues:** {count} ({critical}/{major}/{minor})

{2-3 sentence summary of findings}

---

## Source Analysis

### System Configuration

| Config Type | Path | Present |
|-------------|------|---------|
| System config | config/system-config.yaml | Yes/No |
| Registry | config/registry.yaml | Yes/No |
| Gateway | config/gateway.yaml | Yes/No |
| Observability | config/observability.yaml | Yes/No |

### Services Defined

| Service | Version | RDBMS | Cache | PubSub | REST API | GraphQL | Jobs | Storage | NoSQL | CQRS |
|---------|---------|-------|-------|--------|----------|---------|------|---------|-------|------|
| {qualified name} | {version} | {count} | {count} | {count} | {count} | {count} | {count} | {count} | {count} | {count} |

### Entity Summary

| Service | Block | Entities | Abstract | Enums | Structs | Relationships |
|---------|-------|----------|----------|-------|---------|---------------|
| {service} | {block} | {count} | {count} | {count} | {count} | {count} |

### Feature Summary

| Feature | Services Using It |
|---------|-------------------|
| Cache (Redis) | {list} |
| PubSub | {list} |
| CQRS | {list} |
| Background Jobs | {list} |
| Object Storage | {list} |
| NoSQL (MongoDB) | {list} |
| GraphQL | {list} |
| Inter-service Dependencies | {list} |
| Lifecycle Hooks | {list} |

---

## Generated Output Analysis

### Manifest Summary

| Manifest | Files Listed | Files on Disk | Missing |
|----------|-------------|---------------|---------|
| {language}.json | {count} | {count} | {count} |
| docker.json | {count} | {count} | {count} |
| component.json | {count} | {count} | {count} |
| sql.json | {count} | {count} | {count} |

### Per-Service Verification

#### {Service Name}

| Category | Expected | Found | Missing | Status |
|----------|----------|-------|---------|--------|
| ORM Models / Entities | {N} | {N} | {list or "none"} | PASS/FAIL |
| Schemas / DTOs | {N} | {N} | {list or "none"} | PASS/FAIL |
| Services | {N} | {N} | {list or "none"} | PASS/FAIL |
| Routes / Controllers | {N} | {N} | {list or "none"} | PASS/FAIL |
| Migrations | {N} | {N} | {list or "none"} | PASS/FAIL |
| Cache modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| PubSub modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| Jobs modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| NoSQL modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| Storage modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| Enum files | {N} | {N} | {list or "none"} | PASS/FAIL |
| Tests | {present/absent} | | | PASS/FAIL |
| Dockerfile | {present/absent} | | | PASS/FAIL |
| Requirements | {present/absent} | | | PASS/FAIL |

{Repeat for each service}

---

## Missing or Incomplete Items

### Critical (Deployment Blockers)

{Numbered list of items that MUST be present for deployment:}
1. **{What is missing}** -- {Which service/block} -- {Why it blocks deployment}

### Warnings (Non-blocking but Notable)

{Numbered list of items that are expected but not strictly required:}
1. **{What is missing}** -- {Which service/block} -- {Impact if absent}

### Observations

{Items that are notable but not necessarily problems:}
- {Observation about generated structure}

---

## Semantic Correctness Issues

Generated code that does NOT correctly implement the DSL semantics. These are transpilation errors where the generated Python/TypeScript code exists but does not match the intended behavior from the DSL source.

### Critical Issues (Causes Runtime Errors or Data Loss)

{Transpilation errors that will crash the application or corrupt data at runtime.}

| Entity/Block | DSL Feature | DSL Source | Generated Code | Issue | Expected |
|--------------|-------------|------------|----------------|-------|----------|
| `{Entity.field}` | Computed field | `displayTitle := #"{title} ({year})"` | `return f"{self.title}"` | Missing year in interpolation | `return f"{self.title} ({self.publication_year})"` |
| `{Entity.hook}` | Lifecycle hook | `passwordHash := Auth.hashPassword(password)` | `self.password_hash = password` | Missing hash function call | `self.password_hash = hash_password(self.password)` |

### Major Issues (Incorrect Behavior, No Crash)

{Transpilation errors that produce wrong results but don't crash.}

| Entity/Block | DSL Feature | DSL Source | Generated Code | Issue | Expected |
|--------------|-------------|------------|----------------|-------|----------|
| `{Entity.validation}` | Validation | `if (year > currentYear())` | `if self.year > datetime.now()` | Comparing int to datetime | `if self.year > datetime.now().year` |

### Minor Issues (Cosmetic or Optimization)

{Transpilation inefficiencies or style issues that don't affect correctness.}

| Entity/Block | DSL Feature | DSL Source | Generated Code | Issue | Suggested Fix |
|--------------|-------------|------------|----------------|-------|---------------|
| `{Entity.field}` | Computed field | `fullName := firstName + " " + lastName` | `return str(self.first_name) + " " + str(self.last_name)` | Unnecessary str() calls (fields already strings) | `return self.first_name + " " + self.last_name` |

### How to Fix Semantic Issues (Transpiler-Side)

Semantic issues are caused by bugs in the transpiler that converts DSL expressions to target language code. For each semantic issue above, trace the problem back to the **transpiler code**:

1. **[CRITICAL]** Missing year in displayTitle interpolation
   - **Transpiler:** `ExpressionTranspiler` in `d:\datrix\datrix-common\src\datrix_common\transpiler\expression_transpiler.py`
   - **Root cause:** String interpolation parser not extracting all `{...}` placeholders from DSL template
   - **Suggested fix:** Fix regex or parser logic in `transpile_string_interpolation()` to capture all placeholders

2. **[CRITICAL]** Missing hash function call in beforeCreate hook
   - **Transpiler:** `BuiltinFunctionTranspiler` in `d:\datrix\datrix-common\src\datrix_common\transpiler\builtin_transpiler.py`
   - **Root cause:** `Auth.hashPassword()` not recognized as built-in function, treated as plain assignment
   - **Suggested fix:** Add `Auth.hashPassword` to built-in function registry, map to `hash_password()` import

3. **[MAJOR]** Comparing int to datetime in validation
   - **Transpiler:** `BuiltinFunctionTranspiler` for `currentYear()` built-in
   - **Root cause:** `currentYear()` transpiles to `datetime.now()` instead of `datetime.now().year`
   - **Suggested fix:** Update built-in function mapping for `currentYear()` to include `.year` accessor

---

## Dead / Unnecessary Code

Generated artifacts that should NOT exist given the DSL source and target platform. These waste disk space, bloat dependencies, confuse developers, and may cause runtime errors from misconfigured modules.

### Platform Mismatch

{Files or directories generated for a platform that is NOT the target. E.g., AWS code when deploying to Docker.}

| File / Directory | Platform It Belongs To | Target Platform | Action |
|-----------------|----------------------|-----------------|--------|
| `{path}` | {AWS/Azure/K8s} | {Docker/K8s/...} | Remove from generator |

### Unused Feature Modules

{Modules generated for features not defined in the DSL source.}

| Module Path | Expected DSL Block | Present in DSL? | Action |
|------------|-------------------|-----------------|--------|
| `{service}/src/.../redis/` | `cache` block in `{service}` | No | Remove from generator |

### Orphaned Entity Artifacts

{Entity-level files (models, schemas, services) with no matching DSL entity definition.}

| Artifact | Expected Entity | Present in DSL? |
|----------|----------------|-----------------|
| `{path}` | `{entity name}` | No |

### Stale Infrastructure

{docker-compose.yml services or init containers for blocks/features not in the DSL.}

| Compose Service | Expected DSL Block/Feature | Present in DSL? |
|----------------|---------------------------|-----------------|
| `{service-name}` | `{block type}` in `{service}` | No |

### Unused Dependencies

{Libraries in requirements.txt / package.json for features not used.}

| Dependency | Feature It Supports | Feature Present? |
|-----------|--------------------|-----------------|
| `{package name}` | `{feature}` | No |

### How to Fix Dead Code (Generator-Side)

Dead code is produced because a generator or sub-generator runs unconditionally or has an overly broad feature-detection condition. For each dead code category above, trace the problem back to the **generator code** that produces it:

1. **[PLATFORM]** {What was generated for the wrong platform}
   - **Generator:** `{GeneratorClass}` in `d:\datrix\datrix-codegen-{target}\src\...\{file}.py`
   - **Root cause:** {Generator runs without checking target platform, or platform filter is too broad}
   - **Suggested fix:** {Add platform guard / check `codegen_context.platform` before generating}

2. **[FEATURE]** {Module generated without corresponding DSL block}
   - **Generator:** `{GeneratorClass}` in `d:\datrix\datrix-codegen-{target}\src\...\{file}.py`
   - **Root cause:** {Feature detection returns true even when no block exists, or generator always runs}
   - **Suggested fix:** {Add block-existence check / fix `detect_service_features()` logic}

3. **[DEPENDENCY]** {Library included without corresponding feature}
   - **Generator:** `{GeneratorClass}` or template `{template.j2}`
   - **Root cause:** {Dependency list is static rather than feature-conditional}
   - **Suggested fix:** {Make dependency conditional on feature flag / block existence}

---

## Deployment Readiness Checklist

### Infrastructure

| Check | Status | Details |
|-------|--------|---------|
| docker-compose.yml present | PASS/FAIL | |
| All services in compose | PASS/FAIL | {missing services if any} |
| Database containers | PASS/FAIL | {which databases} |
| Cache containers | PASS/FAIL | |
| Broker containers | PASS/FAIL | |
| NoSQL containers | PASS/FAIL | |
| Storage containers | PASS/FAIL | |
| Health checks configured | PASS/FAIL | {services without health checks} |
| Network defined | PASS/FAIL | |
| Volumes defined | PASS/FAIL | |

### Database

| Check | Status | Details |
|-------|--------|---------|
| Init SQL scripts | PASS/FAIL | |
| Migration configs | PASS/FAIL | {per block} |
| Initial migrations | PASS/FAIL | {per block} |
| Migration containers | PASS/FAIL | |

### Environment

| Check | Status | Details |
|-------|--------|---------|
| .env.example present | PASS/FAIL | |
| Database URLs documented | PASS/FAIL | |
| Secrets documented | PASS/FAIL | |
| All required vars present | PASS/FAIL | {missing vars} |

### Gateway (if multi-service)

| Check | Status | Details |
|-------|--------|---------|
| NGINX config present | PASS/FAIL | |
| All services have upstream | PASS/FAIL | |
| All REST API paths routed | PASS/FAIL | |
| Internal paths blocked | PASS/FAIL | |

### Monitoring (if observability configured)

| Check | Status | Details |
|-------|--------|---------|
| Prometheus config | PASS/FAIL | |
| Prometheus alerts per service | PASS/FAIL | |
| Grafana dashboards | PASS/FAIL | |
| System overview dashboard | PASS/FAIL | |

---

## How to Fix (Generator-Side)

For each missing or incomplete item, trace the problem back to the **Datrix generator code** (not the generated output). The generated code is an artifact -- fixing it directly is pointless because it will be overwritten on the next generation. Always fix the generator that produces the output.

{Numbered list, prioritized by severity. Each entry must identify the generator source:}

1. **[CRITICAL]** {What is missing/broken}
   - **Generator:** `{GeneratorClass}` in `d:\datrix\datrix-codegen-{target}\src\...\{file}.py`
   - **Template:** `{template_name.j2}` in `d:\datrix\datrix-codegen-{target}\src\...\templates\{path}`
   - **Root cause:** {Why the generator does not produce this artifact -- missing condition, missing feature detection, template gap, etc.}
   - **Suggested fix:** {What to change in the generator/template to produce the missing artifact}

2. **[WARNING]** {What is missing/broken}
   - **Generator:** ...
   - **Template:** ...
   - **Root cause:** ...
   - **Suggested fix:** ...

3. **[INFO]** {Observation}
   - **Generator:** ...
   - **Note:** ...

**Key generator locations for tracing:**

| Language | Package | Generator Source | Templates |
|----------|---------|-----------------|-----------|
| Python | `datrix-codegen-python` | `d:\datrix\datrix-codegen-python\src\datrix_codegen_python\generators\` | `d:\datrix\datrix-codegen-python\src\datrix_codegen_python\templates\` |
| TypeScript | `datrix-codegen-typescript` | `d:\datrix\datrix-codegen-typescript\src\datrix_codegen_typescript\generators\` | `d:\datrix\datrix-codegen-typescript\src\datrix_codegen_typescript\templates\` |
| Docker | `datrix-codegen-docker` | `d:\datrix\datrix-codegen-docker\src\datrix_codegen_docker\generators\` | `d:\datrix\datrix-codegen-docker\src\datrix_codegen_docker\templates\` |
| Component | `datrix-codegen-component` | `d:\datrix\datrix-codegen-component\src\datrix_codegen_component\generators\` | `d:\datrix\datrix-codegen-component\src\datrix_codegen_component\templates\` |
| SQL | `datrix-codegen-sql` | `d:\datrix\datrix-codegen-sql\src\datrix_codegen_sql\generators\` | `d:\datrix\datrix-codegen-sql\src\datrix_codegen_sql\templates\` |
| Common (pipeline, orchestrator) | `datrix-common` | `d:\datrix\datrix-common\src\datrix_common\generation\` | N/A |

**When tracing a missing artifact to its generator:**
1. Identify the artifact type (model, schema, route, migration, Docker config, etc.)
2. Find the sub-generator responsible (check `registry.py` in the codegen package for the sub-generator mapping)
3. Read the sub-generator's `generate()` method to find the condition that decides whether to produce this artifact
4. Check if the condition evaluates correctly for the DSL source in question
5. If the condition is wrong or missing, that is the root cause
```

---

### Phase 6: Confirm Report Written

Present summary to user:
```
Evaluation report written to: d:\datrix\eval\{YYYY-MM-DD}-eval-{project-slug}-{language}.md

Summary:
- Overall Readiness: {READY/NOT READY}
- Completeness: {X}/{Y} ({percentage}%)
- Blockers: {N}
- Warnings: {N}
- Dead Code Items: {N}
- Semantic Issues: {N} ({critical}/{major}/{minor})
- Services evaluated: {list}
```

---

## Language-Specific Reference

### Python/FastAPI -- Expected Generated Structure per Service

```
{service_dir}/
+-- alembic-{block}.ini                    # per RDBMS block
+-- migrations-{block}/                    # per RDBMS block
|   +-- env.py
|   +-- script.py.mako
|   +-- versions/0001_initial_schema.py
+-- pyproject.toml
+-- requirements.txt
+-- requirements-dev.txt
+-- Dockerfile
+-- .dockerignore
+-- src/{python_package}/
|   +-- __init__.py
|   +-- main.py
|   +-- config.py
|   +-- auth.py
|   +-- error_handlers.py
|   +-- error_response.py
|   +-- {block_name}/                      # per RDBMS block (kebab-case)
|   |   +-- __init__.py
|   |   +-- base.py
|   |   +-- connection.py
|   |   +-- session.py
|   |   +-- health.py
|   +-- models/{block_name}/               # per RDBMS block
|   |   +-- __init__.py
|   |   +-- {entity_snake}.py              # per non-abstract entity
|   +-- schemas/{block_name}/              # per RDBMS block
|   |   +-- __init__.py
|   |   +-- {entity_snake}.py              # per non-abstract entity
|   +-- schemas/{struct_snake}.py           # per struct (at schemas root)
|   +-- services/_base.py
|   +-- services/{block_name}/             # per RDBMS block
|   |   +-- __init__.py
|   |   +-- {entity_snake}_service.py      # per non-abstract entity
|   +-- routes/                            # per REST API
|   |   +-- __init__.py
|   |   +-- {api_name_snake}.py
|   +-- redis/                             # if cache block
|   |   +-- __init__.py
|   |   +-- access.py
|   |   +-- config.py
|   |   +-- connection.py
|   |   +-- decorators.py
|   +-- mq/                                # if pubsub block
|   |   +-- __init__.py
|   |   +-- config.py
|   |   +-- connection.py
|   |   +-- consumer.py
|   |   +-- producer.py
|   |   +-- schemas.py
|   +-- jobs/                              # if jobs block
|   |   +-- config.py
|   |   +-- runner.py
|   |   +-- scheduler.py
|   +-- store/                             # if storage block
|   |   +-- store_client.py
|   +-- docdb/                             # if nosql block
|   |   +-- client.py
|   |   +-- health.py
|   +-- cqrs/                              # if CQRS block
|   +-- observability/                     # if observability configured
|   |   +-- health_endpoint.py
|   |   +-- metrics_middleware.py
|   |   +-- structured_logger.py
|   |   +-- tracing_setup.py
|   +-- enums/                             # if enums defined
|   |   +-- {enum_snake}.py
|   +-- clients/                           # if service dependencies
|   +-- middleware/
+-- tests/
    +-- unit/
    +-- integration/
```

### TypeScript/NestJS -- Expected Generated Structure per Service

```
{service_dir}/
+-- package.json
+-- tsconfig.json
+-- tsconfig.build.json
+-- Dockerfile
+-- .dockerignore
+-- nest-cli.json
+-- src/
|   +-- main.ts
|   +-- app.module.ts
|   +-- config/
|   |   +-- app.config.ts
|   +-- entities/{block_name}/             # per RDBMS block (snake_case)
|   |   +-- {entity_snake}.entity.ts       # per non-abstract entity
|   +-- dto/{block_name}/                  # per RDBMS block
|   |   +-- create-{entity_kebab}.dto.ts   # per non-abstract entity
|   |   +-- update-{entity_kebab}.dto.ts
|   |   +-- {entity_kebab}.response.dto.ts
|   +-- dto/{struct_kebab}.dto.ts           # per struct
|   +-- controllers/
|   |   +-- {api_kebab}.controller.ts      # per REST API
|   +-- services/{block_name}/
|   |   +-- {entity_kebab}.service.ts      # per non-abstract entity
|   +-- {block_name}-db/                   # database module per RDBMS block (kebab-case)
|   |   +-- database.module.ts
|   |   +-- database.config.ts
|   |   +-- database.health.ts
|   +-- nosql/                             # if nosql block
|   +-- pubsub/ or messaging/              # if pubsub block
|   +-- observability/                     # if observability
|   +-- enums/
|   |   +-- {enum_kebab}.enum.ts
+-- test/
```

### Project-Level Artifacts (both languages)

```
{generated_root}/
+-- docker-compose.yml
+-- .env.example
+-- ENV.md
+-- README.md
+-- .datrix/
|   +-- manifests/
|   |   +-- {language}.json
|   |   +-- docker.json
|   |   +-- component.json
|   |   +-- sql.json
|   +-- snapshots/
+-- config/
|   +-- nginx/nginx.conf                   # if multi-service with gateway
|   +-- prometheus/
|   |   +-- prometheus.yml                 # if observability.metrics
|   |   +-- {service}-alerts.yml           # per service
|   +-- grafana/                           # if observability.visualization
|       +-- dashboards/
|       +-- provisioning/
+-- docs/
|   +-- architecture.md
+-- scripts/
|   +-- init-db/                           # database init SQL
|   +-- init-topics/                       # pubsub topic creation
|   +-- init-storage/                      # storage bucket creation
|   +-- dev/
|       +-- start.py
|       +-- stop.py
+-- tests/
    +-- conftest.py
    +-- deploy_test.py
    +-- run_tests.py
    +-- test-config.json
```

---

## Docker Infrastructure Mapping

Use this table to determine which infrastructure containers should exist in docker-compose.yml:

| DSL Block | Expected Container(s) | Notes |
|-----------|----------------------|-------|
| `rdbms` (PostgreSQL) | `{system}-{service}-{block}-db` | PostgreSQL database |
| `rdbms` (MySQL/MariaDB) | `{system}-{service}-{block}-db` | MySQL/MariaDB database |
| `rdbms` per block | `{service}-{block}-migrate` | Alembic/Flyway migration container |
| `cache redis(...)` | `{system}-redis` | Shared Redis |
| `pubsub mq(...)` (Kafka) | `{system}-kafka`, `{system}-zookeeper` | Kafka + Zookeeper |
| `pubsub mq(...)` (RabbitMQ) | `{system}-rabbitmq` | RabbitMQ |
| `nosql docdb(...)` | `{service}-docdb` | MongoDB |
| `storage store(...)` | `{service}-minio` | MinIO |
| observability.metrics | `{system}-prometheus` | Prometheus |
| observability.visualization | `{system}-grafana` | Grafana |
| observability.tracing | `{system}-jaeger` | Jaeger |
| observability.logging | `{system}-loki` | Loki |
| observability (alerts) | `{system}-alertmanager` | AlertManager |
| observability (container) | `{system}-cadvisor` | Container metrics |
| gateway (multi-service) | `{system}-gateway` | NGINX reverse proxy |
| service with jobs | `{service}-worker` | Background job worker |
| pubsub per block | `{service}-mq-init` | Topic init container |
| storage per block | `{service}-storage-init` | Bucket init container |

---

## Anti-Patterns to Avoid

- **Do NOT explore the project structure manually** -- read `.project-structure.md` for the relevant codegen package(s), don't rediscover it
- **Do NOT run generate.ps1** -- the skill assumes generated output already exists
- **Do NOT modify any files** -- this is a read-only evaluation
- **Do NOT guess at DSL syntax** -- read the actual .dtrx files, do not invent block types or features
- **Do NOT assume features exist** -- only report on blocks actually defined in the DSL
- **Do NOT confuse abstract entities with concrete ones** -- abstract entities do not get their own model/schema/service files; they are base classes only
- **Do NOT count inherited fields as "missing"** -- fields come from parent entity via `extends`
- **Do NOT flag trait fields as "missing"** -- fields injected by `with TraitName` are provided by the trait, not listed in the entity definition
- **Do NOT flag user_files as "missing"** -- files listed under `user_files` in manifests are scaffolded (overwrite=False) and may not exist if never scaffolded initially
- **Do NOT run specification tests** -- semantic verification is code review (reading), not execution (running)
- **Do NOT verify business logic correctness** -- only verify transpilation correctness (DSL expression → Python/TypeScript mapping is correct)
- **Do NOT flag stylistic choices as semantic issues** -- only flag transpilation bugs (e.g., wrong operator, missing function call, incorrect field reference)
- **Do NOT assume transpilation bugs without reading the code** -- verify by reading both DSL source and generated code line-by-line

## CLI Quick Reference

```bash
# Parse a .dtrx file to see its structure (syntax check only)
powershell -File "d:/datrix/datrix/scripts/dev/syntax-checker.ps1" "{source.dtrx}"

# Check generated code compilation (Python syntax + imports)
powershell -File "d:/datrix/datrix/scripts/dev/compile-any-path.ps1" "{generated_service_dir}/src"

# Audit generated code for syntax errors and placeholders
powershell -File "d:/datrix/datrix/scripts/dev/audit.ps1" -Report "d:/datrix/eval/audit-report.md"
```
