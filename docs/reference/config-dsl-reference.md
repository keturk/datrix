# Config DSL Reference

**Version:** 1.1
**Last Updated:** 2026-06-22

---

## Overview

The Config Definition DSL (configDSL) provides a structured, template-based syntax for authoring Datrix configuration. Files with the `.dcfg` extension compile to the same canonical dictionary shape as YAML, validated by the same Pydantic models.

**Key features:**
- Reusable templates with parameters
- Profile inheritance and aliases
- Explicit replacement semantics
- Profile-indexed default values
- Environment variable references with interpolation

---

## File Structure

### Config Declaration

Every `.dcfg` file declares its config kind and owner:

```dcfg
config service ecommerce.OrderService {
  // imports, templates, base, profiles
}

config system ecommerce.System {
  // imports, templates, base, profiles
}

config shared ecommerce.SharedTypes {
  // imports, templates, base, profiles
}
```

The config kind determines which Pydantic model validates the compiled output:
- `config service` → `ServiceConfigProfileConfig`
- `config system` → `SystemConfigProfileConfig`
- `config shared` → `SharedConfigProfileConfig`

---

## Imports

Import templates and config fragments from other `.dcfg` files:

```dcfg
import "config/templates/postgres.dcfg";
import "config/templates/redis.dcfg";
import "config/templates/resilience.dcfg";
```

**Rules:**
- Imports are project-root relative
- Circular imports are errors
- Imported templates are visible in the importing file
- Package-level imports (e.g., `import datrix.config.azure.postgres;`) are deferred to a future version

---

## Templates

Templates define reusable config fragments. They declare shape and policy, not service instances.

### Template Definition

```dcfg
template postgresContainer(database, schema, poolSize = perProfile(test: 2, development: 10, production: 40)) {
  engine = postgres;
  flavor = container;
  host = "localhost";
  port = 5432;
  database = database;
  schema = schema;
  poolSize = poolSize;
  asyncDriver = "postgresql+asyncpg";
  syncDriver = "postgresql+psycopg2";
  healthCheckSql = "SELECT 1";
  dockerImage = "postgres:17-alpine";
  volumePath = "/var/lib/postgresql/data";
}
```

### Template Parameters

**Required parameters:** Omit default values. The caller must supply them.

```dcfg
template postgresAzureFlexibleServer(database, schema, host) {
  engine = postgres;
  flavor = flexible-server;
  host = host;
  database = database;
  schema = schema;
  // ...
}
```

**Optional parameters:** Provide default values.

```dcfg
template httpClient(baseUrl, timeout = 30s, maxRetries = 3) {
  baseUrl = baseUrl;
  timeout = timeout;
  retry.maxAttempts = maxRetries;
}
```

**Parameter typing:** Parameters are untyped. Semantic validation happens after template expansion when the Pydantic models validate the canonical output.

**Instance-specific vs reusable defaults:**
- **Instance-specific data** (database names, hosts, bucket names, queue names, URLs) must be required parameters — no defaults
- **Reusable policy values** (pool sizes, timeouts, retry limits, driver names) may have defaults

### Profile-Indexed Defaults (`perProfile`)

Use `perProfile(...)` to provide different default values per profile:

```dcfg
template postgresContainer(
  database,
  schema,
  poolSize = perProfile(test: 2, development: 10, staging: 20, production: 40)
) {
  poolSize = poolSize;
  // ...
}
```

**Resolution:** `perProfile` is resolved against the active concrete profile at the template use site. It does NOT walk the profile inheritance chain.

**Example:** If `staging extends production`, and a `perProfile` map only lists `production: 40`, the `staging` profile will raise an error unless `default:` is provided:

```dcfg
template httpTimeout(timeout = perProfile(default: 30s, production: 60s)) {
  timeout = timeout;
}
```

**When to use `default:`**
- For low-risk policy values where all profiles should get the same fallback
- Avoid for production-critical values (hosts, credentials, database names)

