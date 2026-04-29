# Datrix Examples

This directory contains complete, production-ready microservices examples written in Datrix (`.dtrx` files). Examples are organized into categories to help you find the right resources for your needs.

## Directory Structure

```
examples/
├── 01-tutorial/              # Step-by-step learning examples (41 progressive tutorials)
└── 02-domains/               # Complete domain implementations (6 real-world examples)
```

## Quick Start

**New to Datrix?** Start with the [tutorial examples](01-tutorial/) - they guide you through concepts step-by-step.

**Building a specific domain?** Check [domain examples](02-domains/) for complete implementations.

Built-in function usage (String, Array, Math, Validator, etc.) is demonstrated in the [tutorial](01-tutorial/) (e.g. 06-validation, 07-lifecycle-hooks, 40-advanced-validation).

---

## 01-tutorial

Step-by-step learning examples that progressively introduce Datrix concepts through a Library Management System. Each version builds on the previous one, from basic entities to advanced patterns like API gateways.

**41 Progressive Tutorials:**
- Entity fundamentals (basic entity, enums, computed fields, relationships, validation, lifecycle hooks)
- API design (REST endpoints, authentication, events)
- Service architecture (multiple services, dependencies, internal endpoints)
- Advanced patterns (structs, integrations, cache, CQRS, background jobs, resilience, API gateway)

See [01-tutorial/README.md](01-tutorial/README.md) for the complete tutorial guide with learning paths.

---

## 02-domains

Complete domain implementations demonstrating real-world microservices architectures.

| Domain | Description |
|--------|-------------|
| [blog-cms](02-domains/blog-cms/) | Content management platform with authors, articles, and comments |
| [ecommerce](02-domains/ecommerce/) | E-commerce platform with orders, payments, and shipping |
| [healthcare](02-domains/healthcare/) | Healthcare system for patients, appointments, and medical records |
| [learning-management](02-domains/learning-management/) | Educational platform for courses and student enrollment |
| [social-platform](02-domains/social-platform/) | Social networking with user profiles, posts, and notifications |
| [task-management](02-domains/task-management/) | Project management with tasks, projects, and team collaboration |

See [02-domains/README.md](02-domains/README.md) for domain details and common patterns.

---

## Common Patterns Demonstrated

All examples demonstrate:

### 1. Service Definition and Imports
```datrix
from ecommerce.common import BaseEntity, Address;

service ecommerce.OrderService : version('1.0.0') {
    // service configuration...
}
```

### 2. Base Entity Pattern
```datrix
rdbms bookDb('config/datasources.yaml') {
    abstract entity BaseEntity {
        UUID id : primaryKey = uuid();
        DateTime createdAt = now();
        DateTime updatedAt = now();
    }

    entity Book extends BaseEntity {
        String(200) title : trim;
        String(20) isbn : unique;
    }
}
```

### 3. Service Discovery
```datrix
service ecommerce.OrderService : version('1.0.0') {
    discovery {
        ProductService { loadBalance: roundRobin, healthyOnly: true }
        PaymentService { loadBalance: roundRobin, healthyOnly: true }
    }
}
```

### 4. Event-Driven Communication
```datrix
service library.BookService : version('1.0.0') {
    pubsub mq('config/pubsub.yaml') {
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
// Inside rdbms bookDb('config/datasources.yaml') { }
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
// Inside rdbms bookDb('config/datasources.yaml') { }
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
└── config/                  # YAML configuration files
    ├── registry.yaml
    └── gateway.yaml
```

### Entry Point Pattern

The `system.dtrx` file is the **entry point** for each project:
```datrix
// system.dtrx - Entry point
include 'common.dtrx';
include 'user-service.dtrx';
include 'product-service.dtrx';
include 'order-service.dtrx';

system ecommerce : version('1.0.0') {
    registry('config/registry.yaml');
    gateway('config/gateway.yaml');
    observability('config/observability.yaml');
    config('config/config.yaml');
}
```

### Running Examples

To generate code from an example:
```bash
# Generate Python service from the system.dtrx entry point
datrix generate examples/02-domains/ecommerce/system.dtrx -l python -p docker

# Or generate TypeScript service
datrix generate examples/02-domains/ecommerce/system.dtrx -l typescript -p docker
```

The parser will:
1. Start from `system.dtrx`
2. Follow all `include` statements recursively
3. Collect all services from included files
4. Load YAML configuration from the `config/` directory
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
   - `system { }` block with YAML configuration references
3. Create a `config/` directory with YAML configuration files
4. Use consistent naming conventions
5. Add `discovery { }` blocks for service-to-service communication
6. Include authentication/authorization where appropriate
7. Add `pubsub mq('path') { }` blocks for event-driven communication

## Related Documentation

- [Architecture Overview](../docs/architecture/architecture-overview.md)
- [Design Principles](../docs/architecture/design-principles.md)
- [Your First Project](../docs/getting-started/first-project.md)
