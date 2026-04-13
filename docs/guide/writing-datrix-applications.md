# Writing Datrix Applications

**A comprehensive guide to building applications with Datrix**

This guide teaches you how to write complete, production-ready Datrix applications. You'll learn how to structure your code, define entities and services, configure infrastructure, and follow best practices for maintainable, scalable microservices.

---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [File Structure and Includes](#file-structure-and-includes)
4. [System Block](#system-block)
5. [Services](#services)
6. [Entities](#entities)
7. [Type System](#type-system)
8. [Relationships](#relationships)
9. [Traits and Inheritance](#traits-and-inheritance)
10. [Enums and Structs](#enums-and-structs)
11. [REST APIs](#rest-apis)
12. [Event-Driven Messaging](#event-driven-messaging)
13. [Caching](#caching)
14. [Background Jobs](#background-jobs)
15. [CQRS](#cqrs)
16. [Storage](#storage)
17. [Validation and Computed Fields](#validation-and-computed-fields)
18. [Lifecycle Hooks](#lifecycle-hooks)
19. [Service Discovery and Resilience](#service-discovery-and-resilience)
20. [Multi-Tenancy](#multi-tenancy)
21. [Best Practices](#best-practices)
22. [Common Patterns](#common-patterns)

---

## Overview

Datrix is a domain-specific language for defining microservice architectures. You write **declarative specifications** in `.dtrx` files that describe:
- **Data models** (entities with fields, relationships, validation)
- **APIs** (REST endpoints with automatic CRUD generation)
- **Events** (publish/subscribe messaging patterns)
- **Infrastructure** (databases, caches, message brokers)
- **Business logic** (lifecycle hooks, background jobs, custom functions)

From these specifications, Datrix generates production-ready code in your target language (Python/FastAPI, TypeScript/NestJS) with all the boilerplate, infrastructure wiring, and deployment configurations.

### Key Benefits

✅ **Type-safe by design** — All types are validated at specification time
✅ **DRY principle** — Define once, generate everywhere
✅ **Platform-agnostic** — Same spec works for Docker, Kubernetes, AWS, Azure
✅ **Fail-fast validation** — Errors caught before code generation
✅ **Zero boilerplate** — No manual CRUD, no manual API routing
✅ **Production-ready output** — Proper error handling, logging, observability

---

## Project Structure

A typical Datrix project follows this structure:

```
my-project/
├── specs/                          # .dtrx specification files
│   ├── system.dtrx                # Entry point (system block + includes)
│   ├── common/                    # Shared modules
│   │   ├── traits.dtrx           # Reusable trait definitions
│   │   └── entities.dtrx         # Shared abstract entities
│   └── services/                  # Service definitions
│       ├── user-service.dtrx
│       ├── order-service.dtrx
│       └── payment-service.dtrx
├── config/                        # Configuration files (YAML)
│   ├── system-config.yaml        # System-level config (language, hosting)
│   ├── gateway.yaml              # API gateway config
│   ├── registry.yaml             # Service registry config
│   ├── observability.yaml        # Observability config
│   ├── user-service/             # Per-service configs
│   │   ├── service-config.yaml   # Service deployment config
│   │   ├── datasources.yaml      # Database/cache/pubsub config
│   │   ├── registration.yaml     # Service metadata
│   │   └── resilience.yaml       # Circuit breaker, retry, etc.
│   └── order-service/
│       ├── service-config.yaml
│       └── datasources.yaml
└── generated/                     # Generated code (managed by Datrix)
    ├── user-service/
    │   ├── app/                  # Python/TypeScript application code
    │   ├── sql/                  # Database migrations
    │   └── docker-compose.yml    # Docker configuration
    └── order-service/
        └── ...
```

### Directory Conventions

| Directory | Purpose | Managed By |
|-----------|---------|------------|
| `specs/` | `.dtrx` specification files | You (version controlled) |
| `config/` | YAML configuration files | You (version controlled) |
| `generated/` | Generated application code | Datrix CLI (overwritten on regeneration) |

> **💡 Tip:** Only edit files in `specs/` and `config/`. Never manually edit `generated/` — your changes will be lost on next generation.

### Layout used in `examples/`

The official [`examples/`](../../examples/) trees usually place **`system.dtrx` and `*.dtrx` service files at the project root** beside a **`config/`** directory. Paths in `include '…'` and `config('…')` are **relative to the file** that contains them. A nested **`specs/`** layout (as sketched above) is equally valid for larger repos—keep paths consistent.

---

## File Structure and Includes

Every Datrix application starts with a **system block** that includes service and module definitions.

### Entry Point: system.dtrx

```dtrx
// specs/system.dtrx
include 'common/traits.dtrx';
include 'common/entities.dtrx';
include 'services/user-service.dtrx';
include 'services/order-service.dtrx';

system ecommerce.System : version('1.0.0') {
    config('config/system-config.yaml');
    registry('config/registry.yaml');
    gateway('config/gateway.yaml');
    observability('config/observability.yaml');
}
```

### Includes

Use `include` to compose your application from multiple files:

```dtrx
include 'common/traits.dtrx';          // Shared traits
include 'common/entities.dtrx';        // Abstract entities
include 'services/order-service.dtrx'; // Service definitions
```

**Rules:**
- Include paths are relative to the file containing the `include` statement
- Files can be included multiple times (Datrix deduplicates)
- Circular includes are detected and rejected
- All includes must resolve before compilation begins

### Imports

Use `from ... import` to reference definitions from modules:

```dtrx
from ecommerce.common import Auditable, BaseEntity, SoftDeletable;

service ecommerce.OrderService : version('1.0.0') {
    rdbms db('config/datasources.yaml') {
        entity Order extends BaseEntity with Auditable {
            // Fields here
        }
    }
}
```

---

## System Block

The **system block** defines global infrastructure shared by all services.

```dtrx
system ecommerce.System : version('1.0.0') {
    config('config/system-config.yaml');
    registry('config/registry.yaml');
    gateway('config/gateway.yaml');
    observability('config/observability.yaml');
}
```

### System Configuration

Each system attribute points to a YAML configuration file:

| Attribute | Config File | Purpose |
|-----------|-------------|---------|
| `config()` | `system-config.yaml` | Language, hosting platform, deployment settings |
| `registry()` | `registry.yaml` | Service discovery/registry (Consul, Eureka, etc.) |
| `gateway()` | `gateway.yaml` | API gateway (routing, authentication, rate limiting) |
| `observability()` | `observability.yaml` | Tracing, metrics, logging, alerting |

**system-config.yaml example:**

```yaml
test:
  language: python         # "python" or "typescript"
  hosting: docker          # "docker", "kubernetes", "aws", "azure"
  defaultTimeout: 30000    # Default request timeout (ms)

production:
  language: python
  hosting: aws
  region: us-east-1
  network:
    vpcId: vpc-abc123
    appSubnets: [subnet-app-1, subnet-app-2]
    dataSubnets: [subnet-data-1, subnet-data-2]
```

> **📖 Reference:** See [Configuration Guide](./configuration-guide.md#system-configuration) for complete system config reference.

---

## Services

A **service** is the unit of deployment. Everything inside a service block belongs to that service and is generated as a single deployable application.

### Basic Service

```dtrx
service ecommerce.OrderService : version('1.0.0'), description('Order management') {
    config('config/order-service/service-config.yaml');
    registration('config/order-service/registration.yaml');

    discovery { }  // Service discovery config

    rdbms db('config/order-service/datasources.yaml') {
        // Entities here
    }

    rest_api OrderAPI : basePath('/api/v1/orders') {
        // API endpoints here
    }
}
```

### Service Attributes

Services support these attributes:

| Attribute | Required | Purpose |
|-----------|----------|---------|
| `version('1.0.0')` | Yes | Service version |
| `description('...')` | No | Human-readable description |

### Service Configuration Blocks

| Block | Config File | Purpose |
|-------|-------------|---------|
| `config()` | `service-config.yaml` | Platform, replicas, resources, health checks |
| `registration()` | `registration.yaml` | Service metadata for registry |
| `discovery { }` | Inline | Dependencies on other services |
| `resilience()` | `resilience.yaml` | Circuit breaker, retry policies, bulkhead |

### Service Discovery

Declare dependencies on other services:

```dtrx
discovery {
    UserService {
        loadBalance: roundRobin,
        healthyOnly: true
    }
    PaymentService {
        loadBalance: leastConnections,
        healthyOnly: true
    }
}
```

This generates service clients with load balancing and health checking.

---

## Entities

Entities define your data model. Each entity maps to:
- Database table
- ORM model class
- API request/response schemas
- TypeScript interfaces (if generating TS)

### Basic Entity

```dtrx
rdbms db('config/datasources.yaml') {
    entity User {
        UUID id : primaryKey = uuid();
        String(100) name : trim;
        Email email : unique, index;
        DateTime createdAt = now();
        DateTime updatedAt = now();
    }
}
```

### Field Definition

```dtrx
<Type> <fieldName> [: <modifiers>] [= <defaultValue>];
```

**Examples:**

```dtrx
String(200) title : trim;                   // Required string, trimmed
String? description;                        // Nullable string
Email email : unique, index;                // Email with unique constraint
Boolean isActive = true;                    // Boolean with default
UUID authorId -> db.Author : index;         // Foreign key with index
Money totalAmount : min(0);                 // Money field, must be >= 0
DateTime? publishedAt;                      // Nullable datetime
List<String> tags;                          // Array/list field
```

### Field Modifiers

| Modifier | Applies To | Effect |
|----------|------------|--------|
| `primaryKey` | UUID, Integer | Primary key constraint |
| `unique` | Any field | Unique constraint |
| `index` | Any field, relationships | Database index for faster lookups |
| `trim` | String | Trim whitespace on input |
| `lowercase` | String | Convert to lowercase on input |
| `uppercase` | String | Convert to uppercase on input |
| `hidden` | Any field | Exclude from API responses |
| `immutable` | Any field | Include in Create, exclude from Update |
| `min(n)`, `max(n)` | Numeric | Value constraints |
| `sortable` | Any field | Enable sorting in list APIs |
| `filterable` | Any field | Enable filtering in list APIs |

### Server-Managed Fields

Prefix a field with `@` to mark it as server-managed (not accepted in API input):

```dtrx
entity Order {
    @UUID id : primaryKey = uuid();        // Server generates on create
    @DateTime createdAt = now();           // Server sets on create
    @DateTime updatedAt = now();           // Server updates on save
    String(200) customerName : trim;       // Client provides
}
```

**API behavior:**
- `@` fields excluded from Create/Update request schemas
- Always included in response schemas
- Values set by server, not client

---

## Type System

Datrix provides a rich type system that maps to appropriate types in each target language and database.

### Primitive Types

| Datrix Type | Python | TypeScript | PostgreSQL | MySQL |
|-------------|--------|------------|------------|-------|
| `String` | `str` | `string` | `TEXT` | `VARCHAR` |
| `String(n)` | `str` | `string` | `VARCHAR(n)` | `VARCHAR(n)` |
| `Text` | `str` | `string` | `TEXT` | `TEXT` |
| `Integer` | `int` | `number` | `INTEGER` | `INT` |
| `Float` | `float` | `number` | `DOUBLE PRECISION` | `DOUBLE` |
| `Boolean` | `bool` | `boolean` | `BOOLEAN` | `BOOLEAN` |
| `Decimal(p,s)` | `Decimal` | `number` | `NUMERIC(p,s)` | `DECIMAL(p,s)` |
| `Bytes` | `bytes` | `Buffer` | `BYTEA` | `BLOB` |

### Domain Types

| Datrix Type | Validation | Python | TypeScript |
|-------------|-----------|--------|------------|
| `UUID` | UUID format | `UUID` | `string` |
| `Email` | Email format | `str` | `string` |
| `URL` | URL format | `str` | `string` |
| `Phone` | Phone number | `str` | `string` |
| `IPAddress` | IP address | `str` | `string` |
| `JSON` | Valid JSON | `dict` | `object` |
| `Slug` | URL-safe string | `str` | `string` |
| `Money` | Decimal currency | `Decimal` | `number` |
| `Percentage` | 0-100 range | `float` | `number` |
| `Color` | Hex color code | `str` | `string` |
| `CountryCode` | ISO 3166-1 alpha-2 | `str` | `string` |
| `LanguageCode` | ISO 639-1 | `str` | `string` |
| `CurrencyCode` | ISO 4217 | `str` | `string` |
| `PostalCode` | Postal code | `str` | `string` |
| `Latitude` | -90 to 90 | `float` | `number` |
| `Longitude` | -180 to 180 | `float` | `number` |
| `CreditCard` | Credit card number | `str` | `string` |
| `IBAN` | IBAN format | `str` | `string` |
| `Password` | Hashed password | `str` | `string` |

### Temporal Types

| Datrix Type | Python | TypeScript | PostgreSQL |
|-------------|--------|------------|------------|
| `DateTime` | `datetime` | `Date` | `TIMESTAMP` |
| `UDateTime` | `datetime` (UTC) | `Date` | `TIMESTAMP` |
| `Date` | `date` | `Date` | `DATE` |
| `Time` | `time` | `string` | `TIME` |
| `Duration` | `timedelta` | `number` (ms) | `INTERVAL` |
| `Timestamp` | `datetime` | `Date` | `TIMESTAMP` |

### Collection Types

```dtrx
List<String> tags;              // Array of strings
Map<String, Integer> counts;    // Key-value map
Set<String> categories;         // Unique set
```

### Nullability

Add `?` suffix to make a field nullable:

```dtrx
String? description;           // Nullable string
DateTime? deletedAt;           // Nullable datetime
UUID? parentId;                // Nullable UUID
```

> **⚠️ Warning:** Use nullable fields sparingly. Non-null fields with proper defaults are easier to work with and reduce null-check boilerplate.

---

## Relationships

Datrix supports four relationship types: `belongsTo`, `hasOne`, `hasMany`, and `manyToMany`.

### BelongsTo (Many-to-One)

```dtrx
entity Post {
    UUID id : primaryKey = uuid();
    String(200) title;
    belongsTo User as author : index;     // Foreign key to User
}

entity User {
    UUID id : primaryKey = uuid();
    String(100) name;
}
```

**Generated:**
- `Post` table gets `author_id` column (UUID, foreign key to `users.id`)
- `Post` Python model gets `author_id: UUID` field
- Database foreign key constraint created
- Index created on `author_id` (because of `: index`)

**Cascade options:**

```dtrx
belongsTo User as author : cascade(delete);  // Cascade delete
belongsTo User as author : restrict;         // Prevent delete if referenced
belongsTo User as author : setNull;          // Set FK to null on delete
```

### HasMany (One-to-Many)

```dtrx
entity User {
    UUID id : primaryKey = uuid();
    String(100) name;
    hasMany Post as posts;                // Inverse of belongsTo
}

entity Post {
    UUID id : primaryKey = uuid();
    belongsTo User as author : index;
}
```

**Generated:**
- `User` Python model gets `posts: List[Post]` property (lazy-loaded)
- No database schema changes (foreign key is on `Post`)

### HasOne (One-to-One)

```dtrx
entity User {
    UUID id : primaryKey = uuid();
    String(100) name;
    hasOne Profile;                       // One-to-one relationship
}

entity Profile {
    UUID id : primaryKey = uuid();
    belongsTo User : unique;              // unique makes it one-to-one
    String bio;
}
```

**Generated:**
- `Profile.user_id` is unique (one profile per user)
- `User` model gets `profile: Profile | None` property

### ManyToMany

```dtrx
entity Post {
    UUID id : primaryKey = uuid();
    String(200) title;
    manyToMany Tag as tags through PostTag;
}

entity Tag {
    UUID id : primaryKey = uuid();
    String(50) name : unique;
    manyToMany Post as posts through PostTag;
}
```

**Generated:**
- Junction table `post_tags` with `post_id` and `tag_id` columns
- Both entities get many-to-many collection properties
- Both sides must declare the `manyToMany` relationship

> **📖 Reference:** See [Datrix Syntax Reference](../../../datrix-language/docs/reference/datrix-syntax-reference.md) for complete relationship syntax including `onSoftDelete`, `noTree`, and other modifiers.

### Self-Referential Relationships

```dtrx
entity Category {
    UUID id : primaryKey = uuid();
    String(100) name;
    belongsTo Category as parent;        // Self-reference
    hasMany Category as children;        // Inverse
}
```

**Tree Helpers:**

When an entity has both self-referential `belongsTo` and `hasMany`, Datrix generates tree navigation methods:
- SQL CHECK constraint preventing self-reference
- Python: `get_ancestors()`, `get_descendants()`, `get_roots()`, `list_by_parent_id()`
- TypeScript: `@Tree('closure-table')`, `@TreeParent()`, `@TreeChildren()`

**Disable tree helpers:**

```dtrx
hasMany Employee as directReports : noTree;  // Plain one-to-many
```

---

## Traits and Inheritance

### Traits

Traits are reusable field groups that can be mixed into entities.

**Define traits in a module:**

```dtrx
// specs/common/traits.dtrx
module ecommerce.common {
    trait Auditable {
        String? createdBy;
        String? updatedBy;
        DateTime? lastModifiedAt;
    }

    trait SoftDeletable {
        DateTime? deletedAt;
        String? deletedBy;
    }

    trait Timestamped {
        @DateTime createdAt = now();
        @DateTime updatedAt = now();
    }
}
```

**Use traits with `with`:**

```dtrx
from ecommerce.common import Auditable, SoftDeletable, Timestamped;

entity Order extends BaseEntity with Auditable, SoftDeletable {
    UUID customerId;
    Money totalAmount;
    // Inherits: createdBy, updatedBy, lastModifiedAt, deletedAt, deletedBy
}
```

### Abstract Entities

Abstract entities provide base fields and cannot be instantiated directly.

```dtrx
module ecommerce.common {
    abstract entity BaseEntity with Timestamped {
        @UUID id : primaryKey = uuid();
        // Inherits: createdAt, updatedAt from Timestamped
    }
}
```

**Extend abstract entities:**

```dtrx
entity User extends BaseEntity {
    String(100) name;
    Email email : unique;
    // Inherits: id, createdAt, updatedAt
}
```

### Inheritance Rules

- An entity can extend **one** abstract entity
- An entity can mix in **multiple** traits
- Traits can reference other traits
- Abstract entities can extend other abstract entities
- Field name conflicts are detected and rejected

**Example hierarchy:**

```dtrx
abstract entity BaseEntity {
    @UUID id : primaryKey = uuid();
}

abstract entity DomainEntity extends BaseEntity with Timestamped {
    // Combines BaseEntity + Timestamped
}

entity User extends DomainEntity with Auditable, SoftDeletable {
    // Gets: id, createdAt, updatedAt, createdBy, updatedBy, lastModifiedAt, deletedAt, deletedBy
}
```

---

## Enums and Structs

### Enums

Enums define a fixed set of values.

```dtrx
enum OrderStatus {
    Pending,
    Confirmed,
    Shipped,
    Delivered,
    Cancelled
}

entity Order {
    OrderStatus status = OrderStatus.Pending;  // Enum field with default
}
```

**Generated:**
- Python: `class OrderStatus(str, Enum)`
- TypeScript: `enum OrderStatus`
- Database: `VARCHAR` with CHECK constraint

### Structs

Structs are value objects (embedded types, not separate tables).

```dtrx
struct Address {
    String(100) street;
    String(100) city;
    String(50) state;
    PostalCode postalCode;
    CountryCode country;
}

entity Customer {
    UUID id : primaryKey = uuid();
    String(100) name;
    Address shippingAddress;    // Embedded struct
    Address? billingAddress;    // Nullable struct
}
```

**Generated (PostgreSQL):**
- `customers` table gets columns: `shipping_address_street`, `shipping_address_city`, etc.
- Python model has `shippingAddress: Address` with nested Pydantic model
- TypeScript has interface `Address` and nested property

> **💡 Tip:** Use structs for composite values that don't need their own identity or relationships.

---

## REST APIs

Datrix generates complete REST APIs with automatic CRUD operations.

### Resource-Based API

```dtrx
rest_api OrderAPI : basePath('/api/v1') {
    resource db.Order;                          // Full CRUD
    resource db.OrderItem : only(list, get);    // Read-only
}
```

**Generated endpoints for `resource db.Order`:**

| Method | Path | Operation |
|--------|------|-----------|
| `POST` | `/orders` | Create order |
| `GET` | `/orders` | List orders (paginated, filtered, sorted) |
| `GET` | `/orders/:id` | Get order by ID |
| `PATCH` | `/orders/:id` | Update order |
| `DELETE` | `/orders/:id` | Delete order |

### Limiting Operations

```dtrx
resource db.Order : only(create, list, get);      // No update/delete
resource db.OrderItem : only(list, get);          // Read-only
```

### Access Control

```dtrx
resource db.Order : access(authenticated);        // Requires auth
resource db.Admin : access(admin);                // Admin-only
resource db.PublicPost : access(public);          // No auth required
```

### Custom Endpoints

```dtrx
rest_api OrderAPI : basePath('/api/v1/orders') {
    resource db.Order;

    @path('/search')
    @authorize
    get search(String? query, OrderStatus? status) -> List<Order> {
        return db.Order.filter(
            title.contains(query) && status == status
        ).limit(50);
    }

    @path('/:id/cancel')
    @authorize
    post cancel(UUID id) -> Order {
        let order = db.Order.findOrFail(id);
        if (order.status != OrderStatus.Pending) {
            throw ValidationError("Cannot cancel order with status: " + order.status);
        }
        order.status = OrderStatus.Cancelled;
        db.Order.save(order);
        return order;
    }
}
```

### Query Parameters

Generated list endpoints support:

**Pagination:**
```
GET /orders?page=1&limit=20
```

**Filtering (if field has `: filterable`):**
```
GET /orders?status=Pending&customerId=abc-123
```

**Sorting (if field has `: sortable`):**
```
GET /orders?sortBy=createdAt&sortOrder=desc
```

**Search:**
```
GET /orders?search=laptop
```

---

## Event-Driven Messaging

Datrix supports publish/subscribe messaging with type-safe events.

### Defining Events

```dtrx
pubsub mq('config/order-service/pubsub.yaml') {
    topic OrderEvents {
        publish OrderCreated(UUID orderId, Money total, UUID customerId);
        publish OrderShipped(UUID orderId, DateTime shippedAt);
        publish OrderCancelled(UUID orderId, String reason);
    }
}
```

### Publishing Events

**In lifecycle hooks:**

```dtrx
entity Order {
    UUID id : primaryKey = uuid();
    Money total;
    OrderStatus status;

    afterCreate {
        emit OrderCreated(id, total, customerId);
    }

    afterUpdate {
        if (status == OrderStatus.Shipped && $old.status != OrderStatus.Shipped) {
            emit OrderShipped(id, now());
        }
    }
}
```

**In custom endpoints:**

```dtrx
post cancelOrder(UUID id) -> Order {
    let order = db.Order.findOrFail(id);
    order.status = OrderStatus.Cancelled;
    db.Order.save(order);
    emit OrderCancelled(id, "User requested cancellation");
    return order;
}
```

### Subscribing to Events

**Same service:**

```dtrx
pubsub mq('config/order-service/pubsub.yaml') {
    topic OrderEvents {
        publish OrderCreated(UUID orderId, Money total, UUID customerId);
    }

    subscribe OrderEvents {
        on OrderCreated(UUID orderId, Money total, UUID customerId) {
            Log.info("Order created", { orderId: orderId, total: total });
            // Update metrics, send notifications, etc.
        }
    }
}
```

**Different service:**

```dtrx
// In notification-service.dtrx
pubsub mq('config/notification-service/pubsub.yaml') {
    subscribe OrderEvents from order {        // 'order' is service namespace
        on OrderCreated(UUID orderId, Money total, UUID customerId) {
            let customer = UserService.getUser(customerId);
            Email.send(
                to: customer.email,
                subject: "Order Confirmation",
                body: "Your order " + orderId + " has been created."
            );
        }
    }
}
```

### Event Modifiers

```dtrx
topic OrderEvents {
    publish OrderCreated(...) : async;       // Async, fire-and-forget
    publish OrderShipped(...) : persist;     // Persist to event store
}
```

---

## Caching

Datrix generates caching code with Redis/Valkey/Memcached.

### Hash Caches

Cache entity data with TTL:

```dtrx
cache redis('config/order-service/cache.yaml') {
    hash OrderCache on db.Order ttl(30m) {
        UUID orderId : primaryKey;
        String customerName;
        Money total;
        OrderStatus status;
    }
}
```

**Generated methods:**
- `OrderCache.set(orderId, data)` — Set cache entry
- `OrderCache.get(orderId)` — Get cache entry
- `OrderCache.delete(orderId)` — Delete cache entry
- `OrderCache.exists(orderId)` — Check if exists

**Auto-invalidation:**

```dtrx
entity Order {
    afterUpdate {
        OrderCache.delete(id);  // Invalidate cache on update
    }
}
```

### Counters

```dtrx
cache redis('config/cache.yaml') {
    counter OrderViewCount : prefix('order:views');
    counter DailyOrders : prefix('metrics:orders:daily');
}
```

**Generated methods:**
- `OrderViewCount.increment(key)` — Increment counter
- `OrderViewCount.decrement(key)` — Decrement counter
- `OrderViewCount.get(key)` — Get current value
- `OrderViewCount.reset(key)` — Reset to zero

**Usage:**

```dtrx
get getOrder(UUID id) -> Order {
    OrderViewCount.increment(id);
    return db.Order.findOrFail(id);
}
```

---

## Background Jobs

Define scheduled or one-off background jobs.

### Cron Jobs

```dtrx
job CleanupExpiredOrders cron('0 2 * * *') {  // Daily at 2 AM
    let expired = db.Order.filter(
        status == OrderStatus.Pending &&
        createdAt < now() - 24h
    );

    for (order in expired) {
        order.status = OrderStatus.Cancelled;
        db.Order.save(order);
        emit OrderCancelled(order.id, "Expired");
    }

    Log.info("Cleanup completed", { count: expired.length });
}
```

### Interval Jobs

```dtrx
job UpdateMetrics interval(5m) {
    let todayOrders = db.Order.filter(
        createdAt >= utcToday()
    ).count();

    DailyOrders.set(utcToday().toString(), todayOrders);
}
```

### Job Configuration

Jobs can reference configuration for timeouts and retries:

```dtrx
job ProcessPayments cron('0 * * * *') config('config/jobs.yaml') {
    // Job logic
}
```

**config/jobs.yaml:**

```yaml
test:
  ProcessPayments:
    timeout: 300000      # 5 minutes
    retryLimit: 3
    retryBackoff: exponential
```

---

## CQRS

Datrix supports Command Query Responsibility Segregation (CQRS) with materialized views, commands, and queries.

### Views

```dtrx
cqrs {
    view OrderSummary {
        UUID orderId;
        String customerName;
        Money totalAmount;
        Integer itemCount;
        OrderStatus status;
    }

    view DashboardView {
        Integer totalOrders;
        Money totalRevenue;
        Integer pendingCount;
        Integer shippedCount;
    }
}
```

### Projections

```dtrx
cqrs {
    view OrderSummary {
        UUID orderId;
        String customerName;
        Money totalAmount;
        OrderStatus status;
    }

    projection BuildOrderSummary on db.Order {
        return OrderSummary {
            orderId: id,
            customerName: UserService.getUser(customerId).name,
            totalAmount: total,
            status: status
        };
    }
}
```

### Commands

```dtrx
cqrs {
    command PlaceOrder(
        UUID customerId,
        List<OrderItem> items
    ) -> Order {
        let total = items.map(i => i.price * i.quantity).reduce((a, b) => a + b, 0);

        let order = db.Order.create({
            customerId: customerId,
            total: total,
            status: OrderStatus.Pending
        });

        for (item in items) {
            db.OrderItem.create({
                orderId: order.id,
                productId: item.productId,
                quantity: item.quantity,
                price: item.price
            });
        }

        emit OrderCreated(order.id, total, customerId);
        return order;
    }
}
```

### Queries

```dtrx
cqrs {
    query GetOrderSummary(UUID orderId) -> OrderSummary {
        let order = db.Order.findOrFail(orderId);
        return OrderSummary {
            orderId: order.id,
            customerName: UserService.getUser(order.customerId).name,
            totalAmount: order.total,
            status: order.status
        };
    }

    query GetDashboard -> DashboardView {
        return DashboardView {
            totalOrders: db.Order.count(),
            totalRevenue: db.Order.sum(total),
            pendingCount: db.Order.filter(status == OrderStatus.Pending).count(),
            shippedCount: db.Order.filter(status == OrderStatus.Shipped).count()
        };
    }
}
```

---

## Storage

Define file/object storage operations (S3-compatible).

```dtrx
storage files config('config/storage.yaml') {
    upload(Bytes file, String filename) -> URL;
    download(String key) -> Bytes;
    delete(String key);
    list(String? prefix) -> List<String>;
}
```

**Generated interface:**

```python
class FileStorage:
    def upload(self, file: bytes, filename: str) -> str: ...
    def download(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def list(self, prefix: str | None = None) -> list[str]: ...
```

**Usage in endpoints:**

```dtrx
@path('/upload')
post uploadProductImage(Bytes image, String filename) -> URL {
    let url = files.upload(image, filename);
    Log.info("Image uploaded", { url: url });
    return url;
}
```

---

## Validation and Computed Fields

### Field Validation

Use modifiers for built-in validation:

```dtrx
entity Product {
    String(200) name : trim;                        // Trim whitespace
    String(50) sku : unique, uppercase;             // Unique, uppercase
    Money price : min(0);                           // Price >= 0
    Integer stock : min(0), max(10000);             // Stock in range
    Email email : unique, lowercase, trim;          // Valid email
    URL? website;                                   // Valid URL if provided
}
```

### Computed Fields

Computed fields are derived from other fields and recalculated on access:

```dtrx
entity Order {
    Money subtotal;
    Percentage taxRate;
    Money tax := subtotal * (taxRate / 100);
    Money total := subtotal + tax;

    DateTime dueDate;
    Boolean isOverdue := dueDate < now() && status != OrderStatus.Delivered;
}
```

**Characteristics:**
- Defined with `:=` operator (not `=`)
- Not stored in database
- Calculated in application code
- Included in API responses
- Cannot be set by clients

### Validation Blocks

Define custom validation logic:

```dtrx
entity Order {
    Money subtotal;
    Money discount;
    Money total;

    validate {
        if (discount > subtotal) {
            throw ValidationError("Discount cannot exceed subtotal");
        }
        if (total != subtotal - discount) {
            throw ValidationError("Total must equal subtotal minus discount");
        }
    }
}
```

---

## Lifecycle Hooks

Hooks run automatically when entity events occur.

### Available Hooks

| Hook | When It Runs |
|------|-------------|
| `beforeCreate` | Before entity is created |
| `afterCreate` | After entity is created |
| `beforeUpdate` | Before entity is updated |
| `afterUpdate` | After entity is updated |
| `beforeDelete` | Before entity is deleted |
| `afterDelete` | After entity is deleted |

### Hook Examples

```dtrx
entity Order {
    UUID id : primaryKey = uuid();
    UUID customerId;
    Money total;
    OrderStatus status = OrderStatus.Pending;
    Integer version = 0;

    beforeCreate {
        // Validate total
        if (total <= 0) {
            throw ValidationError("Order total must be positive");
        }
    }

    afterCreate {
        // Emit event
        emit OrderCreated(id, total, customerId);

        // Update metrics
        DailyOrders.increment(utcToday().toString());
    }

    beforeUpdate {
        // Increment version for optimistic locking
        version = version + 1;
    }

    afterUpdate {
        // Invalidate cache
        OrderCache.delete(id);

        // Check for status change
        if (status != $old.status) {
            emit OrderStatusChanged(id, $old.status, status);
        }
    }

    afterDelete {
        // Cleanup
        OrderCache.delete(id);
        emit OrderDeleted(id);
    }
}
```

### Special Variables

| Variable | Available In | Purpose |
|----------|--------------|---------|
| `$old` | `afterUpdate` | Access previous field values |

**Example:**

```dtrx
afterUpdate {
    if (status == OrderStatus.Shipped && $old.status != OrderStatus.Shipped) {
        emit OrderShipped(id, now());
    }
}
```

---

## Service Discovery and Resilience

### Service Discovery

Register dependencies on other services:

```dtrx
service ecommerce.OrderService : version('1.0.0') {
    discovery {
        UserService {
            loadBalance: roundRobin,
            healthyOnly: true
        }
        PaymentService {
            loadBalance: leastConnections,
            healthyOnly: true
        }
        InventoryService {
            loadBalance: random,
            healthyOnly: false
        }
    }
}
```

**Generated:**
- Service client classes with configured load balancing
- Health check integration
- Service registry integration (Consul, Eureka, etc.)

### Resilience

Configure circuit breaker, retry, timeout, and bulkhead patterns:

**config/order-service/resilience.yaml:**

```yaml
test:
  circuitBreaker:
    failureThreshold: 5
    successThreshold: 2
    timeout: 60000         # 60 seconds

  retry:
    maxAttempts: 3
    backoff:
      type: exponential
      initialDelay: 1000   # 1 second
      maxDelay: 10000      # 10 seconds
      multiplier: 2

  timeout:
    default: 30000         # 30 seconds
    read: 10000            # 10 seconds
    connect: 5000          # 5 seconds

  bulkhead:
    maxConcurrent: 10
    maxWaiting: 5
```

> **📖 Reference:** See [Configuration Guide § Resilience](./configuration-guide.md#resilience-configuration) for complete resilience config options.

---

## Multi-Tenancy

Datrix supports multi-tenant applications with tenant isolation at the data layer.

### Defining Tenantable Entities

```dtrx
from datrix.builtin import Tenantable;

entity Organization extends BaseEntity with Tenantable {
    String(100) name : unique;
    String slug : unique, lowercase;
}

entity User extends BaseEntity with Tenantable {
    String(100) name;
    Email email : unique;
    UUID organizationId;  // Tenant identifier
}

entity Order extends BaseEntity with Tenantable {
    UUID customerId;
    Money total;
    UUID organizationId;  // All Tenantable entities need this
}
```

**The `Tenantable` trait adds:**
- `UUID organizationId` field (or your configured tenant ID field)
- Automatic tenant filtering on all queries
- Validation ensuring tenant context is present

### Configuring Tenancy

**config/order-service/service-config.yaml:**

```yaml
test:
  platform: compose
  replicas: 1
  tenancy:
    identifier:
      source: header         # "header", "jwt", or "path"
      name: X-Tenant-Id      # Header name, JWT claim, or path param
    enforcement: strict      # "strict" or "relaxed"
```

**Identifier sources:**
- `header` — Read from HTTP header (e.g., `X-Tenant-Id`)
- `jwt` — Extract from JWT claim (e.g., `tenantId` claim)
- `path` — Extract from URL path (e.g., `/tenants/:tenantId/...`)

**Enforcement levels:**
- `strict` — All queries require tenant context; missing context = error
- `relaxed` — Tenant filtering is optional (for migration scenarios)

### Generated Behavior

**Python (FastAPI):**

```python
# Middleware extracts tenant ID from request
# All DB queries automatically filtered by tenant

@router.get("/orders")
async def list_orders(tenant_id: UUID = Depends(get_tenant_id)):
    # tenant_id automatically injected
    # Query automatically filtered: WHERE organization_id = tenant_id
    return await Order.find_all()
```

**TypeScript (NestJS):**

```typescript
// Decorator extracts tenant ID
@Get('orders')
@TenantScoped()
async listOrders(@TenantId() tenantId: string) {
  // All queries scoped to tenantId
  return this.orderRepository.find();
}
```

> **📖 Reference:** See [Patterns and Best Practices § Multi-Tenancy](./patterns-and-best-practices.md#multi-tenancy) for implementation patterns.

---

## Best Practices

### 1. Use Abstract Entities for Common Fields

```dtrx
abstract entity BaseEntity {
    @UUID id : primaryKey = uuid();
    @DateTime createdAt = now();
    @DateTime updatedAt = now();
}

// All entities extend BaseEntity
entity User extends BaseEntity { ... }
entity Order extends BaseEntity { ... }
```

### 2. Apply Traits for Cross-Cutting Concerns

```dtrx
trait Auditable {
    String? createdBy;
    String? updatedBy;
}

trait SoftDeletable {
    DateTime? deletedAt;
}

entity Order extends BaseEntity with Auditable, SoftDeletable { ... }
```

### 3. Use Server-Managed Fields

```dtrx
entity Order {
    @UUID id : primaryKey = uuid();        // Server generates
    @DateTime createdAt = now();           // Server sets
    @DateTime updatedAt = now();           // Server updates
    String customerName : trim;            // Client provides
}
```

### 4. Leverage Computed Fields

```dtrx
entity Order {
    Money subtotal;
    Percentage taxRate;
    Money tax := subtotal * (taxRate / 100);        // Computed
    Money total := subtotal + tax;                  // Computed
}
```

### 5. Emit Events in Hooks

```dtrx
entity Order {
    afterCreate {
        emit OrderCreated(id, total, customerId);
    }

    afterUpdate {
        if (status != $old.status) {
            emit OrderStatusChanged(id, $old.status, status);
        }
    }
}
```

### 6. Index Foreign Keys and Frequently Queried Fields

```dtrx
entity Order {
    UUID customerId : index;               // Frequently queried
    OrderStatus status : index;            // Frequently filtered
    DateTime createdAt : sortable;         // Frequently sorted
}
```

### 7. Use Enums for Fixed Value Sets

```dtrx
enum OrderStatus {
    Pending,
    Confirmed,
    Shipped,
    Delivered,
    Cancelled
}

entity Order {
    OrderStatus status = OrderStatus.Pending;
}
```

### 8. Separate Concerns with Modules

```dtrx
// specs/common/traits.dtrx — Shared traits
module ecommerce.common {
    trait Auditable { ... }
}

// specs/common/entities.dtrx — Shared abstract entities
module ecommerce.common {
    abstract entity BaseEntity { ... }
}

// specs/services/order-service.dtrx — Service-specific
service ecommerce.OrderService { ... }
```

### 9. Configure Resilience for External Dependencies

```dtrx
service OrderService {
    discovery {
        PaymentService {
            loadBalance: roundRobin,
            healthyOnly: true
        }
    }

    resilience('config/resilience.yaml');  // Circuit breaker, retry
}
```

### 10. Use Cache Invalidation in Hooks

```dtrx
cache redis {
    hash OrderCache on db.Order ttl(30m) { ... }
}

entity Order {
    afterUpdate {
        OrderCache.delete(id);  // Invalidate cache on update
    }
}
```

---

## Common Patterns

### Pattern: Soft Delete

```dtrx
trait SoftDeletable {
    DateTime? deletedAt;
    String? deletedBy;
}

entity Order extends BaseEntity with SoftDeletable {
    // Fields
}

// In API
delete deleteOrder(UUID id) {
    let order = db.Order.findOrFail(id);
    order.deletedAt = now();
    order.deletedBy = Request.userId();
    db.Order.save(order);
}
```

### Pattern: Optimistic Locking

```dtrx
entity Order {
    Integer version = 0;

    beforeUpdate {
        version = version + 1;
    }
}

// In update logic
patch updateOrder(UUID id, OrderUpdate data) -> Order {
    let order = db.Order.findOrFail(id);
    if (order.version != data.version) {
        throw ConflictError("Order was modified by another user");
    }
    // Apply updates
    db.Order.save(order);
    return order;
}
```

### Pattern: Idempotent Operations

```dtrx
entity PaymentTransaction {
    String idempotencyKey : unique;
    Money amount;
    PaymentStatus status;
}

post processPayment(String idempotencyKey, Money amount) -> PaymentTransaction {
    let existing = db.PaymentTransaction.findBy({ idempotencyKey: idempotencyKey });
    if (existing != null) {
        return existing;  // Already processed
    }

    let transaction = db.PaymentTransaction.create({
        idempotencyKey: idempotencyKey,
        amount: amount,
        status: PaymentStatus.Pending
    });

    // Process payment
    // ...

    return transaction;
}
```

### Pattern: Saga Pattern (Event-Driven)

```dtrx
// Order Service
pubsub mq {
    topic OrderEvents {
        publish OrderPlaced(UUID orderId, UUID customerId, Money total);
        publish OrderCancelled(UUID orderId);
    }
}

// Payment Service
pubsub mq {
    subscribe OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, Money total) {
            // Reserve payment
            let success = PaymentService.reservePayment(customerId, total);
            if (success) {
                emit PaymentReserved(orderId, total);
            } else {
                emit PaymentFailed(orderId, "Insufficient funds");
            }
        }
    }
}

// Inventory Service
pubsub mq {
    subscribe OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, Money total) {
            // Reserve inventory
            let items = OrderService.getOrderItems(orderId);
            let success = InventoryService.reserveItems(items);
            if (success) {
                emit InventoryReserved(orderId);
            } else {
                emit InventoryFailed(orderId, "Out of stock");
            }
        }
    }
}
```

---

## Next Steps

**You've learned how to write Datrix applications!**

Continue with:
- [Configuration Guide](./configuration-guide.md) — Deep dive into all config files
- [Complete Examples](./complete-examples.md) — Working examples to learn from
- [Patterns and Best Practices](./patterns-and-best-practices.md) — Proven patterns

**Reference Documentation:**
- [Language Reference](../reference/language-reference.md) — Quick syntax reference
- [Datrix Syntax Reference](../../../datrix-language/docs/reference/datrix-syntax-reference.md) — Complete grammar
- [CLI Commands](../../../datrix-cli/docs/commands.md) — Command reference

---

**Last Updated:** 2026-03-28