**Nested `perProfile` for irregular names:**

```dcfg
template postgresAzureFlexibleServer(
  database,
  schema,
  host = env(perProfile(
    development: "LOCAL_POSTGRES_HOST",
    staging: "ECOMMERCE_STG_DB_ENDPOINT",
    production: "ECOMMERCE_PROD_POSTGRES_HOST"
  ))
) {
  host = host;
  // ...
}
```

**Restrictions:**
- `perProfile` is valid ONLY inside template parameter defaults and template body expressions
- It must NOT appear directly inside `base` or concrete profile blocks

### Template Usage

**Named block instantiation:**

```dcfg
rdbms orderDb from postgresContainer(
  database: ecommerce_orders,
  schema: orders
);

cache orderCache from redisContainer();

storage orderAttachments from minioStore(
  bucket: "ecommerce-${profile.resource}-order-attachments"
);
```

**Inline instantiation:**

```dcfg
resilience from standardResilience();
```

**Argument passing:**
- Single-argument templates may omit the parameter name: `from redisContainer()`
- Multi-argument templates must use named arguments: `database: ecommerce_orders, schema: orders`

---

## Profiles

### Base Profile

`base` is an inheritance block, NOT a selectable profile:

```dcfg
base {
  port = 8001;
  flavor = compose;
  replicas = 1;
}
```

The CLI cannot select `base`:
```bash
datrix generate --profile base  # ERROR: base is not a concrete profile
```

Interpolation variables like `${profile.name}` and `${profile.env}` are resolved only for concrete profiles.

### Concrete Profiles

Profiles are selectable named blocks:

```dcfg
profile development as "dev" extends base {
  alias env = "DEV";
  alias resource = "dev";
  replicas = 1;
}

profile staging as "stg" extends production {
  alias env = "STG";
  alias resource = "stg";
  replicas = 1;
  scaling.replicas.max = 2;
}

profile production as "prod" extends base {
  alias env = "PROD";
  alias resource = "prod";
  replicas = 3;
}
```

**CLI selection:**
```bash
datrix generate --profile production
datrix generate --profile staging
datrix generate --profile development
```

### Profile Aliases

The `as` value defines the default short alias:

```dcfg
profile production as "prod" extends base {
  // ...
}
```

`${profile.short}` resolves to `"prod"`.

**Named aliases:**

```dcfg
profile production as "prod" extends base {
  alias env = "PROD";
  alias resource = "prod";
  alias region = "us-east-1";
}
```

Aliases are available as `${profile.<alias>}`:
- `${profile.env}` → `"PROD"`
- `${profile.resource}` → `"prod"`
- `${profile.region}` → `"us-east-1"`

**Casing preservation:** Alias values are preserved exactly. The compiler must not normalize casing.

**Use cases:**
- `alias env = "PROD"` → for screaming-snake environment variable names: `env("ECOMMERCE_${profile.env}_POSTGRES_HOST")`
- `alias resource = "prod"` → for lowercase DNS/resource names: `bucket: "ecommerce-${profile.resource}-data"`

**Scope:** Aliases are scoped to the selected profile. Profiles may reuse alias names (`env`, `resource`) because only one profile is active at a time.

**NOT selectable:** Aliases are interpolation metadata only. They do not create additional selectable profile names.

### Profile Inheritance

Profiles inherit explicitly via `extends`:

```dcfg
profile staging as "stg" extends production {
  replicas = 1;  // overrides production's replicas: 3
}
```

**No implicit fallback:** There is NO implicit fallback from one profile to another. The inheritance chain is the contract.

**Merge semantics:**
- Scalars override inherited values
- Objects merge by key
- Lists replace by default
- Named blocks merge by name

---

## Replacement

Use `replace` to completely replace a named block instead of merging:

