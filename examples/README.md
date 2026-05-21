# Datrix Examples

This directory contains complete, production-ready microservices examples written in Datrix (`.dtrx` files). Examples are organized into categories to help you find the right resources for your needs.

## Directory Structure

```
examples/
├── 01-foundation/            # Minimal library service (single entity + REST API)
├── 02-features/              # Focused feature examples organized by category
└── 03-domains/               # Complete domain implementations (real-world examples)
```

## Quick Start

**New to Datrix?** Start with [01-foundation/](01-foundation/) — a minimal library service with one entity and a REST API.

**Learning a specific feature?** Browse [02-features/](02-features/) for focused examples organized by category (core data modeling, service architecture, infrastructure blocks, and more).

**Building a specific domain?** Check [03-domains/](03-domains/) for complete implementations.

---

## 01-foundation

A minimal library service demonstrating the core Datrix pattern: one entity, one REST API, and basic configuration. This is the starting point for understanding the `.dtrx` format.

---

## 02-features

Focused feature examples organized into categories, each demonstrating a specific Datrix capability through a library system:

- **01-core-data-modeling** — Entities, enums, computed fields, relationships, REST APIs
- **02-service-architecture** — Multiple services, dependencies, internal endpoints
- **03-infrastructure-blocks** — Events/pubsub, cache, CQRS, background jobs, storage
- **04-advanced-data-features** — Advanced cache, queries, transactions, batch operations
- **05-infrastructure-combinations** — Multi-database, multi-infrastructure setups
- **06-advanced-language-features** — Structs, integrations, advanced flow control, external integration

---

## 03-domains

Complete domain implementations demonstrating real-world microservices architectures.

| Domain | Description |
|--------|-------------|
| [blog-cms](03-domains/blog-cms/) | Content management platform with authors, articles, and comments |
| [ecommerce](03-domains/ecommerce/) | E-commerce platform with orders, payments, and shipping |
| [finance](03-domains/finance/) | Financial services platform |
| [food-delivery](03-domains/food-delivery/) | Food delivery service |
| [healthcare](03-domains/healthcare/) | Healthcare system for patients, appointments, and medical records |
| [hr-platform](03-domains/hr-platform/) | Human resources platform |
| [iot-platform](03-domains/iot-platform/) | IoT device management platform |
| [learning-management](03-domains/learning-management/) | Educational platform for courses and student enrollment |
| [logistics](03-domains/logistics/) | Logistics and supply chain management |
| [real-estate](03-domains/real-estate/) | Real estate listings and management |
| [social-platform](03-domains/social-platform/) | Social networking with user profiles, posts, and notifications |
| [task-management](03-domains/task-management/) | Project management with tasks, projects, and team collaboration |

---

## Common Patterns Demonstrated

All examples demonstrate:

### 1. Service Definition and Imports
```datrix
from ecommerce.common import BaseEntity, Address;

service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    // service configuration...
}
```

### 2. Base Entity Pattern
```datrix
rdbms bookDb {
    abstract entity BaseEntity {
        UUID id : primaryKey = uuid();
        DateTime createdAt = DateTime.now();
        DateTime updatedAt = DateTime.now();
    }

    entity Book extends BaseEntity {
        String(200) title : trim;
        String(20) isbn : unique;
    }
}
```

### 3. Service Discovery
```datrix
service ecommerce.OrderService('config/order-service.dcfg') : version('1.0.0') {
    discovery {
        ProductService { loadBalance: roundRobin, healthyOnly: true }
        PaymentService { loadBalance: roundRobin, healthyOnly: true }
    }
}
```

### 4. Event-Driven Communication
```datrix
service library.BookService('config/book-service.dcfg') : version('1.0.0') {
    pubsub mq {
        topic BookEvents {
            publish BookAdded(UUID bookId, String title);
            publish BookStatusChanged(UUID bookId, BookStatus oldStatus, BookStatus newStatus);
        }
    }

    subscribe BookEvents {
        on BookStatusChanged(UUID bookId, BookStatus oldStatus, BookStatus newStatus) {
            Log.info("Book {bookId} status: {oldStatus} -> {newStatus}");
        }
    }
}
```

