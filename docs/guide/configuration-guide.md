# Configuration Guide

**Complete reference for Datrix configuration files**

This guide covers all configuration files in Datrix, their structure, options, and how to use profiles for environment-specific settings.

---

## Table of Contents

1. [Configuration Overview](#configuration-overview)
2. [Configuration Hierarchy](#configuration-hierarchy)
3. [Profiles and Environments](#profiles-and-environments)
4. [System Configuration](#system-configuration)
5. [Service Configuration](#service-configuration)
6. [Datasources Configuration](#datasources-configuration)
7. [Service Registration](#service-registration)
8. [Resilience Configuration](#resilience-configuration)
9. [Gateway Configuration](#gateway-configuration)
10. [Registry Configuration](#registry-configuration)
11. [Observability Configuration](#observability-configuration)
12. [Storage Configuration](#storage-configuration)
13. [Jobs Configuration](#jobs-configuration)
14. [Integrations Configuration](#integrations-configuration)
15. [Platform-Specific Configuration](#platform-specific-configuration)
16. [Environment Variables](#environment-variables)
17. [Secrets Management](#secrets-management)

---

## Configuration Overview

Datrix uses a **hierarchical configuration system** with **profile-based environments**. Configuration is split between:

1. **`.dtrx` files** — Behavioral definitions (entities, APIs, services)
2. **YAML files** — Environmental configuration (databases, credentials, deployment)

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

Tier 2: System-Level Config (profile-based YAML)
├── Language and hosting platform
├── API Gateway
├── Service Registry
├── Observability
└── System-wide deployment settings

Tier 3: Service-Level Config (profile-based YAML)
├── Service deployment config
├── Resilience patterns
├── Service metadata
├── Integrations
└── Multi-tenancy settings

Tier 4: Block-Level Config (profile-based YAML)
├── RDBMS (datasources.yaml)
├── Cache (datasources.yaml)
├── PubSub (datasources.yaml)
├── NoSQL (datasources.yaml)
├── Storage (storage.yaml)
└── Jobs (jobs.yaml)
```

---

## Profiles and Environments

Profiles allow environment-specific configuration in a single file.

### Profile Structure

```yaml
# config/system-config.yaml
test:                           # Profile name
  language: python
  hosting: docker

development:
  language: python
  hosting: docker

production:
  language: python
  hosting: aws
  region: us-east-1
```

### Using Profiles

**Default profile:** `test`

**Specify profile:**

```bash
datrix generate --profile production --source specs/system.dtrx --output ./generated
```

**CLI short form:**

```bash
datrix generate -p production -s specs/system.dtrx -o ./generated
```

### Common Profile Names

| Profile | Purpose |
|---------|---------|
| `test` | Local testing, fast feedback |
| `development` | Development environment |
| `staging` | Pre-production testing |
| `production` | Production deployment |

---

## System Configuration

**File:** `config/system-config.yaml`

**Referenced in:** `system` block

```dtrx
system ecommerce.System : version('1.0.0') {
    config('config/system-config.yaml');
}
```

### Complete Example

```yaml
test:
  language: python                    # Required: "python" or "typescript"
  hosting: docker                     # Required: "docker", "kubernetes", "aws", "azure"
  defaultTimeout: 30000              # Default request timeout (ms)

development:
  language: python
  hosting: docker
  defaultTimeout: 30000

production:
  language: python
  hosting: aws
  region: us-east-1                  # AWS region (required for AWS hosting)
  defaultTimeout: 60000
  network:                            # VPC configuration (required for AWS)
    vpcId: vpc-abc123
    appSubnets:
      - subnet-app-1
      - subnet-app-2
    dataSubnets:
      - subnet-data-1
      - subnet-data-2
  registry: 123456789012.dkr.ecr.us-east-1.amazonaws.com  # Docker registry
  secrets:                            # Secrets management
    provider: aws-secrets-manager     # "aws-secrets-manager" or "azure-key-vault"
    region: us-east-1
  encryption:                         # Data encryption
    provider: aws-kms                 # "aws-kms" or "azure-key-vault"
    keyId: arn:aws:kms:...
```

### Required Fields

| Field | Required When | Type | Description |
|-------|--------------|------|-------------|
| `language` | Always | `python` \| `typescript` | Target language |
| `hosting` | Always | `docker` \| `kubernetes` \| `aws` \| `azure` | Hosting platform |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
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

### Hosting Options

| Value | Platform | Service Flavors |
|-------|----------|----------------|
| `docker` | Docker Compose | `compose` |
| `kubernetes` | Kubernetes | `kubernetes` |
| `aws` | Amazon Web Services | `ecs-fargate`, `ecs-ec2`, `lambda`, `app-runner`, `eks` |
| `azure` | Microsoft Azure | `container-apps`, `functions`, `aks`, `app-service` |

---

## Service Configuration

**File:** `config/<service-name>/<service-name>-config.yaml`

**Referenced in:** Service block

```dtrx
service ecommerce.OrderService : version('1.0.0') {
    config('config/order-service/order-service-config.yaml');
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

**Kubernetes hosting:**

```yaml
production:
  platform: kubernetes
```

**AWS hosting:**

```yaml
production:
  platform: ecs-fargate    # Recommended for most workloads
  # platform: ecs-ec2      # When you need EC2 control
  # platform: lambda       # For event-driven functions
  # platform: app-runner   # Fully managed container service
  # platform: eks          # When using EKS cluster
```

**Azure hosting:**

```yaml
production:
  platform: container-apps   # Recommended for containers
  # platform: functions      # For event-driven functions
  # platform: aks            # When using AKS cluster
  # platform: app-service    # For web apps
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

**File:** `config/<service-name>/datasources.yaml`

**Referenced in:** `rdbms`, `cache`, `pubsub`, `nosql` blocks

```dtrx
service OrderService {
    rdbms db('config/order-service/datasources.yaml') { ... }
    cache redis('config/order-service/datasources.yaml') { ... }
    pubsub mq('config/order-service/datasources.yaml') { ... }
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

**File:** `config/<service-name>/registration.yaml`

**Referenced in:** Service block

```dtrx
service OrderService {
    registration('config/order-service/registration.yaml');
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

**File:** `config/<service-name>/resilience.yaml`

**Referenced in:** Service block

```dtrx
service OrderService {
    resilience('config/order-service/resilience.yaml');
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

---

## Gateway Configuration

**File:** `config/gateway.yaml`

**Referenced in:** System block

```dtrx
system {
    gateway('config/gateway.yaml');
}
```

### Complete Example

```yaml
test:
  type: nginx                      # nginx, kong, traefik, aws-alb, azure-agw
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
| `type` | String | Gateway type (nginx, kong, aws-alb, etc.) |
| `host` | String | Gateway host |
| `port` | Integer | Gateway port |
| `cors` | Object | CORS configuration |
| `rateLimit` | Object | Rate limiting configuration |
| `authentication` | Object | Authentication configuration |

---

## Registry Configuration

**File:** `config/registry.yaml`

**Referenced in:** System block

```dtrx
system {
    registry('config/registry.yaml');
}
```

### Example

```yaml
test:
  type: consul                     # consul, eureka, etcd, kubernetes
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

**File:** `config/observability.yaml`

**Referenced in:** System block

```dtrx
system {
    observability('config/observability.yaml');
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
    storage files config('config/order-service/storage.yaml') { ... }
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
job ProcessOrders cron('0 * * * *') config('config/jobs.yaml') { ... }
```

### Example

```yaml
test:
  ProcessOrders:
    timeout: 300000            # 5 minutes
    retryLimit: 3
    retryBackoff: exponential

  CleanupExpired:
    timeout: 600000            # 10 minutes
    retryLimit: 5
    retryBackoff: linear

production:
  ProcessOrders:
    timeout: 900000            # 15 minutes
    retryLimit: 5
    retryBackoff: exponential
```

---

## Integrations Configuration

**File:** `config/<service-name>/integrations.yaml`

**Referenced in:** Service block

```dtrx
service OrderService {
    integrations('config/order-service/integrations.yaml');
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

## Platform-Specific Configuration

### Docker Platform

No additional config file — settings in `system-config.yaml`:

```yaml
production:
  hosting: docker
  registry: registry.example.com  # Optional: private registry
```

### Kubernetes Platform

Namespace and labels configured per-service:

```yaml
production:
  platform: kubernetes
  namespace: ecommerce           # Kubernetes namespace
  labels:
    app: order-service
    environment: production
```

### AWS Platform

Network and IAM configuration:

```yaml
production:
  hosting: aws
  region: us-east-1
  network:
    vpcId: vpc-abc123
    appSubnets: [subnet-app-1, subnet-app-2]
    dataSubnets: [subnet-data-1, subnet-data-2]
  iam:
    roleArn: arn:aws:iam::123456789012:role/OrderServiceRole
```

### Azure Platform

Resource group and managed identity:

```yaml
production:
  hosting: azure
  location: eastus
  resourceGroup: ecommerce-rg
  identity:
    type: system-assigned        # system-assigned or user-assigned
```

---

## Environment Variables

Use environment variables for sensitive values:

```yaml
rdbms:
  password: ${POSTGRES_PASSWORD}
  # Or with default: ${POSTGRES_PASSWORD:defaultpass}
```

**Best practices:**

✅ Always use env vars for secrets (passwords, API keys, tokens)
✅ Use `${VAR}` syntax without defaults for required secrets
✅ Use `${VAR:default}` syntax only for non-sensitive optional values
✅ Never commit secrets to version control

---

## Secrets Management

### AWS Secrets Manager

```yaml
production:
  secrets:
    provider: aws-secrets-manager
    region: us-east-1
    secrets:
      database_password: /ecommerce/prod/db-password
      jwt_secret: /ecommerce/prod/jwt-secret
```

### Azure Key Vault

```yaml
production:
  secrets:
    provider: azure-key-vault
    vaultUrl: https://ecommerce-vault.vault.azure.net
    secrets:
      database-password: db-password
      jwt-secret: jwt-secret
```

**Generated code:**
- Fetches secrets at runtime
- Caches secrets with TTL
- Automatic rotation support

---

## Configuration Validation

All configuration is validated at generation time:

```bash
datrix generate -p production -s specs/system.dtrx -o ./generated
```

**Validation checks:**

✅ Required fields present
✅ Field types correct
✅ Enum values valid
✅ Cross-field constraints (e.g., min <= max)
✅ Platform consistency (e.g., no Azure flavor on AWS hosting)
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
  hosting: docker

production:
  language: python
  hosting: aws
  region: us-east-1

# ❌ Bad: Different fields per profile
test:
  language: python

production:
  hosting: aws  # Missing language!
```

### 2. Environment Variables for Secrets

```yaml
# ✅ Good
rdbms:
  password: ${POSTGRES_PASSWORD}

# ❌ Bad
rdbms:
  password: mypassword123
```

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
ConfigValidationError: Field 'language' is required in system-config.yaml profile 'production'
```

**Fix:** Add the missing field to the profile.

### Error: Invalid enum value

```
ConfigValidationError: Invalid value 'mysqll' for field 'engine'. Valid options: postgres, mysql, mariadb
```

**Fix:** Check spelling and use valid option.

### Error: Platform consistency

```
PlatformValidationError: Service platform 'compose' is incompatible with hosting 'aws'
```

**Fix:** Use compatible platform (e.g., `ecs-fargate` for AWS).

---

## Reference

**Configuration file locations:**

```
config/
├── system-config.yaml              # System configuration
├── gateway.yaml                    # API gateway
├── registry.yaml                   # Service registry
├── observability.yaml              # Observability
└── <service-name>/
    ├── service-config.yaml        # Service deployment
    ├── datasources.yaml           # Database/cache/pubsub
    ├── registration.yaml          # Service metadata
    ├── resilience.yaml            # Circuit breaker/retry
    ├── storage.yaml               # File storage
    ├── jobs.yaml                  # Job configuration
    └── integrations.yaml          # External integrations
```

---

**Last Updated:** 2026-03-28
