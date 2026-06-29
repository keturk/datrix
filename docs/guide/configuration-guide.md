# Configuration Guide

**Complete reference for Datrix configuration files**

This guide covers Datrix `.dcfg` ConfigDSL files, their structure, options, and how to use profiles for environment-specific settings.

---

## Table of Contents

1. [Eliminate-Hardcoded-Defaults Program (Waves A–M)](#eliminate-hardcoded-defaults-program-waves-am)
2. [Configuration Overview](#configuration-overview)
3. [Configuration Hierarchy](#configuration-hierarchy)
4. [Profiles and Environments](#profiles-and-environments)
5. [System Configuration](#system-configuration)
6. [Service Configuration](#service-configuration)
7. [Service dependencies (`dependencies` section)](#service-dependencies-dependencies-section)
8. [Datasources Configuration](#datasources-configuration)
9. [Service Registration](#service-registration)
10. [Resilience Configuration](#resilience-configuration)
11. [Gateway Configuration](#gateway-configuration)
12. [Registry Configuration](#registry-configuration)
13. [Observability Configuration](#observability-configuration)
14. [Storage Configuration](#storage-configuration)
15. [Jobs Configuration](#jobs-configuration)
16. [Queue Configuration](#queue-configuration)
17. [Integrations Configuration](#integrations-configuration)
18. [Extern Service Configuration](#extern-service-configuration)
19. [Platform-Specific Configuration](#platform-specific-configuration)
20. [Seed Configuration](#seed-configuration)
21. [Secrets Management](#secrets-management)
22. [Runtime Config Store](#runtime-config-store)

---

## Eliminate-Hardcoded-Defaults Program (Waves A–M)

Datrix implements a **no-hardcoded-app-defaults principle**: every app-specific sizing, cost, operational, or security value is config-authored and **fails loud** at generation time (not silently at runtime). This section covers the entire program surface introduced across Waves D–L.

### The Principle

**No value may be:**
- Baked into generator code or templates
- Supplied via silent fallback (`x or DEFAULT`, `?? N`, `env || 'localhost'`)
- Hardcoded into deployment config

**Every such value must be:**
- Explicitly authored in the application/system config
- Fail-loud when absent: generation raises `GenerationError` or runtime startup errors loudly

**Exceptions (kept as documented framework constants, not config):**
- Standard protocol ports (postgres 5432, redis 6379, Kafka 9093, etc.) — as named constants
- AWS Fargate/App Runner CPU/memory tier tables — AWS API constraints
- Secure hardening defaults (TLS ≥1.2, HTTPS-only) — exposing these as tunable invites posture weakening

### Configuration Homes (Wave D–L Inventory)

Each new surface lives in one of two config locations, chosen by ownership boundary:

| Surface | Home | Wave | Profile | ConfigDSL Block |
|---------|------|------|---------|-----------------|
| **Per-Deployment Infrastructure** |  |  |  |  |
| AWS CloudWatch alarms (RDS/ElastiCache/DynamoDB thresholds) | `platforms.aws.alarms` | C | system | `alarms { rdsCpuPercent = 80; … }` |
| AWS Lambda sizing (consumer memory/timeout/batch size) | `platforms.aws.lambda` | C | system | `lambda { consumerMemoryMb = 512; … }` |
| AWS ECS/App Runner healthcheck timing | `platforms.aws.ecsHealthCheck` | E | system | `ecsHealthCheck { interval = "30s"; … }` |
| AWS ECS autoscaling (CPU target, scale cooldowns) | `platforms.aws.ecsScaling` | E | system | `ecsScaling { cpuTarget = 70; … }` |
| AWS Lambda trigger settings | `platforms.aws.consumerLambdaTriggers` | E | system | `consumerLambdaTriggers { maxReceiveCount = 3; … }` |
| AWS migration task sizing (Fargate CPU/memory) | `platforms.aws.migrationTask` | C | system | `migrationTask { fargateCpu = 256; … }` |
| AWS scheduled task config (retry attempts, max age, DLQ retention) | `platforms.aws.scheduledTask` | C | system | `scheduledTask { retryAttempts = 2; … }` |
| AWS AppConfig rollout (growth/bake/replicate) | `platforms.aws.appConfig` | E | system | `appConfig { rollout { growth = 10; … } }` |
| AWS CloudFront (connection retries/timeout) | `platforms.aws.cloudFront` | E | system | `cloudFront { connectionRetries = 3; … }` |
| AWS S3 Lifecycle (transition days) | `platforms.aws.sorLifecycle` | C | system | `sorLifecycle { transitionDays = 90; }` |
| Azure App Insights (sampling %, retention days) | `platforms.azure.appInsights` | F | system | `appInsights { samplingPercent = 100; … }` |
| Azure Event Hubs (retention days) | `platforms.azure.eventHubs` | F | system | `eventHubs { retentionDays = 7; }` |
| Azure migration job sizing (CPU, memory) | `platforms.azure.migrationJob` | F | system | `migrationJob { cpu = "0.25"; … }` |
| Azure replica job (timeout, retry limit) | `platforms.azure.replicaJob` | F | system | `replicaJob { timeoutSeconds = 300; … }` |
| Azure database defaults (HA mode, backup retention, geo-redundancy) | `platforms.azure.databaseDefaults` | G | system | `databaseDefaults { haMode = "active"; … }` |
| Azure resource sizing (App Service plan SKU, Function SKU, pools) | `platforms.azure.resources` | G | system | Nested per-resource blocks |
| Docker infra healthcheck timing (all engines) | `platforms.docker.infra.defaultHealthcheck` | D | system | `infra { defaultHealthcheck { interval = "15s"; … } }` |
| Docker PgBouncer connection pooling | `platforms.docker.infra.pgbouncer` | D | system | `infra { pgbouncer { maxClientConn = 200; … } }` |
| Docker Elasticsearch JVM heap | `platforms.docker.infra.elasticsearch` | D | system | `infra { elasticsearch { heap = "512m"; } }` |
| Docker init script retries | `platforms.docker.infra.initScript` | D | system | `infra { initScript { maxRetries = 30; … } }` |
| **Per-Service Operational** |  |  |  |  |
| HTTP security (CORS, allowed hosts) | `httpSecurity` | K | service | `httpSecurity { allowedHosts = […]; corsOrigins = […]; … }` |
| Secrets store layout (Vault/AWS/Azure paths and prefixes) | `secretsStore` | K | service | `secretsStore { vaultMountPoint = "secret"; … }` |
| Cache operations (TTL, pool size, key limits) | `cache` | H | service | `cache { ttlSeconds = 300; keyMaxLength = 100; … }` |
| Queue operations (SQS/Service Bus poll settings) | `queue` | H | service | `queue { sqsPollWaitSeconds = 20; … }` |
| Kafka operations (poll timeouts, max-poll-interval) | `kafka` | H | service | `kafka { consumerPollTimeoutMs = 1000; … }` |
| RabbitMQ operations (prefetch count) | `messaging` | H | service | `messaging { rabbitmqPrefetchCount = 10; }` |
| Download operations (timeout, chunk size, retries) | `download` | H | service | `download { timeoutSeconds = 300; chunkSizeBytes = 65536; … }` |
| Remote config client (Consul/AppConfig timeouts) | `remoteConfig` | H | service | `remoteConfig { consulTimeoutSeconds = 5.0; … }` |
| Rate limiting (window in seconds) | `rateLimit` | H | service | `rateLimit { windowSeconds = 60; }` |
| Microservice client (timeout, circuit-breaker, bulkhead) | `microserviceClient` | H | service | `microserviceClient { timeoutSeconds = 300; cbFailMax = 5; … }` |
| Retry budget (window, ratio) | `retryBudget` | H | service | `retryBudget { window = 100; ratio = 0.1; }` |
| Transactional outbox (flush batch size) | `outbox` | H | service | `outbox { flushBatchSize = 500; }` |
| Service credential token skew | `serviceCredential` | H | service | `serviceCredential { tokenExpirySkewSeconds = 30; }` |
| Payment test mode | `payment.testMode` | K | service | `payment { testMode = true; }` |
| Job timeouts (replay, compaction, concurrency) | `jobs` | H | service | `jobs { replayTimeoutSeconds = 3600; … }` |
| **Per-Block Infrastructure Sizing** |  |  |  |  |
| RDBMS connection pooling | `RdbmsConfig.poolSize` | H | block | `rdbms db { poolSize = 20; maxOverflow = 10; }` |
| RDBMS SSL | `RdbmsConfig.ssl` | K | block | `rdbms db { ssl = true; }` |
| RDBMS port (for pooled groups) | `ServerGroupSpec.port` | L | block | Added to pooled server-group sizing |
| Cache pool sizing | `SearchConfig.replicasCount`, `SearchConfig.partitions` | G | block | `search idx { replicasCount = 3; partitions = 1; }` |
| NoSQL sizing | `NosqlConfig.instance_count`, `NosqlConfig.engine_version` | L | block | `nosql catalog { instanceCount = 1; engineVersion = "5.0.0"; }` |
| Resilience timeout defaults | `ResilienceProfileConfig.defaults.timeout` | H | service | `resilience { defaults { timeout = "10s"; } }` |
| Resilience circuit-breaker timeout | `CircuitBreakerConfig.timeout` | L | service | `resilience { defaults { circuitBreaker { timeout = "30s"; } } }` |

### `.dcfg` Authoring Syntax

All new config surfaces use the ConfigDSL generic block syntax. Here are representative examples:

#### System Config (deployment-wide)

```dcfg
config system ecommerce.System {
  profile production as "prod" {
    language = python;
    deployment { runtime = ecs-fargate; provider = aws; }

    platforms {
      aws {
        # Wave C: AWS alarms
        alarms {
          rdsCpuPercent = 80;
          elasticacheCpuPercent = 75;
          sqsDepth = 1000;
        }
        # Wave C: Lambda sizing
        lambda {
          consumerMemoryMb = 512;
          consumerTimeoutSeconds = 300;
        }
        # Wave E: ECS autoscaling
        ecsScaling {
          cpuTarget = 70;
          scaleOutCooldown = 60;
          scaleInCooldown = 60;
        }
      }

      azure {
        # Wave F: App Insights
        appInsights {
          samplingPercent = 100.0;
          retentionDays = 30;
        }
        # Wave G: Database defaults
        databaseDefaults {
          haMode = "active";
          backupRetentionDays = 7;
          geoRedundant = true;
        }
      }

      docker {
        # Wave D: Infra healthchecks
        infra {
          defaultHealthcheck {
            interval = "30s";
            timeout = "5s";
            retries = 3;
          }
          pgbouncer {
            maxClientConn = 200;
            defaultPoolSize = 20;
          }
          elasticsearch {
            heap = "512m";
          }
        }
      }
    }
  }
}
```

#### Service Config (per-service)

```dcfg
config service ecommerce.OrderService {
  profile production as "prod" {
    port = 8001;

    # Wave K: HTTP security (required for REST APIs)
    httpSecurity {
      allowedHosts = ["api.shop.example.com"];
      corsOrigins = ["https://shop.example.com"];
      corsMethods = ["GET", "POST", "PUT", "DELETE"];
      corsHeaders = ["Content-Type", "Authorization"];
    }

    # Wave K: Secrets store layout
    secretsStore {
      vaultMountPoint = "secret";
      vaultPath = "data/ecommerce/order-service/prod";
    }

    # Wave H: Cache operations
    cache {
      ttlSeconds = 300;
      keyMaxLength = 100;
      redisPoolSize = 10;
    }

    # Wave H: Queue operations
    queue {
      sqsPollWaitSeconds = 20;
      sqsMaxMessagesPerPoll = 10;
    }

    # Wave H: Microservice client resilience
    microserviceClient {
      timeoutSeconds = 300;
      circuitBreakerFailMax = 5;
      circuitBreakerResetSeconds = 30;
      bulkheadMaxConcurrent = 10;
    }

    # Wave K: Payment integration
    payment {
      processor = "stripe";
      testMode = false;
    }
  }
}
```

#### Datasource Blocks (RDBMS, NoSQL, Search)

```dcfg
config service ecommerce.InventoryService {
  profile production as "prod" {
    rdbms inventoryDb {
      engine = postgres;
      platform = rds;
      # Wave K: SSL requirement (fail-loud when absent for production)
      ssl = true;
      # Wave H: Connection pool sizing (fail-loud when absent for pooled groups)
      poolSize = 20;
      maxOverflow = 10;
    }

    nosql catalog {
      engine = mongodb;
      platform = documentdb;
      # Wave L: Sizing (fail-loud when absent)
      instanceCount = 1;
      engineVersion = "5.0.0";
    }

    search index {
      engine = elasticsearch;
      platform = opensearch;
      # Wave G: Search index sizing (fail-loud when absent)
      replicasCount = 1;
      partitions = 1;
    }
  }
}
```

### Secure-by-Authoring

**The permissive test backfill was removed.** 

Wave M removed the helper-function backfill of `httpSecurity` and `secretsStore` defaults that allowed examples and tests to generate without real config values. All `.dcfg` files (examples, tests, and production) must now author **proper, non-wildcard values** at generation time. This prevents:
- Examples silently deploying with `["*"]` CORS origins
- Test fixtures masking real config requirements
- Accidental permissive values reaching production

**Pattern for secure authoring:**

```dcfg
# ✅ Correct: explicit non-wildcard values
httpSecurity {
  allowedHosts = ["localhost", "dev.internal"];
  corsOrigins = ["http://localhost:3000"];
  corsMethods = ["GET", "POST"];
  corsHeaders = ["Content-Type"];
}

# ❌ Wrong: permissive wildcards
httpSecurity {
  allowedHosts = ["*"];
  corsOrigins = ["*"];
  corsMethods = ["*"];
  corsHeaders = ["*"];
}
```

### Language-Specific and Platform-Specific Docs

Each generator package publishes detailed docs for its config surfaces:

- **Python:** [Service Configuration — Security Surfaces and Operational Blocks](../../../datrix-codegen-python/docs/service-config-operational-blocks.md) — detailed Wave H/K surface reference and examples
- **AWS:** [Wave L Sizing Configuration](../../../datrix-codegen-aws/docs/wave-l-sizing-configuration.md) — RDS/OpenSearch/DocumentDB/ElastiCache instance and SKU config
- **Azure:** [Platforms Azure Configuration](../../../datrix-codegen-azure/docs/platforms-azure-config.md) — database defaults, alarms, resource sizing

**Program status:** Complete (Waves A–M, Phases 84–93). All hardcoded app-specific sizing, cost, operational, and security defaults have been moved to config-authored, fail-loud surfaces. See the language- and platform-specific docs linked above for per-wave field references.

---

## Configuration Overview

Datrix uses a **hierarchical configuration system** with **profile-based environments**. Configuration is split between:

1. **`.dtrx` files** — Behavioral definitions (entities, APIs, services)
2. **ConfigDSL (`.dcfg`) files** — Environmental configuration (databases, credentials, deployment)

### Key Principles

✅ **Typed and Validated** — All config is validated against Pydantic models
✅ **Fail-Fast** — Missing or invalid config causes errors at generation time
✅ **Profile-Based** — Different settings per environment (test, dev, prod)
✅ **No Silent Fallbacks** — Explicit configuration required
✅ **Single Source of Truth** — Each value defined in exactly one place

---

## Configuration Hierarchy

Configuration flows through **four tiers**:

```
Tier 1: Project Settings (assembled from generator defaults)
├── Python version, Node.js version
├── Tool settings (ruff, mypy, pytest)
├── Docker settings
├── Dependency version catalog
└── Infrastructure image catalog

Tier 2: System-Level Config (profile-based ConfigDSL)
├── Language and deployment target
├── API Gateway
├── Service Registry
├── Observability
└── System-wide deployment settings

Tier 3: Service-Level Config (profile-based ConfigDSL)
├── Service deployment config
├── Resilience patterns
├── Service metadata
├── Integrations
└── Multi-tenancy settings

Tier 4: Block-Level Config (profile-based ConfigDSL)
├── RDBMS (datasources.dcfg) — per **service** or **`shared`** block
├── Cache (datasources.dcfg)
├── PubSub (datasources.dcfg)
├── NoSQL (datasources.dcfg)
├── Storage (storage.dcfg)
├── Jobs (jobs.dcfg)
└── Queues (queue.dcfg — separate file, not a datasource)
```

**`shared` blocks** use the **same** Tier 4 ConfigDSL shapes as services; paths in `.dtrx` are resolved relative to the project root during **`resolve_infrastructure_configs`** just like service-owned blocks.

---

## Profiles and Environments

Profiles allow environment-specific configuration in a single file.

### Profile Structure with `base:` Inheritance

To avoid repeating common values across profiles, use a `base:` section. Profiles without explicit sections inherit from `base:`.

```dcfg
# config/system.dcfg — using base inheritance
config system ecommerce.System {
  base {
    language = python;
    deployment {
      runtime = docker-compose;
      provider = local;
    }
    defaultTimeout = 30000;
  }

  profile production as "prod" extends base {
    alias env = "PROD";
    deployment {
      runtime = ecs-fargate;
      provider = aws;
    }
  }
}
```

`test` and `development` inherit from `base` automatically (no explicit profile needed). Only `production` needs overrides.

**ConfigDSL format:**

```dcfg
# config/system.dcfg
config system ecommerce.System {
  profile test as "test" {
    alias env = "TEST";
    language = python;
    deployment {
      runtime = docker-compose;
      provider = local;
    }
  }

  profile development as "dev" {
    alias env = "DEV";
    language = python;
    deployment {
      runtime = docker-compose;
      provider = local;
    }
  }

  profile production as "prod" {
    alias env = "PROD";
    language = python;
    deployment {
      runtime = ecs-fargate;
      provider = aws;
    }
  }
}
```

### Using Profiles

**Default profile:** `test`

**Specify profile:**

```bash
datrix generate --profile production --source specs/system.dtrx --output ./generated
```

**CLI short form:**

```bash
datrix generate --profile production -s specs/system.dtrx -o ./generated
```

### Common Profile Names

| Profile | Purpose |
|---------|---------|
| `test` | Local testing, fast feedback |
| `development` | Development environment |
| `staging` | Pre-production testing |
| `production` | Production deployment |

### Template Reuse with Imports

Share common config across services using imports and templates:

```dcfg
# config/templates/base.dcfg — project-wide shared config
template baseService(port = 8000) {
  flavor = compose;
  replicas = 1;
  resources {
    cpu = "100m";
    memory = "256Mi";
  }
  healthCheck {
    path = "/health";
    initialDelay = 10s;
  }
  port = port;
}

template productionService(port = 8000) {
  flavor = ecs-fargate;
  replicas = 2;
  resources {
    cpu = "500m";
    memory = "512Mi";
  }
  port = port;
}
```

```dcfg
# config/order-service.dcfg
import "config/templates/base.dcfg";

config service ecommerce.OrderService {
  base from baseService(port: 8001) {
    rdbms orderDb {
      engine = postgres;
      database = ecommerce_orders;
    }
  }

  profile production as "prod" extends base from productionService(port: 8001) {
    alias env = "PROD";
    replicas = 3;
    rdbms orderDb {
      host = env("DB_HOST");
      flavor = rds;
    }
  }
}
```

Order service uses templates for common config plus production overrides.

### Engine Defaults

Fields like `port`, `docker_image`, `asyncDriver`, `syncDriver` are auto-injected based on engine choice:

```yaml
base:
  rdbms:
    bookDb:
      engine: postgres          # Enough for test/dev!
      database: library_books
      poolSize: 20
      # port, docker_image, asyncDriver, etc. auto-injected from engine defaults

production:
  rdbms:
    bookDb:
      host: ${DB_HOST}
      platform: rds
      ssl: true
```

No need to specify `port: 5432`, `docker_image: postgres:17-alpine`, etc. — the loader fills them in automatically.

### Convention Defaults

Missing `registration` or `resilience` sections get sensible defaults:

```yaml
base:
  port: 8000
  rdbms:
    bookDb:
      engine: postgres
      database: library
  # registration: omitted → defaults to { tags: [api, <system-name>, v1], healthCheck: { type: http, path: /health, interval: 10s } }
  # resilience: omitted → defaults to { timeout: 10s, retry: { maxAttempts: 2, backoff: { type: exponential, initial: 100ms } } }
```

To explicitly opt out:

```yaml
base:
  registration: null   # No service registration
  resilience: null     # No resilience config
```

---

## System Configuration

**File:** `config/system.dcfg` (ConfigDSL format)

**Referenced in:** `system` block (declaration-level config path)

```dtrx
system ecommerce.System('config/system.dcfg') : version('1.0.0') {
}
```

### Complete Example (with `base` inheritance)

```dcfg
config system ecommerce.System {
  base {
    language = python;                    # Required: python or typescript
    deployment {                         # Required: deployment target
      runtime = docker-compose;           # docker-compose, ecs-fargate, app-runner, etc.
      provider = local;                   # local, existing, aws, azure
    }
    defaultTimeout = 30000;              # Default request timeout (ms)
    secrets { provider = env; }
    gateway {
      port = 80;
      rateLimit { default { requests = 100; window = 1m; key = ip; } }
      cors {
        origins = ["http://localhost:3000"];
        methods = [GET, POST, PUT, DELETE, PATCH];
      }
    }
    observability {
      metrics { provider = prometheus; endpoint = "/metrics"; }
      tracing { provider = jaeger; samplingRate = 0.1; }
      logging { level = info; format = json; }
    }
    serviceDiscovery { type = consul; host = "localhost"; port = 8500; }
  }

  profile production as "prod" extends base {
    alias env = "PROD";
    language = python;
    deployment {
      runtime = ecs-fargate;
      provider = aws;
    }
    region = "us-east-1";                  # AWS region (required for AWS provider)
    defaultTimeout = 60000;
    network {                            # VPC configuration (required for AWS)
      vpcId = "vpc-abc123";
      appSubnets = ["subnet-app-1", "subnet-app-2"];
      dataSubnets = ["subnet-data-1", "subnet-data-2"];
    }
    registry = "123456789012.dkr.ecr.us-east-1.amazonaws.com";  # Docker registry
    secrets {                            # Secrets management
      provider = aws-secrets-manager;     # aws-secrets-manager or azure-key-vault
      region = "us-east-1";
    }
    encryption {                         # Data encryption
      provider = aws-kms;                 # aws-kms or azure-key-vault
      keyId = "arn:aws:kms:...";
    }
  }
}
```

### Required Fields

| Field | Required When | Type | Description |
|-------|--------------|------|-------------|
| `language` | Always | `python` \| `typescript` | Target language |
| `deployment.runtime` | Always | See [Deployment Runtime Options](#deployment-runtime-options) | Deployment runtime shape |
| `deployment.provider` | Always | See [Deployment Provider Options](#deployment-provider-options) | Infrastructure provider |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `deployment.target` | String | — | Provider-specific target (e.g., `vm`) |
| `deployment.registry` | String | — | Provider-specific image registry (e.g., `acr`, `ecr`) |
| `defaultTimeout` | Integer | 30000 | Default request timeout (ms) |
| `region` | String | — | Cloud region (required for AWS/Azure) |
| `network` | Object | — | VPC/network configuration |
| `registry` | String | — | Docker registry URL |
| `secrets` | Object | — | Secrets management config |
| `encryption` | Object | — | Data encryption config |

### Language Options

| Value | Generates |
|-------|-----------|
| `python` | FastAPI application + Python code + SQL |
| `typescript` | NestJS application + TypeScript code + SQL |

### Deployment Runtime Options

| Value | Artifact Shape | Service Flavors |
|-------|----------------|----------------|
| `docker-compose` | Docker Compose (Dockerfile, docker-compose.yml, .env) | `compose` |
| `ecs-fargate` | AWS CDK stacks (ECS Fargate, ALB, VPC) | `ecs-fargate` |
| `app-runner` | AWS CDK stacks (App Runner) | `app-runner` |
| `azure-app-service` | Azure Bicep modules (App Service) | `app-service` |

### Deployment Provider Options

| Value | Meaning | Valid Runtimes |
|-------|---------|---------------|
| `local` | Local machine (no cloud) | `docker-compose` |
| `aws` | Amazon Web Services | `ecs-fargate`, `app-runner` |
| `azure` | Microsoft Azure | `azure-app-service` |

### Deployment Examples

```yaml
# Local Docker Compose
deployment:
  runtime: docker-compose
  provider: local

# AWS ECS Fargate
deployment:
  runtime: ecs-fargate
  provider: aws
  registry: ecr

# Azure App Service
deployment:
  runtime: azure-app-service
  provider: azure
  registry: acr

# AWS App Runner
deployment:
  runtime: app-runner
  provider: aws
  registry: ecr
```

---

## Service dependencies (`dependencies.dcfg`)

**DSL:** `dependencies('config/<service-name>/dependencies.dcfg');` inside a **`service { }`** body sets **`Service.dependencies_path`**. Stage 1 config resolution loads **`DependenciesProfileConfig`** (`datrix_common.config.dependencies`) into **`service.dependencies`**.

**Purpose:** supply **operational** metadata for **`uses`** targets — remote **service** URLs, timeouts, retries, and optional **shared**-block overrides — separate from behavioral DSL.

**Shape (per active profile):**

```yaml
services:
  PaymentService:
    url: http://payment-service:8080
    version: "1.0"
    healthCheck: /health
    timeout: 30s
    retry:
      maxAttempts: 3
      backoff: exponential

shared:
  IngestionEvents: {}
```

- **`services`** — keys are the **simple** service names referenced by **`uses`**. Each value is a **`ServiceDependencyConfig`** (`url`, `version`, `healthCheck`, `timeout`, `retry`, optional `loadBalance`, `healthyOnly`).
- **`shared`** — keys match **`shared BlockName`** containers. Values are **`SharedDependencyConfig`** objects (`extra="allow"`) for engine-specific connection overrides.

Files may be **flat** (top-level keys `development` / `production` / `test`) or **nested** profiles; see the loader docstring in **`datrix_common/config/dependencies.py`**.

---

## Service Configuration

**File:** `config/<service-name>/<service-name>.dcfg`

**Referenced in:** Service block

```dtrx
service ecommerce.OrderService : version('1.0.0') {
    config('config/order-service/order-service.dcfg');
}
```

### Complete Example

```yaml
test:
  platform: compose                   # Required: service runtime flavor
  replicas: 1                         # Number of replicas
  resources:
    cpu: "500m"                       # CPU limit (millicores)
    memory: "512Mi"                   # Memory limit
  healthCheck:
    path: /health
    interval: 10s
    timeout: 5s
    retries: 3

production:
  platform: ecs-fargate               # AWS ECS Fargate
  replicas: 3
  strategy:                           # Deployment strategy
    rolling:
      maxUnavailable: "25%"
      maxSurge: "50%"
  resources:
    cpu: "1000m"
    memory: "2Gi"
  healthCheck:
    path: /health
    interval: 30s
    timeout: 10s
    retries: 3
  tenancy:                            # Multi-tenancy config (optional)
    identifier:
      source: header                  # "header", "jwt", or "path"
      name: X-Tenant-Id              # Header name, JWT claim, or path param
    enforcement: strict               # "strict" or "relaxed"
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `platform` | String | Service runtime flavor (see Platform Options below) |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `replicas` | Integer | 1 | Number of service instances |
| `resources` | Object | — | CPU and memory limits |
| `healthCheck` | Object | — | Health check configuration |
| `strategy` | Object | — | Deployment strategy |
| `tenancy` | Object | — | Multi-tenancy configuration |
| `scaling` | Object | — | Auto-scaling configuration |

### Platform Options by Hosting

**Docker hosting:**

```yaml
test:
  platform: compose
```

**AWS hosting:**

```yaml
production:
  platform: ecs-fargate    # Recommended for most workloads
  # platform: ecs-ec2      # When you need EC2 control
  # platform: app-runner   # Fully managed container service
  # Event-driven / Lambda-style handlers: declare a serverless {} block in the DSL
  # and set platform: lambda | functions | container in that block's YAML — not here.
```

**Azure hosting:**

```yaml
production:
  platform: container-apps   # Recommended for containers
  # platform: app-service    # For web apps
  # Azure Functions-style handlers: serverless block YAML (platform: functions), not service platform.
```

### Resources Configuration

```yaml
resources:
  cpu: "1000m"        # 1 vCPU (millicores)
  memory: "2Gi"       # 2 GiB of memory
```

**CPU formats:**
- `"500m"` — 500 millicores (0.5 vCPU)
- `"1000m"` — 1000 millicores (1 vCPU)
- `"2"` — 2 vCPUs

**Memory formats:**
- `"512Mi"` — 512 MiB
- `"1Gi"` — 1 GiB
- `"2Gi"` — 2 GiB

### Health Check Configuration

```yaml
healthCheck:
  path: /health            # Health check endpoint
  interval: 30s            # Check every 30 seconds
  timeout: 10s             # Timeout after 10 seconds
  retries: 3               # 3 consecutive failures = unhealthy
```

Deployment probes wire directly to the generated health endpoints:
- **Liveness probe** → `/live` (process responsiveness only)
- **Readiness probe** → `/ready` (all required dependencies healthy)

See [Dependency Health and Readiness](#dependency-health-and-readiness) for the full three-endpoint contract.

### Deployment Strategy

**Rolling update:**

```yaml
strategy:
  rolling:
    maxUnavailable: "25%"   # Max % of instances down during update
    maxSurge: "50%"         # Max % of extra instances during update
```

**Blue-green deployment:**

```yaml
strategy:
  blueGreen:
    greenFleetWeight: 10    # % of traffic to new version initially
```

### Multi-Tenancy Configuration

```yaml
tenancy:
  identifier:
    source: header          # Where to read tenant ID
    name: X-Tenant-Id      # Header name, JWT claim, or path param
  enforcement: strict       # "strict" or "relaxed"
```

**Identifier sources:**
- `header` — Read from HTTP header
- `jwt` — Extract from JWT claim
- `path` — Extract from URL path parameter

**Enforcement levels:**
- `strict` — All queries require tenant context (error if missing)
- `relaxed` — Tenant filtering is optional

---

## Datasources Configuration

**File:** `config/<service-name>/datasources.dcfg`

**Referenced in:** `rdbms`, `cache`, `pubsub`, `nosql` blocks

```dtrx
service OrderService {
    rdbms db('config/order-service/datasources.dcfg') { ... }
    cache redis('config/order-service/datasources.dcfg') { ... }
    pubsub mq('config/order-service/datasources.dcfg') { ... }
}
```

### Complete Example

```yaml
test:
  rdbms:
    engine: postgres                    # Required: postgres, mysql, mariadb
    platform: container                 # Required: container, rds, flexible-server, etc.
    host: localhost
    port: 5432
    database: orders_test
    username: postgres
    password: ${POSTGRES_PASSWORD}      # Environment variable
    docker_image: postgres:16-alpine    # Docker image (for container platform)
    volume_path: ./data/postgres        # Volume mount path
    sync_driver: psycopg2              # Sync driver: psycopg2, pg8000
    async_driver: asyncpg              # Async driver: asyncpg, aiomysql
    health_check_sql: "SELECT 1"       # Health check SQL

  cache:
    engine: redis                       # Required: redis, valkey, memcached
    platform: container                 # Required: container, elasticache, cache-for-redis
    host: localhost
    port: 6379
    password: ${REDIS_PASSWORD}
    docker_image: redis:7-alpine
    volume_path: ./data/redis
    health_check_cmd: "redis-cli ping"

  pubsub:
    engine: kafka                       # Required: kafka, rabbitmq, sns-sqs, servicebus, eventbridge
    platform: container                 # Required: container, msk, managed
    brokers: localhost:9092
    docker_image: confluentinc/cp-kafka:7.5.0
    volume_path: ./data/kafka
    controller_port: 9093
    management_port: 8082

production:
  rdbms:
    engine: postgres
    platform: rds                       # AWS RDS
    database: orders_prod
    # Host/port managed by AWS

  cache:
    engine: redis
    platform: elasticache               # AWS ElastiCache
    # Host/port managed by AWS

  pubsub:
    engine: kafka
    platform: msk                       # AWS MSK (Managed Streaming for Kafka)
    # Brokers managed by AWS
```

### RDBMS Configuration

**Required fields:**

| Field | Type | Options |
|-------|------|---------|
| `engine` | String | `postgres`, `mysql`, `mariadb` |
| `platform` | String | `container`, `rds`, `aurora`, `flexible-server` |
| `database` | String | Database name |

**Optional fields (container platform):**

| Field | Type | Description |
|-------|------|-------------|
| `host` | String | Database host |
| `port` | Integer | Database port |
| `username` | String | Database username |
| `password` | String | Database password (use env vars) |
| `docker_image` | String | Docker image for database |
| `volume_path` | String | Volume mount path |
| `sync_driver` | String | Synchronous driver |
| `async_driver` | String | Asynchronous driver |
| `health_check_sql` | String | SQL for health checks |

**Drivers by engine:**

| Engine | Sync Drivers | Async Drivers |
|--------|-------------|---------------|
| `postgres` | `psycopg2`, `pg8000` | `asyncpg` |
| `mysql` | `pymysql`, `mysqlclient` | `aiomysql` |
| `mariadb` | `pymysql`, `mysqlclient` | `aiomysql` |

### Cache Configuration

**Required fields:**

| Field | Type | Options |
|-------|------|---------|
| `engine` | String | `redis`, `valkey`, `memcached` |
| `platform` | String | `container`, `elasticache`, `memorydb`, `cache-for-redis` |

**Optional fields (container platform):**

| Field | Type | Description |
|-------|------|-------------|
| `host` | String | Cache host |
| `port` | Integer | Cache port |
| `password` | String | Cache password |
| `docker_image` | String | Docker image |
| `volume_path` | String | Volume mount path |
| `health_check_cmd` | String | Health check command |

### PubSub Configuration

**Required fields:**

| Field | Type | Options |
|-------|------|---------|
| `engine` | String | `kafka`, `rabbitmq`, `sns-sqs`, `servicebus`, `eventbridge` |
| `platform` | String | `container`, `msk`, `managed` |

**Optional fields (container platform):**

| Field | Type | Description |
|-------|------|-------------|
| `brokers` | String | Broker connection string |
| `docker_image` | String | Docker image |
| `volume_path` | String | Volume mount path |
| `controller_port` | Integer | Controller port |
| `management_port` | Integer | Management UI port |

**Cloud-managed engines:**

For cloud engines (`sns-sqs`, `servicebus`, `eventbridge`), `brokers` field is not used. Connection details are managed by the cloud provider.

### NoSQL Configuration

```yaml
nosql:
  engine: mongodb                     # mongodb, dynamodb, cosmosdb
  platform: container                 # container, documentdb, atlas, cosmos-db
  host: localhost
  port: 27017
  database: orders
  username: admin
  password: ${MONGO_PASSWORD}
  docker_image: mongo:7
  volume_path: ./data/mongo
  health_check_cmd: "mongosh --eval 'db.runCommand({ping: 1})'"
```

---

## Service Registration

**File:** `config/<service-name>/registration.dcfg`

**Referenced in:** Service block

```dtrx
service OrderService {
    registration('config/order-service/registration.dcfg');
}
```

### Example

```yaml
test:
  name: order-service
  description: Order management and fulfillment
  version: 1.0.0
  tags:
    - ecommerce
    - orders
  metadata:
    team: platform
    contact: platform@example.com
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Service name for registry |
| `description` | String | Human-readable description |
| `version` | String | Service version |
| `tags` | List | Tags for discovery and filtering |
| `metadata` | Object | Additional key-value metadata |

---

## Resilience Configuration

**File:** `config/<service-name>/resilience.dcfg`

**Referenced in:** Service block

```dtrx
service OrderService {
    resilience('config/order-service/resilience.dcfg');
}
```

### Complete Example

```yaml
test:
  circuitBreaker:
    enabled: true
    failureThreshold: 5         # Open circuit after 5 failures
    successThreshold: 2         # Close circuit after 2 successes
    timeout: 60000              # Stay open for 60 seconds

  retry:
    enabled: true
    maxAttempts: 3              # Retry up to 3 times
    backoff:
      type: exponential         # exponential, linear, constant
      initialDelay: 1000        # Start with 1 second
      maxDelay: 10000           # Cap at 10 seconds
      multiplier: 2             # Double delay each retry

  timeout:
    enabled: true
    default: 30000              # Default timeout (ms)
    read: 10000                 # Read timeout
    connect: 5000               # Connection timeout

  bulkhead:
    enabled: true
    maxConcurrent: 10           # Max concurrent requests
    maxWaiting: 5               # Max requests in queue

  fallback:
    enabled: true
    type: cache                 # cache, static, default
    cacheTtl: 300               # Cache fallback for 5 minutes
```

### Circuit Breaker

Prevents cascading failures by opening circuit after repeated failures.

```yaml
circuitBreaker:
  enabled: true
  failureThreshold: 5      # Open after 5 failures
  successThreshold: 2      # Close after 2 successes
  timeout: 60000           # Half-open after 60 seconds
```

**States:**
- **Closed** — Normal operation
- **Open** — All requests fail immediately
- **Half-Open** — Test requests allowed to check recovery

### Retry Policy

Automatically retry failed requests.

```yaml
retry:
  enabled: true
  maxAttempts: 3
  backoff:
    type: exponential      # exponential, linear, constant
    initialDelay: 1000     # First retry after 1 second
    maxDelay: 10000        # Cap delays at 10 seconds
    multiplier: 2          # Double delay each time
```

**Backoff types:**
- `exponential` — Delay doubles: 1s, 2s, 4s, 8s
- `linear` — Delay increases linearly: 1s, 2s, 3s, 4s
- `constant` — Same delay: 1s, 1s, 1s, 1s

### Timeout

Prevent requests from hanging indefinitely.

```yaml
timeout:
  enabled: true
  default: 30000           # Default for all requests
  read: 10000              # Read operation timeout
  connect: 5000            # Connection establishment timeout
```

### Bulkhead

Limit concurrent requests to prevent resource exhaustion.

```yaml
bulkhead:
  enabled: true
  maxConcurrent: 10        # Max concurrent requests
  maxWaiting: 5            # Max queued requests
```

### Fallback

Provide alternative responses when primary fails.

```yaml
fallback:
  enabled: true
  type: cache              # cache, static, default
  cacheTtl: 300            # Cache TTL in seconds
  staticValue: null        # For type: static
  defaultValue: {}         # For type: default
```

### Dependency Resilience Policy

Every `service` dependency that a service issues inter-service calls to requires an **explicit** resilience policy. The generator never synthesizes timeout, circuit-breaker, or bulkhead values. If a called service has no resolved policy, generation fails with `RESILIENCE_POLICY_REQUIRED`.

#### Two-Level Hierarchy

Policy is resolved from two levels — later takes precedence:

1. **Application-level baseline** — `resilience.dependencyPolicy.defaults.service`, declared once in the service `.dcfg` and inherited by every `service` dependency.
2. **Per-service override** — `resilience.dependencyPolicy.service <Name>`, applied only where one dependency differs from the baseline.

#### `standardServicePolicy()` Template

The recommended starting point for the `service` baseline:

```dcfg
template standardServicePolicy() {
  availability = "required";
  health = "ready";
  timeout = 5000;
}

resilience {
  dependencyPolicy {
    defaults {
      service from standardServicePolicy();
    }
    service InventoryService {
      timeout = 2000;        // tighter timeout for one dependency
    }
  }
}
```

Opting in **by name** keeps values visible in config — they are never inherited silently.

#### Canonical Service Name

Config must use the **canonical resolved service model name** (e.g., `OrderService`, `InventoryService`). A non-canonical or misspelled name is a config error, never silently aliased.

#### Retry Off by Default

Retry stays **off** for service calls unless the target endpoint is marked `idempotent`. Even then, it is bounded by a retry budget and is circuit-breaker-aware. Timeout, circuit breaker, and bulkhead are non-amplifying and stay active within the declared policy.

#### `RESILIENCE_POLICY_REQUIRED`

Triggered when a `service` dependency with calls is covered at **neither** the application baseline nor the per-service override level. The fix is to declare `defaults { service from standardServicePolicy(); }` at the service level, or a per-service block for that specific dependency.

See [config-dsl-reference.md — dependencyPolicy block](../reference/config-dsl-reference.md#dependencypolicy-block) for the full field reference.

### Dependency Health and Readiness {#dependency-health-and-readiness}

Generated services expose three distinct health endpoints:

| Endpoint | Semantics |
|---|---|
| `/live` | Process liveness — the service process can respond. No dependency checks. |
| `/ready` | Readiness — all `required`-availability dependencies are up. Fails 503 when a required dependency is down. |
| `/health` | Full status — all dependency checks including degraded optional dependencies. |

**Deployment probes point at `/ready` for readiness, `/live` for liveness.** The old single `/health` contract is replaced outright; there are no backward-compatible fields.

#### Readiness and Health Severity

Each dependency's health severity controls how its failure affects the endpoints:

| `health` value | `/ready` on dependency failure | `/health` |
|---|---|---|
| `ready` | 503 | unhealthy |
| `degraded` | 200 (stays ready) | degraded |
| `degraded` + `readyOnDegraded = false` | 503 (blocks readiness) | degraded |
| `ignored` | 200 (no check) | omitted |

Use `readyOnDegraded = false` to make a degraded dependency block rollout readiness without marking it fully required.

#### Example `/health` Response

```json
{
  "status": "degraded",
  "service": "order_service",
  "checks": {
    "database": {"status": "up", "required": true},
    "cache.sessionCache": {"status": "down", "required": false, "health": "degraded", "error": "connection refused"}
  }
}
```

---

## Gateway Configuration

**File:** `config/gateway.dcfg`

**Referenced in:** System block

```dtrx
system {
    gateway('config/gateway.dcfg');
}
```

### Complete Example

```yaml
test:
  type: nginx                      # nginx, managed
  host: localhost
  port: 8080
  cors:
    enabled: true
    allowedOrigins:
      - http://localhost:3000
      - http://localhost:4200
    allowedMethods: [GET, POST, PUT, PATCH, DELETE, OPTIONS]
    allowedHeaders: [Content-Type, Authorization]
    allowCredentials: true
    maxAge: 3600

  rateLimit:
    enabled: true
    requestsPerMinute: 1000
    burstSize: 100

  authentication:
    type: jwt                      # jwt, oauth2, api-key
    jwtSecret: ${JWT_SECRET}
    jwtIssuer: ecommerce-api
    jwtAudience: ecommerce-app

production:
  type: aws-alb
  cors:
    enabled: true
    allowedOrigins:
      - https://app.example.com
    allowedMethods: [GET, POST, PUT, PATCH, DELETE]
    allowCredentials: true

  rateLimit:
    enabled: true
    requestsPerMinute: 10000

  authentication:
    type: jwt
    jwtSecret: ${JWT_SECRET}
    jwtIssuer: ecommerce-api
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | String | Gateway type (nginx, managed) |
| `host` | String | Gateway host |
| `port` | Integer | Gateway port |
| `cors` | Object | CORS configuration |
| `rateLimit` | Object | Rate limiting configuration |
| `authentication` | Object | Authentication configuration |

---

## Registry Configuration

**File:** `config/registry.dcfg`

**Referenced in:** System block

```dtrx
system {
    registry('config/registry.dcfg');
}
```

### Example

```yaml
test:
  type: consul                     # consul, eureka, etcd
  host: localhost
  port: 8500
  healthCheckInterval: 10s
  deregisterAfter: 30s

production:
  type: consul
  host: consul.internal
  port: 8500
  healthCheckInterval: 30s
  deregisterAfter: 90s
  datacenter: us-east-1
```

---

## Observability Configuration

**File:** `config/observability.dcfg`

**Referenced in:** System block

```dtrx
system {
    observability('config/observability.dcfg');
}
```

### Complete Example

```yaml
test:
  metrics:
    enabled: true
    type: prometheus           # prometheus, cloudwatch, azure-monitor
    endpoint: http://localhost:9090
    interval: 15s

  tracing:
    enabled: true
    type: jaeger               # jaeger, zipkin, aws-xray, azure-monitor
    endpoint: http://localhost:14268/api/traces
    sampleRate: 1.0            # 100% sampling in test

  logging:
    enabled: true
    type: console              # console, cloudwatch, azure-monitor
    level: debug               # debug, info, warn, error
    format: json               # json, text

  visualization:
    enabled: true
    type: grafana
    endpoint: http://localhost:3000

  alerting:
    enabled: false

production:
  metrics:
    enabled: true
    type: prometheus
    endpoint: ${PROMETHEUS_ENDPOINT}
    interval: 60s

  tracing:
    enabled: true
    type: aws-xray
    sampleRate: 0.1            # 10% sampling in production
    level: standard            # none, minimal, standard, full

  logging:
    enabled: true
    type: cloudwatch
    level: info
    format: json

  visualization:
    enabled: true
    type: grafana
    endpoint: ${GRAFANA_ENDPOINT}

  alerting:
    enabled: true
    type: pagerduty
    endpoint: ${PAGERDUTY_ENDPOINT}
```

### Tracing Levels

| Level | Description |
|-------|-------------|
| `none` | No tracing generated |
| `minimal` | Framework-only instrumentation |
| `standard` | Feature-based library instrumentation (default) |
| `full` | All instrumentations regardless of features |

---

## Storage Configuration

**File:** `config/<service-name>/storage.yaml`

**Referenced in:** Storage blocks

```dtrx
service OrderService {
    storage files config('config/order-service/storage.dcfg') { ... }
}
```

### Complete Example

```yaml
test:
  provider: minio                # minio, s3, azure-blob, gcs
  bucket: order-files
  endpoint: http://localhost:9000
  accessKey: ${MINIO_ACCESS_KEY}
  secretKey: ${MINIO_SECRET_KEY}
  region: us-east-1

production:
  provider: s3
  bucket: order-files-prod
  region: us-east-1
  accessKey: ${AWS_ACCESS_KEY}
  secretKey: ${AWS_SECRET_KEY}
```

### Providers

| Provider | Platform | Configuration |
|----------|----------|---------------|
| `minio` | Self-hosted | Requires `endpoint`, `accessKey`, `secretKey` |
| `s3` | AWS | Requires `bucket`, `region`, `accessKey`, `secretKey` |
| `azure-blob` | Azure | Requires `container`, `connectionString` |
| `gcs` | Google Cloud | Requires `bucket`, `credentials` |

---

## Jobs Configuration

**File:** `config/<service-name>/jobs.yaml`

**Referenced in:** Job blocks

```dtrx
job ProcessOrders cron('0 * * * *') config('config/jobs.dcfg') { ... }
```

### Example

Per-profile entries live under a `jobs:` key. Each job requires a `schedule` (cron string), supports duration strings for `timeout`, and accepts either the `retries` shorthand (total attempts) or a nested `retry` object with `maxAttempts` and `backoff` (`fixed`, `linear`, or `exponential`). Unknown keys are rejected by the loader.

```yaml
test:
  jobs:
    ProcessOrders:
      schedule: "0 * * * *"
      timeout: 5m
      retries: 3

    CleanupExpired:
      schedule: "30 */6 * * *"
      timeout: 10m
      retry: { maxAttempts: 5, backoff: linear }

production:
  jobs:
    ProcessOrders:
      schedule: "0 */1 * * *"
      timeout: 15m
      retry: { maxAttempts: 5, backoff: exponential }

    CleanupExpired:
      schedule: "0 */6 * * *"
      timeout: 20m
      retries: 2
      concurrency: 1
```

---

## Serverless configuration {#serverless-configuration}

**File:** one YAML per `serverless` block (path in the DSL, e.g. `serverless handlers('config/my-service/handlers.dcfg')`).

**Resolved in:** infrastructure config resolution (`resolve_infrastructure_configs`) onto **`ServerlessBlock.config`** as the active profile’s **`ServerlessProfileConfig`**.

Each profile root (`test`, `development`, `production`, …) includes:

- **`platform`** (required): `lambda` \| `functions` \| `container` — where handlers run for that environment.
- **`defaults`** (optional): `timeout` (seconds), `memory` (MB) applied to every handler unless overridden.
- **`handlers`** (optional): map from DSL-derived handler name to per-handler overrides (`timeout`, `memory`, Lambda-only `reservedConcurrency` / `provisionedConcurrency`, Azure-only `planSku` / `runtimeVersion`).

Handler keys match **`on EventName`**, **`job JobName`**, **`@name('X')`** for HTTP endpoints inside `serverless`, or the **queue name** for `enqueue` consumers. Full rules and platform limits: [config-system — Serverless](../../../datrix-common/docs/architecture/config-system.md#serverless-handler-configuration) and [Code Generation — Serverless](../../../datrix-common/docs/architecture/code-generation.md#serverless-functions).

---

## Queue Configuration

**File:** `config/<service-name>.dcfg`

**Referenced in:** `service ServiceName('config/<service-name>.dcfg')` with a **`queues { ... }`** block on a producing service.

The service `.dcfg` queues section configures **task-dispatch** brokers (RabbitMQ, SQS, Azure Service Bus, Azure Storage Queue). It is **not** a datasource. Services that only **consume** queues via `enqueue OtherService.TaskName { … }` do **not** define a `queues` section; workers and clients resolve settings from the **producer’s** `.dcfg`.

### Profiles and engines

Each profile (`test`, `production`, …) is a `QueueConfig` object:

- **`engine`** (required): `rabbitmq` \| `sqs` \| `service-bus` \| `storage-queue`
- **`platform`** (required): `container` \| `external` \| `sqs` \| `amazon-mq` \| `service-bus` \| `storage-queue` — must match hosting + engine (see [config-system architecture](../../../datrix-common/docs/architecture/config-system.md#queue-configuration) in datrix-common)

Connection and ops fields (when required): `host`, `port`, `managementPort`, `defaultUser`, `dockerImage`, `volumePath`, `healthCheckCmd`, `region`, `queuePrefix`, `connectionString`, `sku`.

### Defaults and overrides

| ConfigDSL key | Role |
|----------|------|
| `visibilityTimeout` | Seconds before redelivery (default 30) |
| `maxReceiveCount` | Max deliveries before DLQ routing (default 5) |
| `retentionDays` | Retention in days (default 14) |
| `delay` | Default delay seconds (0); RabbitMQ may use delayed-exchange plugin when non-zero |
| `maxConcurrency` | Worker prefetch / concurrency (default 5) |
| `timeout` | Handler timeout seconds (default 60) |
| `workerReplicas` | Worker replica count for generated deployments (default 1) |
| `queues` | Map of **queue name** → optional overrides of the fields above |

### Example: RabbitMQ (test + production)

```yaml
test:
  engine: rabbitmq
  platform: container
  host: localhost
  port: 5672
  managementPort: 15672
  defaultUser: datrix
  dockerImage: rabbitmq:3-management-alpine
  volumePath: /var/lib/rabbitmq
  healthCheckCmd: '["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]'
  visibilityTimeout: 30
  maxReceiveCount: 5
  retentionDays: 14
  delay: 0
  maxConcurrency: 5
  timeout: 60
  workerReplicas: 1
  queues:
    ProcessPayment:
      visibilityTimeout: 300
      maxReceiveCount: 2
      maxConcurrency: 2
      timeout: 300

production:
  engine: rabbitmq
  platform: amazon-mq
  host: ${QUEUE_RABBITMQ_HOST}
  port: 5671
  visibilityTimeout: 60
  maxReceiveCount: 3
  retentionDays: 14
  maxConcurrency: 10
  timeout: 120
  workerReplicas: 2
```

### Example: SQS (LocalStack test + AWS production)

```yaml
test:
  engine: sqs
  platform: container
  host: localhost
  port: 4566
  region: us-east-1
  visibilityTimeout: 30
  maxReceiveCount: 5
  retentionDays: 14
  delay: 0
  maxConcurrency: 5
  timeout: 60
  workerReplicas: 1

production:
  engine: sqs
  platform: sqs
  region: us-east-1
  visibilityTimeout: 60
  maxReceiveCount: 5
  retentionDays: 14
  maxConcurrency: 10
  timeout: 120
  workerReplicas: 2
```

**Language codegen note:** Python and TypeScript queue **clients and workers** are generated for `rabbitmq`, `sqs`, and `service-bus` only today; `storage-queue` is for Azure infra / future parity.

---

## Integrations Configuration

**File:** `config/<service-name>/integrations.yaml`

**Referenced in:** Service block

```dtrx
service OrderService {
    integrations('config/order-service/integrations.dcfg');
}
```

### Example

```yaml
test:
  email:
    provider: smtp             # smtp, sendgrid, ses, sendgrid
    host: localhost
    port: 1025
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    from: noreply@example.com

  sms:
    provider: twilio           # twilio, sns
    accountSid: ${TWILIO_ACCOUNT_SID}
    authToken: ${TWILIO_AUTH_TOKEN}
    fromNumber: "+15551234567"

  payment:
    provider: stripe           # stripe, paypal, square
    apiKey: ${STRIPE_API_KEY}
    webhookSecret: ${STRIPE_WEBHOOK_SECRET}

production:
  email:
    provider: ses
    region: us-east-1
    from: noreply@example.com

  sms:
    provider: sns
    region: us-east-1

  payment:
    provider: stripe
    apiKey: ${STRIPE_API_KEY}
    webhookSecret: ${STRIPE_WEBHOOK_SECRET}
```

---

## Extern Service Configuration

**File:** Path specified in the `extern service` declaration (e.g., `'config/pricing-engine.dcfg'`)

**Referenced in:** Extern service block

```dtrx
extern service pricing.PricingEngine('config/pricing-engine.dcfg') {
    // ...
}
```

### Deployment Modes

Each extern service config must declare a `deployment` mode:

| Mode | Description | Required Fields |
|------|-------------|-----------------|
| `container` | Datrix manages the container (Docker Compose) | `image`, `port` |
| `external` | Remote URL, not managed by Datrix | `url` |

### Single Profile

```dcfg
config extern pricing.PricingEngine {
  profile development as "dev" {
    deployment = "container";
    image = "myregistry/pricing-engine:1.2.0";
    port = 8080;
    health {
      path = "/health";
      interval = "10s";
      timeout = "5s";
      startPeriod = "40s";
      retries = 3;
    }
    auth {
      type = "apiKey";
      header = "X-API-Key";
      secret = "PRICING_API_KEY";
    }
    timeout = "30s";
    retry {
      maxAttempts = 3;
      backoff = "exponential";
    }
    resources {
      memory = "512m";
      cpu = "0.5";
    }
    environment {
      EXTRA_VAR = "value";
    }
  }
}
```

### Multi-Profile Format

Different config per profile:

```dcfg
config extern pricing.PricingEngine {
  profile development as "dev" {
    deployment = "container";
    image = "pricing-engine:dev";
    port = 8080;
    auth {
      type = "apiKey";
      header = "X-API-Key";
      secret = "PRICING_API_KEY_DEV";
    }
  }

  profile production as "prod" {
    deployment = "external";
    url = "https://pricing.example.com/api";
    auth {
      type = "bearer";
      secret = "PRICING_BEARER_TOKEN";
    }
    timeout = "60s";
  }

  profile test as "test" {
    deployment = "container";
    image = "pricing-engine:test";
    port = 8080;
  }
}
```

### Field Reference

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `deployment` | `container` or `external` | (required) | Deployment mode |
| `image` | string | — | Docker image. **Required** for `container` |
| `port` | integer | — | Container port. **Required** for `container` |
| `url` | string | — | Remote endpoint. **Required** for `external` |
| `timeout` | duration string | `30s` | Request timeout |
| `health.path` | string | `/health` | Health check endpoint path |
| `health.interval` | duration string | `10s` | Health check interval |
| `health.timeout` | duration string | `5s` | Health check response timeout |
| `health.startPeriod` | duration string | `40s` | Grace period before first check |
| `health.retries` | integer | `3` | Failures before unhealthy |
| `auth.type` | string | `none` | `apiKey`, `bearer`, `serviceJwt`, `none` |
| `auth.header` | string | — | Header name for `apiKey` auth |
| `auth.secret` | string | — | Environment variable name holding the credential |
| `retry.maxAttempts` | integer | `3` | Maximum retry attempts |
| `retry.backoff` | string | `exponential` | `exponential`, `linear`, `fixed` |
| `resources.memory` | string | — | Memory limit (e.g., `512m`, `1g`) |
| `resources.cpu` | string | — | CPU limit (e.g., `0.5`, `1`) |
| `environment` | map | `{}` | Extra environment variables passed to the container |

### What Gets Generated from Config

**`deployment: container`:**
- Docker Compose service entry with image, ports, health check, environment variables, `restart: unless-stopped`
- Consuming services get `{SERVICE}_SERVICE_URL=http://{name}:{port}` and `depends_on` with `condition: service_healthy`

**`deployment: external`:**
- No deployment artifacts (service not managed by Datrix)
- Consuming services get `{SERVICE}_SERVICE_URL={url}` as an environment variable

### Example: Container + External by Profile

A common pattern is to run a local container in development and point to a managed service in production:

```dcfg
config extern pricing.PricingEngine {
  profile development as "dev" {
    deployment = "container";
    image = "myregistry/pricing-engine:dev";
    port = 8080;
    auth {
      type = "apiKey";
      header = "X-API-Key";
      secret = "PRICING_API_KEY";
    }
    resources {
      memory = "256m";
      cpu = "0.25";
    }
  }

  profile production as "prod" {
    deployment = "external";
    url = "https://pricing.prod.internal/api";
    auth {
      type = "bearer";
      secret = "PRICING_BEARER_TOKEN";
    }
    timeout = "60s";
    retry {
      maxAttempts = 5;
      backoff = "exponential";
    }
  }
}
```

---

## Platform-Specific Configuration

### Docker Compose (Local)

No additional config file — settings live in the selected system `.dcfg` profile:

```dcfg
profile base {
    deployment {
        runtime: docker-compose
        provider: local
    }
    registry: registry.example.com
}
```

### AWS (ECS Fargate)

Network and IAM configuration:

```yaml
production:
  deployment:
    runtime: ecs-fargate
    provider: aws
  region: us-east-1
  network:
    vpcId: vpc-abc123
    appSubnets: [subnet-app-1, subnet-app-2]
    dataSubnets: [subnet-data-1, subnet-data-2]
  iam:
    roleArn: arn:aws:iam::123456789012:role/OrderServiceRole
```

### Azure (Container Apps)

Resource group and managed identity:

```yaml
production:
  deployment:
    runtime: azure-container-apps
    provider: azure
  location: eastus
  resourceGroup: ecommerce-rg
  identity:
    type: system-assigned        # system-assigned or user-assigned
```

---

## Seed Configuration

Seed configuration controls which seed categories are active per profile and how seed data is managed. Seed data declarations live in `.dseed` files (see [Seed Data Guidelines](./seed-data-guidelines.md)); configuration policies live in `.dcfg`.

### System-Level Seed Defaults

Override the default category-to-profile mapping in `system.dcfg`:

```dcfg
config system ecommerce.System {
  base {
    seed {
      categories {
        reference = ["dev", "test", "stg", "prod"];
        baseline  = ["dev", "test", "stg"];
        volume    = ["stg"];
      }
    }
  }
}
```

### Default Category Mapping

Without explicit configuration, these defaults apply:

| Category | Default Profiles |
|----------|-----------------|
| `reference` | all (dev, test, stg, prod) |
| `baseline` | dev, test, stg |
| `volume` | stg |

### Production Safety

Production profiles run **only reference data** by default. Baseline and volume categories are rejected unless explicitly overridden with `--force` on the CLI. `--reset` is never allowed on production.

### Component-Scoped Seed Policy

Seed policy can be configured per target component (`rdbms`, `nosql`, or `storage`) rather than at the service level. Global defaults in `system.dcfg` apply unless overridden by component-specific settings.

For the full SeedDSL syntax and authoring guidelines, see [Seed Data Guidelines](./seed-data-guidelines.md) and [SeedDSL Syntax Reference](../../../datrix-language/docs/reference/seed-dsl-syntax-reference.md).

---

## Secrets Management

Generated services follow a **zero-environment contract**: they read **no environment
variables** for secrets, credentials, or connection passwords at runtime. Credentials
are never written into application config, generated code, or infrastructure-as-code.
Instead, secrets are declared as **logical handles** in application config and bound to
a concrete secret store by **deployment-level policy**.

> Do **not** put passwords, API keys, or tokens in `.dcfg` as literals or as `${ENV_VAR}`
> placeholders. Raw credential literals are rejected at generation time, and generated
> services do not read credential env vars. Declare a logical secret handle instead.

### 1. Declare logical secret handles (service config)

A logical secret is a stable **handle** — a name that says *which* secret is needed,
never *what it is*. Declare handles in the service-level `secrets` block:

```dcfg
config service ecommerce.OrderService {
  base {
    secrets {
      secret db_password    { required = true; purpose = "rdbms-connection-password"; }
      secret jwt_secret     { required = true; purpose = "jwt-signing-secret"; }
      secret stripe_api_key { required = true; purpose = "payment-provider-api-key"; }
    }
  }
}
```

- `required` — Boolean, defaults to `true` (fail-closed). A required handle that the
  deployment does not bind makes the service fail to start; no empty/default substitution.
- `purpose` — Non-secret, human-readable description (metadata only).

Connection passwords are auto-derived: a declared `rdbms orders { … }` datasource emits
non-secret `orders_host` / `orders_port` / `orders_database` config keys plus an
`orders_password` **secret handle** — you do not declare the password by hand.

Application config carries **no backend or naming policy**. The legacy
`secrets { provider = "aws-secrets-manager" | "azure-key-vault" | … }` selector form has
been **removed** — provider strings in application `.dcfg` are a hard generation error.

### 2. Bind handles to a backend (system profile)

Which store backs a handle, and how handle names map to backend names, is chosen by
`secretBackendPolicy` on the **system** deployment profile — not in the service `.dcfg`:

```dcfg
config system ecommerce.System {
  profile production as "prod" {
    deployment { runtime = ecs-fargate; provider = aws; }

    secretBackendPolicy {
      defaultBackend = aws-secrets-manager;   // or azure-key-vault | file | docker-secret
      namePrefix     = "/prod/orders/";        // db_password -> /prod/orders/db_password
      nameSeparator  = "/";
    }
  }
}
```

Runtime-valid backends are `aws-secrets-manager`, `azure-key-vault`, `file`, and
`docker-secret`. The `env` and `aws-ssm` backends are **rejected at generation time**
(they would break the zero-env contract).

| Deployment target | Secret store | How the app authenticates |
|---|---|---|
| AWS ECS Fargate / App Runner | AWS Secrets Manager | task/instance role via IMDS (region baked) |
| Azure App Service | Azure Key Vault | system-assigned managed identity |
| LOCAL / docker-compose | Mounted files under `/run/secrets/` | file read (no network) |

### 3. What the generated code actually does

- **Provisions named, empty placeholders** in the store (CDK for AWS, Bicep for Azure,
  mounted files for Docker). No secret value is ever emitted into code or IaC.
- **Resolves each handle at startup** by rendering the backend name from the policy and
  fetching it with the baked credential mechanism (managed identity / instance role /
  mounted file). Missing required secrets **fail closed** with an error naming the handle
  and rendered name — never the value.
- **Caches each resolved secret for the lifetime of the process.** There is **no TTL and
  no background refresh** — a rotated secret is not observed until the process restarts
  (see [Rotating secrets](#rotating-secrets-and-keys)).

You supply the real values **after** infrastructure is provisioned (they are never in
git):

```bash
# AWS
aws secretsmanager put-secret-value --secret-id /prod/orders/db_password --secret-string "$VALUE"
# Azure
az keyvault secret set --vault-name <app-kv> --name db-password --value "$VALUE"
# LOCAL / docker (file backend)
printf '%s' "$VALUE" > ./secrets/db_password   # mounted read-only at /run/secrets/db_password
```

### Rotating secrets and keys

Rotation is **operator-owned and requires a restart** — generated services resolve each
secret once and cache it for the process lifetime:

1. **Write the new value** to the backend (the `put-secret-value` / `az keyvault secret set`
   / file-write commands above).
2. **Restart the service** so new process instances re-read the secret (rolling restart,
   redeploy, or task/pod recycle). Until then, running instances keep using the old value.

For database credentials, rotate **dual-valid**: add the new credential, roll the service
to pick it up, then retire the old one — so instances still on the old value keep working
until they cycle.

**Exception — JWT signing keys.** The self-hosted identity provider (`provider self`,
engine Zitadel) rotates its asymmetric token-signing keys natively and publishes them via
`/.well-known/jwks.json`; verifiers refresh from JWKS, so issuer signing-key rotation does
not require the write-and-restart sequence above. This applies to the *issuer's* signing
keys, not to application secrets like database passwords.

> **Reference:** [Secret Backend Policy](../../../datrix-common/docs/secret-backend-policy.md),
> [ConfigDSL Reference — Logical Secrets](../reference/config-dsl-reference.md),
> and the runtime resolver in `datrix-codegen-python` (`templates/service/secrets_resolver.py.j2`).

---

## Runtime Config Store

The `configStore` section in a **system** ConfigDSL profile enables a runtime-mutable configuration plane — feature flags, kill switches, rate-limit tuning, and per-environment overrides — without rebuilding or redeploying services.

**Key traits:**
- **Additive and gated:** services receive a generated runtime client only when `configStore` is declared; apps without it produce byte-equivalent output (no client files, no env vars, no infrastructure).
- **Non-sensitive values only:** keys hold typed scalar values and *references* to secrets, never raw secret values.
- **Typed, grouped profiles:** `freeform` profiles accept any scalar type; `featureFlag` profiles are Boolean-only and render to provider-native feature-flag shapes.

**Supported engines:**

| Engine | Platform | Runtime target |
|--------|----------|---------------|
| `aws-managed` | `managed` | AWS provider |
| `azure-managed` | `managed` | Azure provider |
| `consul` | `container` | Docker (Datrix-provisioned) |
| `consul` | `external` | Any (connect to existing backend) |

### Minimal example

```dcfg
config system ecommerce.System {
  profile production as "prod" {
    language = python;
    deployment {
      runtime = ecs-fargate;
      provider = aws;
    }

    configStore {
      engine = aws-managed;
      platform = managed;
      applicationName = "ecommerce-api";
      environment = "prod";
      pollingIntervalSeconds = 60;
      failOpen = true;

      profiles {
        featureFlags {
          kind = featureFlag;
          keys {
            enableCheckoutV2 { type = Boolean; default = false; }
          }
        }

        rateLimits {
          kind = freeform;
          keys {
            ordersPerMinute {
              type = Integer;
              default = 100;
              constraints { min = 1; max = 10000; }
            }
          }
        }
      }
    }
  }
}
```

Generated services receive a `RemoteConfigClient` (Python or TypeScript) that polls the configured engine, caches values locally, and exposes typed accessors (`get_bool`, `get_int`, `get_float`, `get_string`, `get_secret_ref`).

**Full reference:** [Config Store Schema Reference](../../../datrix-common/docs/config-store.md) — schema, enums, validation rules, engine compatibility matrix, and examples.

**Language client docs:**
- Python: [Runtime Config Client](../../../datrix-codegen-python/docs/runtime-config-client.md)
- TypeScript: [Runtime Config Client](../../../datrix-codegen-typescript/docs/runtime-config-client.md)

---

## Configuration Validation

All configuration is validated at generation time:

```bash
datrix generate --profile production -s specs/system.dtrx -o ./generated
```

**Validation checks:**

✅ Required fields present
✅ Field types correct
✅ Enum values valid
✅ Cross-field constraints (e.g., min <= max)
✅ Deployment consistency (e.g., no Azure infrastructure flavor with `provider: aws`)
✅ Engine-flavor compatibility (e.g., memcached works with elasticache)

**Error messages include:**
- Missing field name and location
- Expected type and received value
- Available options for enums
- Suggestions for fixing

---

## Best Practices

### 1. Use Profiles Consistently

```yaml
# ✅ Good: Same structure across profiles
test:
  language: python
  deployment:
    runtime: docker-compose
    provider: local

production:
  language: python
  deployment:
    runtime: ecs-fargate
    provider: aws
  region: us-east-1

# ❌ Bad: Different fields per profile
test:
  language: python

production:
  deployment:
    runtime: ecs-fargate
    provider: aws  # Missing language!
```

### 2. Logical Handles for Secrets

Declare a logical secret handle and let deployment policy bind it to a backend — never
put a credential (literal or `${ENV_VAR}`) in config:

```dcfg
// ✅ Good: a logical handle; the value lives only in the secret store
secrets {
  secret db_password { required = true; purpose = "rdbms-connection-password"; }
}

// ❌ Bad: raw literal (rejected at generation time)
rdbms { password = "mypassword123"; }

// ❌ Bad: env placeholder (generated services read no credential env vars)
rdbms { password = "${POSTGRES_PASSWORD}"; }
```

See [Secrets Management](#secrets-management) for the full handle → backend flow.

### 3. Explicit Over Implicit

```yaml
# ✅ Good: Explicit values
circuitBreaker:
  enabled: true
  failureThreshold: 5

# ❌ Bad: Relying on defaults
circuitBreaker:
  enabled: true
```

### 4. Document Configuration Choices

```yaml
# ✅ Good: Comment explains why
production:
  replicas: 3  # 3 replicas for HA across availability zones
```

---

## Troubleshooting

### Error: Missing required field

```
ConfigValidationError: Field 'language' is required in system .dcfg profile 'production'
```

**Fix:** Add the missing field to the profile.

### Error: Invalid enum value

```
ConfigValidationError: Invalid value 'mysqll' for field 'engine'. Valid options: postgres, mysql, mariadb
```

**Fix:** Check spelling and use valid option.

### Error: Deployment consistency

```
DeploymentValidationError: Service flavor 'compose' is incompatible with deployment runtime 'ecs-fargate', provider 'aws'
```

**Fix:** Use a compatible service flavor for the selected runtime/provider (e.g., `ecs-fargate` for AWS).

---

## Reference

**Configuration file locations:**

```
config/
├── system.dcfg                     # System profiles: language, deployment, gateway, registry, observability
├── templates/                      # Optional shared ConfigDSL templates/imports
└── <service-name>.dcfg             # Service profiles: deployment, infrastructure, dependencies, jobs, queues, integrations
```

---

**Last Updated:** April 24, 2026
