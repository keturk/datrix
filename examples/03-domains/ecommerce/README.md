# E-commerce Platform

A complete e-commerce platform with product catalog, shopping cart, orders, payments,
shipping, and order notifications — six services, one `system.dtrx`.

## Services

| Service | Port | Description |
|---------|------|-------------|
| UserService | 8006 | Customer accounts, authentication, and sessions |
| ProductService | 8004 | Product catalog, inventory, reservations, reviews, and images |
| OrderService | 8002 | Shopping cart, orders, and transaction orchestration |
| PaymentService | 8003 | Payment processing, refunds, and transactions |
| ShippingService | 8005 | Shipping rates, carriers, and tracking |
| NotificationService | 8001 | Order-confirmation consumer (email) |

## Infrastructure

### Databases
- **PostgreSQL** — every service declares its own `rdbms` block (`userDb`, `productDb`,
  `orderDb`, `paymentDb`, `shippingDb`, `notificationDb`); `paymentDb` is audited
- **MongoDB** — `docdb` on ProductService for product reviews and browsing analytics

### Messaging
- **Kafka** — the `mq` pub/sub block on every publishing service; topics `UserEvents`,
  `ProductEvents`, `OrderEvents`, `PaymentEvents`, `ShipmentEvents`
- **RabbitMQ** — OrderService's work queues (`ProcessPayment`, `SendOrderConfirmation`,
  `SettlePayment` with FIFO ordering per merchant)

### Caching
- **Redis** — session storage and query caching on User, Product, Order, and Shipping

### Object Storage
- **S3 / MinIO** — product images and thumbnails (`store` on ProductService)

### Identity and Gateway
- **Zitadel** (self-hosted on the compose profiles; Cognito / Entra on the cloud profiles)
  behind an nginx gateway with **JWT (RS256)** enforcement, per-API rate limiting, and CORS

### Observability
- **Prometheus**, **Jaeger**, **Loki**, **Grafana**, **Alertmanager** on the compose profiles;
  CloudWatch / X-Ray and Azure Monitor / Application Insights on the cloud profiles

### Background Work
- Scheduled `jobs` on Product, Order, and Shipping; service discovery via Consul

## Key Features

- Product catalog with categories, variants, and inventory tracking
- Inventory reservation system with TTL for cart holds
- Order workflow (pending → paid → shipped → delivered)
- Distributed transactions using two-phase reservation
- Multiple payment provider support with idempotency
- Shipping rate calculation and carrier integration
- Event-driven notifications across services
- Circuit breakers and retry policies for resilience

## Apps

Two frontend apps are written in the same `.dtrx` language as the services and generated in
the same run, under the generated project's `clients/<target>/`. Both import the shared
[`ui.dtrx`](ui.dtrx) module (the `Brand` theme, the `Panel` and `StatusBadge` components).

| App | Audience | Targets | Pages | Config |
|-----|----------|---------|-------|--------|
| [Storefront](storefront-app.dtrx) | Customers | web (Angular), mobile (Flutter) | `/`, `/products`, `/products/:slug`, `/cart`, `/orders`, `/orders/new`, `/orders/:id`; `/shop` redirects to `/products` | [`config/storefront-app.dcfg`](config/storefront-app.dcfg) |
| [Admin](admin-app.dtrx) | Staff | web (Angular) | `/products` (list, detail and edit of the product catalog) | [`config/admin-app.dcfg`](config/admin-app.dcfg) |

- **Derived, not restated.** Neither app declares a route table, a login, a guard or a form
  field list: routes come from `@path`, each page's guard and the hosted login from the auth
  of the endpoints it reaches, and every form and table from the backend struct it binds.
  The Admin `workspace` narrows every catalog page to the `admin` role with one `auth(...)`.
