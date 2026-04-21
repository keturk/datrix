# Datrix Language Reference

Datrix is a domain-specific language for defining microservice architectures. A `.dtrx` file describes your entire backend — services, data models, APIs, messaging, caching, and infrastructure — in a concise, platform-agnostic syntax. The Datrix compiler validates your definitions and generates production-ready code for your target language and platform.

---

## File Structure

Every Datrix application is organized around three top-level blocks:

```dtrx
// system.dtrx — entry point (paths are relative to this file)
include 'common.dtrx';
include 'order-service.dtrx';

system ecommerce : version('1.0.0') {
    config('config/system-config.yaml');
    registry('config/registry.yaml');
    gateway('config/gateway.yaml');
    observability('config/observability.yaml');
}
```

| Block | Cardinality | Purpose |
|-------|-------------|---------|
| `system` | Exactly one per application | Global infrastructure: gateway, observability, service registry |
| `module` | Multiple | Shared code: traits, abstract entities, enums, structs, constants, `exceptions`, `scalar` |
| `service` | Multiple | Business logic + owned infrastructure |

Multiple files can contribute to the same service — the compiler merges them automatically.

---

## Services

A service is the unit of deployment. Everything inside a service block belongs to that service.

```dtrx
service ecommerce.OrderService : version('1.0.0') {

    config('config/order-service/config.yaml');
    registration('config/order-service/registration.yaml');

    discovery {
        UserService    { loadBalance: roundRobin, healthyOnly: true }
        PaymentService { loadBalance: roundRobin, healthyOnly: true }
    }

    resilience('config/order-service/resilience.yaml');

    rdbms db('config/order-service/datasources.yaml') { ... }
    cache redis('config/order-service/cache.yaml') { ... }
    pubsub mq('config/order-service/pubsub.yaml') { ... }

    rest_api OrderAPI : basePath('/api/v1/orders') { ... }
}
```

---

## Entities

Entities define your data model with fields, types, relationships, validation, and lifecycle hooks.

```dtrx
entity Order extends BaseEntity with Auditable {
    UUID customerId -> db.Customer : index;
    String(200) description : trim;
    Money total;
    OrderStatus status = OrderStatus.Pending;
    Boolean isOverdue := dueDate < now();

    index(customerId, status);

    afterCreate {
        emit OrderCreated(id, total);
    }
}
```

Key features:
- **Inheritance**: `extends BaseEntity` inherits fields from abstract entities
- **Traits**: `with Auditable` mixes in reusable field groups
- **Relationships**: `belongsTo`, `hasMany`, `hasOne`, and **`manyToMany`** define entity relationships. `manyToMany` generates a junction table and requires a matching inverse on the target entity (see [Many-to-Many](../../../datrix-language/docs/reference/datrix-syntax-reference.md) in the syntax reference). `onSoftDelete` cascades soft-deletes to children (valid on `hasMany`/`hasOne` only, requires `SoftDeletable` on both entities). See **Self-Referential Tree Helpers** below for tree behavior and the `noTree` modifier.
- **Computed fields**: `:=` defines derived values
- **Lifecycle hooks**: `afterCreate`, `afterUpdate`, `afterDelete` trigger side effects
- **Validation modifiers**: `: trim`, `: unique`, `: index`, `: nullable`
- **Default values**: `= OrderStatus.Pending`, `= now()`, `= uuid()`

### Self-Referential Tree Helpers

When an entity has both a self-referential `belongsTo` and a self-referential `hasMany` (e.g. `Category` with `parent` and `children`), the generators emit **tree helpers**: SQL CHECK constraint (no self-reference), Python service methods (`get_ancestors`, `get_descendants`, `get_roots`, `list_by_parent_id`), and TypeScript TypeORM tree decorators (`@Tree('closure-table')`, `@TreeParent()`, `@TreeChildren()`). Use the **`noTree`** modifier on the `hasMany` to disable this and get plain `ManyToOne`/`OneToMany` (e.g. `hasMany Employee as directReports : noTree`). Semantic rules REL007 (warning) and REL008 (error) enforce consistent use of `noTree` and self-ref pairs.

---

## Type System

Datrix provides a rich type system that maps to concrete types in each target language and database.

### Primitives

`String`, `Text`, `Integer`, `Float`, `Boolean`, `Decimal`, `Bytes`

### Domain Types

`UUID`, `Email`, `URL`, `Phone`, `IPAddress`, `JSON`, `Slug`, `Money`, `Percentage`, `Color`, `CountryCode`, `LanguageCode`, `CurrencyCode`, `PostalCode`, `Latitude`, `Longitude`, `CreditCard`, `IBAN`, `Password`

