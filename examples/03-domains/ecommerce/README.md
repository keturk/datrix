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

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/ecommerce/system.dtrx -l python -p docker

# Generate TypeScript services with Kubernetes
datrix generate examples/02-domains/ecommerce/system.dtrx -l typescript -p kubernetes
```

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

