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
- **Consul** (development) / **Kubernetes** (production)

### Observability
- **Prometheus** - Metrics collection
- **Jaeger** - Distributed tracing
- **JSON logging** - Structured logs with trace correlation

### API Gateway
- **JWT authentication** (HS256)
- **Rate limiting** per API and user
- **CORS** configuration for web clients

## Key Features

- Product catalog with categories, variants, and inventory tracking
- Inventory reservation system with TTL for cart holds
- Order workflow (pending → paid → shipped → delivered)
- Distributed transactions using two-phase reservation
- Multiple payment provider support with idempotency
- Shipping rate calculation and carrier integration
- Event-driven notifications across services
- Circuit breakers and retry policies for resilience

## Usage

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/ecommerce/system.dtrx -l python -p docker

# Generate TypeScript services with Kubernetes
datrix generate examples/02-domains/ecommerce/system.dtrx -l typescript -p kubernetes
```

## Files

```
ecommerce/
├── system.dtrx                 # Entry point - system configuration
├── common.dtrx                 # Shared types (Money, Address, Currency, etc.)
├── user-service.dtrx           # User accounts and authentication
├── product-service.dtrx        # Product catalog and inventory
├── order-service.dtrx          # Orders and transaction orchestration
├── payment-service.dtrx        # Payment processing
├── shipping-service.dtrx       # Shipping and tracking
└── config/
    ├── config.yaml             # Application configuration
    ├── discovery.yaml          # Service discovery (Consul/Kubernetes)
    ├── gateway.yaml            # API gateway (JWT, rate limits, CORS)
    ├── observability.yaml      # Metrics, tracing, logging
    ├── user-service/
    │   ├── datasources.yaml    # PostgreSQL, Redis, Kafka
    │   ├── resilience.yaml     # Timeouts, retries, circuit breakers
    │   ├── registration.yaml   # Service registration
    ├── product-service/
    │   └── ...
    ├── order-service/
    │   └── ...
    ├── payment-service/
    │   └── ...
    └── shipping-service/
        └── ...
```

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
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│OrderService │────▶│PaymentSvc   │────▶│ShippingService│
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  PostgreSQL │     │  PostgreSQL │     │  PostgreSQL │
└─────────────┘     └─────────────┘     └─────────────┘
```
