# Patterns and Best Practices

**Proven patterns for building robust Datrix applications**

This guide covers common patterns, best practices, and anti-patterns based on real-world Datrix applications.

---

## Table of Contents

1. [Entity Design Patterns](#entity-design-patterns)
2. [API Design Patterns](#api-design-patterns)
3. [Event-Driven Patterns](#event-driven-patterns)
4. [Extern Service Patterns](#extern-service-patterns)
5. [Queue Patterns](#queue-patterns)
6. [Multi-Tenancy Patterns](#multi-tenancy-patterns)
7. [Caching Strategies](#caching-strategies)
8. [Error Handling](#error-handling)
9. [Data Validation](#data-validation)
10. [Testing Strategies](#testing-strategies)
11. [Performance Optimization](#performance-optimization)
12. [Deployment Considerations](#deployment-considerations)
13. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

---

## Entity Design Patterns

### Pattern: Base Entity with Timestamps

**Problem:** Every entity needs ID, created/updated timestamps.

**Solution:** Create abstract base entity.

```datrix context=rdbms
abstract entity BaseEntity {
    UUID id : primaryKey, server = uuid();
    DateTime createdAt : server = DateTime.now();
    DateTime updatedAt : server = DateTime.now();
}

entity User extends BaseEntity {
    // Inherits id, createdAt, updatedAt
    String(100) name;
    Email email : unique;
}
```

**Benefits:**
- ✅ DRY — Define once, use everywhere
- ✅ Consistency — All entities have same base fields
- ✅ Maintainability — Change in one place

---

### Pattern: Soft Delete

**Problem:** Need to delete records without losing data for auditing.

**Solution:** Use the **builtin** `SoftDeletable` trait (opt-in with `with SoftDeletable`—do not redefine the trait). It supplies `deletedAt`, `deletedBy`, and a computed `isDeleted`. See [Architecture Overview — Builtin traits](../architecture/architecture/builtin-traits-enums.md#builtin-traits-and-enums).

```datrix context=service
rdbms db {
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

    // Exclude soft-deleted rows in queries
    @path('/active')
    get() : auth(required, providers: [identity]) -> Array<Order> {
        return Order.where(deletedAt: null).all();
    }
}
```

**Cascade soft deletes:**

```datrix context=rdbms
entity Post extends BaseEntity with SoftDeletable {
    hasMany Comment as comments : onSoftDelete(cascade);
}

entity Comment extends BaseEntity with SoftDeletable {
    belongsTo Post;
}

// When Post is soft-deleted, all Comments are also soft-deleted
```

---

### Pattern: Audit Trail

**Problem:** Track who created/modified records.

**Solution:** Use Auditable trait.

```datrix context=rdbms
trait Auditable {
    String? createdBy;
    String? updatedBy;
}

entity Order extends BaseEntity with Auditable {
    Money total;

    beforeCreate {
        this.createdBy = Auth.subject;
    }

    beforeUpdate {
        this.updatedBy = Auth.subject;
    }
}
```

---

### Pattern: Optimistic Locking

**Problem:** Prevent lost updates when multiple users edit same record.

**Solution:** Use version field.

```datrix context=service
exceptions {
    ConflictError : status(409), message("The record was modified by another user");
}

struct OrderUpdate {
    Integer expectedVersion;
    Money total;
}

rdbms db {
    trait Versionable {
        Integer version = 0;
    }

    entity Order with Versionable {
        UUID id : primaryKey, server = uuid();
        Money total;

        beforeUpdate {
            version = version + 1;
        }
    }
}

rest_api OrderAPI : basePath('/api/v1/orders'), rdbms(db) {
    @path('/:id')
    patch(UUID id, OrderUpdate data) : auth(required, providers: [identity]) -> Order {
        let Order order = Order.findOrFail(id);

        if (order.version != data.expectedVersion) {
            throw ConflictError();
        }

        order.total = data.total;
        order.save();  // version incremented by beforeUpdate
        return order;
    }
}
```

---

### Pattern: Self-Referential Hierarchies

**Problem:** Model tree structures (categories, org charts, comments).

**Solution:** Self-referential relationships with tree helpers.

```datrix context=rdbms
entity Category extends BaseEntity {
    String(100) name;
    belongsTo Category as parent;
    hasMany Category as children;

    // The generated service layer gains tree helpers:
    // get_ancestors, get_descendants, get_roots, list_by_parent_id
}
```

The helpers belong to the generated service code (Python: `get_ancestors()` and friends on the
category service; TypeScript: TypeORM tree repositories), not to DSL expressions.

**Disable tree helpers if not needed:**

```datrix context=rdbms
entity Employee extends BaseEntity {
    belongsTo Employee as manager;
    hasMany Employee as directReports : noTree;  // Plain one-to-many
}
```

---

## API Design Patterns

### Pattern: Standard CRUD with Resources

**Problem:** Need CRUD operations for entities.

**Solution:** Use `resource` keyword.

```datrix context=service
rest_api OrderAPI : basePath('/api/v1') {
    resource db.Order : auth(required, providers: [identity]);  // Full CRUD
}

// Generates:
// POST   /orders      — Create order
// GET    /orders      — List orders (paginated, filtered, sorted)
// GET    /orders/:id  — Get order by ID
// PATCH  /orders/:id  — Update order
// DELETE /orders/:id  — Delete order
```

---

### Pattern: Limited Operations

**Problem:** Entity should be read-only or have limited operations.

**Solution:** Use `: only(...)` modifier.

```datrix context=service
rest_api OrderAPI : basePath('/api/v1') {
    resource db.Order : only(create, list, get), auth(required, providers: [identity]);  // No update/delete
    resource db.OrderItem : only(list, get), auth(public);                               // Read-only
}
```

---

### Pattern: Custom Actions

**Problem:** Need non-CRUD operations (cancel, approve, etc.).

**Solution:** Custom endpoints with explicit paths.

```datrix context=service
rest_api OrderAPI : basePath('/api/v1/orders') {
    resource db.Order : auth(required, providers: [identity]);

    @path('/:id/cancel')
    post(UUID id, CancelRequest request) : auth(required, providers: [identity]) -> db.Order {
        let db.Order order = db.Order.findOrFail(id);

        if (order.status == OrderStatus.Cancelled) {
            throw ValidationError("Order is already cancelled");
        }

        if (order.status == OrderStatus.Shipped) {
            throw ValidationError("Cannot cancel shipped order");
        }

        order.status = OrderStatus.Cancelled;
        order.save();

        dispatch OrderCancelled(id, request.reason ?? "No reason provided");
        return order;
    }

    @path('/:id/approve')
    post(UUID id) : auth(required, providers: [identity], roles: [admin]) -> db.Order {
        let db.Order order = db.Order.findOrFail(id);
        order.status = OrderStatus.Confirmed;
        order.save();
        return order;
    }
}
```

---

### Pattern: Search and Filter

**Problem:** Need complex queries beyond basic CRUD.

**Solution:** Custom search endpoint with filters.

```datrix context=service
rest_api ProductAPI : basePath('/api/v1'), rdbms(db) {
    resource Product : auth(public);

    @path('/products/search')
    get search(
        String? q,                      // Text search
        UUID? categoryId,               // Filter by category
        Money? minPrice,                // Price range
        Money? maxPrice,
        Boolean? inStock                // Availability
    ) : auth(public) -> Array<Product> {
        let Array<Product> matches = Product.where(isActive: true).orderBy(createdAt: desc).limit(100).all();

        // Text search
        if (q != null) {
            matches = matches.filter(p => p.name.contains(q) || p.description.contains(q));
        }

        // Category filter
        if (categoryId != null) {
            matches = matches.filter(p => p.categoryId == categoryId);
        }

        // Price range
        if (minPrice != null) {
            matches = matches.filter(p => p.price >= minPrice);
        }
        if (maxPrice != null) {
            matches = matches.filter(p => p.price <= maxPrice);
        }

        // In stock filter
        if (inStock == true) {
            matches = matches.filter(p => p.stockQuantity > 0);
        }

        return matches;
    }
}
```

---

### Pattern: Pagination

**Problem:** Large result sets need pagination, and a client that shows page numbers needs the total.

**Solution:** Return `Page<T>` and end the chain with `.page(request)`. The route takes one `PageRequest`
(its `offset` and `limit`, always counted in rows); the generated route binds it from the backend's own
query pair and bounds the size at `MAX_PAGE_SIZE`.

```datrix context=service
rest_api OrderAPI : basePath('/api/v1') {
    @path('/orders')
    get listOrders(PageRequest page) : auth(required, providers: [identity]) -> Page<db.Order> {
        return db.Order.where(customerId: Auth.userId()).orderBy(createdAt: desc).page(page);
    }
}
```

The response is `{ items, total, offset, limit }`: `total` counts the same chain the items are cut
from, and `offset`/`limit` are the window the server applied.

**Note:** Resource list endpoints are `Page<T>` routes too, so they page with no code.

---

### Pattern: API Versioning

**Problem:** API needs to evolve without breaking clients.

**Solution:** Version in basePath.

```datrix context=service
// Current version
rest_api OrderAPIV1 : basePath('/api/v1/orders') {
    resource db.Order : auth(required, providers: [identity]);
}

// New version with breaking changes
rest_api OrderAPIV2 : basePath('/api/v2/orders') {
    resource db.Order : only(create, list, get), auth(required, providers: [identity]);  // Removed update/delete

    @path('/:id/update-status')
    post updateStatus(UUID id, StatusChange change) : auth(required, providers: [identity]) -> db.Order {
        let db.Order order = db.Order.findOrFail(id);
        order.status = change.status;
        order.save();
        return order;
    }
}
```

---

## Event-Driven Patterns

**Service-level `subscribe`:** Consumer handlers live in **`subscribe QualifiedTopicName { on Event … }`** blocks that are **siblings** of `pubsub` inside the **service** — not nested under `pubsub`. Use a **qualified** topic name when the topic is defined on another service or on a **`shared`** block (for example `ecommerce.OrderService.mq.OrderEvents` or `IngestionEvents.mq.IngestionEvents`). Declare **`uses TargetName : subscribe;`** (and other modifiers as needed) so the analyzer can enforce SHR004–SHR006.

**`dispatch`** sends pubsub events and queue tasks from hooks and handlers (queue **`dispatch`** follows the same keyword).

### Pattern: Domain Events

**Problem:** Notify other services when important things happen.

**Solution:** Dispatch events in lifecycle hooks.

```datrix context=rdbms
entity Order {
    UUID id : primaryKey, server = uuid();
    UUID customerId;
    Money total;
    OrderStatus status;

    afterCreate {
        dispatch OrderCreated(id, customerId, total);
    }

    afterUpdate {
        if (isChanged(status)) {
            dispatch OrderStatusChanged(id, oldValue(status), status);
        }
    }

    afterDelete {
        dispatch OrderDeleted(id);
    }
}
```

---

### Pattern: Event Subscribers

**Problem:** React to events from other services.

**Solution:** Subscribe to topics.

```datrix
// In NotificationService
service notification.NotificationService('config/notification-service.dcfg') : version('1.0.0') {
    uses OrderService : subscribe;

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderCreated(UUID orderId, Email customerEmail, Money total) {
            Email.send({
                to: customerEmail,
                subject: "Order Confirmation",
                body: #"Your order #{orderId} has been placed."
            });

            Log.info("Order confirmation email sent", { orderId: orderId });
        }

        on OrderShipped(UUID orderId, Phone customerPhone, DateTime shippedAt) {
            SMS.send(customerPhone, #"Your order #{orderId} has shipped!");
        }
    }
}
```

The events carry the contact details the handler needs, so the subscriber never calls back into
the publisher.

---

### Pattern: Saga Pattern (Distributed Transactions)

**Problem:** Multi-step process across services that must be atomic.

**Solution:** Event-driven saga with compensating actions.

```datrix
// Order Service
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    uses PaymentService : subscribe;
    uses InventoryService : subscribe;

    pubsub mq {
        topic OrderEvents {
            publish OrderPlaced(UUID orderId, UUID customerId, Money total);
            publish OrderConfirmed(UUID orderId);
            publish OrderCancelled(UUID orderId, String reason);
        }
    }

    subscribe ecommerce.PaymentService.mq.PaymentEvents {
        on PaymentFailed(UUID orderId, String reason) {
            let db.Order order = db.Order.findOrFail(orderId);
            order.status = OrderStatus.Cancelled;
            order.save();
            dispatch OrderCancelled(orderId, #"Payment failed: {reason}");
        }
    }

    subscribe ecommerce.InventoryService.mq.InventoryEvents {
        on InventoryReserved(UUID orderId) {
            let db.Order order = db.Order.findOrFail(orderId);
            order.status = OrderStatus.Confirmed;
            order.save();
            dispatch OrderConfirmed(orderId);
        }

        on InventoryInsufficient(UUID orderId) {
            let db.Order order = db.Order.findOrFail(orderId);
            order.status = OrderStatus.Cancelled;
            order.save();
            dispatch OrderCancelled(orderId, "Insufficient inventory");
        }
    }
}

// Payment Service
service ecommerce.PaymentService('config/payment-service.dcfg') : version('1.0.0') {
    uses OrderService : subscribe;

    pubsub mq {
        topic PaymentEvents {
            publish PaymentSucceeded(UUID orderId, Money amount);
            publish PaymentFailed(UUID orderId, String reason);
        }
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, Money total) {
            let Boolean charged = chargeCustomer(customerId, total);

            if (charged) {
                dispatch PaymentSucceeded(orderId, total);
            } else {
                dispatch PaymentFailed(orderId, "Card declined");
            }
        }

        on OrderCancelled(UUID orderId, String reason) {
            // Compensating action: refund payment if already charged
            refundPayment(orderId);
        }
    }
}

// Inventory Service
service ecommerce.InventoryService('config/inventory-service.dcfg') : version('1.0.0') {
    uses OrderService : subscribe;

    pubsub mq {
        topic InventoryEvents {
            publish InventoryReserved(UUID orderId);
            publish InventoryInsufficient(UUID orderId);
        }
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, Money total) {
            let Boolean reserved = reserveStock(orderId);

            if (reserved) {
                dispatch InventoryReserved(orderId);
            } else {
                dispatch InventoryInsufficient(orderId);
            }
        }

        on OrderCancelled(UUID orderId, String reason) {
            // Compensating action: release reserved inventory
            releaseStock(orderId);
        }
    }
}
```

`chargeCustomer`, `refundPayment`, `reserveStock` and `releaseStock` are each service's own `fn`
declarations, left out here to keep the saga's shape visible.

---

### Pattern: Shared infrastructure (`shared { }`)

**When to use:** Put **pubsub**, **rdbms**, **cache**, **storage**, **queues**, or **nosql** under a top-level **`shared Name { … }`** when **multiple services** must publish, subscribe, or query the **same** broker, schema, bucket, or queue contract. Examples: one **`topic`** for ingestion events shared by many writers; reference **RDBMS** entities (product tables) read-only from several services; a **cache** used for rate limits across an edge tier.

**When not to use:** If only **one** service touches a resource, keep the block **inside that service** — shared blocks add cross-service coupling and require explicit **`uses`** on every consumer/producer.

**Operational pairing:** The DSL **`uses SharedName : subscribe | publish | readonly | readwrite;`** names only the access mode. The shared block's connection settings live in the shared container's own `config shared` `.dcfg`; a service's call timeouts to other services live in its `resilience` block (see [Configuration guide](./configuration-guide.md#timeout)).

---

### Pattern: Event Sourcing (Basic)

**Problem:** Need complete history of state changes.

**Solution:** Store all events and rebuild state from events.

```datrix context=service
enum OrderStatus { Pending, Confirmed, Shipped, Cancelled }

rdbms db {
    entity OrderEvent {
        UUID id : primaryKey, server = uuid();
        UUID orderId : index;
        String eventType : index;
        OrderStatus newStatus;
        DateTime occurredAt : server = DateTime.now();
    }

    entity Order {
        UUID id : primaryKey, server = uuid();
        OrderStatus status;

        afterUpdate {
            if (isChanged(status)) {
                OrderEvent.create({ orderId: id, eventType: "StatusChanged", newStatus: status });
            }
        }
    }
}

// Rebuild order state from events
fn reconstructOrder(UUID orderId) -> db.Order {
    let Array<db.OrderEvent> events = db.OrderEvent.where(orderId: orderId).orderBy(occurredAt: asc).all();
    let db.Order order = db.Order.findOrFail(orderId);

    foreach event in events {
        // Apply each event to rebuild state
        if (event.eventType == "StatusChanged") {
            order.status = event.newStatus;
        }
    }

    return order;
}
```

---

### Pattern: Serverless handlers (same semantics, different deployment)

**Problem:** Ingestion, webhooks, or scheduled work must deploy as **Lambda** or **Azure Functions** in production, but developers still want **in-process** execution in dev/test without maintaining two copies of the handler.

**Solution:** Put **`subscribe`**, **`job`**, HTTP endpoints, or **`enqueue`** consumers inside **`serverless BlockName { … }`**. The block's entry in the service `.dcfg` chooses **`platform`** per profile: `container` for local parity, `lambda` or `functions` for cloud.

**Example:**

```datrix
service notification.NotificationService('config/notification-service.dcfg') : version('1.0.0') {
    pubsub mq {
        topic UserEvents {
            publish UserRegistered(UUID userId, String email);
        }
    }

    // Serverless event handler
    serverless eventHandlers {
        subscribe notification.NotificationService.mq.UserEvents {
            on UserRegistered(UUID userId, String email) {
                // Send welcome email
                Log.info(#"Sending welcome email to {email}");
            }
        }
    }
}
```

**Config (production):**
```yaml
production:
  platform: lambda        # Deploy as Lambda
  defaults:
    timeout: 60
    memory: 256
```

**Config (development):**
```yaml
development:
  platform: container     # Run in-process locally
```

**Result:** Same handler code runs in-process during local development and as a Lambda function in production. No code duplication, no conditional logic.

**Handler keys:** Config keys under `handlers:` must match DSL-derived names:
- **Event handlers:** `on` event name (e.g., `UserRegistered`)
- **Jobs:** `job` identifier (e.g., `DailyReport`)
- **HTTP endpoints:** `@name('...')` or auto-derived from path+method
- **Queue consumers:** Queue task name

The semantic layer enforces the same reference rules as service-level blocks.

**Shared topics, service-owned handlers:** a **`shared`** block may own the topic several services
publish to, but never a `serverless` block (`SLS007`): the handlers live in a service that `uses`
the shared block:

```datrix
system ecommerce.Platform('config/system.dcfg') : version('1.0.0') {}

shared Analytics('config/analytics.dcfg') {
    pubsub mq {
        topic AnalyticsEvents {
            publish PageViewed(String path);
        }
    }
}

service ecommerce.AnalyticsService('config/analytics-service.dcfg') : version('1.0.0') {
    uses Analytics : subscribe;

    serverless processors {
        subscribe Analytics.mq.AnalyticsEvents {
            on PageViewed(String path) {
                Log.info(#"page {path} viewed");
            }
        }
    }
}
```

**When to use serverless blocks:**
- ✅ Event-driven handlers that scale to zero between invocations
- ✅ Scheduled tasks that run infrequently (daily/weekly reports)
- ✅ Webhook processors with unpredictable traffic
- ✅ Lightweight data transforms or notifications
- ❌ Long-running processes or connection pools (use service containers)
- ❌ Handlers needing persistent WebSocket connections

See [Writing Datrix Applications — Serverless blocks](./writing-datrix-applications.md#serverless-blocks) for complete examples.

---

## Extern Service Patterns

### Pattern: Wrapping a Domain-Specific Tool

**Problem:** Your application needs a computation engine (pricing, risk assessment, ML inference) that Datrix doesn't generate.

**Solution:** Declare an `extern service` with the tool's API contract. Datrix generates typed clients in every consuming service.

```datrix
extern service pricing.PricingEngine('config/pricing-engine.dcfg')
    : version('1.0.0') {

    struct PricingRequest {
        String productId;
        Int quantity;
    }

    struct PricingResponse {
        Decimal totalPrice;
        String currency;
    }

    rest_api PricingAPI : basePath('/api/v1') {
        post calculatePrice(PricingRequest req) -> PricingResponse {
            ensure req.quantity > 0;
        }
    }

    errors {
        PricingNotFound(String message);
    }

    auth : apiKey(header: 'X-API-Key');
    health : path('/health');
}

service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    uses PricingEngine;
    // A typed PricingEngine client is generated into OrderService
}
```

**Benefits:**
- Type-safe API calls — no manual HTTP client code
- Contract validation at call site via `ensure` clauses
- Auth headers injected automatically
- Deployment wired into Docker Compose

### Pattern: Profile-Based Deployment Modes

**Problem:** You want to run the extern service locally during development but point to a managed instance in production.

**Solution:** Use Datrix-owned access config with `container` for dev and `external` for prod:

```dcfg
# config/pricing-engine.dcfg
config extern pricing.PricingEngine {
  profile development as "dev" {
    deployment = "container";
    image = "pricing-engine:dev";
    port = 8080;
    auth {
      type = "apiKey";
      header = "X-API-Key";
      secret = "PRICING_API_KEY";
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
  }
}
```

**Benefits:**
- One spec, different deployment per environment
- Dev gets a local container with health checks
- Prod points to the managed service with no extra infrastructure

### Anti-pattern: Using Extern Services for Datrix-to-Datrix Communication

**Problem:** Two Datrix-generated services need to call each other.

**Wrong:** Declare one as an `extern service`.

**Right:** Use `discovery` and `uses` with regular services. Datrix already generates inter-service clients, health checks, and deployment wiring for regular services. Extern services are for code Datrix does **not** generate.

### Anti-pattern: Missing Ensure Clauses on Critical Endpoints

**Problem:** An extern service call fails deep in the external system because of invalid input.

**Wrong:**

```datrix
extern service pricing.PricingEngine('config/pricing-engine.dcfg') {
    struct PricingRequest { String productId; Int quantity; }
    struct PricingResponse { Decimal totalPrice; }

    rest_api PricingAPI : basePath('/api/v1') {
        post calculatePrice(PricingRequest req) -> PricingResponse;
    }
}
```

**Right:** Add `ensure` clauses so invalid input is caught at the call site before the HTTP request:

```datrix
extern service pricing.PricingEngine('config/pricing-engine.dcfg') {
    struct PricingRequest { String productId; Int quantity; }
    struct PricingResponse { Decimal totalPrice; }

    rest_api PricingAPI : basePath('/api/v1') {
        post calculatePrice(PricingRequest req) -> PricingResponse {
            ensure req.quantity > 0;
            ensure req.productId != null;
        }
    }
}
```

---

## Queue Patterns

### Pattern: Background task processing

**Problem:** Expensive work must not block HTTP request threads.

**Solution:** Declare a `queue` on the owning service, `dispatch` from the handler, and run logic in a **worker** process generated for the consumer service.

```datrix context=service
// OrderService — producer
queues {
    queue ProcessPayment(UUID orderId, Money amount, String currency) {
        ensure amount > 0;
    }
}
// In createOrder endpoint or afterCreate:
// dispatch ProcessPayment(orderId, total, currency);
```

### Pattern: Cross-service queue consumption

**Problem:** Service A creates work that Service B must execute exactly once.

**Solution:** Service A owns the `queues { }` block (and its broker settings in A's `.dcfg`); Service B lists A in `discovery` and implements `enqueue A.TaskName(…) { … }`.

### Pattern: FIFO queue for ordered processing

**Problem:** Tasks for the same business key must run in order.

**Solution:** Use the FIFO modifier: `queue SettlePayment(...) : fifo(merchantId) { … }`.

### Anti-pattern: Using queues for broadcast

**Problem:** Several services need the same notification.

**Wrong:** Multiple `enqueue` targets for the same queue (semantic error **QUE003**).

**Right:** Use **pubsub** for broadcast; use **queues** for point-to-point work.

### When to use queues vs pub/sub

| Scenario | Use |
|----------|-----|
| Notify all interested services | Pub/Sub |
| One worker processes each task | Queue |
| Fire-and-forget fan-out | Pub/Sub |
| Retries, DLQ, visibility timeout | Queue |
| FIFO ordering per key | Queue |

---

## Multi-Tenancy Patterns

### Pattern: Tenant Isolation

**Problem:** SaaS app with multiple organizations, data must be isolated.

**Solution:** Use Tenantable trait and tenant configuration.

```datrix context=rdbms
entity Organization extends BaseEntity {
    String(100) name : unique;
    Boolean isActive = true;
}

// `with Tenantable` (a builtin trait, no import) adds the UUID tenantId field
entity User extends BaseEntity with Tenantable {
    String(100) name;
    Email email : unique;   // becomes UNIQUE (tenant_id, email)
}

entity Project extends BaseEntity with Tenantable {
    String(200) name;
    hasMany Task as tasks;
}

entity Task extends BaseEntity with Tenantable {
    String(200) title;
    belongsTo Project;
}

// All queries on these entities are filtered by tenantId
```

**Config:**

```dcfg
config service projects.ProjectService {
  base {
    tenancy {
      identifier {
        source = "jwt";
        name = "tenant_id";
      }
      enforcement = "strict";
    }
  }
}
```

**Generated behavior:**
- Middleware extracts tenant ID from JWT
- All DB queries automatically add `WHERE tenant_id = ?`
- Attempting to access other tenant's data = error

---

### Pattern: Tenant-Specific Configuration

**Problem:** Different tenants have different feature flags/limits.

**Solution:** Store tenant-level config in Organization entity.

```datrix context=service
enum PlanType {
    Free,
    Starter,
    Professional,
    Enterprise
}

exceptions {
    LimitExceededError : status(403), message("The plan's project limit is reached; upgrade to create more projects");
}

struct NewProject {
    UUID organizationId;
    String(200) name;
}

rdbms db {
    entity Organization {
        UUID id : primaryKey, server = uuid();
        String(100) name;
        PlanType plan = PlanType.Free;
        Integer userLimit;
        Integer projectLimit;
        Integer storageLimitGb;
        Boolean featureAdvancedReports = false;
        Boolean featureApiAccess = false;
    }

    entity Project with Tenantable {
        UUID id : primaryKey, server = uuid();
        String(200) name;
    }
}

rest_api ProjectAPI : basePath('/api/v1/projects'), rdbms(db) {
    // Check tenant limits
    @path('/')
    post(NewProject input) : auth(required, providers: [identity]) -> Project {
        let Organization org = Organization.findOrFail(input.organizationId);

        if (Project.where(tenantId: org.id).count() >= org.projectLimit) {
            throw LimitExceededError();
        }

        return Project.create({ name: input.name });
    }
}
```

---

### Pattern: Cross-Tenant Staff and Service Routes

**Problem:** An internal admin console, a support-staff sweep, or a service-to-service route
needs to read or act across every tenant's rows, not just one — but the default tenant rule
gives every body that touches a Tenantable entity exactly one tenant, or fails generation.

**Solution:** Declare the body `@crossTenant`. It is legal only on `auth(service)` endpoints,
role-gated `auth(required)` endpoints whose every provider is workforce-only, service/`rest_api`
functions, pub/sub and queue consumers, and jobs — never on a public, optional, or customer-
facing route, and never reachable from one through a helper call.

```datrix context=service
rest_api SupportAPI : basePath('/internal/support') {
    @crossTenant
    @path('/organizations/:orgId/credit')
    post(UUID orgId) : auth(required, providers: [workforce], roles: [SupportAgent]) -> Void {
        let db.Organization org = db.Organization.findOrFail(orgId);
        tenant(org.id) {
            applyEmergencyCredit(org.id);
        }
    }
}
```

**Generated behavior:**
- A top-level read is unscoped; a top-level write (`create`, `update(id, …)`, batch operations)
  fails generation instead of silently guessing a tenant.
- Inside `tenant(<expr>) { … }`, or inside a `foreach` over rows that already carry a tenant,
  every read is filtered, every create is stamped, and every call to a tenant-scoped function
  carries that tenant.
- Every declared body logs `cross_tenant_access handler=… kind=…` once, on entry, so every
  unscoped execution is auditable.
- The `tenant(...)` expression must be an identifier or property chain the body already holds
  (`org.id`, never a literal or a computed value) — it can only narrow scope, never widen it.

---

## Caching Strategies

### Pattern: Cache-Aside (Read-Through)

**Problem:** Database queries are expensive.

**Solution:** Check cache first, query DB on miss, populate cache.

```datrix context=service
cache redis {
    hash ProductCache : prefix('product:'), ttl(3600) {
        UUID productId : primaryKey;
        String name;
        Money price;
        Integer stockQuantity;
    }
}

rest_api ProductAPI : basePath('/api/v1/products') {
    @path('/:id')
    get(UUID id) : auth(public) -> db.Product {
        // Check cache first
        let redis.ProductCache? cached = redis.ProductCache.get(id);
        if (cached != null) {
            return db.Product.findOrFail(cached.productId);
        }

        // Cache miss — query database
        let db.Product product = db.Product.findOrFail(id);

        // Populate cache
        redis.ProductCache.set(id, {
            productId: product.id,
            name: product.name,
            price: product.price,
            stockQuantity: product.stockQuantity
        });

        return product;
    }
}
```

---

### Pattern: Write-Through Cache

**Problem:** Cache and DB can get out of sync.

**Solution:** Invalidate cache on write.

```datrix context=rdbms
entity Product {
    UUID id : primaryKey, server = uuid();
    String(200) name;
    Money price;
    Integer stockQuantity;

    afterUpdate {
        redis.ProductCache.delete(id);  // Invalidate cache
    }

    afterDelete {
        redis.ProductCache.delete(id);
    }
}
```

Or refresh the entry immediately instead of deleting it:

```datrix context=entity
afterUpdate {
    redis.ProductCache.set(id, {
        productId: id,
        name: name,
        price: price,
        stockQuantity: stockQuantity
    });
}
```

---

### Pattern: Counter Cache

**Problem:** Counting records on every request is slow.

**Solution:** Use counter cache.

```datrix context=service
struct MetricsResponse {
    Integer ordersToday;
    Date date;
}

cache redis {
    counter ProductViewCount : prefix('product:views');
    counter DailyOrders : prefix('metrics:orders:daily');
}

rdbms db {
    entity Order {
        UUID id : primaryKey, server = uuid();

        // Update daily metrics
        afterCreate {
            redis.DailyOrders.increment(utcToday().toString());
        }
    }
}

rest_api MetricsAPI : basePath('/api/v1') {
    @path('/products/:id')
    get(UUID id) : auth(public) -> db.Product {
        redis.ProductViewCount.increment(id);
        return db.Product.findOrFail(id);
    }

    // Read metrics
    @path('/metrics')
    get() : auth(required, providers: [workforce], roles: [analyst]) -> MetricsResponse {
        let Integer ordersToday = redis.DailyOrders.get(utcToday().toString());
        return { ordersToday: ordersToday, date: utcToday() };
    }
}
```

---

## Error Handling

### Pattern: Explicit Errors

**Problem:** Errors should be clear and actionable.

**Solution:** Throw specific errors with helpful messages.

```datrix context=service
rest_api OrderAPI : basePath('/api/v1/orders') {
    @path('/')
    post(OrderRequest request) : auth(required, providers: [identity]) -> db.Order {
        // Validate customer
        let db.User customer = db.User.findOrFail(request.customerId);

        if (!customer.isActive) {
            throw ValidationError(
                "Customer account is inactive. " +
                "Please reactivate the account before placing orders."
            );
        }

        // Validate items
        if (request.items.length() == 0) {
            throw ValidationError(
                "Order must contain at least one item. " +
                "Please add items to the order."
            );
        }

        foreach item in request.items {
            let db.Product product = db.Product.findOrFail(item.productId);

            if (product.stockQuantity < item.quantity) {
                throw ValidationError(
                    #"Insufficient stock for {product.name}. Requested: {item.quantity}, available: {product.stockQuantity}"
                );
            }
        }

        return db.Order.create({ customerId: customer.id });
    }
}
```

`findOrFail` already answers a missing row with a not-found error that names the entity and the
key; there is no need to repeat that check by hand.

---

### Pattern: Error Logging

**Problem:** Need to track errors for debugging.

**Solution:** Log errors with context.

```datrix context=service
fn processPayment(UUID orderId, PaymentDetails payment) -> PaymentResult {
    let db.Order order = db.Order.findOrFail(orderId);

    try {
        let PaymentResult result = chargeCard(payment, order.total);

        Log.info("Payment processed", {
            orderId: orderId,
            amount: order.total,
            transactionId: result.transactionId
        });

        return result;
    } catch (Exception error) {
        Log.error("Payment failed", {
            orderId: orderId,
            amount: order.total,
            error: error.message
        });

        dispatch PaymentFailed(orderId, error.message);
        throw error;
    }
}
```

---

## Data Validation

### Pattern: Field-Level Validation

**Problem:** Input must meet specific constraints.

**Solution:** Use field modifiers.

```datrix context=rdbms
entity Product {
    String(200) name : trim;                        // Trim whitespace
    String(50) sku : unique, uppercase;             // Unique, uppercase
    Money price : min(0);                           // Price >= 0
    Integer stockQuantity : min(0), max(10000);     // 0-10000 range
    Email email : unique, lowercase, trim;          // Valid email
    URL? website;                                   // Valid URL if provided
    Percentage discount : min(0), max(100);         // 0-100%
}
```

---

### Pattern: Cross-Field Validation

**Problem:** Fields depend on each other.

**Solution:** Use validation blocks.

```datrix context=rdbms
entity Order {
    Money subtotal;
    Money discount;
    Money tax;
    Money total;

    validate {
        if (discount > subtotal)
            ValidationError("Discount cannot exceed the subtotal");

        if (total != subtotal - discount + tax)
            ValidationError("Total must equal subtotal - discount + tax");
    }
}
```

A `validate` block is a list of `if (condition) ValidationError("message");` rules, each message a
plain string literal; every rule is evaluated and the failures are reported together.

---

### Pattern: Business Rule Validation

**Problem:** Complex business rules need validation.

**Solution:** Validate in hooks or custom endpoints.

```datrix context=rdbms
entity Order {
    OrderStatus status;
    DateTime? shippedAt;

    beforeUpdate {
        // Can only ship confirmed orders
        if (status == OrderStatus.Shipped && oldValue(status) != OrderStatus.Confirmed) {
            throw ValidationError(
                #"Cannot ship order with status: {oldValue(status)}. Order must be confirmed first."
            );
        }

        // Set shipped timestamp
        if (status == OrderStatus.Shipped && shippedAt == null) {
            this.shippedAt = DateTime.now();
        }
    }
}
```

---

## Testing Strategies

### Pattern: Test Data Builders

**Problem:** Setting up test data is verbose.

**Solution:** Create builder functions in tests.

```python
# Python test code (not .dtrx)
def create_test_user(
    name: str = "Test User",
    email: str = "test@example.com",
    is_active: bool = True
) -> User:
    return User.create({
        "name": name,
        "email": email,
        "passwordHash": hash_password("password123"),
        "isActive": is_active
    })

def test_user_can_place_order():
    user = create_test_user()
    product = create_test_product(price=100, stock=10)

    order = create_order(customer_id=user.id, items=[
        {"product_id": product.id, "quantity": 2}
    ])

    assert order.total == 200
```

---

### Pattern: Integration Tests

**Problem:** Need to test full workflows.

**Solution:** Test generated APIs end-to-end.

```python
# Python integration test
def test_order_workflow(client):
    # Create user
    user_response = client.post("/api/v1/users", json={
        "name": "Test User",
        "email": "test@example.com"
    })
    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    # Create product
    product_response = client.post("/api/v1/products", json={
        "name": "Test Product",
        "price": 100,
        "stock": 10
    })
    product_id = product_response.json()["id"]

    # Place order
    order_response = client.post("/api/v1/orders", json={
        "customerId": user_id,
        "items": [{"productId": product_id, "quantity": 2}]
    })
    assert order_response.status_code == 201
    order = order_response.json()
    assert order["total"] == 200

    # Cancel order
    cancel_response = client.post(f"/api/v1/orders/{order['id']}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "Cancelled"
```

---

## Performance Optimization

### Pattern: Eager Loading

**Problem:** N+1 query problem with relationships.

**Solution:** Use eager loading (implemented by generators).

```datrix context=rdbms
// In .dtrx, just define relationships
entity Post {
    UUID id : primaryKey, server = uuid();
    belongsTo User as author;
    belongsTo Category;
    hasMany Comment as comments;
}
```

The generated data access layer loads the related rows a read needs, so the DSL carries no
loading hints.

---

### Pattern: Computed Fields vs Stored Fields

**Problem:** Should I compute or store?

**Solution:**
- **Compute** if calculation is cheap and value changes often
- **Store** if calculation is expensive or value rarely changes

```datrix context=rdbms
entity Order {
    Money subtotal;
    Money tax;

    // Cheap calculation, changes often → compute
    Money total := subtotal + tax;

    // Expensive calculation → consider storing
    Integer itemCount;  // Updated in afterCreate/afterUpdate of OrderItem
}
```

---

### Pattern: Indexes

**Problem:** Queries are slow.

**Solution:** Add indexes on frequently queried fields.

```datrix context=rdbms
entity Order {
    UUID customerId : index;           // Frequently filtered
    OrderStatus status : index;        // Frequently filtered
    DateTime createdAt : sortable;     // Frequently sorted
    String orderNumber : unique, index; // Unique constraint + index

    // Composite index: query by customer + status together
    index(customerId, status);
}
```

---

## Deployment Considerations

### Pattern: Environment-Based Configuration

**Problem:** Different settings per environment.

**Solution:** Use profiles.

```dcfg
config system ecommerce.System {
  base {
    deployment {
      runtime = "docker-compose";
      provider = "local";
    }
    defaultTimeout = 30000;
  }

  profile test as "test" extends base {
    defaultTimeout = 10000;
  }

  profile production as "prod" extends base {
    deployment {
      runtime = "ecs-fargate";
      provider = "aws";
    }
    region = "us-east-1";
    defaultTimeout = 90000;
  }
}
```

---

### Pattern: Feature Flags

**Problem:** Deploy code but enable features later.

**Solution:** Store feature flags in config or database.

```datrix context=service
rdbms db {
    entity FeatureFlag {
        UUID id : primaryKey, server = uuid();
        String(100) name : unique;
        Boolean isEnabled = false;
        String? description;
    }
}

fn isFeatureEnabled(String name) -> Boolean {
    return db.FeatureFlag.where(name: name, isEnabled: true).count() > 0;
}

// Use in code
fn processOrder(UUID orderId) -> Void {
    if (isFeatureEnabled("advanced-fraud-detection")) {
        runFraudDetection(orderId);
    }
    Log.info(#"order {orderId} processed");
}
```

---

### Pattern: Health Checks

**Problem:** Need to monitor service health.

**Solution:** Implement health check endpoint (auto-generated).

Nothing is declared in the DSL: every generated service serves `/health`, and its readiness
checks cover database connectivity, cache connectivity and the external services it calls. The
path and probe timings are `healthCheck` keys of the service `.dcfg`.

---

## Anti-Patterns to Avoid

### ❌ Anti-Pattern: No Base Entity

**Problem:**

```datrix context=rdbms
entity User {
    UUID id : primaryKey = uuid();
    DateTime createdAt = DateTime.now();
    DateTime updatedAt = DateTime.now();
    String name;
}

entity Product {
    UUID id : primaryKey = uuid();
    DateTime createdAt = DateTime.now();
    DateTime updatedAt = DateTime.now();
    String name;
}

// Repeated in every entity!
```

**Solution:**

```datrix context=rdbms
abstract entity BaseEntity {
    UUID id : primaryKey, server = uuid();
    DateTime createdAt : server = DateTime.now();
    DateTime updatedAt : server = DateTime.now();
}

entity User extends BaseEntity {
    String name;
}

entity Product extends BaseEntity {
    String name;
}
```

---

### ❌ Anti-Pattern: Missing Indexes

**Problem:**

```datrix context=rdbms
entity Order {
    UUID customerId;  // No index!
    OrderStatus status;  // No index!
}

// Slow query: WHERE customer_id = ? AND status = ?
```

**Solution:**

```datrix context=rdbms
entity Order {
    UUID customerId : index;
    OrderStatus status : index;

    index(customerId, status);  // Composite index
}
```

---

### ❌ Anti-Pattern: Not Using Events

**Problem:**

```datrix context=service
fn createOrder(UUID customerId, Money total) -> db.Order {
    let db.Order order = db.Order.create({ customerId: customerId, total: total });

    // Directly calling other services — tight coupling!
    NotificationService.NotificationAPI.post.orderCreated(order.id);
    InventoryService.InventoryAPI.post.reserveStock(order.id);
    PaymentService.PaymentAPI.post.capturePayment(order.id);

    return order;
}
```

**Solution:**

```datrix context=rdbms
entity Order {
    UUID id : primaryKey, server = uuid();
    UUID customerId;
    Money total;

    afterCreate {
        dispatch OrderCreated(id, customerId, total);
    }
}

// Other services subscribe to OrderCreated event
// Loose coupling, easier to add new subscribers
```

---

### ❌ Anti-Pattern: Nullable Instead of Validation

**Problem:**

```datrix context=rdbms
entity Product {
    String? name;  // Should never be null!
    Money? price;  // Should never be null!
}
```

**Solution:**

```datrix context=rdbms
entity Product {
    String(200) name : trim;   // Required, trimmed
    Money price;               // Required; Money is never negative

    validate {
        if (name.trim().isEmpty()) ValidationError("Name is required");
    }
}
```

---

### ❌ Anti-Pattern: Computed Field for Expensive Calculation

**Problem:**

```datrix context=rdbms
entity Order {
    // Computed field that queries database — BAD!
    Integer itemCount := db.OrderItem.where(orderId: id).count();
}
```

**Solution:**

```datrix context=rdbms
entity Order {
    UUID id : primaryKey, server = uuid();
    Integer itemCount = 0;  // Stored field, updated when items change
}

entity OrderItem {
    UUID id : primaryKey, server = uuid();
    belongsTo Order;

    afterCreate {
        let Order order = Order.findOrFail(orderId);
        order.itemCount = order.itemCount + 1;
        order.save();
    }

    afterDelete {
        let Order order = Order.findOrFail(orderId);
        order.itemCount = order.itemCount - 1;
        order.save();
    }
}
```

---

### ❌ Anti-Pattern: No Cache Invalidation

**Problem:**

```datrix context=service
cache redis {
    hash ProductCache : prefix('product:'), ttl(3600) {
        UUID productId : primaryKey;
        String name;
    }
}

rdbms db {
    entity Product {
        UUID id : primaryKey, server = uuid();
        String name;
        // No cache invalidation on update — stale data!
    }
}
```

**Solution:**

```datrix context=entity
afterUpdate {
    redis.ProductCache.delete(id);  // Invalidate cache
}

afterDelete {
    redis.ProductCache.delete(id);
}
```

---

### ❌ Anti-Pattern: No Multi-Tenancy When Needed

**Problem:**

```datrix context=service
rdbms db {
    entity User {
        UUID id : primaryKey, server = uuid();
        String name;
        UUID organizationId;  // Manual tenant field
    }
}

// Must remember to filter by organizationId in every query — error-prone!
fn listUsers() -> Array<db.User> {
    // Forgot to filter by organizationId — data leak!
    return db.User.all();
}
```

**Solution:**

```datrix context=service
rdbms db {
    entity User with Tenantable {
        UUID id : primaryKey, server = uuid();
        String name;
    }
}

// Automatic tenant filtering in all queries
fn listUsers() -> Array<db.User> {
    return db.User.all();  // Automatically filtered by tenantId
}
```

---

## Summary Checklist

**Entity Design:**
- ✅ Use abstract base entities for common fields
- ✅ Apply traits for cross-cutting concerns
- ✅ Add indexes on foreign keys and frequently queried fields
- ✅ Use server-managed fields (the `server` modifier: `DateTime createdAt : server = DateTime.now();`)
- ✅ Leverage computed fields for derived values
- ✅ Implement soft delete with SoftDeletable trait
- ✅ Add audit trail with Auditable trait
- ✅ Use optimistic locking for concurrent updates

**API Design:**
- ✅ Use `resource` for standard CRUD
- ✅ Limit operations with `: only(...)` when needed
- ✅ Implement custom actions for non-CRUD operations
- ✅ Provide search/filter endpoints
- ✅ Support pagination for large result sets
- ✅ Version APIs with basePath

**Events:**
- ✅ Emit domain events in lifecycle hooks
- ✅ Use events for cross-service communication
- ✅ Implement saga pattern for distributed transactions
- ✅ Log all events for debugging

**Caching:**
- ✅ Use cache-aside pattern for reads
- ✅ Invalidate cache on writes
- ✅ Use counter caches for aggregates
- ✅ Set appropriate TTLs

**Validation:**
- ✅ Use field modifiers for simple validation
- ✅ Use validation blocks for cross-field rules
- ✅ Validate business rules in hooks
- ✅ Provide clear, actionable error messages

**Performance:**
- ✅ Add indexes on frequently queried fields
- ✅ Use eager loading for relationships
- ✅ Cache expensive queries
- ✅ Use computed fields for cheap calculations

---

## Next Steps

- Apply these patterns to your Datrix applications
- Read [Writing Datrix Applications](./writing-datrix-applications.md) for detailed syntax
- See [Complete Examples](./complete-examples.md) for working code
- Reference [Configuration Guide](./configuration-guide.md) for config details

---

**Last Updated:** April 24, 2026