### Temporal Types

`DateTime`, `UDateTime` (UTC), `Date`, `Time`, `Duration`, `Timestamp`

### Collections

`List<T>`, `Map<K, V>`, `Set<T>`

### Sized Types

`String(200)` limits to 200 characters. `Decimal(10,2)` sets precision and scale.

### Nullability

`String? note` — the `?` suffix makes a field nullable.

---

## Enums

```dtrx
enum OrderStatus {
    Pending,
    Confirmed,
    Shipped,
    Delivered,
    Cancelled
}
```

Enums are first-class types used in fields, parameters, and event payloads.

---

## REST APIs

```dtrx
rest_api OrderAPI : basePath('/api/v1/orders') {
    resource db.Order;
    resource db.OrderItem : only(list, get), access(admin);

    @path('/search')
    fn search(String? query, OrderStatus? status) -> List<Order> {
        return db.Order.filter(
            title.contains(query) && status == status
        );
    }
}
```

`resource` generates standard CRUD endpoints. Use `: only(...)` to limit operations, `: access(...)` to restrict access. Custom endpoints are defined as functions.

---

## Event-Driven Messaging

```dtrx
pubsub mq('config/pubsub.yaml') {
    topic OrderEvents {
        publish OrderCreated(UUID orderId, Money total);
        publish OrderShipped(UUID orderId, DateTime shippedAt);
    }

    subscribe OrderEvents {
        on OrderCreated(UUID orderId, Money total) {
            Log.info("Order created", { orderId: orderId });
        }
    }
}
```

Topics, events, publishers, and subscribers are defined declaratively. The compiler validates that every subscribed event has a matching publisher.

### Event Contracts

Events can declare value-level invariants using `ensure` clauses:

```dtrx
publish OrderCreated(UUID orderId, Decimal totalAmount, Int itemCount) {
    ensure totalAmount > 0;
    ensure itemCount > 0;
}
```

Contracts are enforced at the publisher side — fail-fast at `emit`, before invalid payloads reach subscribers. See the [Event Contracts Guide](../guide/event-contracts.md) for full syntax, generated code examples, and design decisions.

---

## Caching

```dtrx
cache redis('config/cache.yaml') {
    hash OrderCache on db.Order ttl(30m) {
        UUID orderId : primaryKey;
        String customerName;
        OrderStatus status;
    }

    counter OrderViewCount : prefix('order:views');
}
```

Hash caches and counters are defined with TTL and key strategies.

---

## Background Jobs

```dtrx
job CleanupExpired cron('0 */6 * * *') {
    let expired = db.Order.filter(status == OrderStatus.Pending && createdAt < now() - 24h);
    for (order in expired) {
        order.status = OrderStatus.Cancelled;
        db.Order.save(order);
    }
}
```

---

## CQRS

```dtrx
cqrs {
    view DashboardView {
        Int totalOrders;
        Money totalRevenue;
        Int pendingCount;
    }

    query GetDashboard -> DashboardView { ... }
    command PlaceOrder(UUID customerId, List<OrderItem> items) -> Order { ... }
}
```

---

## Storage

```dtrx
storage images(bucket: 'product-images') {
    upload(Bytes file, String filename) -> URL;
    download(String key) -> Bytes;
    delete(String key);
}
```

---

## Service Discovery and Resilience

```dtrx
discovery {
    PaymentService { loadBalance: roundRobin, healthyOnly: true }
}

resilience('config/resilience.yaml');
```

Service discovery and resilience (circuit breaker, retry, bulkhead) are configured per service. Generators produce the appropriate client-side implementation.

---

## Built-in Objects

Datrix provides built-in objects for common operations, available without imports:

| Object | Purpose |
|--------|---------|
| `Auth` | Authentication and authorization |
| `Cache` | Cache read/write operations |
| `Crypto` | Hashing, encryption, token generation |
| `DateTime` | Date/time parsing and formatting |
| `Email` | Send email notifications |
| `Http` | HTTP client for external APIs |
| `JSON` | Parse and serialize JSON |
| `Log` | Structured logging |
| `Math` | Mathematical operations |
| `Queue` | Message queue operations |
| `Random` | Random value generation |
| `Request` | HTTP request context |
| `SMS` | SMS notifications |
| `Storage` | File/object storage (S3-compatible) |
| `String` | String manipulation |
| `Validator` | Input validation helpers |

---

## Imports and Modules

```dtrx
// Import from a module
from ecommerce.common import BaseEntity, Auditable;

// Module definition — shared across services
module ecommerce.common {
    trait Auditable {
        String? createdBy;
        String? updatedBy;
    }

    abstract entity BaseEntity {
        UUID id : primaryKey, server = uuid();
        DateTime createdAt : server = now();
        DateTime updatedAt : server = now();
    }
}
```

