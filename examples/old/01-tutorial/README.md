# Tutorial Examples

This directory contains 41 progressive tutorials that teach Datrix concepts through a **Library Management System**. Each tutorial builds on the previous one, introducing new concepts incrementally.

## Learning Path

### Entity Fundamentals (01-07)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [01-basic-entity](01-basic-entity/) | Entity, fields, types | Define your first entity with basic field types |
| [02-enums](02-enums/) | Enum types | Add status and format enumerations |
| [03-basic-api](03-basic-api/) | REST API, resources | Expose entities through REST endpoints |
| [04-computed-fields](04-computed-fields/) | Computed fields (`:=`) | Add derived fields that auto-calculate |
| [05-relationships](05-relationships/) | `belongsTo`, `hasMany` | Model relationships between entities |
| [06-validation](06-validation/) | `validate` block | Add business rule validation |
| [07-lifecycle-hooks](07-lifecycle-hooks/) | `beforeCreate`, `afterUpdate` | Execute logic on entity lifecycle events |

### API Design (08-09)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [08-authentication](08-authentication/) | `auth()`, `access()` | Secure endpoints with authentication and authorization |
| [09-events](09-events/) | `emit`, `on` | Publish and subscribe to domain events |

### Service Architecture (10-12)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [10-multiple-services](10-multiple-services/) | Multiple services | Split into Book and Member services |
| [11-service-dependencies](11-service-dependencies/) | `dependencies` block | Add Loan service with cross-service calls |
| [12-internal-endpoints](12-internal-endpoints/) | `: internal` modifier | Create service-to-service only endpoints |

### Advanced Patterns (13-25)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [13-structs](13-structs/) | `struct` types | Define reusable data structures |
| [14-integrations](14-integrations/) | External services | Integrate email, SMS, and storage providers |
| [15-cache](15-cache/) | Caching | Add caching for performance optimization |
| [16-advanced-relationships](16-advanced-relationships/) | Complex relationships | Many-to-many and self-referential relationships |
| [17-entity-functions](17-entity-functions/) | Entity methods | Add custom functions to entities |
| [18-module-functions](18-module-functions/) | Module functions | Create reusable module-level functions |
| [19-api-functions](19-api-functions/) | API functions | Custom endpoint logic and transformations |
| [20-cqrs](20-cqrs/) | CQRS pattern | Separate read and write models |
| [21-background-jobs](21-background-jobs/) | Async jobs | Background task processing |
| [22-resilience](22-resilience/) | Circuit breakers, retries | Fault tolerance patterns |
| [23-api-gateway](23-api-gateway/) | API Gateway | Unified entry point with routing |
| [24-nosql](24-nosql/) | `nosql`, `collection` | Document database for analytics |
| [25-storage](25-storage/) | `storage`, `folder` | Object storage for file uploads |

### Full-Stack Features (26-28)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [26-advanced-types](26-advanced-types/) | Semantic types, `Map`, `Set` | Rich type system with domain-specific types |
| [27-advanced-features](27-advanced-features/) | `switch`, `while`, `continue`, `break` | Advanced control flow and entity features |
| [28-multi-database](28-multi-database/) | Multiple `rdbms` blocks | Separate databases for different concerns |

### Modules and APIs (29-31)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [29-modules](29-modules/) | `module`, `import` | Shared modules with cross-service imports |
| [30-graphql](30-graphql/) | `graphql_api`, `type`, `input`, `query`, `mutation` | GraphQL API with types, queries, mutations, subscriptions |
| [31-advanced-queries](31-advanced-queries/) | `fulltext()`, `orderBy()`, `whereIn()`, `whereNull()` | Advanced query patterns and full-text search |

### Data Integrity (32-34)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [32-transactions](32-transactions/) | `transaction()` | Wrap multi-step operations in transactions |
| [33-batch-operations](33-batch-operations/) | `batch`, `refreshOn()` | Bulk CRUD and automatic view refresh |
| [34-advanced-cache](34-advanced-cache/) | `sortedset`, `set`, `list`, `ttl()` | Advanced Redis data structures |

### Type System (35-38)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [35-advanced-enums](35-advanced-enums/) | `value()` on enum members | Enum members with explicit values |
| [36-field-security](36-field-security/) | `encrypted`, `sensitive` | Field-level encryption and sensitivity |
| [37-semantic-types](37-semantic-types/) | `Money`, `Slug`, `Password`, `IPAddress`, `Date` | Domain-specific semantic types |
| [38-hasone-relationship](38-hasone-relationship/) | `hasOne` | One-to-one entity relationships |

### Production Patterns (39-41)

| Tutorial | Concepts | Description |
|----------|----------|-------------|
| [39-webhooks-idempotency](39-webhooks-idempotency/) | Idempotency keys, webhooks, `Void` return | Idempotent operations and webhook endpoints |
| [40-advanced-validation](40-advanced-validation/) | `min()`, `max()`, `positive`, `Validator`, `today()` | Declarative validation constraints |
| [41-file-operations](41-file-operations/) | `store.upload()`, `store.download()`, `Blob` | File upload and download operations |

## Getting Started

Start with tutorial 01 and progress sequentially:

```bash
# Generate code from tutorial 01
datrix generate examples/01-tutorial/01-basic-entity/system.dtrx -l python -p docker
```

## Project Structure

Each tutorial follows this structure:
```
XX-tutorial-name/
├── system.dtrx           # Entry point with system configuration
├── book-service.dtrx     # Book service (present in all tutorials)
├── member-service.dtrx   # Member service (from tutorial 10+)
├── loan-service.dtrx     # Loan service (from tutorial 11+)
├── common.dtrx           # Shared module (from tutorial 29+)
└── config/               # YAML configuration files
```
