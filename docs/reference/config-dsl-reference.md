# Config DSL Reference

**Version:** 1.0
**Last Updated:** 2026-05-19

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
      runtime = kubernetes;
      provider = azure;
      target = aks;
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

## Diagnostic Output (Planned)

The ConfigDSL compiler does not write YAML config files during normal generation. A planned diagnostic command will print the resolved canonical dictionary for review, testing, and migration verification:

```bash
datrix config resolve config/order-service.dcfg --profile production --format json
```

This is useful for inspecting the resolved config without running the full generation pipeline. It does not reintroduce YAML as an authoring or runtime config format.

---

## See Also

- **[Configuration System Architecture](../../../datrix-common/docs/architecture/config-system.md)** — Config taxonomy, validation, pipeline integration
