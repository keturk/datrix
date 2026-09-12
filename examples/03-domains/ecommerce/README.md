# E-commerce Platform

A complete e-commerce platform with product catalog, shopping cart, orders, payments, and shipping.

## Services

| Service | Port | Description |
|---------|------|-------------|
| UserService | 8000 | Customer accounts, authentication, and sessions |
| ProductService | 8001 | Product catalog, inventory, and reservations |
| OrderService | 8002 | Shopping cart, orders, and transaction orchestration |
| PaymentService | 8003 | Payment processing, refunds, and transactions |
| ShippingService | 8004 | Shipping rates, carriers, and tracking |

## Infrastructure

### Databases
- **PostgreSQL** - Each service has its own database (database-per-service pattern)
  - `ecommerce_users` - User accounts and sessions
  - `ecommerce_products` - Product catalog and inventory
  - `ecommerce_orders` - Orders and line items
  - `ecommerce_payments` - Payment transactions
  - `ecommerce_shipping` - Shipments and tracking
- **MongoDB** - Document store for semi-structured data
  - `ecommerce_product_reviews` - Product reviews and browsing analytics

### Message Queue
- **Kafka** - Event-driven communication between services
  - Topics: `UserEvents`, `ProductEvents`, `OrderEvents`, `PaymentEvents`, `ShippingEvents`

### Caching
- **Redis** - Session storage and query caching

### Object Storage
- **S3/MinIO** - Product images and thumbnails

### Service Discovery
- **Consul**

### Observability
- **Prometheus** - Metrics collection
- **Jaeger** - Distributed tracing
- **JSON logging** - Structured logs with trace correlation

### API Gateway
- **JWT authentication** (RS256)
- **Rate limiting** per API and user
- **CORS** configuration for web clients

## Key Features

- Product catalog with categories, variants, and inventory tracking
- Inventory reservation system with TTL for cart holds
- Order workflow (pending â†’ paid â†’ shipped â†’ delivered)
- Distributed transactions using two-phase reservation
- Multiple payment provider support with idempotency
- Shipping rate calculation and carrier integration
- Event-driven notifications across services
- Circuit breakers and retry policies for resilience

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

The cloud profiles declare CloudWatch / Azure Monitor metrics; a language whose
generator does not realize those providers is rejected at generation time with
the provider it does realize.

## Files

config/ contains the ConfigDSL files referenced by system.dtrx and each service:
    - config/notification-service.dcfg
    - config/order-service.dcfg
    - config/payment-service.dcfg
    - config/product-service.dcfg
    - config/shipping-service.dcfg
    - config/system.dcfg
    - config/user-service.dcfg

## Architecture

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚   Gateway   â”‚â”€â”€â”€â”€â–¶â”‚ UserService â”‚â”€â”€â”€â”€â–¶â”‚  PostgreSQL â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
       â”‚                   â”‚
       â”‚            â”Œâ”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”
       â”‚            â”‚    Kafka    â”‚
       â”‚            â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”˜
       â”‚                   â”‚
       â–¼                   â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚OrderService â”‚â”€â”€â”€â”€â–¶â”‚PaymentSvc   â”‚â”€â”€â”€â”€â–¶â”‚ShippingServiceâ”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
       â”‚                   â”‚                   â”‚
       â–¼                   â–¼                   â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  PostgreSQL â”‚     â”‚  PostgreSQL â”‚     â”‚  PostgreSQL â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