- **Text lives in strings files.** Every user-visible string is a `Msg.<key>` or a derived
  label resolved from [`config/strings/storefront.en-US.dcfg`](config/strings/storefront.en-US.dcfg)
  (the system's `defaultLocale`) and [`storefront.tr-TR.dcfg`](config/strings/storefront.tr-TR.dcfg).
- **Push.** The Storefront declares `push : targets(flutter)`; the device registry is
  injected into `NotificationService`, the one used service that configures
  `integrations.push`.
- **Hosting.** The compose profiles serve the Storefront on port 4200 and Admin on 4300; the
  `aws`, `azure` and `azureVm` profiles serve them at `shop.` and `admin.` custom domains and
  sign the Storefront's mobile release with handles the operator supplies.
- **Tests.** The Storefront's three `test(...)` blocks generate one Vitest spec on Angular and
  one widget test on Flutter each.

## Usage

The target language is a generation parameter; the deployment target is selected
by the ConfigDSL profile in `config/system.dcfg`.

```bash
# Local docker-compose stack (the default profile, `test`)
datrix generate -s examples/03-domains/ecommerce/system.dtrx -L python

# Same stack for another language
datrix generate -s examples/03-domains/ecommerce/system.dtrx -L typescript
```

| Profile | Target | Notes |
|---------|--------|-------|
| `test`, `development`, `production` | docker-compose on the developer machine | nginx gateway, self-hosted Zitadel, Prometheus/Jaeger/Loki/Grafana/Alertmanager |
| `aws` | ECS Fargate | managed API Gateway, RDS, ElastiCache, MSK, SQS, DocumentDB, S3, CloudWatch/X-Ray, AppConfig, Cognito |
| `azure` | Web App for Containers | API Management, Flexible Server, Azure Cache for Redis, Event Hubs (pooled namespace), Service Bus, Cosmos DB, Blob Storage, Azure Monitor/Application Insights, App Configuration, Entra |
| `azureVm` | docker-compose on one Azure VM | the `compose` stack behind API Management with PostgreSQL and blob storage on the managed Flexible Server and Storage Account |

```bash
datrix generate -s examples/03-domains/ecommerce/system.dtrx -L python --profile aws
```

Every language realizes the `aws` profile's CloudWatch metrics (the service exposes
the same Prometheus endpoint a CloudWatch-agent sidecar scrapes). Today only
`-L python` generates the `aws` profile end to end: the profile's service-level
`subscribe`/`enqueue` consumers are deployed as Lambda functions on AWS and
`datrix-codegen-aws` packages Lambda images for Python only (`-L java`/`-L dotnet`
are rejected naming those consumers), and the MSK broker endpoints are deploy-resolved,
which the TypeScript runtime cannot bind (`-L typescript` is rejected at the pubsub
block). The `azure` profile's Azure Monitor metrics are realized by Python alone;
other languages are rejected naming the provider they do realize.

## Generated Code

[generated/](generated/) holds the output of the local docker-compose profile (`test`),
one directory per registered language, exactly as `datrix generate` wrote it:

| Directory | Language | Stack |
|-----------|----------|-------|
| [generated/python-docker/](generated/python-docker/) | Python 3 | FastAPI, SQLAlchemy (async), Alembic |
| [generated/typescript-docker/](generated/typescript-docker/) | TypeScript | NestJS, MikroORM |
| [generated/dotnet-docker/](generated/dotnet-docker/) | C# / .NET 10 | ASP.NET Core, EF Core, FluentMigrator |
| [generated/java-docker/](generated/java-docker/) | Java 25 | Spring Boot, Spring Data JPA, Liquibase |

The directory name is `<language>-<platform>`; a snapshot of a cloud profile would sit
beside these as, for example, `python-aws/`.

Each directory is a runnable project: `README.md` (quick start), `docker-compose.yml`, one
package per service, `config/` (gateway, identity, observability), `scripts/` (deploy,
init), `clients/` (the shared client contract), and the project's own `.gitignore`. Compare
the same service across the four trees — for example `ecommerce_order_service/` — to see
how one `.dtrx` body renders in each language.

Three kinds of file are deliberately absent from the checked-in copies, because
`datrix generate` writes them and a commit must not carry them:

- **build output** (`bin/`, `obj/`, `target/`, `node_modules/`, `__pycache__/`);
- **`.datrix/`** — the run's manifests and snapshots, used only for incremental regeneration;
- **`secrets/<service>/`** — the per-service file-backed secrets the compose stack mounts at
  `/run/secrets`. The generated `.gitignore` excludes them, and `datrix generate` recreates
  them, together with the matching `.env.example`, on every run. The development RS256 JWT
  key pair directly under `secrets/` is a fixed development key shipped by the generator, not
  a credential.

To run one of them, regenerate into a scratch directory (that restores `secrets/`) or run
`datrix generate` against this example and follow the generated `README.md`.

## Files

`config/` contains the ConfigDSL files referenced by `system.dtrx` and each service:

- `config/system.dcfg`
- `config/identity/identity.dcfg`
- `config/user-service.dcfg`
- `config/product-service.dcfg`
- `config/order-service.dcfg`
- `config/payment-service.dcfg`
- `config/shipping-service.dcfg`
- `config/notification-service.dcfg`
- `config/storefront-app.dcfg`, `config/admin-app.dcfg`
- `config/strings/storefront.en-US.dcfg`, `config/strings/storefront.tr-TR.dcfg`

`assets/` holds the Storefront's logo, launcher icon and splash image.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Gateway   │────▶│ UserService │────▶│  PostgreSQL │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       │            ┌──────▼──────┐
       │            │    Kafka    │
       │            └──────┬──────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌───────────────┐
│OrderService │────▶│ PaymentSvc  │────▶│ShippingService│
└─────────────┘     └─────────────┘     └───────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  PostgreSQL │     │  PostgreSQL │     │  PostgreSQL │
└─────────────┘     └─────────────┘     └─────────────┘
```
