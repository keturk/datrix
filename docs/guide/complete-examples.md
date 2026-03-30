# Complete Examples

**Working Datrix applications you can copy and adapt**

This guide provides complete, production-ready examples of common Datrix application patterns. Each example includes `.dtrx` files and configuration files you can copy and modify.

---

## Table of Contents

1. [Blog Service](#example-1-blog-service)
2. [E-Commerce System](#example-2-e-commerce-system)
3. [Event-Driven Microservices](#example-3-event-driven-microservices)
4. [Multi-Tenant SaaS](#example-4-multi-tenant-saas)
5. [CQRS Pattern](#example-5-cqrs-pattern)
6. [File Upload Service](#example-6-file-upload-service)
7. [Scheduled Job Service](#example-7-scheduled-job-service)

---

## Example 1: Blog Service

A complete blog platform with users, posts, comments, and tags.

### Project Structure

```
blog/
├── specs/
│   ├── system.dtrx
│   ├── common/
│   │   └── base.dtrx
│   └── services/
│       └── blog-service.dtrx
└── config/
    ├── system-config.yaml
    ├── gateway.yaml
    ├── registry.yaml
    ├── observability.yaml
    └── blog-service/
        ├── service-config.yaml
        ├── datasources.yaml
        ├── registration.yaml
        └── resilience.yaml
```

### specs/common/base.dtrx

```dtrx
// Common module with shared traits and base entities
module blog.common {
    trait Timestamped {
        @DateTime createdAt = now();
        @DateTime updatedAt = now();
    }

    trait SoftDeletable {
        DateTime? deletedAt;
    }

    abstract entity BaseEntity with Timestamped {
        @UUID id : primaryKey = uuid();
    }
}
```

### specs/services/blog-service.dtrx

```dtrx
// Blog service with entities and API
from blog.common import BaseEntity, SoftDeletable;

service blog.BlogService : version('1.0.0'), description('Blog management service') {
    config('config/blog-service/service-config.yaml');
    registration('config/blog-service/registration.yaml');
    discovery { }
    resilience('config/blog-service/resilience.yaml');

    enum PostStatus {
        Draft,
        Published,
        Archived
    }

    rdbms db('config/blog-service/datasources.yaml') {
        entity User extends BaseEntity {
            String(100) name : trim;
            Email email : unique, lowercase, index;
            Password passwordHash : hidden;
            String? bio;
            URL? website;
            Boolean isActive = true;
        }

        entity Category extends BaseEntity {
            String(100) name : unique, trim;
            String(100) slug : unique, lowercase;
            String? description;
        }

        entity Tag extends BaseEntity {
            String(50) name : unique, trim, lowercase;
            String(50) slug : unique, lowercase;
        }

        entity Post extends BaseEntity with SoftDeletable {
            String(200) title : trim;
            String(200) slug : unique, lowercase, index;
            Text content;
            Text? excerpt;
            PostStatus status = PostStatus.Draft : index;
            DateTime? publishedAt : sortable;
            Integer viewCount = 0 : sortable;

            belongsTo User as author : index;
            belongsTo Category : index;
            manyToMany Tag as tags through PostTag;
            hasMany Comment as comments;

            // Computed field
            Boolean isPublished := status == PostStatus.Published && publishedAt != null;

            afterCreate {
                if (status == PostStatus.Published) {
                    emit PostPublished(id, title, author.id);
                }
            }

            afterUpdate {
                if (status == PostStatus.Published && $old.status != PostStatus.Published) {
                    this.publishedAt = now();
                    emit PostPublished(id, title, author.id);
                }
            }
        }

        entity Comment extends BaseEntity with SoftDeletable {
            Text content : trim;
            Boolean isApproved = false;

            belongsTo Post : index;
            belongsTo User as author : index;
            belongsTo Comment as parent;  // For threaded comments
            hasMany Comment as replies;

            afterCreate {
                emit CommentAdded(id, post.id, author.id);
            }
        }
    }

    cache redis('config/blog-service/datasources.yaml') {
        hash PostCache on db.Post ttl(30m) {
            UUID postId : primaryKey;
            String title;
            String slug;
            PostStatus status;
        }

        counter PostViewCount : prefix('post:views');
    }

    pubsub mq('config/blog-service/datasources.yaml') {
        topic BlogEvents {
            publish PostPublished(UUID postId, String title, UUID authorId);
            publish CommentAdded(UUID commentId, UUID postId, UUID authorId);
        }

        subscribe BlogEvents {
            on PostPublished(UUID postId, String title, UUID authorId) {
                Log.info("Post published", { postId: postId, title: title });
            }
        }
    }

    rest_api BlogAPI : basePath('/api/v1') {
        resource db.User : only(list, get), access(public);
        resource db.Post : access(public);
        resource db.Category : access(public);
        resource db.Tag : access(public);
        resource db.Comment : access(authenticated);

        @path('/posts/:slug')
        get getPostBySlug(String slug) -> db.Post {
            let post = db.Post.findBy({ slug: slug });
            if (post == null) {
                throw NotFoundError("Post not found");
            }
            PostViewCount.increment(post.id);
            return post;
        }

        @path('/posts/:id/publish')
        @authorize
        post publishPost(UUID id) -> db.Post {
            let post = db.Post.findOrFail(id);
            if (post.status == PostStatus.Published) {
                throw ValidationError("Post is already published");
            }
            post.status = PostStatus.Published;
            post.publishedAt = now();
            db.Post.save(post);
            return post;
        }

        @path('/posts/search')
        get searchPosts(String? q, PostStatus? status) -> List<db.Post> {
            return db.Post.filter(
                title.contains(q) &&
                status == status &&
                deletedAt == null
            ).orderBy(publishedAt, desc).limit(50);
        }
    }
}
```

### specs/system.dtrx

```dtrx
// System entry point
include 'common/base.dtrx';
include 'services/blog-service.dtrx';

system blog.System : version('1.0.0') {
    config('config/system-config.yaml');
    registry('config/registry.yaml');
    gateway('config/gateway.yaml');
    observability('config/observability.yaml');
}
```

### config/system-config.yaml

```yaml
test:
  language: python
  hosting: docker
  defaultTimeout: 30000

production:
  language: python
  hosting: aws
  region: us-east-1
  network:
    vpcId: vpc-abc123
    appSubnets: [subnet-app-1, subnet-app-2]
    dataSubnets: [subnet-data-1, subnet-data-2]
```

### config/blog-service/datasources.yaml

```yaml
test:
  rdbms:
    engine: postgres
    platform: container
    host: localhost
    port: 5432
    database: blog_test
    username: postgres
    password: ${POSTGRES_PASSWORD}
    docker_image: postgres:16-alpine
    volume_path: ./data/postgres
    sync_driver: psycopg2
    async_driver: asyncpg

  cache:
    engine: redis
    platform: container
    host: localhost
    port: 6379
    docker_image: redis:7-alpine
    volume_path: ./data/redis

  pubsub:
    engine: kafka
    platform: container
    brokers: localhost:9092
    docker_image: confluentinc/cp-kafka:7.5.0
    volume_path: ./data/kafka

production:
  rdbms:
    engine: postgres
    platform: rds
    database: blog_prod

  cache:
    engine: redis
    platform: elasticache

  pubsub:
    engine: kafka
    platform: msk
```

---

## Example 2: E-Commerce System

Multi-service e-commerce platform with orders, inventory, and payments.

### Project Structure

```
ecommerce/
├── specs/
│   ├── system.dtrx
│   ├── common/
│   │   ├── traits.dtrx
│   │   └── entities.dtrx
│   └── services/
│       ├── user-service.dtrx
│       ├── product-service.dtrx
│       ├── order-service.dtrx
│       └── inventory-service.dtrx
└── config/
    └── ... (configs per service)
```

### specs/common/traits.dtrx

```dtrx
module ecommerce.common {
    trait Timestamped {
        @DateTime createdAt = now();
        @DateTime updatedAt = now();
    }

    trait Auditable {
        String? createdBy;
        String? updatedBy;
    }

    trait SoftDeletable {
        DateTime? deletedAt;
        String? deletedBy;
    }

    trait Versionable {
        Integer version = 0;
    }
}
```

### specs/common/entities.dtrx

```dtrx
from ecommerce.common import Timestamped;

module ecommerce.common {
    abstract entity BaseEntity with Timestamped {
        @UUID id : primaryKey = uuid();
    }

    struct Address {
        String(100) street;
        String(100) city;
        String(50) state;
        PostalCode postalCode;
        CountryCode country;
    }

    struct Money {
        Decimal(10,2) amount;
        CurrencyCode currency;
    }
}
```

### specs/services/user-service.dtrx

```dtrx
from ecommerce.common import BaseEntity, Address, SoftDeletable;

service ecommerce.UserService : version('1.0.0') {
    config('config/user-service/service-config.yaml');
    registration('config/user-service/registration.yaml');
    discovery { }

    enum UserRole {
        Customer,
        Admin,
        Seller
    }

    rdbms db('config/user-service/datasources.yaml') {
        entity User extends BaseEntity with SoftDeletable {
            String(100) name : trim;
            Email email : unique, lowercase, index;
            Password passwordHash : hidden;
            Phone? phone;
            UserRole role = UserRole.Customer;
            Boolean isVerified = false;
            Boolean isActive = true;

            Address? shippingAddress;
            Address? billingAddress;

            afterCreate {
                emit UserRegistered(id, email, name);
            }
        }
    }

    pubsub mq('config/user-service/datasources.yaml') {
        topic UserEvents {
            publish UserRegistered(UUID userId, Email email, String name);
            publish UserVerified(UUID userId);
        }
    }

    rest_api UserAPI : basePath('/api/v1/users') {
        resource db.User : only(list, get, update), access(authenticated);

        @path('/register')
        @access(public)
        post register(String name, Email email, Password password) -> db.User {
            let existing = db.User.findBy({ email: email });
            if (existing != null) {
                throw ValidationError("Email already registered");
            }

            let user = db.User.create({
                name: name,
                email: email,
                passwordHash: Auth.hashPassword(password),
                isVerified: false
            });

            return user;
        }
    }
}
```

### specs/services/product-service.dtrx

```dtrx
from ecommerce.common import BaseEntity, SoftDeletable;

service ecommerce.ProductService : version('1.0.0') {
    config('config/product-service/service-config.yaml');
    registration('config/product-service/registration.yaml');
    discovery { }

    enum ProductStatus {
        Draft,
        Active,
        OutOfStock,
        Discontinued
    }

    rdbms db('config/product-service/datasources.yaml') {
        entity Category extends BaseEntity {
            String(100) name : unique, trim;
            String(100) slug : unique, lowercase;
            belongsTo Category as parent;
            hasMany Category as children;
            hasMany Product as products;
        }

        entity Product extends BaseEntity with SoftDeletable {
            String(200) name : trim;
            String(200) slug : unique, lowercase, index;
            Text description;
            String(50) sku : unique, uppercase;
            Money price : min(0);
            Money? salePrice : min(0);
            Integer stockQuantity = 0 : min(0);
            ProductStatus status = ProductStatus.Draft : index;
            List<String> images;

            belongsTo Category : index;

            // Computed fields
            Boolean inStock := stockQuantity > 0;
            Boolean onSale := salePrice != null;
            Money effectivePrice := onSale ? salePrice : price;

            validate {
                if (onSale && salePrice >= price) {
                    throw ValidationError("Sale price must be less than regular price");
                }
            }
        }
    }

    cache redis('config/product-service/datasources.yaml') {
        hash ProductCache on db.Product ttl(1h) {
            UUID productId : primaryKey;
            String name;
            Money price;
            Integer stockQuantity;
        }

        counter ProductViewCount : prefix('product:views');
    }

    rest_api ProductAPI : basePath('/api/v1') {
        resource db.Category : access(public);
        resource db.Product : access(public);

        @path('/products/search')
        get search(String? q, UUID? categoryId, Money? maxPrice) -> List<db.Product> {
            return db.Product.filter(
                name.contains(q) &&
                categoryId == categoryId &&
                effectivePrice <= maxPrice &&
                status == ProductStatus.Active
            ).limit(100);
        }
    }
}
```

### specs/services/order-service.dtrx

```dtrx
from ecommerce.common import BaseEntity, Auditable, Versionable;

service ecommerce.OrderService : version('1.0.0') {
    config('config/order-service/service-config.yaml');
    registration('config/order-service/registration.yaml');

    discovery {
        UserService { loadBalance: roundRobin, healthyOnly: true }
        ProductService { loadBalance: roundRobin, healthyOnly: true }
        InventoryService { loadBalance: roundRobin, healthyOnly: true }
    }

    resilience('config/order-service/resilience.yaml');

    enum OrderStatus {
        Pending,
        Confirmed,
        Processing,
        Shipped,
        Delivered,
        Cancelled,
        Refunded
    }

    enum PaymentStatus {
        Pending,
        Authorized,
        Captured,
        Failed,
        Refunded
    }

    rdbms db('config/order-service/datasources.yaml') {
        entity Order extends BaseEntity with Auditable, Versionable {
            String(20) orderNumber : unique, uppercase, index;
            UUID customerId : index;
            OrderStatus status = OrderStatus.Pending : index;
            PaymentStatus paymentStatus = PaymentStatus.Pending;
            Money subtotal : min(0);
            Money tax : min(0);
            Money shipping : min(0);
            Money discount = 0 : min(0);
            Money total : min(0);
            Text? notes;

            hasMany OrderItem as items;

            validate {
                if (total != subtotal + tax + shipping - discount) {
                    throw ValidationError("Total calculation is incorrect");
                }
            }

            afterCreate {
                emit OrderPlaced(id, customerId, total);
            }

            afterUpdate {
                if (status != $old.status) {
                    emit OrderStatusChanged(id, $old.status, status);
                }
            }
        }

        entity OrderItem extends BaseEntity {
            UUID productId : index;
            String(200) productName;
            String(50) productSku;
            Integer quantity : min(1);
            Money unitPrice : min(0);
            Money subtotal : min(0);

            belongsTo Order : index;

            validate {
                if (subtotal != unitPrice * quantity) {
                    throw ValidationError("Subtotal must equal unit price × quantity");
                }
            }
        }
    }

    pubsub mq('config/order-service/datasources.yaml') {
        topic OrderEvents {
            publish OrderPlaced(UUID orderId, UUID customerId, Money total);
            publish OrderStatusChanged(UUID orderId, OrderStatus oldStatus, OrderStatus newStatus);
            publish OrderCancelled(UUID orderId, String reason);
        }
    }

    rest_api OrderAPI : basePath('/api/v1/orders') {
        resource db.Order : access(authenticated);

        @path('/create')
        @authorize
        post createOrder(UUID customerId, List<OrderItemInput> items) -> db.Order {
            // Validate customer
            let customer = UserService.getUser(customerId);
            if (!customer.isActive) {
                throw ValidationError("Customer account is inactive");
            }

            // Calculate totals
            let subtotal = 0;
            for (item in items) {
                let product = ProductService.getProduct(item.productId);
                if (!product.inStock || product.stockQuantity < item.quantity) {
                    throw ValidationError("Product " + product.name + " is out of stock");
                }
                subtotal = subtotal + (product.effectivePrice * item.quantity);
            }

            let tax = subtotal * 0.1;  // 10% tax
            let shipping = subtotal > 100 ? 0 : 10;  // Free shipping over $100
            let total = subtotal + tax + shipping;

            // Create order
            let order = db.Order.create({
                orderNumber: "ORD-" + Random.alphanumeric(10),
                customerId: customerId,
                subtotal: subtotal,
                tax: tax,
                shipping: shipping,
                total: total,
                createdBy: Request.userId()
            });

            // Create order items
            for (item in items) {
                let product = ProductService.getProduct(item.productId);
                db.OrderItem.create({
                    orderId: order.id,
                    productId: product.id,
                    productName: product.name,
                    productSku: product.sku,
                    quantity: item.quantity,
                    unitPrice: product.effectivePrice,
                    subtotal: product.effectivePrice * item.quantity
                });
            }

            return order;
        }

        @path('/:id/cancel')
        @authorize
        post cancelOrder(UUID id) -> db.Order {
            let order = db.Order.findOrFail(id);

            if (order.status != OrderStatus.Pending && order.status != OrderStatus.Confirmed) {
                throw ValidationError("Cannot cancel order with status: " + order.status);
            }

            order.status = OrderStatus.Cancelled;
            order.updatedBy = Request.userId();
            db.Order.save(order);

            emit OrderCancelled(id, "Cancelled by customer");
            return order;
        }
    }
}
```

### specs/services/inventory-service.dtrx

```dtrx
from ecommerce.common import BaseEntity;

service ecommerce.InventoryService : version('1.0.0') {
    config('config/inventory-service/service-config.yaml');
    registration('config/inventory-service/registration.yaml');
    discovery {
        ProductService { loadBalance: roundRobin, healthyOnly: true }
    }

    rdbms db('config/inventory-service/datasources.yaml') {
        entity InventoryRecord extends BaseEntity {
            UUID productId : unique, index;
            Integer availableQuantity : min(0);
            Integer reservedQuantity : min(0);
            Integer reorderLevel : min(0);
            Integer reorderQuantity : min(0);

            // Computed field
            Integer totalQuantity := availableQuantity + reservedQuantity;
            Boolean needsReorder := availableQuantity <= reorderLevel;
        }
    }

    pubsub mq('config/inventory-service/datasources.yaml') {
        subscribe OrderEvents from order {
            on OrderPlaced(UUID orderId, UUID customerId, Money total) {
                let order = OrderService.getOrder(orderId);
                for (item in order.items) {
                    let record = db.InventoryRecord.findBy({ productId: item.productId });
                    if (record == null) {
                        Log.error("Inventory record not found", { productId: item.productId });
                        continue;
                    }

                    if (record.availableQuantity < item.quantity) {
                        emit InventoryInsufficient(orderId, item.productId, item.quantity);
                        continue;
                    }

                    record.availableQuantity = record.availableQuantity - item.quantity;
                    record.reservedQuantity = record.reservedQuantity + item.quantity;
                    db.InventoryRecord.save(record);

                    emit InventoryReserved(orderId, item.productId, item.quantity);
                }
            }
        }
    }
}
```

---

## Example 3: Event-Driven Microservices

Demonstrates event-driven communication between services.

### specs/services/notification-service.dtrx

```dtrx
service ecommerce.NotificationService : version('1.0.0') {
    config('config/notification-service/service-config.yaml');
    registration('config/notification-service/registration.yaml');

    discovery {
        UserService { loadBalance: roundRobin, healthyOnly: true }
    }

    integrations('config/notification-service/integrations.yaml');

    rdbms db('config/notification-service/datasources.yaml') {
        entity Notification extends BaseEntity {
            UUID userId : index;
            String(100) type : index;
            String(200) subject;
            Text body;
            Boolean isSent = false;
            DateTime? sentAt;
            String? error;
        }
    }

    pubsub mq('config/notification-service/datasources.yaml') {
        subscribe UserEvents from user {
            on UserRegistered(UUID userId, Email email, String name) {
                Email.send(
                    to: email,
                    subject: "Welcome to E-Commerce!",
                    body: "Hi " + name + ", welcome to our platform!"
                );

                db.Notification.create({
                    userId: userId,
                    type: "welcome_email",
                    subject: "Welcome to E-Commerce!",
                    body: "Registration confirmation sent",
                    isSent: true,
                    sentAt: now()
                });
            }
        }

        subscribe OrderEvents from order {
            on OrderPlaced(UUID orderId, UUID customerId, Money total) {
                let customer = UserService.getUser(customerId);

                Email.send(
                    to: customer.email,
                    subject: "Order Confirmation #" + orderId,
                    body: "Your order for $" + total + " has been placed successfully!"
                );

                db.Notification.create({
                    userId: customerId,
                    type: "order_confirmation",
                    subject: "Order Confirmation",
                    body: "Order " + orderId + " placed",
                    isSent: true,
                    sentAt: now()
                });
            }

            on OrderStatusChanged(UUID orderId, OrderStatus oldStatus, OrderStatus newStatus) {
                let order = OrderService.getOrder(orderId);
                let customer = UserService.getUser(order.customerId);

                if (newStatus == OrderStatus.Shipped) {
                    Email.send(
                        to: customer.email,
                        subject: "Your order has shipped!",
                        body: "Order #" + orderId + " is on its way!"
                    );
                }
            }
        }
    }
}
```

---

## Example 4: Multi-Tenant SaaS

Multi-tenant application with organization-level data isolation.

### specs/services/tenant-service.dtrx

```dtrx
from datrix.builtin import Tenantable;
from ecommerce.common import BaseEntity;

service saas.TenantService : version('1.0.0') {
    config('config/tenant-service/service-config.yaml');
    registration('config/tenant-service/registration.yaml');
    discovery { }

    enum PlanType {
        Free,
        Starter,
        Professional,
        Enterprise
    }

    rdbms db('config/tenant-service/datasources.yaml') {
        entity Organization extends BaseEntity {
            String(100) name : unique, trim;
            String(100) slug : unique, lowercase;
            PlanType plan = PlanType.Free;
            Boolean isActive = true;
            Integer userLimit : min(1);
            Integer storageLimit : min(0);  // In GB

            hasMany User as users;
            hasMany Project as projects;
        }

        entity User extends BaseEntity with Tenantable {
            String(100) name : trim;
            Email email : unique, lowercase, index;
            Password passwordHash : hidden;
            UUID organizationId : index;  // Tenant identifier
            Boolean isActive = true;

            belongsTo Organization : index;
        }

        entity Project extends BaseEntity with Tenantable {
            String(200) name : trim;
            String? description;
            UUID organizationId : index;  // Tenant identifier
            Boolean isActive = true;

            belongsTo Organization : index;
            hasMany Task as tasks;
        }

        entity Task extends BaseEntity with Tenantable {
            String(200) title : trim;
            Text? description;
            UUID projectId : index;
            UUID? assignedTo : index;
            UUID organizationId : index;  // Tenant identifier
            Boolean isCompleted = false;

            belongsTo Project : index;
            belongsTo User as assignee;
        }
    }

    rest_api TenantAPI : basePath('/api/v1') {
        resource db.Organization : only(list, get, update), access(admin);
        resource db.Project : access(authenticated);
        resource db.Task : access(authenticated);

        // All queries automatically filtered by organizationId from tenant context
    }
}
```

### config/tenant-service/service-config.yaml

```yaml
test:
  platform: compose
  replicas: 1
  tenancy:
    identifier:
      source: header
      name: X-Organization-Id
    enforcement: strict

production:
  platform: ecs-fargate
  replicas: 3
  tenancy:
    identifier:
      source: jwt
      name: organizationId
    enforcement: strict
```

---

## Example 5: CQRS Pattern

Demonstrates CQRS with commands, queries, and views.

### specs/services/analytics-service.dtrx

```dtrx
from ecommerce.common import BaseEntity;

service ecommerce.AnalyticsService : version('1.0.0') {
    config('config/analytics-service/service-config.yaml');
    registration('config/analytics-service/registration.yaml');

    discovery {
        OrderService { loadBalance: roundRobin, healthyOnly: true }
        ProductService { loadBalance: roundRobin, healthyOnly: true }
    }

    rdbms db('config/analytics-service/datasources.yaml') {
        entity SalesRecord extends BaseEntity {
            UUID orderId : index;
            UUID productId : index;
            UUID customerId : index;
            Money amount;
            Integer quantity;
            Date saleDate : index;
        }
    }

    cqrs {
        view DashboardView {
            Money totalRevenue;
            Integer totalOrders;
            Integer totalCustomers;
            Money averageOrderValue;
            Date lastUpdated;
        }

        view ProductSalesView {
            UUID productId;
            String productName;
            Integer totalQuantitySold;
            Money totalRevenue;
            Money averagePrice;
        }

        view CustomerLifetimeValueView {
            UUID customerId;
            String customerName;
            Integer totalOrders;
            Money totalSpent;
            Date firstOrderDate;
            Date lastOrderDate;
        }

        query GetDashboard -> DashboardView {
            let totalRevenue = db.SalesRecord.sum(amount);
            let totalOrders = db.SalesRecord.distinctCount(orderId);
            let totalCustomers = db.SalesRecord.distinctCount(customerId);

            return DashboardView {
                totalRevenue: totalRevenue,
                totalOrders: totalOrders,
                totalCustomers: totalCustomers,
                averageOrderValue: totalRevenue / totalOrders,
                lastUpdated: now()
            };
        }

        query GetProductSales(UUID? productId) -> List<ProductSalesView> {
            let records = productId != null
                ? db.SalesRecord.filter(productId == productId)
                : db.SalesRecord.all();

            let grouped = records.groupBy(productId);
            let results = [];

            for (group in grouped) {
                let product = ProductService.getProduct(group.key);
                results.push(ProductSalesView {
                    productId: group.key,
                    productName: product.name,
                    totalQuantitySold: group.sum(quantity),
                    totalRevenue: group.sum(amount),
                    averagePrice: group.avg(amount / quantity)
                });
            }

            return results;
        }

        command RecordSale(
            UUID orderId,
            UUID productId,
            UUID customerId,
            Money amount,
            Integer quantity
        ) -> SalesRecord {
            return db.SalesRecord.create({
                orderId: orderId,
                productId: productId,
                customerId: customerId,
                amount: amount,
                quantity: quantity,
                saleDate: utcToday()
            });
        }
    }

    pubsub mq('config/analytics-service/datasources.yaml') {
        subscribe OrderEvents from order {
            on OrderPlaced(UUID orderId, UUID customerId, Money total) {
                let order = OrderService.getOrder(orderId);

                for (item in order.items) {
                    RecordSale(
                        orderId: orderId,
                        productId: item.productId,
                        customerId: customerId,
                        amount: item.subtotal,
                        quantity: item.quantity
                    );
                }
            }
        }
    }
}
```

---

## Example 6: File Upload Service

Service with S3-compatible storage for file uploads.

### specs/services/media-service.dtrx

```dtrx
from ecommerce.common import BaseEntity;

service ecommerce.MediaService : version('1.0.0') {
    config('config/media-service/service-config.yaml');
    registration('config/media-service/registration.yaml');
    discovery { }

    enum MediaType {
        Image,
        Video,
        Document,
        Other
    }

    rdbms db('config/media-service/datasources.yaml') {
        entity Media extends BaseEntity {
            String(200) filename : trim;
            String(500) storageKey : unique;
            URL publicUrl;
            MediaType type : index;
            String(100) mimeType;
            Integer fileSize : min(0);  // In bytes
            UUID uploadedBy : index;

            // Image-specific fields
            Integer? width;
            Integer? height;

            afterCreate {
                emit MediaUploaded(id, filename, type);
            }
        }
    }

    storage files config('config/media-service/storage.yaml') {
        upload(Bytes file, String filename) -> URL;
        download(String key) -> Bytes;
        delete(String key);
        list(String? prefix) -> List<String>;
    }

    pubsub mq('config/media-service/datasources.yaml') {
        topic MediaEvents {
            publish MediaUploaded(UUID mediaId, String filename, MediaType type);
            publish MediaDeleted(UUID mediaId);
        }
    }

    rest_api MediaAPI : basePath('/api/v1/media') {
        resource db.Media : access(authenticated);

        @path('/upload')
        @authorize
        post uploadFile(Bytes file, String filename, MediaType type) -> db.Media {
            // Validate file size (max 10MB)
            if (file.length > 10485760) {
                throw ValidationError("File size exceeds 10MB limit");
            }

            // Generate storage key
            let timestamp = now().timestamp();
            let random = Random.alphanumeric(8);
            let storageKey = "uploads/" + timestamp + "-" + random + "-" + filename;

            // Upload to storage
            let url = files.upload(file, storageKey);

            // Create media record
            let media = db.Media.create({
                filename: filename,
                storageKey: storageKey,
                publicUrl: url,
                type: type,
                mimeType: Request.header("Content-Type"),
                fileSize: file.length,
                uploadedBy: Request.userId()
            });

            return media;
        }

        @path('/:id/download')
        @authorize
        get downloadFile(UUID id) -> Bytes {
            let media = db.Media.findOrFail(id);
            return files.download(media.storageKey);
        }

        @path('/:id')
        @authorize
        delete deleteFile(UUID id) {
            let media = db.Media.findOrFail(id);

            // Delete from storage
            files.delete(media.storageKey);

            // Delete record
            db.Media.delete(id);

            emit MediaDeleted(id);
        }
    }
}
```

### config/media-service/storage.yaml

```yaml
test:
  provider: minio
  bucket: media-files
  endpoint: http://localhost:9000
  accessKey: ${MINIO_ACCESS_KEY}
  secretKey: ${MINIO_SECRET_KEY}

production:
  provider: s3
  bucket: ecommerce-media-prod
  region: us-east-1
  accessKey: ${AWS_ACCESS_KEY}
  secretKey: ${AWS_SECRET_KEY}
```

---

## Example 7: Scheduled Job Service

Service with background jobs for cleanup and reports.

### specs/services/maintenance-service.dtrx

```dtrx
from ecommerce.common import BaseEntity;

service ecommerce.MaintenanceService : version('1.0.0') {
    config('config/maintenance-service/service-config.yaml');
    registration('config/maintenance-service/registration.yaml');

    discovery {
        OrderService { loadBalance: roundRobin, healthyOnly: true }
        NotificationService { loadBalance: roundRobin, healthyOnly: true }
    }

    rdbms db('config/maintenance-service/datasources.yaml') {
        entity JobLog extends BaseEntity {
            String(100) jobName : index;
            DateTime startedAt;
            DateTime? completedAt;
            Boolean success = false;
            String? error;
            Integer recordsProcessed = 0;
        }
    }

    job CleanupExpiredOrders cron('0 2 * * *') config('config/maintenance-service/jobs.yaml') {
        // Daily at 2 AM: Cancel orders pending for more than 24 hours

        let log = db.JobLog.create({
            jobName: "CleanupExpiredOrders",
            startedAt: now()
        });

        let cutoff = now() - 24h;
        let expiredOrders = OrderService.listOrders({
            status: OrderStatus.Pending,
            createdBefore: cutoff
        });

        let count = 0;
        for (order in expiredOrders) {
            OrderService.cancelOrder(order.id, "Expired after 24 hours");
            count = count + 1;
        }

        log.completedAt = now();
        log.success = true;
        log.recordsProcessed = count;
        db.JobLog.save(log);

        Log.info("Cleanup completed", {
            jobName: "CleanupExpiredOrders",
            ordersProcessed: count
        });
    }

    job GenerateDailyReport cron('0 8 * * *') config('config/maintenance-service/jobs.yaml') {
        // Daily at 8 AM: Generate and email daily sales report

        let log = db.JobLog.create({
            jobName: "GenerateDailyReport",
            startedAt: now()
        });

        let yesterday = utcToday() - 1d;
        let orders = OrderService.listOrders({
            createdAfter: yesterday,
            createdBefore: utcToday()
        });

        let totalOrders = orders.length;
        let totalRevenue = orders.map(o => o.total).reduce((a, b) => a + b, 0);
        let avgOrderValue = totalOrders > 0 ? totalRevenue / totalOrders : 0;

        let report = "Daily Sales Report - " + yesterday.format("YYYY-MM-DD") + "\n\n" +
                     "Total Orders: " + totalOrders + "\n" +
                     "Total Revenue: $" + totalRevenue + "\n" +
                     "Average Order Value: $" + avgOrderValue;

        NotificationService.sendEmail({
            to: "admin@example.com",
            subject: "Daily Sales Report - " + yesterday.format("YYYY-MM-DD"),
            body: report
        });

        log.completedAt = now();
        log.success = true;
        log.recordsProcessed = totalOrders;
        db.JobLog.save(log);

        Log.info("Daily report generated", {
            date: yesterday,
            totalOrders: totalOrders,
            totalRevenue: totalRevenue
        });
    }

    job CleanupOldLogs interval(1h) config('config/maintenance-service/jobs.yaml') {
        // Hourly: Delete job logs older than 30 days

        let cutoff = now() - 30d;
        let oldLogs = db.JobLog.filter(createdAt < cutoff);
        let count = oldLogs.length;

        for (log in oldLogs) {
            db.JobLog.delete(log.id);
        }

        Log.info("Old logs cleaned up", { count: count });
    }
}
```

### config/maintenance-service/jobs.yaml

```yaml
test:
  CleanupExpiredOrders:
    timeout: 300000      # 5 minutes
    retryLimit: 3
    retryBackoff: exponential

  GenerateDailyReport:
    timeout: 600000      # 10 minutes
    retryLimit: 2
    retryBackoff: linear

  CleanupOldLogs:
    timeout: 120000      # 2 minutes
    retryLimit: 1

production:
  CleanupExpiredOrders:
    timeout: 900000      # 15 minutes
    retryLimit: 5

  GenerateDailyReport:
    timeout: 1800000     # 30 minutes
    retryLimit: 3

  CleanupOldLogs:
    timeout: 300000      # 5 minutes
    retryLimit: 2
```

---

## Running the Examples

### 1. Setup Project

```bash
mkdir my-project
cd my-project
mkdir -p specs config
```

### 2. Copy Files

Copy the `.dtrx` files to `specs/` and YAML files to `config/`.

### 3. Install Generators

```bash
pip install datrix-codegen-python datrix-codegen-sql datrix-codegen-docker
```

### 4. Validate

```bash
datrix validate specs/system.dtrx
```

### 5. Generate

```bash
datrix generate --profile test --source specs/system.dtrx --output ./generated
```

### 6. Run

```bash
cd generated/<service-name>
docker-compose up -d  # Start infrastructure
pip install -r requirements.txt
python -m app.main
```

---

## Next Steps

- Modify these examples for your use case
- Read [Writing Datrix Applications](./writing-datrix-applications.md) for detailed explanations
- See [Patterns and Best Practices](./patterns-and-best-practices.md) for proven patterns
- Reference [Configuration Guide](./configuration-guide.md) for config options

---

**Last Updated:** 2026-03-28