```dcfg
profile production as "prod" extends base {
  replace rdbms orderDb from postgresAzureFlexibleServer(
    database: ecommerce_orders,
    schema: orders
  );

  replace cache orderCache {
    engine = redis;
    flavor = cache-for-redis;
    url = env("ECOMMERCE_${profile.env}_REDIS_URL");
    sku = Standard_C1;
  }
}
```

**Without `replace`:** Assignments merge into the inherited block.
**With `replace`:** The entire named block is replaced.

This replaces YAML's `_replace: true` marker with a first-class keyword.

---

## Field Assignment

### Block Syntax

```dcfg
resilience {
  retry {
    maxAttempts = 5;
    initialDelay = 2s;
    maxDelay = 30s;
  }
}
```

### Path Syntax

```dcfg
resilience.retry.maxAttempts = 5;
resilience.retry.initialDelay = 2s;
resilience.retry.maxDelay = 30s;
```

Both forms compile to the same canonical dictionary.

---

## Environment Variables

Use `env(...)` for environment variable references:

```dcfg
host = env("POSTGRES_HOST");
accessKey = env("MINIO_ACCESS_KEY", default: "minioadmin");
```

**String interpolation in env names:**

```dcfg
host = env("ECOMMERCE_${profile.env}_POSTGRES_HOST");
url = env("ECOMMERCE_${profile.env}_REDIS_URL");
bucket = "ecommerce-${profile.resource}-order-data";
```

**For `profile production as "prod"` with `alias env = "PROD"` and `alias resource = "prod"`:**

```yaml
# Canonical output
host: ${ECOMMERCE_PROD_POSTGRES_HOST}
url: ${ECOMMERCE_PROD_REDIS_URL}
bucket: ecommerce-prod-order-data
```

**Canonical form:** The compiler preserves environment references as `${VAR_NAME}` or `${VAR_NAME:default}` strings consumed by the application runtime.

---

## Interpolation Variables

| Variable | Meaning |
|----------|---------|
| `${profile}` | Active profile name (e.g., `production`) |
| `${profile.name}` | Same as `${profile}` |
| `${profile.short}` | Default short alias from `as` (e.g., `prod`) |
| `${profile.env}` | Named alias `env` |
| `${profile.resource}` | Named alias `resource` |
| `${profile.<custom>}` | Any named alias declared in the profile |

**Error handling:** Using a missing alias is an error at compile time.

---

## Deployment Target

ConfigDSL follows the deployment target contract. System configs declare deployment settings per profile:

```dcfg
config system ecommerce.System {
  profile development as "dev" {
    alias env = "DEV";
    alias resource = "dev";
    language = python;

    deployment {
      runtime = docker-compose;
      provider = local;
    }
  }

  profile production as "prod" {
    alias env = "PROD";
    alias resource = "prod";
    language = python;

    deployment {
      runtime = azure-app-service;
      provider = azure;
      registry = acr;
    }
  }
}
```

**Flavor terminology:** ConfigDSL uses `flavor` for both service runtime flavor and infrastructure provisioning flavor. Context determines the meaning:

```dcfg
flavor = container-apps;  // service runtime flavor (system-level)

rdbms orderDb {
  flavor = flexible-server;  // infrastructure provisioning flavor
}

cache orderCache {
  flavor = cache-for-redis;  // infrastructure provisioning flavor
}
```

**Output boundary mapping:** The `.dcfg` compiler maps DSL `flavor` to canonical `platform` at the output boundary where existing config models still use `platform`. This mapping is transitional and does not change the authoring contract.

---

## RDBMS Migration Identity

Every `rdbms` block must declare an `id` field containing a UUID string. This UUID is the canonical migration identity used by the incremental RDBMS migration system to track schema snapshots and revision history.

**Inline example:**

```dcfg
rdbms orderDb {
  id = "8b7d0a8e-4b97-46df-8f3a-40df4f65be54";
  engine = postgres;
  flavor = container;
  database = "ecommerce_orders";
  schema = "orders";
}
```

**Template example:**