Modules provide reusable traits, abstract entities, enums, and structs that can be imported by any service.

---

## Decorators and Modifiers

**Decorators** (`@name`) apply to DSL functions and to REST endpoints (for example `@retry`, `@rateLimit` on a `rest_api` operation). They are **not** used for server-managed entity fields — those use the **`server`** modifier on the field instead (see below).

```dtrx
@authorize @cache(ttl: 60s)
fn getUser(UUID id) -> User { ... }
```

**Modifiers** (`: name, …`) apply to fields and declarations. **`server`** marks a field as server-managed (populate from server defaults / hooks, excluded from client create/update payloads):

```dtrx
String email : unique, index, trim;
UUID id : primaryKey, server = uuid();
DateTime createdAt : server = now();
UUID authorId -> db.Author : cascade(delete);
resource db.Order : only(list, get), access(admin);
```

---

## Specification-Level Tests

`test` blocks at the service level verify business logic through real execution. They complement auto-generated tests (which verify structure and wiring) by exercising lifecycle hooks, computed fields, validation rules, and event emission.

```dtrx
test("overdue books are flagged on update") {
    #Book book = db.Book.create({
        dueDate: today().subtractDays(1),
        status: BookStatus.Available
    });
    book.title = "Trigger Update";
    book.save();
    assert book.status == BookStatus.Overdue;
}

test("validation rejects empty title") {
    assert throws(() => db.Book.create({ title: "" }), ValidationError("Title is required"));
}

test("afterCreate emits BookCreated") {
    #Book book = db.Book.create({ title: "New Book" });
    assert emitted(BookCreated(book.id, book.title));
}
```

Key features:
- **`assert expression;`** — Boolean assertion, fails the test if false
- **`throws(() => call, error)`** — Verifies that a call raises the expected error
- **`emitted(Event(params))`** — Verifies that an event was emitted during the test
- **Real execution** — `.create()` persists, `.save()` updates, hooks fire through the service layer
- **Self-contained** — Each test sets up its own data, no shared state
- **Cross-block** — Tests can reference entities from any `rdbms` block in the same service

Transpiles to pytest (Python) or Jest (TypeScript) under `tests/spec/` / `test/spec/`. See the [Spec Testing Guide](../guide/spec-testing.md) for full syntax and best practices.

---

## Exceptions catalog

Declare domain-specific errors with HTTP status codes on **`module`** or **`service`**. Each entry can include `status(N)`, optional `message("…")`, and optional structured fields in `{ … }`.

```dtrx
module ecommerce.common {
    exceptions {
        InvalidCurrencyError : status(400), message("Unsupported currency code");
    }
}

service ecommerce.OrderService : version('1.0.0') {
    exceptions {
        OrderExpiredError : status(410), message("Order has expired and cannot be modified");
        InsufficientStockError : status(409), message("Not enough stock available") {
            Int availableStock;
            Int requestedQuantity;
        }
    }
}
```

Design and semantics: [DESIGN-DSL-SYNTAX-EXTENSIONS.md](../../../design/DESIGN-DSL-SYNTAX-EXTENSIONS.md) (section 2C).

---

## Custom scalar types

Define constrained aliases on top of existing primitive or domain types inside **`module`** or **`service`**. Use the new scalar name as a field type elsewhere in the module/service.

```dtrx
module aviation.common {
    scalar Altitude : Float {
        min(0);
        max(60000);
    }

    scalar IataCode : String(3) {
        pattern("[A-Z]{3}");
    }
}
```

These differ from **extension-pack** scalars (declared via `use extension` and `DatrixExtension`): packs add wholly new types with per-language maps; custom scalars are aliases with constraints. See [DESIGN-DSL-SYNTAX-EXTENSIONS.md](../../../design/DESIGN-DSL-SYNTAX-EXTENSIONS.md) (section 2D) and [DESIGN-DOMAIN-EXTENSIONS.md](../../../design/DESIGN-DOMAIN-EXTENSIONS.md).

---

## Expression Language

Datrix includes a full expression language for business logic inside hooks, jobs, API functions, event handlers, and test blocks:

```dtrx
// Variables and assignment
let total = order.items.map(i => i.price * i.quantity).reduce((a, b) => a + b, 0);

// Conditionals
if (total > 1000) {
    order.discount = total * 0.1;
}

// Iteration
for (item in order.items) {
    item.subtotal = item.price * item.quantity;
}

// Transactions
transaction {
    db.Order.save(order);
    db.Inventory.decrementStock(order.items);
}
```
