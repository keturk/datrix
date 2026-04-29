# Patterns and Best Practices

**Proven patterns for building robust Datrix applications**

This guide covers common patterns, best practices, and anti-patterns based on real-world Datrix applications.

---

## Table of Contents

1. [Entity Design Patterns](#entity-design-patterns)
2. [API Design Patterns](#api-design-patterns)
3. [Event-Driven Patterns](#event-driven-patterns)
4. [Queue Patterns](#queue-patterns)
5. [Multi-Tenancy Patterns](#multi-tenancy-patterns)
6. [Caching Strategies](#caching-strategies)
7. [Error Handling](#error-handling)
8. [Data Validation](#data-validation)
9. [Testing Strategies](#testing-strategies)
10. [Performance Optimization](#performance-optimization)
11. [Deployment Considerations](#deployment-considerations)
12. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

---

## Entity Design Patterns

### Pattern: Base Entity with Timestamps

**Problem:** Every entity needs ID, created/updated timestamps.

**Solution:** Create abstract base entity.

```dtrx
abstract entity BaseEntity {
    UUID id : primaryKey, server = uuid();
    UDateTime createdAt : server = utcNow();
    UDateTime updatedAt : server = utcNow();
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

**Solution:** Use the **builtin** `SoftDeletable` trait (opt-in with `with SoftDeletable`—do not redefine the trait). It supplies `deletedAt`, `deletedBy`, and a computed `isDeleted`. See [Architecture Overview — Builtin traits](../architecture/architecture-overview.md#builtin-traits-and-enums).

```dtrx
entity Order extends BaseEntity with SoftDeletable {
    // entity fields
}

// In API (conceptual)
delete deleteOrder(UUID id) {
    let order = db.Order.findOrFail(id);
    order.deletedAt = now();
    order.deletedBy = Request.userId();
    db.Order.save(order);
}

// Exclude soft-deleted in queries
get listOrders() -> List<Order> {
    return db.Order.filter(deletedAt == null);
}
```

**Cascade soft deletes:**

```dtrx
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

```dtrx
trait Auditable {
    String? createdBy;
    String? updatedBy;
}

entity Order extends BaseEntity with Auditable {
    Money total;

    beforeCreate {
        this.createdBy = Request.userId();
    }

    beforeUpdate {
        this.updatedBy = Request.userId();
    }
}
```

---

### Pattern: Optimistic Locking

**Problem:** Prevent lost updates when multiple users edit same record.

**Solution:** Use version field.

```dtrx
trait Versionable {
    Integer version = 0;
}

entity Order extends BaseEntity with Versionable {
    Money total;

    beforeUpdate {
        version = version + 1;
    }
}

// In update endpoint
patch updateOrder(UUID id, Integer expectedVersion, OrderUpdate data) -> Order {
    let order = db.Order.findOrFail(id);

    if (order.version != expectedVersion) {
        throw ConflictError(
            "Order was modified by another user. " +
            "Expected version: " + expectedVersion +
            ", current version: " + order.version
        );
    }

    // Apply updates
    order.total = data.total;
    db.Order.save(order);  // version auto-incremented
    return order;
}
```

---

### Pattern: Self-Referential Hierarchies

**Problem:** Model tree structures (categories, org charts, comments).

**Solution:** Self-referential relationships with tree helpers.

```dtrx
entity Category extends BaseEntity {
    String(100) name;
    belongsTo Category as parent;
    hasMany Category as children;

    // Tree helpers automatically generated:
    // - get_ancestors()
    // - get_descendants()
    // - get_roots()
    // - list_by_parent_id()
}

// Get category with ancestors
get getCategory(UUID id) -> CategoryResponse {
    let category = db.Category.findOrFail(id);
    let ancestors = category.get_ancestors();

    return CategoryResponse {
        category: category,
        breadcrumb: ancestors.map(c => c.name)
    };
}
```

**Disable tree helpers if not needed:**

```dtrx
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

```dtrx
rest_api OrderAPI : basePath('/api/v1') {
    resource db.Order;  // Full CRUD
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

```dtrx
rest_api OrderAPI : basePath('/api/v1') {
    resource db.Order : only(create, list, get);      // No update/delete
    resource db.OrderItem : only(list, get);          // Read-only
}
```

---

### Pattern: Custom Actions

**Problem:** Need non-CRUD operations (cancel, approve, etc.).

**Solution:** Custom endpoints with explicit paths.

```dtrx
rest_api OrderAPI : basePath('/api/v1/orders') {
    resource db.Order;

    @path('/:id/cancel')
    @authorize
    post cancel(UUID id, String? reason) -> Order {
        let order = db.Order.findOrFail(id);

        if (order.status == OrderStatus.Cancelled) {
            throw ValidationError("Order is already cancelled");
        }

        if (order.status == OrderStatus.Shipped) {
            throw ValidationError("Cannot cancel shipped order");
        }

        order.status = OrderStatus.Cancelled;
        db.Order.save(order);

        dispatch OrderCancelled(id, reason ?? "No reason provided");
        return order;
    }

    @path('/:id/approve')
    @authorize(admin)
    post approve(UUID id) -> Order {
        let order = db.Order.findOrFail(id);
        order.status = OrderStatus.Confirmed;
        db.Order.save(order);
        return order;
    }
}
```

---

### Pattern: Search and Filter

**Problem:** Need complex queries beyond basic CRUD.

**Solution:** Custom search endpoint with filters.

```dtrx
rest_api ProductAPI : basePath('/api/v1') {
    resource db.Product;

    @path('/products/search')
    get search(
        String? q,                      // Text search
        UUID? categoryId,               // Filter by category
        Money? minPrice,                // Price range
        Money? maxPrice,
        Boolean? inStock,               // Availability
        String? sortBy,                 // Sort field
        String? sortOrder               // Sort direction
    ) -> List<Product> {
        let query = db.Product.query();

        // Text search
        if (q != null) {
            query = query.where(
                name.contains(q) || description.contains(q)
            );
        }

        // Category filter
        if (categoryId != null) {
            query = query.where(categoryId == categoryId);
        }

        // Price range
        if (minPrice != null) {
            query = query.where(price >= minPrice);
        }
        if (maxPrice != null) {
            query = query.where(price <= maxPrice);
        }

        // In stock filter
        if (inStock == true) {
            query = query.where(stockQuantity > 0);
        }

        // Sorting
        if (sortBy != null) {
            let order = sortOrder == "desc" ? desc : asc;
            query = query.orderBy(sortBy, order);
        } else {
            query = query.orderBy(createdAt, desc);  // Default sort
        }

        return query.limit(100);
    }
}
```

---

### Pattern: Pagination

**Problem:** Large result sets need pagination.

**Solution:** Use page/limit parameters (auto-generated for resources).

```dtrx
@path('/orders')
get listOrders(
    Integer? page = 1,
    Integer? limit = 20,
    OrderStatus? status
) -> PaginatedResponse<Order> {
    let query = db.Order.filter(status == status);

    let total = query.count();
    let offset = (page - 1) * limit;
    let orders = query.skip(offset).limit(limit);

    return PaginatedResponse {
        data: orders,
        total: total,
        page: page,
        limit: limit,
        pages: Math.ceil(total / limit)
    };
}
```

**Note:** Resource endpoints automatically support pagination via `?page=1&limit=20`.

---

### Pattern: API Versioning

**Problem:** API needs to evolve without breaking clients.

**Solution:** Version in basePath.

```dtrx
// Current version
rest_api OrderAPIV1 : basePath('/api/v1/orders') {
    resource db.Order;
}

// New version with breaking changes
rest_api OrderAPIV2 : basePath('/api/v2/orders') {
    resource db.Order : only(create, list, get);  // Removed update/delete

    @path('/:id/update-status')
    post updateStatus(UUID id, OrderStatus status) -> Order {
        // New way to update orders
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

```dtrx
entity Order {
    OrderStatus status;

    afterCreate {
        dispatch OrderCreated(id, customerId, total);
    }

    afterUpdate {
        if (status != $old.status) {
            dispatch OrderStatusChanged(id, $old.status, status);
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

```dtrx
// In NotificationService
service notification.NotificationService : version('1.0.0') {
    pubsub mq('config/notification-service/pubsub.yaml') {
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderCreated(UUID orderId, UUID customerId, Money total) {
            let customer = UserService.getUser(customerId);

            Email.send(
                to: customer.email,
                subject: "Order Confirmation",
                body: "Your order #" + orderId + " has been placed."
            );

            Log.info("Order confirmation email sent", {
                orderId: orderId,
                customerId: customerId
            });
        }

        on OrderShipped(UUID orderId, DateTime shippedAt) {
            let order = OrderService.getOrder(orderId);
            let customer = UserService.getUser(order.customerId);

            SMS.send(
                to: customer.phone,
                message: "Your order #" + orderId + " has shipped!"
            );
        }
    }
}
```

---

### Pattern: Saga Pattern (Distributed Transactions)

**Problem:** Multi-step process across services that must be atomic.

**Solution:** Event-driven saga with compensating actions.

```dtrx
// Order Service
service ecommerce.OrderService : version('1.0.0') {
    pubsub mq('config/order-service/pubsub.yaml') {
        topic OrderEvents {
            publish OrderPlaced(UUID orderId, UUID customerId, List<OrderItem> items);
            publish OrderConfirmed(UUID orderId);
            publish OrderCancelled(UUID orderId, String reason);
        }
    }

    subscribe ecommerce.PaymentService.mq.PaymentEvents {
        on PaymentFailed(UUID orderId, String reason) {
            let order = db.Order.findOrFail(orderId);
            order.status = OrderStatus.Cancelled;
            db.Order.save(order);
            dispatch OrderCancelled(orderId, "Payment failed: " + reason);
        }
    }

    subscribe ecommerce.InventoryService.mq.InventoryEvents {
        on InventoryReserved(UUID orderId) {
            let order = db.Order.findOrFail(orderId);
            order.status = OrderStatus.Confirmed;
            db.Order.save(order);
            dispatch OrderConfirmed(orderId);
        }

        on InventoryInsufficient(UUID orderId) {
            let order = db.Order.findOrFail(orderId);
            order.status = OrderStatus.Cancelled;
            db.Order.save(order);
            dispatch OrderCancelled(orderId, "Insufficient inventory");
        }
    }
}

// Payment Service
service ecommerce.PaymentService : version('1.0.0') {
    pubsub mq('config/payment-service/pubsub.yaml') {
        topic PaymentEvents {
            publish PaymentSucceeded(UUID orderId, Money amount);
            publish PaymentFailed(UUID orderId, String reason);
        }
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, List<OrderItem> items) {
            let success = processPayment(customerId, calculateTotal(items));

            if (success) {
                dispatch PaymentSucceeded(orderId, calculateTotal(items));
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
service ecommerce.InventoryService : version('1.0.0') {
    pubsub mq('config/inventory-service/pubsub.yaml') {
        topic InventoryEvents {
            publish InventoryReserved(UUID orderId);
            publish InventoryInsufficient(UUID orderId);
        }
    }

    subscribe ecommerce.OrderService.mq.OrderEvents {
        on OrderPlaced(UUID orderId, UUID customerId, List<OrderItem> items) {
            let canReserve = checkAndReserve(items);

            if (canReserve) {
                dispatch InventoryReserved(orderId);
            } else {
                dispatch InventoryInsufficient(orderId);
            }
        }

        on OrderCancelled(UUID orderId, String reason) {
            // Compensating action: release reserved inventory
            releaseInventory(orderId);
        }
    }
}
```

---

### Pattern: Shared infrastructure (`shared { }`)

**When to use:** Put **pubsub**, **rdbms**, **cache**, **storage**, **queues**, or **nosql** under a top-level **`shared Name { … }`** when **multiple services** must publish, subscribe, or query the **same** broker, schema, bucket, or queue contract. Examples: one **`topic`** for ingestion events shared by many writers; reference **RDBMS** entities (airport tables) read-only from several services; a **cache** used for rate limits across an edge tier.

**When not to use:** If only **one** service touches a resource, keep the block **inside that service** — shared blocks add cross-service coupling and require explicit **`uses`** on every consumer/producer.

**Operational pairing:** Pair DSL **`uses SharedName : subscribe | publish | readonly | readwrite;`** with **`dependencies('config/dependencies.yaml');`** for URLs, timeouts, and health checks (see [Configuration guide](./configuration-guide.md)).

---

### Pattern: Event Sourcing (Basic)

**Problem:** Need complete history of state changes.

**Solution:** Store all events and rebuild state from events.

```dtrx
entity OrderEvent extends BaseEntity {
    UUID orderId : index;
    String eventType : index;
    JSON eventData;
    DateTime occurredAt : server = now();
}

entity Order {
    afterUpdate {
        db.OrderEvent.create({
            orderId: id,
            eventType: "OrderUpdated",
            eventData: {
                oldStatus: $old.status,
                newStatus: status,
                updatedBy: Request.userId()
            }
        });
    }
}

// Rebuild order state from events
fn reconstructOrder(UUID orderId) -> Order {
    let events = db.OrderEvent.filter(orderId == orderId)
        .orderBy(occurredAt, asc);

    let order = db.Order.findOrFail(orderId);

    for (event in events) {
        // Apply each event to rebuild state
        if (event.eventType == "OrderUpdated") {
            order.status = event.eventData.newStatus;
        }
        // ... handle other event types
    }

    return order;
}
```

---

## Queue Patterns

### Pattern: Background task processing

**Problem:** Expensive work must not block HTTP request threads.

**Solution:** Declare a `queue` on the owning service, `dispatch` from the handler, and run logic in a **worker** process generated for the consumer service.

```dtrx
// OrderService — producer
queues('config/order-service/queue.yaml') {
    queue ProcessPayment(UUID orderId, Money amount, String currency) {
        ensure amount > 0;
    }
}
// In createOrder endpoint or afterCreate:
// dispatch ProcessPayment(orderId, total, currency);
```

### Pattern: Cross-service queue consumption

**Problem:** Service A creates work that Service B must execute exactly once.

**Solution:** Service A owns `queue.yaml` and `queues { }`; Service B lists A in `discovery` and implements `enqueue A.TaskName(…) { … }`.

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

```dtrx
from datrix.builtin import Tenantable;

entity Organization extends BaseEntity {
    String(100) name : unique;
    Boolean isActive = true;
}

entity User extends BaseEntity with Tenantable {
    String(100) name;
    Email email : unique;
    UUID organizationId;  // Tenant identifier

    belongsTo Organization;
}

entity Project extends BaseEntity with Tenantable {
    String(200) name;
    UUID organizationId;  // Tenant identifier

    belongsTo Organization;
    hasMany Task as tasks;
}

entity Task extends BaseEntity with Tenantable {
    String(200) title;
    UUID projectId;
    UUID organizationId;  // Tenant identifier

    belongsTo Project;
}

// All queries automatically filtered by organizationId
```

**Config:**

```yaml
# service-config.yaml
production:
  platform: ecs-fargate
  tenancy:
    identifier:
      source: jwt            # Extract from JWT
      name: organizationId   # Claim name
    enforcement: strict      # All queries require tenant context
```

**Generated behavior:**
- Middleware extracts tenant ID from JWT
- All DB queries automatically add `WHERE organization_id = ?`
- Attempting to access other tenant's data = error

---

### Pattern: Tenant-Specific Configuration

**Problem:** Different tenants have different feature flags/limits.

**Solution:** Store tenant-level config in Organization entity.

```dtrx
enum PlanType {
    Free,
    Starter,
    Professional,
    Enterprise
}

entity Organization extends BaseEntity {
    String(100) name;
    PlanType plan = PlanType.Free;
    Integer userLimit : min(1);
    Integer projectLimit : min(1);
    Integer storageLimit : min(0);  // In GB
    Boolean featureAdvancedReports = false;
    Boolean featureApiAccess = false;
}

// Check tenant limits
post createProject(String name) -> Project {
    let org = db.Organization.findOrFail(Request.tenantId());

    let currentProjects = db.Project.filter(organizationId == org.id).count();
    if (currentProjects >= org.projectLimit) {
        throw LimitExceededError(
            "Project limit reached for " + org.plan + " plan. " +
            "Upgrade to create more projects."
        );
    }

    return db.Project.create({
        name: name,
        organizationId: org.id
    });
}
```

---

## Caching Strategies

### Pattern: Cache-Aside (Read-Through)

**Problem:** Database queries are expensive.

**Solution:** Check cache first, query DB on miss, populate cache.

```dtrx
cache redis {
    hash ProductCache on db.Product ttl(1h) {
        UUID productId : primaryKey;
        String name;
        Money price;
        Integer stockQuantity;
    }
}

get getProduct(UUID id) -> Product {
    // Check cache first
    let cached = ProductCache.get(id);
    if (cached != null) {
        return cached;
    }

    // Cache miss — query database
    let product = db.Product.findOrFail(id);

    // Populate cache
    ProductCache.set(id, {
        productId: product.id,
        name: product.name,
        price: product.price,
        stockQuantity: product.stockQuantity
    });

    return product;
}
```

---

### Pattern: Write-Through Cache

**Problem:** Cache and DB can get out of sync.

**Solution:** Invalidate cache on write.

```dtrx
entity Product {
    afterUpdate {
        ProductCache.delete(id);  // Invalidate cache
    }

    afterDelete {
        ProductCache.delete(id);
    }
}

// Or refresh cache immediately
entity Product {
    afterUpdate {
        ProductCache.set(id, {
            productId: id,
            name: name,
            price: price,
            stockQuantity: stockQuantity
        });
    }
}
```

---

### Pattern: Counter Cache

**Problem:** Counting records on every request is slow.

**Solution:** Use counter cache.

```dtrx
cache redis {
    counter ProductViewCount : prefix('product:views');
    counter DailyOrders : prefix('metrics:orders:daily');
}

get getProduct(UUID id) -> Product {
    ProductViewCount.increment(id);
    return db.Product.findOrFail(id);
}

// Update daily metrics
entity Order {
    afterCreate {
        DailyOrders.increment(utcToday().toString());
    }
}

// Read metrics
get getMetrics() -> MetricsResponse {
    let today = utcToday().toString();
    let ordersToday = DailyOrders.get(today);

    return MetricsResponse {
        ordersToday: ordersToday,
        date: utcToday()
    };
}
```

---

## Error Handling

### Pattern: Explicit Errors

**Problem:** Errors should be clear and actionable.

**Solution:** Throw specific errors with helpful messages.

```dtrx
post createOrder(UUID customerId, List<OrderItem> items) -> Order {
    // Validate customer
    let customer = db.User.findBy({ id: customerId });
    if (customer == null) {
        throw NotFoundError(
            "Customer not found with ID: " + customerId +
            ". Please provide a valid customer ID."
        );
    }

    if (!customer.isActive) {
        throw ValidationError(
            "Customer account is inactive. " +
            "Please reactivate the account before placing orders."
        );
    }

    // Validate items
    if (items.length == 0) {
        throw ValidationError(
            "Order must contain at least one item. " +
            "Please add items to the order."
        );
    }

    for (item in items) {
        let product = db.Product.findBy({ id: item.productId });
        if (product == null) {
            throw NotFoundError(
                "Product not found: " + item.productId +
                ". Available products: " + db.Product.all().map(p => p.id).join(", ")
            );
        }

        if (product.stockQuantity < item.quantity) {
            throw ValidationError(
                "Insufficient stock for " + product.name +
                ". Requested: " + item.quantity +
                ", available: " + product.stockQuantity
            );
        }
    }

    // Create order...
}
```

---

### Pattern: Error Logging

**Problem:** Need to track errors for debugging.

**Solution:** Log errors with context.

```dtrx
post processPayment(UUID orderId, PaymentDetails payment) -> PaymentResult {
    let order = db.Order.findOrFail(orderId);

    try {
        let result = PaymentGateway.charge(payment, order.total);

        Log.info("Payment processed", {
            orderId: orderId,
            amount: order.total,
            transactionId: result.transactionId
        });

        return result;
    } catch (error) {
        Log.error("Payment failed", {
            orderId: orderId,
            amount: order.total,
            error: error.message,
            customerId: order.customerId
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

```dtrx
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

```dtrx
entity Order {
    Money subtotal;
    Money discount;
    Money tax;
    Money total;

    validate {
        if (discount > subtotal) {
            throw ValidationError(
                "Discount ($" + discount + ") cannot exceed subtotal ($" + subtotal + ")"
            );
        }

        let expectedTotal = subtotal - discount + tax;
        if (total != expectedTotal) {
            throw ValidationError(
                "Total is incorrect. " +
                "Expected: $" + expectedTotal +
                ", got: $" + total
            );
        }
    }
}
```

---

### Pattern: Business Rule Validation

**Problem:** Complex business rules need validation.

**Solution:** Validate in hooks or custom endpoints.

```dtrx
entity Order {
    OrderStatus status;
    DateTime? shippedAt;

    beforeUpdate {
        // Can only ship confirmed orders
        if (status == OrderStatus.Shipped && $old.status != OrderStatus.Confirmed) {
            throw ValidationError(
                "Cannot ship order with status: " + $old.status +
                ". Order must be confirmed first."
            );
        }

        // Set shipped timestamp
        if (status == OrderStatus.Shipped && shippedAt == null) {
            this.shippedAt = now();
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

```dtrx
// In .dtrx, just define relationships
entity Post {
    belongsTo User as author;
    belongsTo Category;
    hasMany Comment as comments;
}

// Generated code includes eager loading
get getPost(UUID id) -> Post {
    return db.Post.with(['author', 'category', 'comments']).findOrFail(id);
}
```

---

### Pattern: Computed Fields vs Stored Fields

**Problem:** Should I compute or store?

**Solution:**
- **Compute** if calculation is cheap and value changes often
- **Store** if calculation is expensive or value rarely changes

```dtrx
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

```dtrx
entity Order {
    UUID customerId : index;           // Frequently filtered
    OrderStatus status : index;        // Frequently filtered
    DateTime createdAt : sortable;     // Frequently sorted
    String orderNumber : unique, index; // Unique constraint + index
}

// Composite index
entity Order {
    UUID customerId;
    OrderStatus status;

    index(customerId, status);  // Query by customer + status together
}
```

---

## Deployment Considerations

### Pattern: Environment-Based Configuration

**Problem:** Different settings per environment.

**Solution:** Use profiles.

```yaml
# config/system-config.yaml
test:
  language: python
  hosting: docker
  defaultTimeout: 10000

development:
  language: python
  hosting: docker
  defaultTimeout: 30000

staging:
  language: python
  hosting: aws
  region: us-east-1
  defaultTimeout: 60000

production:
  language: python
  hosting: aws
  region: us-east-1
  defaultTimeout: 90000
  network:
    vpcId: vpc-prod
    appSubnets: [subnet-1, subnet-2, subnet-3]
```

---

### Pattern: Feature Flags

**Problem:** Deploy code but enable features later.

**Solution:** Store feature flags in config or database.

```dtrx
entity FeatureFlag extends BaseEntity {
    String(100) name : unique;
    Boolean isEnabled = false;
    String? description;
}

fn isFeatureEnabled(String name) -> Boolean {
    let flag = db.FeatureFlag.findBy({ name: name });
    return flag != null && flag.isEnabled;
}

// Use in code
post processOrder(UUID orderId) -> Order {
    if (isFeatureEnabled("advanced-fraud-detection")) {
        runFraudDetection(orderId);
    }

    // Continue processing...
}
```

---

### Pattern: Health Checks

**Problem:** Need to monitor service health.

**Solution:** Implement health check endpoint (auto-generated).

```dtrx
// Health check endpoint automatically generated at /health

// Custom health checks in generated code:
// - Database connectivity
// - Cache connectivity
// - External service availability
```

---

## Anti-Patterns to Avoid

### ❌ Anti-Pattern: No Base Entity

**Problem:**

```dtrx
entity User {
    UUID id : primaryKey = uuid();
    DateTime createdAt = now();
    DateTime updatedAt = now();
    String name;
}

entity Product {
    UUID id : primaryKey = uuid();
    DateTime createdAt = now();
    DateTime updatedAt = now();
    String name;
}

// Repeated in every entity!
```

**Solution:**

```dtrx
abstract entity BaseEntity {
    UUID id : primaryKey, server = uuid();
    DateTime createdAt : server = now();
    DateTime updatedAt : server = now();
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

```dtrx
entity Order {
    UUID customerId;  // No index!
    OrderStatus status;  // No index!
}

// Slow query: WHERE customer_id = ? AND status = ?
```

**Solution:**

```dtrx
entity Order {
    UUID customerId : index;
    OrderStatus status : index;

    index(customerId, status);  // Composite index
}
```

---

### ❌ Anti-Pattern: Not Using Events

**Problem:**

```dtrx
post createOrder(...) -> Order {
    let order = db.Order.create({...});

    // Directly calling other services — tight coupling!
    NotificationService.sendEmail(order.customerId, "Order created");
    InventoryService.reserveStock(order.items);
    PaymentService.capturePayment(order.paymentId);

    return order;
}
```

**Solution:**

```dtrx
entity Order {
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

```dtrx
entity Product {
    String? name;  // Should never be null!
    Money? price;  // Should never be null!
}
```

**Solution:**

```dtrx
entity Product {
    String(200) name : trim;   // Required, validated
    Money price : min(0);      // Required, positive
}
```

---

### ❌ Anti-Pattern: Computed Field for Expensive Calculation

**Problem:**

```dtrx
entity Order {
    // Computed field that queries database — BAD!
    Integer itemCount := db.OrderItem.filter(orderId == id).count();
}
```

**Solution:**

```dtrx
entity Order {
    Integer itemCount = 0;  // Stored field

    // Update when items change
}

entity OrderItem {
    afterCreate {
        let order = db.Order.findOrFail(orderId);
        order.itemCount = order.itemCount + 1;
        db.Order.save(order);
    }

    afterDelete {
        let order = db.Order.findOrFail(orderId);
        order.itemCount = order.itemCount - 1;
        db.Order.save(order);
    }
}
```

---

### ❌ Anti-Pattern: No Cache Invalidation

**Problem:**

```dtrx
cache redis {
    hash ProductCache on db.Product ttl(1h) { ... }
}

entity Product {
    // No cache invalidation on update — stale data!
}
```

**Solution:**

```dtrx
entity Product {
    afterUpdate {
        ProductCache.delete(id);  // Invalidate cache
    }

    afterDelete {
        ProductCache.delete(id);
    }
}
```

---

### ❌ Anti-Pattern: No Multi-Tenancy When Needed

**Problem:**

```dtrx
entity User {
    String name;
    UUID organizationId;  // Manual tenant field
}

// Must remember to filter by organizationId in every query — error-prone!
get listUsers() -> List<User> {
    // Forgot to filter by organizationId — data leak!
    return db.User.all();
}
```

**Solution:**

```dtrx
from datrix.builtin import Tenantable;

entity User extends BaseEntity with Tenantable {
    String name;
    UUID organizationId;  // Tenant field
}

// Automatic tenant filtering in all queries
get listUsers() -> List<User> {
    return db.User.all();  // Automatically filtered by tenant
}
```

---

## Summary Checklist

**Entity Design:**
- ✅ Use abstract base entities for common fields
- ✅ Apply traits for cross-cutting concerns
- ✅ Add indexes on foreign keys and frequently queried fields
- ✅ Use server-managed fields (`@` prefix)
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