```dcfg
template postgresContainer(id, database, schema) {
  id = id;
  engine = postgres;
  flavor = container;
  database = database;
  schema = schema;
}

rdbms orderDb from postgresContainer(
  id: "8b7d0a8e-4b97-46df-8f3a-40df4f65be54",
  database: ecommerce_orders,
  schema: orders
);
```

**Validation rules:**

- Every resolved `rdbms` block must have `id`; generation fails if missing
- `id` must be a valid UUID string
- Within each resolved profile, IDs must be globally unique across all service-owned and shared-owned RDBMS blocks
- When the same owner-qualified RDBMS block appears in multiple profiles, it must resolve to the same `id` in every profile
- The `id` survives profile, engine, platform, owner, and block-alias changes — it is the durable logical storage contract identity
- Changing an `id` for a block that has existing migration state is a generation error

The `id` is not affected by changes to resolved database engine, profile, platform, output directory, connection host, database name, schema name, owner container, or block alias. Migration state under `{app_dir}/.datrix/rdbms-migrations/{rdbms_id}/` is keyed solely by this UUID.

Use `datrix migrations init-rdbms-ids --app <app-dir>` to add missing `id` fields to existing RDBMS blocks. See [migrations CLI commands](../../../datrix-cli/docs/commands/migrations.md) and [RDBMS migration decisions](../architecture/rdbms-migration-decisions.md).

---

## Drift Policy Selector

The drift policy selector controls whether database drift detection and reconciliation is required in an environment. It is **additive, gated, and defaults to off** — a project that does not declare it produces byte-identical generation output.

**Declaration:**

```dcfg
profile production as "prod" extends base {
  driftPolicy {
    mode = "guard";
  }
}

profile staging as "stg" extends base {
  driftPolicy {
    mode = "reconcile";
  }
}
```

**Modes:**

| Mode | Behavior | Use Case |
|------|----------|----------|
| `off` (default) | No drift workflow required. Drift detection and reconciliation commands remain available for manual use. | Development and non-critical environments. |
| `guard` | Production guard mode. Drift detection is required before deploying; reconciliation verbs refuse execution. Use this to ensure live database state matches expected schema. | Production environments. |
| `reconcile` | Pre-production mode. Reconciliation verbs are available. Allows auto-reconciliation via `datrix migrations reconcile --adopt` or `--to-desired`. | Staging, QA, and development environments. |

**Important Notes:**

- **Additive and gated:** The absence of `driftPolicy` (or an unspecified `mode`) defaults to `off`. When `off`, no workflow machinery is required; existing applications continue unchanged.
- **No database connectivity:** The drift policy selector never grants Datrix database connectivity. It controls only whether exported live snapshots are required for the guard/reconcile workflow. Credentials, connection strings, and hostnames remain in the deployment environment.
- **Requires live snapshot export:** When `guard` or `reconcile` is active, the environment must export a live database snapshot (via an environment-side exporter or CLI tool) before drift detection or reconciliation can run.