### 5. Internal Endpoints
```datrix
rest_api UserAPI : basePath("/api/v1/users") {
    // Internal endpoint - only accessible by other services
    get(UUID id) : internal -> userDb.User {
        return userDb.User.findOrFail(id);
    }
}
```

### 6. Authentication & Authorization
```datrix
rest_api BookAPI : basePath("/api/v1/books") {
    // Public endpoints - no auth required
    resource bookDb.Book : only(list, get), public;

    // Protected endpoints - require librarian role
    resource bookDb.Book : only(create, update, delete), access(librarian);

    @path('/search')
    get(String query) : public -> bookDb.Book[] {
        return bookDb.Book.where(title: query).all();
    }
}
```

### 7. Computed Fields
```datrix
// Inside rdbms bookDb { }
entity Book extends BaseEntity {
    String(200) title : trim;
    Int publicationYear;
    BookStatus status = BookStatus.Available;

    // Computed fields use := operator
    Boolean isAvailable := status == BookStatus.Available;
    String displayTitle := "{title} ({publicationYear})";
    Boolean isOldBook := publicationYear < 2000;
}
```

### 8. Lifecycle Hooks
```datrix
// Inside rdbms bookDb { }
entity Book extends BaseEntity {
    String(50)? catalogNumber;
    BookStatus status;

    // Lifecycle hooks are direct children of entity
    beforeCreate {
        catalogNumber = "CAT-{Random.string(8).toUpperCase()}";
    }

    afterCreate {
        dispatch BookAdded(id, title);
    }

    afterUpdate {
        if (isChanged(status)) {
            dispatch BookStatusChanged(id, oldValue(status), status);
        }
    }
}
```

## File Structure and Inclusion

Each example follows this structure:
```
example-name/
├── system.dtrx              # Entry point - includes all service files
├── common.dtrx              # Shared types and utilities (optional)
├── service-1.dtrx           # First microservice
├── service-2.dtrx           # Second microservice
├── service-3.dtrx           # Third microservice
└── config/                  # ConfigDSL files
    ├── system.dcfg
    ├── service-1.dcfg
    └── service-2.dcfg
```

### Entry Point Pattern

The `system.dtrx` file is the **entry point** for each project:
```datrix
// system.dtrx - Entry point
include 'common.dtrx';
include 'user-service.dtrx';
include 'product-service.dtrx';
include 'order-service.dtrx';

system ecommerce.System('config/system.dcfg') : version('1.0.0') {
    // services reference their own config/*.dcfg files
}
```

### Running Examples

To generate code from an example:
```bash
# Generate Python service from the system.dtrx entry point
datrix generate examples/03-domains/ecommerce/system.dtrx -l python -p docker

# Or generate TypeScript service
datrix generate examples/03-domains/ecommerce/system.dtrx -l typescript -p docker
```

The parser will:
1. Start from `system.dtrx`
2. Follow all `include` statements recursively
3. Collect all services from included files
4. Load ConfigDSL configuration from the referenced `.dcfg` files
5. Validate the `system { }` block and resolve references

## Usage

These examples serve as:
1. **Reference implementations** for Datrix syntax
2. **Learning resources** for microservices patterns
3. **Templates** for starting new projects
4. **Documentation** of best practices

## Notes

- All examples use the `.dtrx` file extension (Datrix format)
- Examples are complete and production-ready
- Each service is independently deployable
- Services communicate via REST APIs and events

## Extending the examples

When adding or changing examples in this repository:
1. Follow the existing structure and patterns
2. Create a `system.dtrx` entry point file with:
   - `include` statements for all service files
   - `system Name('config/system.dcfg') { }` block
3. Create a `config/` directory with `.dcfg` configuration files
4. Use consistent naming conventions
5. Add `discovery { }` blocks for service-to-service communication
6. Include authentication/authorization where appropriate
7. Add `pubsub mq { }` blocks for event-driven communication

## Related Documentation

- [Architecture Overview](../docs/architecture/architecture-overview.md)
- [Design Principles](../docs/architecture/design-principles.md)
- [Your First Project](../docs/getting-started/first-project.md)
