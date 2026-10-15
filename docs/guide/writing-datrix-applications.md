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
12. [Shared infrastructure (`shared { }`)](#shared-infrastructure-shared-)
13. [Event-Driven Messaging](#event-driven-messaging)
14. [Caching](#caching)
15. [Background Jobs](#background-jobs)
16. [CQRS](#cqrs)
17. [Storage](#storage)
18. [Validation and Computed Fields](#validation-and-computed-fields)
19. [Lifecycle Hooks](#lifecycle-hooks)
20. [Service Discovery and Resilience](#service-discovery-and-resilience)
21. [Extern Services](#extern-services)
22. [Multi-Tenancy](#multi-tenancy)
23. [Best Practices](#best-practices)
24. [Common Patterns](#common-patterns)

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
✅ **Platform-agnostic** — Same spec works for Docker, AWS, Azure
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
├── config/                        # config documents (.dcfg)
│   ├── system.dcfg               # System-level profile config
│   ├── user-service.dcfg         # User service runtime/infrastructure config
│   └── order-service.dcfg        # Order service runtime/infrastructure config
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
| `config/` | `.dcfg` config documents | You (version controlled) |
| `generated/` | Generated application code | Datrix CLI (overwritten on regeneration) |

> **💡 Tip:** Only edit files in `specs/` and `config/`. Never manually edit `generated/` — your changes will be lost on next generation.

### Layout used in `examples/`

The official [`examples/`](../../examples/) trees usually place **`system.dtrx` and `*.dtrx` service files at the project root** beside a **`config/`** directory. Paths in `include '…'` and declaration-level `.dcfg` paths are **relative to the file** that contains them. A nested **`specs/`** layout (as sketched above) is equally valid for larger repos—keep paths consistent.

---

## File Structure and Includes

Every Datrix application starts with a **system block** that includes service and module definitions.

### Entry Point: system.dtrx

`specs/system.dtrx` lists the other files, then declares the system:

```text
include 'common/traits.dtrx';          // Shared traits
include 'common/entities.dtrx';        // Abstract entities
include 'services/user-service.dtrx';  // Service definitions
include 'services/order-service.dtrx';
```

```datrix
system ecommerce.System('config/system.dcfg') : version('1.0.0') {
}
```

### Includes

Use `include '<path>';` lines, as above, to compose your application from multiple files.

**Rules:**
- Include paths are relative to the file containing the `include` statement
- Files can be included multiple times (Datrix deduplicates)
- Circular includes are detected and rejected
- All includes must resolve before compilation begins

### Imports

Use `from ... import` to reference definitions from modules:

```datrix
from ecommerce.common import Auditable, BaseEntity, SoftDeletable;

service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    rdbms db {
        entity Order extends BaseEntity with Auditable {
            Money total;
        }
    }
}
```

---

## System Block

The **system block** names the application and its config document; global infrastructure
(gateway, observability, deployment) is configured in that document.

```datrix
system ecommerce.System('config/system.dcfg') : version('1.0.0') {
    discovery { }
}
```

### System Configuration

The declaration-level `.dcfg` path points to the system config document:

| Location | Config File | Purpose |
|----------|-------------|---------|
| `system QualifiedName('config/system.dcfg')` | `system.dcfg` | Runtime/provider/target, registry, gateway, observability, and shared system settings |

**system.dcfg example:**

```dcfg
config system ecommerce.System {
  base {
    deployment {
      runtime = "docker-compose";
      provider = "local";
    }
    defaultTimeout = 30000;
  }

  profile production as "prod" extends base {
    deployment {
      runtime = "ecs-fargate";
      provider = "aws";
    }
    region = "us-east-1";
  }
}
```

Target language is not a `.dcfg` field — it is a required generation parameter passed via `--language`/`-L` on `datrix generate`.

> **📖 Reference:** See [Configuration Guide](./configuration-guide.md#system-configuration) for complete system config reference.

---

## Services

A **service** is the unit of deployment. Everything inside a service block belongs to that service and is generated as a single deployable application.

### Basic Service

```datrix
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0'), description('Order management') {
    discovery { }  // Service discovery config

    rdbms db {
        entity Order {
            UUID id : primaryKey, server = uuid();
            Money total;
        }
    }

    rest_api OrderAPI : basePath('/api/v1/orders'), rdbms(db) {
        resource Order : auth(required, providers: [identity]);
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
| Declaration `.dcfg` path | `config/<service>.dcfg` | Platform, replicas, resources, health checks, registration, resilience, and infrastructure settings |
| `discovery { }` | Inline | Dependencies on other services |

### Service Discovery

Declare dependencies on other services:

```datrix context=service
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

```datrix context=service
rdbms db {
    entity User {
        UUID id : primaryKey = uuid();
        String(100) name : trim;
        Email email : unique, index;
        DateTime createdAt = DateTime.now();
        DateTime updatedAt = DateTime.now();
    }
}
```

### Field Definition

```datrix-grammar
<Type> <fieldName> [: <modifiers>] [= <defaultValue>];
```

**Examples:**

```datrix context=entity
String(200) title : trim;                   // Required string, trimmed
String? description;                        // Nullable string
Email email : unique, index;                // Email with unique constraint
Boolean isActive = true;                    // Boolean with default
belongsTo Author : index;                   // Foreign key (authorId) with index
Money totalAmount;                          // Money field, never negative
DateTime? publishedAt;                      // Nullable datetime
Array<String> tags;                         // Array field
```

### Field Modifiers

| Modifier | Applies To | Effect |
|----------|------------|--------|
| `server` | Any field | Server-managed: excluded from create/update API input; value from server defaults / hooks |
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

Add the **`server`** modifier to a field’s modifier list to mark it as server-managed (not accepted in API input on create/update):

```datrix context=rdbms
entity Order {
    UUID id : primaryKey, server = uuid();        // Server generates on create
    DateTime createdAt : server = DateTime.now();           // Server sets on create
    DateTime updatedAt : server = DateTime.now();           // Server updates on save
    String(200) customerName : trim;       // Client provides
}
```

**API behavior:**
- **`server`** fields are excluded from Create/Update request schemas
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
| `Decimal(p,s)` | `Decimal` | `DecimalString` | `NUMERIC(p,s)` | `DECIMAL(p,s)` |
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
| `Money` | Decimal currency | `Decimal` | `DecimalString` |
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
| `DateTime` | `datetime` (UTC) | `Date` | `TIMESTAMP` |
| `Date` | `date` | `Date` | `DATE` |
| `Time` | `time` | `string` | `TIME` |
| `Duration` | `timedelta` | `string` (ISO-8601) | `INTERVAL` |
| `Timestamp` | `datetime` | `Date` | `TIMESTAMP` |

### Collection Types

```datrix context=entity
Array<String> tags;             // Array of strings
Map<String, Integer> counts;    // Key-value map
Set<String> categories;         // Unique set
```

A `Set` is stored and sent as a JSON array on every backend. Its values are unique: a
request that repeats a value is refused with `422` (it is never silently de-duplicated),
and a stored value that is not an array fails on read. A TypeScript service built before
this encoding stored every `Set` as `{}`; the generated project carries a data revision
that rewrites those rows to `[]` and logs how many it rewrote. The values those rows held
were lost and cannot be recovered.

### Nullability

Add `?` suffix to make a field nullable:

```datrix context=entity
String? description;           // Nullable string
DateTime? deletedAt;           // Nullable datetime
UUID? parentId;                // Nullable UUID
```

> **⚠️ Warning:** Use nullable fields sparingly. Non-null fields with proper defaults are easier to work with and reduce null-check boilerplate.

---

## Relationships

Datrix supports four relationship types: `belongsTo`, `hasOne`, `hasMany`, and `manyToMany`.

### BelongsTo (Many-to-One)

```datrix context=rdbms
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

```datrix context=entity
belongsTo User as author : onDelete(cascade);   // Cascade delete
belongsTo User as reviewer : onDelete(restrict); // Prevent delete if referenced (the default)
belongsTo User as editor : onDelete(setNull);    // Set FK to null on delete (nullable FK)
```

### HasMany (One-to-Many)

```datrix context=rdbms
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

```datrix context=rdbms
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

```datrix context=rdbms
entity Post {
    UUID id : primaryKey = uuid();
    String(200) title;
    manyToMany Tag as tags;
}

entity Tag {
    UUID id : primaryKey = uuid();
    String(50) name : unique;
    manyToMany Post as posts;
}
```

**Generated:**
- Junction table `post_tags` with `post_id` and `tag_id` columns
- Both entities get many-to-many collection properties
- Both sides must declare the `manyToMany` relationship

> **📖 Reference:** See [Datrix Syntax Reference](../../../datrix-language/docs/reference/datrix-syntax-reference.md) for complete relationship syntax including `onSoftDelete`, `noTree`, and other modifiers.

### Self-Referential Relationships

```datrix context=rdbms
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

```datrix context=entity
hasMany Employee as directReports : noTree;  // Plain one-to-many
```

---

## Traits and Inheritance

### Traits

Traits are reusable field groups that can be mixed into entities.

**Define traits in a module:**

```datrix
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
        DateTime createdAt : server = DateTime.now();
        DateTime updatedAt : server = DateTime.now();
    }
}
```

**Use traits with `with`:**

```datrix
from ecommerce.common import Auditable, SoftDeletable, Timestamped;

service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    rdbms db {
        entity Order with Auditable, SoftDeletable {
            UUID id : primaryKey, server = uuid();
            UUID customerId;
            Money totalAmount;
            // Inherits: createdBy, updatedBy, lastModifiedAt, deletedAt, deletedBy
        }
    }
}
```

### Abstract Entities

Abstract entities provide base fields and cannot be instantiated directly.

```datrix
module ecommerce.common {
    abstract entity BaseEntity with Timestamped {
        UUID id : primaryKey, server = uuid();
        // Inherits: createdAt, updatedAt from Timestamped
    }
}
```

**Extend abstract entities:**

```datrix context=rdbms
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

```datrix context=rdbms
abstract entity BaseEntity {
    UUID id : primaryKey, server = uuid();
}

abstract entity DomainEntity extends BaseEntity with Timestamped {
    // Combines BaseEntity + Timestamped
}

entity User extends DomainEntity with Auditable, SoftDeletable {
    // Gets: id, createdAt, updatedAt, createdBy, updatedBy, lastModifiedAt, deletedAt, deletedBy
    String(100) name;
}
```

---

## Enums and Structs

### Enums

Enums define a fixed set of values.

```datrix context=service
enum OrderStatus {
    Pending,
    Confirmed,
    Shipped,
    Delivered,
    Cancelled
}

rdbms db {
    entity Order {
        UUID id : primaryKey, server = uuid();
        OrderStatus status = OrderStatus.Pending;  // Enum field with default
    }
}
```

**Generated:**
- Python: `class OrderStatus(str, Enum)`
- TypeScript: `enum OrderStatus`
- Database: `VARCHAR` with CHECK constraint

### Structs

Structs are value objects (embedded types, not separate tables).

```datrix context=service
struct Address {
    String(100) street;
    String(100) city;
    String(50) state;
    PostalCode postalCode;
    CountryCode country;
}

rdbms db {
    entity Customer {
        UUID id : primaryKey = uuid();
        String(100) name;
        Address shippingAddress;    // Embedded struct
        Address? billingAddress;    // Nullable struct
    }
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

```datrix context=service
rest_api OrderAPI : basePath('/api/v1') {
    resource db.Order : auth(required, providers: [identity]);                        // Full CRUD
    resource db.OrderItem : only(list, get), auth(required, providers: [identity]);   // Read-only
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

```datrix context=service
rest_api OrderAPI : basePath('/api/v1') {
    resource db.Order : only(create, list, get), auth(required, providers: [identity]);   // No update/delete
    resource db.OrderItem : only(list, get), auth(required, providers: [identity]);       // Read-only
}
```

### Access Control

Every resource and endpoint declares an `auth(...)` modifier; there is no default access level.

```datrix context=service
rest_api StoreAPI : basePath('/api/v1') {
    resource db.Order : auth(required, providers: [identity]);                       // Requires auth
    resource db.Warehouse : auth(required, providers: [identity], roles: [admin]);   // Admin-only
    resource db.Product : only(list, get), auth(public);                              // No auth required
}
```

The full set of modes (`public`, `optional`, `required`, `service`, `webhook`) and their arguments is in the [access-levels reference](../../../datrix-language/docs/reference/access-levels.md).

### Custom Endpoints

```datrix context=service
rest_api OrderAPI : basePath('/api/v1/orders'), rdbms(db) {
    resource Order : auth(required, providers: [identity]);

    @path('/search')
    get(OrderStatus wanted) : auth(required, providers: [identity]) -> Array<Order> {
        return Order.where(status: wanted).limit(50).all();
    }

    @path('/:id/cancel')
    post(UUID id) : auth(required, providers: [identity]) -> Order {
        let Order order = Order.findOrFail(id);
        if (order.status != OrderStatus.Pending) {
            throw ValidationError(#"Cannot cancel order with status: {order.status}");
        }
        order.status = OrderStatus.Cancelled;
        order.save();
        return order;
    }
}
```

### Calling Another Service's Endpoints

A Datrix service calls another service's REST endpoint as a **typed RPC** — never by building a path string. Two rules govern the surface:

1. **Cross-service callability is bound to `auth(service, ...)`.** A custom endpoint is callable from a peer if and only if it declares `auth(service, providers: [...])`, and a service-facing custom endpoint **must** carry a name (placed right after the HTTP method, like a function name). External-facing endpoints (`auth(public)`, `auth(optional, ...)`, `auth(required, ...)` with or without roles, `auth(webhook)`) carry no cross-service name and cannot be invoked as an RPC — so a peer can never reach a user-facing endpoint and bypass its end-user authorization. Resource (auto-CRUD) operations are cross-service-callable only when the resource is declared `auth(service, ...)`.
2. **You call by identity, not by route.** The cross-service identity is `(HTTP method, name)`. Endpoint names are noun/resource phrases (the verb is the method), and the route (`@path`) is a deployment detail callers never see.

**Provider — name and expose a service-facing endpoint:**

```datrix context=service
rest_api ProductAPI : basePath('/api/v1'), rdbms(db) {

    // External, user-facing: no name, not cross-service-callable
    @path('/products/sku/:sku')
    get(String sku) : auth(required, providers: [identity]) -> db.Product {
        return db.Product.where(sku: sku).first();
    }

    // Service-facing: auth(service, ...) ⇒ a name is mandatory; callable as
    //   ProductService.ProductAPI.get.productBySku(sku)
    @path('/service/products/sku/:sku')
    get productBySku(String sku) : auth(service, providers: [internal]), hidden -> db.Product {
        return db.Product.where(sku: sku).first();
    }

    // Idempotent read — opts the call into bounded, breaker-aware retry
    @path('/service/products/nearby')
    get productsInWarehouse(UUID warehouseId) : auth(service, providers: [internal]), idempotent -> Array<db.Product> {
        return db.Product.where(warehouseId: warehouseId).all();
    }
}
```

**Consumer — call by method + name, with typed arguments:**

```datrix context=fn
let Product p            = ProductService.ProductAPI.get.productBySku(sku);
let Array<Product> stock = ProductService.ProductAPI.get.productsInWarehouse(warehouseId);

// Resource (auto-CRUD) endpoints address block + database + entity + operation:
let Product one          = ProductService.ProductAPI.db.Product.get(id);
let Array<Product> all   = ProductService.ProductAPI.db.Product.list(limit: 20);
```

The call requires a matching `uses ProductService;` / discovery dependency. Arguments are checked against the provider endpoint's declared parameters (positional first, named after) at generation time — a typo, an undeclared dependency, an unresolved endpoint, an argument type mismatch, or a target that is not `auth(service, ...)` is a generation error, not a runtime 404/422/500. The call's static type is the provider's declared return type, decoded into a generated, validated response struct (only `-> JSON` endpoints stay untyped), so no defensive shape-checking is needed. The old string-path (`Service.Api.get('/route', ...)`), interpolated-path, and pathless positional call forms are removed.

### Query Parameters

Generated list endpoints support:

**Pagination** (a route returning `Page<T>`; the query pair is the backend's own, shown here for a row-offset backend):
```
GET /orders?skip=0&limit=20
```
The answer is the envelope `{ "items": [...], "total": 340, "offset": 0, "limit": 20 }`. A size above
`MAX_PAGE_SIZE` or a negative position is refused with a request-validation problem.

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

## Shared infrastructure (`shared { }`)

Use a **top-level** `shared Name('<config-path>') { … }` block (a simple name: `uses` cannot reach a dotted one) when **several services** must share the same broker topics, reference tables, buckets, caches, or queues. Allowed members mirror service infrastructure: **`rdbms`**, **`nosql`**, **`cache`**, **`pubsub`**, **`storage`**, **`queues`**. There are **no** REST/GraphQL APIs, jobs, CQRS, or `subscribe` inside `shared` — consumers always **`subscribe`** from a **service**, with a **qualified** topic name and a matching **`uses`** declaration.

**Authoring checklist**

1. Pick a **descriptive** block name (`IngestionEvents`, `ProductCatalogData`).
2. Place `shared` blocks in the same **`specs/`** tree as services (or `include` them from `system.dtrx`).
3. Keep infrastructure members pathless in `.dtrx`; their operational settings live in the owning `config shared` `.dcfg`.
4. In every service that publishes or subscribes across the boundary, add **`uses SharedName : publish | subscribe | readonly | readwrite;`** and the matching dependency settings in the service `.dcfg` (see [Configuration guide](./configuration-guide.md)).

**Generated layout:** shared artifacts land under **`shared/<kebab-name>/…`** next to **`services/<service>/…`** in the codegen output.

---

## Event-Driven Messaging

Datrix supports publish/subscribe messaging with type-safe events.

### Defining Events

```datrix context=service
pubsub mq {
    topic OrderEvents {
        publish OrderCreated(UUID orderId, Money total, UUID customerId);
        publish OrderShipped(UUID orderId, DateTime shippedAt);
        publish OrderCancelled(UUID orderId, String reason);
    }
}
```

### Publishing Events

**In lifecycle hooks:**

```datrix context=rdbms
entity Order {
    UUID id : primaryKey = uuid();
    UUID customerId;
    Money total;
    OrderStatus status;

    afterCreate {
        dispatch OrderCreated(id, total, customerId);
    }

    afterUpdate {
        if (isChanged(status) && status == OrderStatus.Shipped) {
            dispatch OrderShipped(id, DateTime.now());
        }
    }
}
```

**In custom endpoints:**

```datrix context=service
rest_api OrderAPI : basePath('/api/v1/orders'), rdbms(db) {
    @path('/:id/cancel')
    post(UUID id) : auth(required, providers: [identity]) -> Order {
        let Order order = Order.findOrFail(id);
        order.status = OrderStatus.Cancelled;
        order.save();
        dispatch OrderCancelled(id, "User requested cancellation");
        return order;
    }
}
```

### Subscribing to Events

**Same service:**

```datrix
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    pubsub mq {
        topic OrderEvents {
            publish OrderCreated(UUID orderId, Money total, UUID customerId);
        }
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderCreated(UUID orderId, Money total, UUID customerId) {
            Log.info("Order created", { orderId: orderId, total: total });
            // Update metrics, send notifications, etc.
        }
    }
}
```

**Different service:**

```datrix
// In notification-service.dtrx
service notification.NotificationService('config/notification-service.dcfg') : version('1.0.0') {
    uses OrderService : subscribe;

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderCreated(UUID orderId, Money total, Email customerEmail) {
            Email.send({
                to: customerEmail,
                subject: "Order Confirmation",
                body: #"Your order {orderId} has been created."
            });
        }
    }
}
```

An event is a `publish Name(...)` declaration, optionally with `{ ensure ...; }` contracts (see the
[Event Contracts guide](./event-contracts.md)); it takes no modifiers. Delivery guarantees and
retention are broker settings in the `.dcfg`.

### Serverless blocks

Use one or more **`serverless BlockName { … }`** sections when handlers should deploy as an independent unit rather than run in-process inside the service. The selected service `.dcfg` profile controls the deployment target: **AWS** realizes the block as Lambda functions, **Azure** as Function Apps (or in-process consumers under `serverless { hosting = "inProcess" }`), and **local/existing** (Docker Compose) as dedicated long-running containers — one per block per trigger kind (consumer, scheduler, queue worker, or small web app), all running the same platform-agnostic handler code. There is no local "runs in-process" mode for a serverless block — that is what distinguishes it from an ordinary in-process handler.

**Key concept:** The `serverless` block is a **deployment boundary only**. It contains the same DSL members you would use at service scope (`subscribe`, `job`, HTTP endpoints, `enqueue` consumers) with **identical syntax**. Moving a handler between in-process and serverless deployment is a simple cut-and-paste operation — no code changes required.

#### Complete example

```datrix
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    rdbms db {
        entity Order {
            UUID id : primaryKey, server = uuid();
            Decimal amount;
            String currency;
            String status;
        }
    }

    pubsub mq {
        topic OrderEvents {
            publish OrderPlaced(UUID orderId, Decimal amount);
            publish OrderCancelled(UUID orderId);
        }
    }

    rest_api OrderAPI : basePath('/api/v1') {
        resource db.Order : auth(required, providers: [identity]);
    }

    // This job runs in-process inside the service container
    jobs {
        job QuickCleanup {
            Log.info("quick cleanup");  // lightweight task, runs alongside the API
        }
    }

    // Event handlers deployed as Lambda/Azure Functions
    serverless eventHandlers {

        subscribe ecommerce.OrderService.mq.OrderEvents {
            on OrderPlaced(UUID orderId, Decimal amount) {
                // Can access db.Order — same service scope
                let db.Order order = db.Order.findOrFail(orderId);
                if (amount > 10000) {
                    Log.warn(#"Large order detected: {order.id} amount={amount}");
                }
            }

            on OrderCancelled(UUID orderId) {
                Log.info(#"Order cancelled: {orderId}");
            }
        }

        // HTTP endpoint — standalone Lambda behind API Gateway
        @path('/webhooks/payments')
        post(JSON payload) : auth(webhook), verify(sharedSecret, secretRef: paymentsWebhookSecret) {
            Log.info("payment webhook received");
        }
    }

    // Scheduled tasks — separate config, separate deployment
    serverless scheduledTasks {
        job DailyOrderReport {
            let Array<db.Order> orders = db.Order.where(status: "completed").all();
            Log.info(#"Daily report: {orders.length()} completed orders");
        }
    }
}
```

#### Configuration

Serverless handler settings live under the block's name in the service `.dcfg`; the `flavor`
must be the one the profile's deployment provider realizes (`lambda` on AWS, `functions` on
Azure, `container` locally):

```dcfg
config service ecommerce.OrderService {
  base {
    serverless eventHandlers {
      flavor = "container";
      defaults {
        timeout = 300;
        memory = 512;
      }
      handlers {
      }
    }
  }

  profile production as "prod" extends base {
    replace serverless eventHandlers {
      flavor = "lambda";
      defaults {
        timeout = 300;
        memory = 512;
      }
      handlers {
        OrderPlaced {
          timeout = 60;
          memory = 256;
          reservedConcurrency = 50;
        }
      }
    }
  }
}
```

#### Multiple blocks for organization

A service can have multiple `serverless` blocks to group handlers by concern:

- **Event handlers** — one block, one config (event-driven logic)
- **Scheduled tasks** — separate block, separate config (cron jobs)
- **Webhooks** — another block for HTTP-triggered handlers

Each block can have different timeout/memory settings or even different platforms per profile.

#### Serverless and shared blocks

A `shared` block may own the topic, but never a `serverless` block (`SLS007`): the handlers that
react to a shared topic live in a service that `uses` the shared block (see
[datrix-grammar — Shared block usage](../../../datrix-language/docs/reference/datrix-grammar.md#shared-block-usage)).

#### Moving between in-process and serverless

Refactoring is a cut-and-paste operation:

```datrix context=service
// Before: runs in the service container
jobs {
    job DailyReport { Log.info("daily report"); }    // <-- cut this
}
```

```datrix context=service
// After: deploys as Lambda/Azure Function
serverless tasks {
    job DailyReport { Log.info("daily report"); }    // <-- paste here, unchanged
}
```

Same for `subscribe` handlers, `enqueue` consumers, and HTTP endpoints.

**Handler name matching:** Config keys under `handlers:` match DSL-derived names: `on` event names, `job` identifiers, `@name('…')` for HTTP endpoints, or queue task names. See [Configuration Guide — Serverless](./configuration-guide.md#serverless-configuration) for details.

**Example:** [`examples/02-features/02-service-architecture/serverless`](../../examples/02-features/02-service-architecture/serverless/)

---

## Task queues (point-to-point)

Queues offload **exactly-once consumer** work to workers. Queue declarations live in the producing service's `queues { ... }` block; broker settings and worker defaults live in that service's `.dcfg` profile.

1. Add queue settings to `config/<service>.dcfg` with `engine`, `platform`, broker settings, and worker defaults (`visibilityTimeout`, `maxConcurrency`, `workerReplicas`, …). See [Configuration Guide — Queue Configuration](./configuration-guide.md#queue-configuration).
2. Declare queues in DSL; use `dispatch TaskName(args);` from entities, commands, or HTTP handlers (same keyword as pubsub events — **QUE005** ensures the name resolves).
3. For a **consumer** in another service: add the producer to `discovery { }` and write `enqueue ProducerService.TaskName(…) { … }`. The generator emits a **separate worker entrypoint** (e.g. `python -m …workers.queue_worker`) suitable for its own container/pod.

Walkthrough: [`examples/02-features/03-infrastructure-blocks/queue`](../../examples/02-features/03-infrastructure-blocks/queue/).

---

## Caching

Datrix generates caching code with Redis/Valkey/Memcached.

### Hash Caches

Cache entity data with TTL:

```datrix context=service
cache redis {
    hash OrderCache : prefix('order:'), ttl(1800) {
        UUID orderId : primaryKey;
        String customerName;
        Money total;
        OrderStatus status;
    }
}
```

**Generated methods** (reached through the block: `redis.OrderCache`):
- `redis.OrderCache.set(orderId, data)` — Set cache entry
- `redis.OrderCache.get(orderId)` — Get cache entry
- `redis.OrderCache.delete(orderId)` — Delete cache entry
- `redis.OrderCache.exists(orderId)` — Check if exists

**Invalidation on write:**

```datrix context=entity
afterUpdate {
    redis.OrderCache.delete(id);  // Invalidate cache on update
}
```

### Counters

```datrix context=service
cache redis {
    counter OrderViewCount : prefix('order:views');
    counter DailyOrders : prefix('metrics:orders:daily');
}
```

**Generated methods:**
- `redis.OrderViewCount.increment(key)` — Increment counter
- `redis.OrderViewCount.decrement(key)` — Decrement counter
- `redis.OrderViewCount.get(key)` — Get current value
- `redis.OrderViewCount.reset(key)` — Reset to zero

**Usage:**

```datrix context=service
rest_api OrderAPI : basePath('/api/v1/orders') {
    @path('/:id')
    get(UUID id) : auth(required, providers: [identity]) -> db.Order {
        redis.OrderViewCount.increment(id);
        return db.Order.findOrFail(id);
    }
}
```

---

## Background Jobs

Define scheduled background jobs. A job declaration is a name and a body; its schedule, timeout
and retry live under `jobs` in the service's config document. The `jobs { }` block names no
path of its own.

### Scheduled Jobs

```datrix context=service
jobs {
    job CleanupExpiredOrders {
        let Array<db.Order> pending = db.Order.where(status: OrderStatus.Pending).all();
        let Integer cancelled = 0;

        foreach order in pending {
            if (order.createdAt < DateTime.now().subtractHours(24)) {
                order.status = OrderStatus.Cancelled;
                order.save();
                dispatch OrderCancelled(order.id, "Expired");
                cancelled = cancelled + 1;
            }
        }

        Log.info("Cleanup completed", { count: cancelled });
    }

    job UpdateMetrics {
        let Integer todayOrders = db.Order.where(createdAt: utcToday()).count();
        redis.DailyOrders.set(utcToday().toString(), todayOrders);
    }
}
```

### Job Configuration

**config/order-service.dcfg:**

```dcfg
config service ecommerce.OrderService {
  base {
    jobs {
      jobs {
        CleanupExpiredOrders {
          schedule = "0 2 * * *";
          timeout = "300s";
        }
        UpdateMetrics {
          schedule = "*/5 * * * *";
          timeout = "60s";
        }
      }
    }
  }
}
```

---

## CQRS

Datrix supports Command Query Responsibility Segregation (CQRS) with materialized views, commands, and queries.

### Views

```datrix context=service
cqrs {
    view OrderSummaryView {
        UUID orderId : primaryKey;
        String customerName;
        Money totalAmount;
        Integer itemCount;
        OrderStatus status;
    }

    view DashboardView {
        UUID id : primaryKey;
        Integer totalOrders;
        Money totalRevenue;
        Integer pendingCount;
        Integer shippedCount;
    }
}
```

### Projections

A projection reacts to events and keeps a view current. The view it updates is found by name: a
projection named `<Name>Projection` updates the view `<Name>View` of the same `cqrs` block, and a
projection with no such view is an error (`CQRS003`):

```datrix context=service
cqrs {
    view OrderSummaryView {
        UUID orderId : primaryKey;
        String customerName;
        Money totalAmount;
        OrderStatus status;
    }

    projection OrderSummaryProjection {
        on OrderCreated(UUID orderId, Money total, String customerName) {
            OrderSummaryView.upsert(orderId, {
                orderId: orderId,
                customerName: customerName,
                totalAmount: total,
                status: OrderStatus.Pending
            });
        }
    }
}
```

### Commands

```datrix context=service
cqrs {
    command PlaceOrder(PlaceOrderInput input) -> db.Order {
        let Money total = 0;
        foreach item in input.items {
            total = total + item.price * item.quantity;
        }

        let db.Order order = db.Order.create({
            customerId: input.customerId,
            total: total,
            status: OrderStatus.Pending
        });

        foreach item in input.items {
            db.OrderItem.create({
                orderId: order.id,
                productId: item.productId,
                quantity: item.quantity,
                price: item.price
            });
        }

        dispatch OrderCreated(order.id, total, input.customerName);
        return order;
    }
}
```

### Queries

```datrix context=service
cqrs {
    query GetOrderSummary(UUID orderId) -> OrderSummaryView {
        return OrderSummaryView.findOrFail(orderId);
    }

    query GetDashboard(UUID id) -> DashboardView {
        return DashboardView.findOrFail(id);
    }
}
```

A query reads views (or entities); keeping the view current is the projection's job, so a query
never aggregates on the request path.

---

## Storage

Declare file/object storage (S3-compatible) as a block of folders; the bucket and provider are
keys of the block's entry in the service `.dcfg`.

```datrix context=service
storage files {
    folder productImages : path('products/'), allowed(['image/jpeg', 'image/png']), maxSize('5mb');
}
```

Each folder offers `upload`, `download`, `delete`, `exists`, `list` and `getMetadata`, reached as
`files.productImages.upload(...)`; `upload` returns a `StorageRef`.

**Usage in endpoints:**

```datrix context=service
rest_api ProductAPI : basePath('/api/v1/products') {
    @path('/images')
    post uploadProductImage(Bytes image, String filename) : auth(required, providers: [identity], roles: [catalogEditor]) -> StorageRef {
        let StorageRef ref = files.productImages.upload(filename, image, "image/png");
        Log.info("Image uploaded", { key: ref.key });
        return ref;
    }
}
```

---

## Validation and Computed Fields

### Field Validation

Use modifiers for built-in validation:

```datrix context=rdbms
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

```datrix context=rdbms
entity Order {
    Money subtotal;
    Percentage taxRate;
    OrderStatus status;
    Money tax := subtotal * (taxRate / 100);
    Money total := subtotal + tax;

    DateTime dueDate;
    Boolean isOverdue := dueDate < DateTime.now() && status != OrderStatus.Delivered;
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

```datrix context=rdbms
entity Order {
    Money subtotal;
    Money discount;
    Money total;

    validate {
        if (discount > subtotal)
            ValidationError("Discount cannot exceed subtotal");
        if (total != subtotal - discount)
            ValidationError("Total must equal subtotal minus discount");
    }
}
```

Each rule is `if (condition) ValidationError("message");` with a plain string message; every rule
is evaluated and the failures are reported together.

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

```datrix context=rdbms
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
        dispatch OrderCreated(id, total, customerId);

        // Update metrics
        redis.DailyOrders.increment(utcToday().toString());
    }

    beforeUpdate {
        // Increment version for optimistic locking
        version = version + 1;
    }

    afterUpdate {
        // Invalidate cache
        redis.OrderCache.delete(id);

        // Check for status change
        if (isChanged(status)) {
            dispatch OrderStatusChanged(id, oldValue(status), status);
        }
    }

    afterDelete {
        // Cleanup
        redis.OrderCache.delete(id);
        dispatch OrderDeleted(id);
    }
}
```

### Previous Values

| Call | Available In | Purpose |
|------|--------------|---------|
| `isChanged(field)` | `beforeUpdate`, `afterUpdate` | Whether the update changed the field |
| `oldValue(field)` | `beforeUpdate`, `afterUpdate` | The field's value before the update |

**Example:**

```datrix context=entity
afterUpdate {
    if (isChanged(status) && status == OrderStatus.Shipped) {
        dispatch OrderShipped(id, DateTime.now());
    }
}
```

---

## Service Discovery and Resilience

### Service Discovery

Register dependencies on other services:

```datrix
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
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

**config/order-service.dcfg:**

```dcfg
config service ecommerce.OrderService {
  base {
    resilience {
      defaults {
        timeout = "10s";
        retry {
          maxAttempts = 3;
          backoff {
            type = "exponential";
            initial = "1s";
            multiplier = 2;
            max = "10s";
          }
        }
      }
      config {
        PaymentService {
          timeout = "30s";
          circuitBreaker {
            failureThreshold = 5;
            timeout = "60s";
          }
          bulkhead {
            maxConcurrent = 10;
            maxWait = "500ms";
          }
        }
      }
    }
  }
}
```

`defaults` applies to every call to another service; `config` overrides it per dependency, keyed
by the service name as the `uses` line spells it.

> **📖 Reference:** See [Configuration Guide § Resilience](./configuration-guide.md#resilience-configuration) for complete resilience config options.

### Dependency Resilience Policy

Resilience is a property of the **dependency**, declared once and applied everywhere — Datrix never synthesizes timeout/breaker/bulkhead values and never auto-classifies an operation as safe to degrade. A `dependencyPolicy` section under `resilience` declares, for each dependency kind a generated service probes (`cache`, `rdbms`, `pubsub`), its availability, health severity and — for a cache — operation-level failure behavior. The safe baseline is authored **once at the application level** in a `defaults` block; an individual dependency overrides only where it differs.

```dcfg
resilience {
  dependencyPolicy {
    defaults {
      rdbms { availability = "required"; health = "ready"; }

      cache {
        availability = "required"; health = "ready";
        operations {
          read   { onFailure = "raise"; }
          write  { onFailure = "raise"; }
        }
      }
    }

    // Override the app-level baseline for one dependency only where it differs
    rdbms archiveDb { availability = "optional"; health = "degraded"; }
  }
}
```

Key rules:

- **Declared once, inherited.** One `defaults { rdbms { … } }` covers every rdbms block the service realizes; a per-block entry overrides the baseline only where one dependency differs.
- **Uncovered is an error.** A policy-managed operation (a cache `read` or `write`) left uncovered at every level fails generation with `RESILIENCE_POLICY_REQUIRED` — nothing is invented to fill the gap.
- **Only realized knobs are accepted.** A `service`, `extern` or `objectStorage` entry is rejected with `RESILIENCE_POLICY_INVALID`: no generated service probes a peer, so its availability would change nothing. Check a peer in code with `Microservice.health()`/`isAvailable()`.
- **The operation vocabulary is closed.** Only a cache's `read` and `write` have a per-operation failure policy; any other `operations` key is rejected with `RESILIENCE_POLICY_INVALID`. Counter increments, lock acquisitions and rate-limit checks have no policy: their failures always propagate, so a limiter never admits a request it could not count, and there is no opt-out flag.
- **Readiness stays honest.** `availability = "optional"` together with `health = "ready"` is rejected (it would gate readiness on an optional dependency).
- **Typed calls route through resilient clients.** Every typed inter-service call (see [Calling Another Service's Endpoints](#calling-another-services-endpoints)) goes through a generated per-dependency resilient client driven by this policy. Timeout, circuit breaker, and bulkhead are non-amplifying and stay on; **retry is off by default** and is enabled only when the provider endpoint is marked `idempotent` (an HTTP `GET` is *not* assumed idempotent), bounded by a retry budget and suppressed while the breaker is open.

### Liveness, Readiness, and Health

Generated services expose three distinct probes rather than one conflated `/health`:

| Endpoint | Reports |
|----------|---------|
| `/live` | Process liveness only |
| `/ready` | All readiness-blocking dependencies usable and every in-process consumer running — returns 503 otherwise |
| `/health` | Detailed per-dependency report, including `degraded` optional dependencies |

Every language probes the same dependencies — each rdbms block, each nosql block, each pubsub block the service publishes on (through its publish path), each policy-governed cache — and reports each under `<kind>.<block>` (`rdbms.orderDb`, `pubsub.orderEvents`). A dependency declared `health = "degraded"` keeps `/ready` green while `/health` reports `degraded`, unless you set `readyOnDegraded = false` to make it a readiness blocker for guarded rollouts. Deployment probes (Docker healthcheck) point at `/ready`.

---

## Extern Services

**Extern services** let you integrate external libraries, custom tools, or third-party services that live outside the Datrix-generated codebase. You declare the external service's API contract in `.dtrx`, and Datrix generates a **typed HTTP client** in every consuming service — complete with authentication, error types, and contract validation.

### When to Use Extern Services

Extern services are the right choice when:

- You need a **domain-specific tool** that Datrix doesn't generate (pricing engines, ML models, PDF generators)
- You want to wrap a **third-party API** (payment gateways, shipping providers) behind a typed contract
- You have a **legacy service** with a REST API that Datrix services need to call

Extern services are **not** for communication between Datrix-generated services — use `discovery` and `uses` with regular services for that.

### Declaring an Extern Service

An extern service is a top-level `.dtrx` block that describes the external service's API:

```datrix
extern service pricing.PricingEngine('config/pricing-engine.dcfg')
    : version('1.0.0'), description('External pricing engine') {

    // Data types used in API calls
    struct PricingRequest {
        String productId;
        Int quantity;
    }

    struct PricingResponse {
        Decimal totalPrice;
        String currency;
    }

    enum PricingTier {
        STANDARD,
        PREMIUM,
        ENTERPRISE
    }

    // REST API contract (signature-only — no implementation body)
    rest_api PricingAPI : basePath('/api/v1') {
        post calculatePrice(PricingRequest req) -> PricingResponse;
        get getPrice(String productId) -> PricingResponse {
            ensure productId != null;
        }
        delete clearCache();
    }

    // Typed errors the extern service can return
    errors {
        PricingNotFound(String message);
        InvalidQuantity(String message, Int quantity);
    }

    // Authentication method
    auth : apiKey(header: 'X-API-Key');

    // Health check endpoint
    health : path('/health');
}
```

Key differences from a regular `service`:
- Endpoints are **signature-only** (no implementation body, just `;` or `{ ensure ... }`)
- No infrastructure blocks (`rdbms`, `cache`, `pubsub`, `queues`, etc.)
- You provide and deploy the actual implementation yourself

### Consuming an Extern Service

A Datrix service consumes an extern service with `uses`, just like `shared` blocks:

```datrix
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    uses PricingEngine;

    // PricingRequest, PricingResponse and PricingTier are in scope here, and a typed
    // PricingEngine client (with its auth and contracts) is generated into this service.
    rest_api OrderAPI : basePath('/api/v1/orders') {
        @path('/tiers')
        get() : auth(public) -> Array<PricingTier> {
            return [PricingTier.STANDARD, PricingTier.PREMIUM, PricingTier.ENTERPRISE];
        }
    }
}
```

### Deployment Modes

The Datrix-owned extern service access .dcfg file specifies how generated services reach or run it:

**Container mode** — Datrix manages the container alongside your services:

```dcfg
config extern pricing.PricingEngine {
  profile development as "dev" {
    deployment = "container";
    image = "myregistry/pricing-engine:1.2.0";
    port = 8080;
  }
}
```

This generates Docker Compose entries for the extern service, including health checks and environment variables.

**External mode** — The service runs somewhere else (cloud, on-premises):

```dcfg
config extern pricing.PricingEngine {
  profile production as "prod" {
    deployment = "external";
    url = "https://pricing.example.com/api";
  }
}
```

No deployment artifacts are generated. Consuming services receive the URL as an environment variable.

### Generated Code

For each extern service consumed via `uses`, Datrix generates:

| File | Contents |
|------|----------|
| `clients/{name}.py` / `.ts` | Async HTTP client class with one method per endpoint |
| `clients/{name}_models.py` / `.models.ts` | Pydantic models or TypeScript interfaces for structs/enums |
| `clients/{name}_errors.py` / `.errors.ts` | Typed exception classes (if `errors` block exists) |
| `clients/{name}_contracts.py` / `.contracts.ts` | Contract validation functions (if `ensure` clauses exist) |

**Python client usage (generated):**

```python
from clients.pricing_engine import PricingEngineClient
from clients.pricing_engine_models import PricingRequest

client = PricingEngineClient()  # URL from PRICING_ENGINE_SERVICE_URL env var
response = await client.calculate_price(
    PricingRequest(product_id="SKU-123", quantity=5)
)
```

**TypeScript client usage (generated):**

```typescript
import { PricingEngineClient } from './clients/pricing-engine';
import { PricingRequest } from './clients/pricing-engine.models';

const client = new PricingEngineClient();
const response = await client.calculatePrice({
    productId: 'SKU-123',
    quantity: 5,
});
```

### Environment Variables

Datrix automatically injects these environment variables into consuming services:

| Variable | Source | Example |
|----------|--------|---------|
| `{SERVICE}_SERVICE_URL` | Container: `http://{name}:{port}` / External: config `url` | `PRICING_ENGINE_SERVICE_URL` |
| `{SERVICE}_API_KEY` | From auth config secret | `PRICING_ENGINE_API_KEY` |

In Docker Compose, container-mode extern services also get a `depends_on` with `condition: service_healthy`.

> **📖 Reference:** See [Configuration Guide § Extern Service Configuration](./configuration-guide.md#extern-service-configuration) for the complete Datrix-owned `.dcfg` access config schema. See [Language Reference § Extern Services](../reference/language-reference.md#extern-services) for the full syntax.

---

## Multi-Tenancy

Datrix supports multi-tenant applications with tenant isolation at the data layer.

### Defining Tenantable Entities

```datrix context=rdbms
entity Organization extends BaseEntity {
    String(100) name : unique;
    String slug : unique, lowercase;
}

entity User extends BaseEntity with Tenantable {
    String(100) name;
    Email email;

    index(tenantId, email) : unique;   // unique within each tenant
}

entity Order extends BaseEntity with Tenantable {
    UUID customerId : index; // becomes INDEX (tenant_id, customer_id)
    Money total;
}
```

**The builtin `Tenantable` trait (no import needed) adds:**
- A `UUID tenantId` field
- Automatic tenant filtering on all queries, and tenant-scoped indexes and unique constraints
- Validation ensuring tenant context is present

### Configuring Tenancy

**config/order-service.dcfg:**

```dcfg
config service ecommerce.OrderService {
  base {
    tenancy {
      identifier {
        source = "header";
        name = "X-Tenant-Id";
      }
      enforcement = "strict";
    }
  }
}
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
    # Query automatically filtered: WHERE tenant_id = :tenant_id
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

### Declaring a Body Deliberately Cross-Tenant

Tenant scoping is fail-closed by default: every body that reaches a Tenantable entity gets
exactly one tenant, or generation fails. A handful of trusted-caller bodies legitimately need to
read across every tenant instead — a service-to-service route, a role-gated staff route, a
consumer of an event with no tenant, a scheduled job. Write `@crossTenant` on one of these to
declare it intentionally unscoped:

```datrix context=service
jobs {
    @crossTenant
    job SweepStaleOrders {
        let Array<db.Order> stale = db.Order.where(status: OrderStatus.Submitted).all();
        foreach order in stale {
            order.status = OrderStatus.Expired;
            order.save();
        }
    }
}
```

`@crossTenant` is legal only on `auth(service)` endpoints, role-gated `auth(required)` endpoints
whose every provider is workforce-only, service/`rest_api` functions, pub/sub and queue
consumers, and jobs — an ordinary customer-facing route can never declare it, and can never
reach one through a helper call either.

A top-level read in such a body is unscoped; a top-level write (`create`, `update(id, …)`,
batch operations) fails generation. To write for one tenant inside a declared body, either loop
over rows that already carry a tenant, or scope a region explicitly:

```datrix context=service
jobs {
    @crossTenant
    job GenerateMonthlyInvoices {
        let Array<db.Customer> customers = db.Customer.all();
        foreach customer in customers {
            tenant(customer.id) {
                generateInvoicesForPeriod(previousBillingPeriod());
            }
        }
    }
}
```

Everything inside `tenant(<expr>) { … }` is scoped to that one tenant: reads are filtered,
creates are stamped, and calls to tenant-scoped functions carry it. The tenant expression must
be an identifier or a property chain the body already holds — never a literal or a call.

A trusted service route may also name its tenant with a declared path or query parameter instead
of a request-body field:

```datrix context=service
rest_api UsageAPI : basePath('/internal') {
    @path('/usage/:orgId')
    get serviceUsage(UUID orgId) : auth(service, providers: [internal]) -> UsageReport {
        return db.Organization.findOrFail(orgId).usageReport();
    }
}
```

> **📖 Reference:** See [Patterns and Best Practices § Multi-Tenancy](./patterns-and-best-practices.md#multi-tenancy) for implementation patterns, and the [Datrix Syntax Reference § Multi-Tenancy](../../../datrix-language/docs/reference/datrix-syntax-reference.md#multi-tenancy) for the full decorator, block and validator rules.

---

## Best Practices

### 1. Use Abstract Entities for Common Fields

```datrix context=rdbms
abstract entity BaseEntity {
    UUID id : primaryKey, server = uuid();
    DateTime createdAt : server = DateTime.now();
    DateTime updatedAt : server = DateTime.now();
}

// All entities extend BaseEntity
entity User extends BaseEntity { String(100) name; }
entity Order extends BaseEntity { Money total; }
```

### 2. Apply Traits for Cross-Cutting Concerns

```datrix context=rdbms
trait Auditable {
    String? createdBy;
    String? updatedBy;
}

// SoftDeletable is a builtin trait: use it, never redefine it
entity Order extends BaseEntity with Auditable, SoftDeletable { Money total; }
```

### 3. Use Server-Managed Fields

```datrix context=rdbms
entity Order {
    UUID id : primaryKey, server = uuid();        // Server generates
    DateTime createdAt : server = DateTime.now();           // Server sets
    DateTime updatedAt : server = DateTime.now();           // Server updates
    String customerName : trim;            // Client provides
}
```

### 4. Leverage Computed Fields

```datrix context=rdbms
entity Order {
    Money subtotal;
    Percentage taxRate;
    Money tax := subtotal * (taxRate / 100);        // Computed
    Money total := subtotal + tax;                  // Computed
}
```

### 5. Emit Events in Hooks

```datrix context=entity
afterCreate {
    dispatch OrderCreated(id, total, customerId);
}

afterUpdate {
    if (isChanged(status)) {
        dispatch OrderStatusChanged(id, oldValue(status), status);
    }
}
```

### 6. Index Foreign Keys and Frequently Queried Fields

```datrix context=rdbms
entity Order {
    UUID customerId : index;               // Frequently queried
    OrderStatus status : index;            // Frequently filtered
    DateTime createdAt : sortable;         // Frequently sorted
}
```

### 7. Use Enums for Fixed Value Sets

```datrix context=service
enum OrderStatus {
    Pending,
    Confirmed,
    Shipped,
    Delivered,
    Cancelled
}

rdbms db {
    entity Order {
        UUID id : primaryKey, server = uuid();
        OrderStatus status = OrderStatus.Pending;
    }
}
```

### 8. Separate Concerns with Modules

Each file holds one concern: `specs/common/traits.dtrx` the shared traits, `specs/common/entities.dtrx`
the shared abstract entities, and one file per service:

```datrix
// specs/common/traits.dtrx — Shared traits
module ecommerce.common {
    trait Auditable { String? createdBy; }
}

// specs/services/order-service.dtrx — Service-specific
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    enum OrderStatus { Pending, Shipped }
}
```

### 9. Configure Resilience for External Dependencies

```datrix
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    discovery {
        PaymentService {
            loadBalance: roundRobin,
            healthyOnly: true
        }
    }

    // Circuit breaker and retry settings resolve from config/order-service.dcfg.
}
```

### 10. Use Cache Invalidation in Hooks

```datrix context=service
cache redis {
    hash OrderCache : prefix('order:'), ttl(1800) {
        UUID orderId : primaryKey;
        Money total;
    }
}

rdbms db {
    entity Order {
        UUID id : primaryKey, server = uuid();
        Money total;

        afterUpdate {
            redis.OrderCache.delete(id);  // Invalidate cache on update
        }
    }
}
```

---

## Common Patterns

### Pattern: Soft Delete

```datrix context=service
rdbms db {
    // SoftDeletable is builtin: it supplies deletedAt, deletedBy and isDeleted
    entity Order with SoftDeletable {
        UUID id : primaryKey, server = uuid();
        Money total;
    }
}

rest_api OrderAPI : basePath('/api/v1/orders'), rdbms(db) {
    @path('/:id')
    delete(UUID id) : auth(required, providers: [identity]) -> Void {
        let Order order = Order.findOrFail(id);
        order.deletedAt = DateTime.now();
        order.deletedBy = Auth.subject;
        order.save();
    }
}
```

### Pattern: Optimistic Locking

```datrix context=service
exceptions {
    ConflictError : status(409), message("Order was modified by another user");
}

struct OrderUpdate {
    Integer version;
    Money total;
}

rdbms db {
    entity Order {
        UUID id : primaryKey, server = uuid();
        Money total;
        Integer version = 0;

        beforeUpdate {
            version = version + 1;
        }
    }
}

rest_api OrderAPI : basePath('/api/v1/orders'), rdbms(db) {
    @path('/:id')
    patch(UUID id, OrderUpdate data) : auth(required, providers: [identity]) -> Order {
        let Order order = Order.findOrFail(id);
        if (order.version != data.version) {
            throw ConflictError();
        }
        order.total = data.total;
        order.save();
        return order;
    }
}
```

### Pattern: Idempotent Operations

```datrix context=service
enum PaymentStatus { Pending, Settled, Failed }

struct PaymentRequest {
    String idempotencyKey;
    Money amount;
}

rdbms db {
    entity PaymentTransaction {
        UUID id : primaryKey, server = uuid();
        String idempotencyKey : unique;
        Money amount;
        PaymentStatus status;
    }
}

rest_api PaymentAPI : basePath('/api/v1/payments'), rdbms(db) {
    @path('/')
    post(PaymentRequest request) : auth(required, providers: [identity]) -> PaymentTransaction {
        let PaymentTransaction? existing = PaymentTransaction.where(idempotencyKey: request.idempotencyKey).first();
        if (existing != null) {
            return existing;  // Already processed
        }

        return PaymentTransaction.create({
            idempotencyKey: request.idempotencyKey,
            amount: request.amount,
            status: PaymentStatus.Pending
        });
    }
}
```

### Pattern: Saga Pattern (Event-Driven)

```datrix
// Order Service
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    pubsub mq {
        topic OrderEvents {
            publish OrderPlaced(UUID orderId, UUID customerId, Money total);
            publish OrderCancelled(UUID orderId);
        }
    }
}

// Payment Service
service ecommerce.PaymentService('config/payment-service.dcfg') : version('1.0.0') {
    uses OrderService : subscribe;

    pubsub mq {
        topic PaymentEvents {
            publish PaymentReserved(UUID orderId, Money total);
            publish PaymentFailed(UUID orderId, String reason);
        }
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, Money total) {
            // Reserve payment with the service's own fn
            let Boolean reserved = reservePayment(customerId, total);
            if (reserved) {
                dispatch PaymentReserved(orderId, total);
            } else {
                dispatch PaymentFailed(orderId, "Insufficient funds");
            }
        }
    }
}

// Inventory Service
service ecommerce.InventoryService('config/inventory-service.dcfg') : version('1.0.0') {
    uses OrderService : subscribe;

    pubsub mq {
        topic InventoryEvents {
            publish InventoryReserved(UUID orderId);
            publish InventoryFailed(UUID orderId, String reason);
        }
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, Money total) {
            // Reserve inventory with the service's own fn
            let Boolean reserved = reserveStock(orderId);
            if (reserved) {
                dispatch InventoryReserved(orderId);
            } else {
                dispatch InventoryFailed(orderId, "Out of stock");
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

**Last Updated:** April 24, 2026