**See also:** [Decision D29 — Drift as a Production Guard and Pre-Prod Reconcile Path](../architecture/rdbms-migration-decisions.md#d29-drift-is-a-production-guard-and-a-pre-prod-reconcile-path) and [Database Drift Reconciliation Guide](../../guide/database-drift-reconciliation.md).

---

## Logical Secrets (`secrets` block)

The `secrets` block declares a **platform-agnostic logical-secret table** for a service. Each entry is a non-secret *handle* — a stable name that feature configs reference instead of carrying a credential value inline. Think of a logical secret as a foreign key into the deployment secret-binding layer: it names *which* secret is needed, never *what the secret is*.

**Location:** Service config (`config service`). The `secrets` block is a service-level section, a sibling of `integrations`. It may appear in `base` or any `profile`.

**Syntax:**

```dcfg
secrets {
  secret search_basic_auth_username {
    required = true;                          // bool; defaults to true (fail-closed)
    purpose = "search-basic-auth-username";   // non-secret description only
  }
  secret search_basic_auth_password { required = true; purpose = "search-basic-auth-password"; }
  secret stripe_webhook_secret { required = true; purpose = "webhook-signature-secret"; }
}
```

**Secret fields:**

- `required` — Boolean. Defaults to `true` (fail-closed). When `true`, the deployment must bind this handle or the service fails to start; the generator never substitutes an empty or default value.
- `purpose` — Non-secret, human-readable description of what the handle is for. It is metadata only.

**Handle invariants:**

- A logical secret is a **handle, not a value**. It MUST NEVER carry the secret value, be derived from the value, or act as a fallback for a missing value.
- The table is service-level; feature configs (e.g. `integrations { search { … } }`) reference these handles by name only.
- Every reference to a handle must resolve to a `secret` declared in this table (cross-reference validated at generation time).

**Backend selection is out of application config:**

Logical secrets carry **no backend or naming policy**. Which secret store backs a handle (env, vault, AWS Secrets Manager, Azure Key Vault, Docker secret, …) and how handle names map to backend secret names are decided by **deployment/platform configuration**, not by application `.dcfg`. As a consequence:

- The earlier config-store **backend selector** form — `secrets { provider = "env" | "vault" | "keyvault" | "secrets-manager"; path = …; }` — is **removed** from application `.dcfg`. Provider strings (`env`, `vault`, `aws-secrets-manager`, `azure-key-vault`, `docker-secret`, `secrets-manager`, `keyvault`) no longer appear in application config.
- A legacy inline `secretRef.provider` string inside a new logical-secret config is a **hard error**, not a silent skip. The author must declare a logical handle and let deployment policy choose the backend.

---

## Search Integration (`integrations { search }`)

A `search` integration declares a service's connection to a search engine. Credentials are referenced through **logical secret handles** (see [Logical Secrets](#logical-secrets-secrets-block)) — never as raw literals.

**Location:** Service config integrations block (`config service`).

**Example:**

```dcfg
integrations {
  search {
    provider = "opensearch";
    authRequired = true;
    credentials {
      usernameCredentialRef = "search_basic_auth_username";
      passwordCredentialRef = "search_basic_auth_password";
    }
  }
}
```

**Schema fields:**

- `provider` — Required: search engine provider (e.g. `"opensearch"`, `"elasticsearch"`).
- `authRequired` — Boolean. **Fail-closed: defaults to `true`.** `authRequired = false` is **rejected in all profiles** (hard generation error). There is no unauthenticated branch — generated search clients always resolve credentials and fail loud if a required handle is missing or empty.
- `credentials.usernameCredentialRef` / `credentials.passwordCredentialRef` — Logical secret handles. Each MUST resolve to a `secret` declared in the service `secrets` table (cross-reference validated). Raw username/password literals are **rejected**.

**Pairing with the `secrets` table:**

```dcfg
config service ecommerce.OrderService {
  base {
    secrets {
      secret search_basic_auth_username { required = true; purpose = "search-basic-auth-username"; }
      secret search_basic_auth_password { required = true; purpose = "search-basic-auth-password"; }
    }

    integrations {
      search {
        provider = "opensearch";
        authRequired = true;
        credentials {
          usernameCredentialRef = "search_basic_auth_username";
          passwordCredentialRef = "search_basic_auth_password";
        }
      }
    }
  }
}
```

**Validation rules:**

- `authRequired = false` is a generation error in **every** profile.
- A `usernameCredentialRef` or `passwordCredentialRef` that names an **undeclared** logical handle is a generation error.
- Raw credential literals in `usernameCredentialRef` / `passwordCredentialRef` are rejected.

---

## Syntax Rules

### General

- Files use UTF-8 encoding and `.dcfg` extension
- Statements require semicolons (`;`)
- Block declarations end with `}` and do NOT require trailing semicolons
- Comments use `//` (single-line) or `/* */` (multi-line)

### Identifiers and Values

- Identifiers follow Datrix identifier rules (alphanumeric + underscore, start with letter)
- Strings use double quotes: `"value"`
- Durations support units: `2s`, `500ms`, `5m`, `1h`
- Lists: `[a, b, c]`
- Inline objects: `{ key: value, key2: value2 }`

### Keywords

- `config` — Declare config kind and owner
- `import` — Import templates from another file
- `template` — Define reusable config fragment
- `base` — Inheritance-only profile block
- `profile` — Concrete selectable profile
- `as` — Define short profile alias
- `extends` — Inherit from another profile
- `alias` — Define named interpolation alias
- `replace` — Replace entire block instead of merging
- `from` — Instantiate template
- `perProfile` — Profile-indexed default value
- `env` — Environment variable reference

### Resolution Order

1. Parse `.dcfg` file
2. Resolve imports
3. Register templates and validate parameter lists
4. Build concrete profile inheritance chain
5. Expand templates in inheritance order
6. Resolve `perProfile` expressions for active profile
7. Apply merges and replacements
8. Resolve string interpolation
9. Convert DSL aliases to canonical field names
10. Emit canonical dictionary
11. Validate with Pydantic config models

### Error Handling

**The resolver fails fast with actionable errors for:**
- Unknown profile names
- Unknown template names
- Unknown import paths
- Circular imports
- Missing template parameters
- Missing `perProfile` keys (without `default`)
- Missing interpolation aliases
- Invalid syntax

**The resolver NEVER:**
- Guesses alternate profiles
- Falls back to default values silently
- Ignores unknown references

**Logical-secret error messages:**

Undeclared logical secret handle:

```
ConfigValidationError: Credential ref 'search_basic_auth_username' in integrations.search.credentials
does not resolve to a declared secret. Declare it in the service 'secrets' block, e.g.
secret search_basic_auth_username { required = true; purpose = "search-basic-auth-username"; }.
```

Unauthenticated search rejected:

```
ConfigValidationError: integrations.search.authRequired = false is not allowed in any profile.
Search auth is fail-closed; declare credential handles in the 'secrets' block and reference them
via usernameCredentialRef/passwordCredentialRef.
```

Legacy secret backend selector rejected:

```
ConfigValidationError: 'secrets { provider = … }' / inline 'secretRef.provider' is not valid in
application config. Declare logical secret handles in the 'secrets' block; backend selection and
naming live in the deployment target policy.
```

---

## Complete Example

```dcfg
config service ecommerce.OrderService {
  import "config/templates/postgres.dcfg";
  import "config/templates/redis.dcfg";
  import "config/templates/resilience.dcfg";

  template paymentApi(baseUrl, timeout = 60s) {
    baseUrl = baseUrl;

    rateLimit {
      requestsPerSecond = 2.0;
      burstAllowed = 5;
    }

    retry {
      maxAttempts = 3;
      initialDelay = 1s;
      maxDelay = 10s;
      retryOn = [429, 503, 504];
    }

    timeout {
      connect = 10s;
      read = timeout;
    }
  }

  base {
    port = 8001;
    flavor = compose;
    replicas = 1;

    healthCheck {
      path = "/health";
      retries = 3;
      interval = 10s;
      timeout = 5s;
    }

    resources {
      cpu = "1000m";
      memory = "1Gi";
    }

    rdbms orderDb from postgresContainer(
      database: ecommerce_orders,
      schema: orders
    );

    cache orderCache from redisContainer();

    registration {
      name = "order-service";
      host = "localhost";
      port = 3001;
      tags = ["api", "orders", "ecommerce"];
    }

    resilience from standardResilience();

    integrations {
      paymentService from paymentApi("http://localhost:8002");
    }
  }

  profile development as "dev" extends base {
    alias env = "DEV";
    alias resource = "dev";

    rdbms orderDb {
      poolSize = 10;
    }
  }

  profile production as "prod" extends base {
    alias env = "PROD";
    alias resource = "prod";

    flavor = container-apps;
    replicas = 3;

    resources {
      cpu = "2000m";
      memory = "4Gi";
    }

    scaling {
      replicas {
        min = 2;
        max = 8;
      }
      triggers = [{ metric: cpu, target: "70%" }];
    }

    replace rdbms orderDb from postgresAzureFlexibleServer(
      database: ecommerce_orders,
      schema: orders,
      host: env("ECOMMERCE_${profile.env}_POSTGRES_HOST")
    );

    replace cache orderCache from azureRedis(
      url: env("ECOMMERCE_${profile.env}_REDIS_URL")
    );

    resilience.retry {
      maxAttempts = 5;
      initialDelay = 2s;
      maxDelay = 30s;
    }

    resilience.bulkhead {
      enabled = true;
      maxConcurrent = 100;
      maxQueue = 200;
    }
  }
}
```

**Canonical output for `production` profile:**

```yaml
port: 8001
platform: container-apps
replicas: 3
resources:
  cpu: 2000m
  memory: 4Gi
scaling:
  replicas:
    min: 2
    max: 8
  triggers:
    - metric: cpu
      target: "70%"
rdbms:
  orderDb:
    engine: postgres
    platform: flexible-server
    host: ${ECOMMERCE_PROD_POSTGRES_HOST}
    database: ecommerce_orders
    schema: orders
    poolSize: 40
    ssl: true
    asyncDriver: postgresql+asyncpg
    syncDriver: postgresql+psycopg2
    healthCheckSql: SELECT 1
cache:
  orderCache:
    url: ${ECOMMERCE_PROD_REDIS_URL}
healthCheck:
  path: /health
  retries: 3
  interval: 10s
  timeout: 5s
registration:
  name: order-service
  host: localhost
  port: 3001
  tags:
    - api
    - orders
    - ecommerce
resilience:
  retry:
    maxAttempts: 5
    initialDelay: 2s
    maxDelay: 30s
  bulkhead:
    enabled: true
    maxConcurrent: 100
    maxQueue: 200
integrations:
  paymentService:
    baseUrl: http://localhost:8002
    rateLimit:
      requestsPerSecond: 2.0
      burstAllowed: 5
    retry:
      maxAttempts: 3
      initialDelay: 1s
      maxDelay: 10s
      retryOn: [429, 503, 504]
    timeout:
      connect: 10s
      read: 60s
```

---

## `dependencyPolicy` Block {#dependencypolicy-block}

The `dependencyPolicy` block is nested inside a `resilience { }` block and declares the explicit failure-behavior policy for every dependency that requires one. The generator **never** synthesizes a policy value — every `service` dependency with inter-service calls must be covered or generation fails with `RESILIENCE_POLICY_REQUIRED`.

### Structure

```dcfg
resilience {
  dependencyPolicy {
    defaults {
      service from standardServicePolicy();   // baseline for all service deps
      cache {                                  // baseline for all cache deps
        availability = "required";
        health = "ready";
        operations {
          read   { onFailure = "fallback"; fallback = "sourceOfTruth"; }
          write  { onFailure = "raise"; }
          delete { onFailure = "warn"; }
        }
      }
    }
    service InventoryService {               // per-service override
      timeout = 2000;
    }
    cache sessionCache {                     // per-cache override
      availability = "optional";
      health = "degraded";
    }
  }
}
```

### `defaults` Section

Declares per-kind application-level baselines. Each kind entry is inherited by every dependency of that kind unless a named override exists.

- `service from <template>()` — opt into a named template for the `service` baseline.
- Named kind blocks (`cache { … }`, `rdbms { … }`, etc.) — inline baseline for that kind.

### Per-Dependency Overrides

Named blocks (`service <Name> { … }` / `cache <Name> { … }`) override the baseline for exactly one dependency. The name must be the **canonical resolved dependency name**:
- `service` kind → canonical service model name (e.g., `OrderService`)
- Other kinds → declared name in the DSL block (e.g., `sessionCache`, `orderDb`)

Non-canonical names are a config error, never silently aliased.

### Per-Dependency Fields

| Field | Values | Inherit behavior |
|---|---|---|
| `availability` | `required` / `optional` / `degraded` | `None` → inherit baseline |
| `health` | `live` / `ready` / `degraded` / `ignored` | `None` → inherit baseline (no implicit `ready`) |
| `readyOnDegraded` | `true` (default) / `false` | `false` makes degraded a readiness blocker |
| `operations` | Per-operation `onFailure` blocks | Only specified operations overridden |

After merging, the resolved `availability` and `health` must both be non-`None`. If either is missing, generation fails with `RESILIENCE_POLICY_REQUIRED`.

### Operations Block

Each operation entry specifies failure behavior for one database/cache/service operation:

```dcfg
operations {
  read   { onFailure = "fallback"; fallback = "sourceOfTruth"; }
  write  { onFailure = "degrade"; }
  delete { onFailure = "raise"; }
  counterIncrement { onFailure = "deny"; }
}
```

`onFailure` values: `raise` / `deny` / `degrade` / `warn` / `fallback` / `ignore`. The `fallback` field (when `onFailure = "fallback"`) names the fallback source kind (e.g., `"sourceOfTruth"`).

### Validation Diagnostics

| Diagnostic | Cause |
|---|---|
| `RESILIENCE_POLICY_REQUIRED` | `service` dependency with calls has no resolved `availability` or `health` |
| `RESILIENCE_POLICY_INVALID` | Non-canonical dependency name; unsupported operation for kind |
| `RESILIENCE_RATE_LIMIT_COUNTER` | Rate-limit counter set to `degrade`/`warn`/`ignore` without `unsafeAllowFailOpen = true` |
| `RESILIENCE_AUTH_CACHE_DELETE` | Authorization/session cache `delete` set to `warn` without proof stale cache cannot authorize |

### No Grammar Change

The existing named-block parser already accepts `cache <name> { … }` / `service <name> { … }`. No `.dcfg` grammar change is needed to use `dependencyPolicy`.

---

## Diagnostic Output (Planned)

The ConfigDSL compiler does not write YAML config files during normal generation. A planned diagnostic command will print the resolved canonical dictionary for review, testing, and migration verification:

```bash
datrix config resolve config/order-service.dcfg --profile production --format json
```

This is useful for inspecting the resolved config without running the full generation pipeline. It does not reintroduce YAML as an authoring or runtime config format.

---

## See Also

- **[Configuration System Architecture](../../../datrix-common/docs/architecture/config-system.md)** — Config taxonomy, validation, pipeline integration
- **[ConfigDSL Reference (Canonical — datrix-common)](../../../datrix-common/docs/config-dsl-reference.md)** — Complete reference including [Author Migration](../../../datrix-common/docs/config-dsl-reference.md#author-migration-logical-secrets-and-deployment-profile-secret-backend-policy) (logical secrets, deployment-profile policy, breaking changes)
- **[ConfigDSL Reference — Identity Provider Config Keys](../../../datrix-common/docs/config-dsl-reference.md#identity-provider-config-keys-localidentity-profileprojection-profilestore)** — `localIdentity`, `profileProjection`, and `profileStore` config-key reference for provider `.dcfg` files
- **[Identity Subsystem Architecture](../../../datrix-common/docs/architecture/identity.md#local-identity-resolution-localidentity)** — Architecture rationale for `localIdentity` resolution modes and opt-in profile projection
- **[Secret Backend Policy](../../../datrix-common/docs/secret-backend-policy.md)** — Deployment-level secret backend selection and name rendering
- **[Decision 14: Runtime Configuration & Secrets — Zero-Environment Architecture](./architecture-overview.md#decision-14-runtime-configuration--secrets--zero-environment-architecture)** — Zero-environment design and single planning pipeline
