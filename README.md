# Datrix

*Latin: "she who gives" — from dare (to give), the same root as "data." Datrix gives you your entire backend from a simple high-level language.*

---

## ~130 lines of `.dtrx` &rarr; ~280 files of production code

Datrix is a backend microservices application code generator. You define your architecture once in Datrix DSL — entities, services, APIs, events, infrastructure — and Datrix generates a complete, production-ready system from it. Not scaffolding. Not boilerplate. The whole thing.

At the moment, Datrix is a commercial product, offered to startups as a professional service. This repository is a public showcase — the examples, generated output, and documentation are here to give you a real sense of what it produces. If you're building a backend and want to move faster without sacrificing quality, [get in touch](#get-in-touch).

---

## What Does Datrix Generate?

From a single `.dtrx` definition, Datrix produces:

- **Application code** — Python (FastAPI) or TypeScript (NestJS), with full async/await, type safety, and business logic
- **Database layer** — SQLAlchemy/TypeORM models, Alembic/TypeORM migrations, SQL schemas
- **REST APIs** — Routers, request/response schemas, pagination, filtering, auth middleware
- **Event-driven messaging** — Kafka/RabbitMQ producers and consumers with topic routing
- **Caching** — Redis integration with hash, sorted set, list, and counter patterns
- **Observability** — Prometheus metrics, OpenTelemetry tracing, structured logging, Grafana dashboards
- **Infrastructure** — Dockerfiles, docker-compose, Kubernetes manifests, AWS CDK, Azure Bicep
- **Testing** — Unit and integration test suites with real database fixtures
- **Documentation** — API docs, environment variable reference, architecture diagrams

---

## See It In Action

Here's a complete task management service — the entire definition:

```java
from taskmgmt.common import BaseEntity;

service taskmgmt.TaskService : version('1.0.0') {

    config('config/task-service/task-service-config.yaml');
    registration('config/task-service/registration.yaml');
    discovery {
        ProjectService { loadBalance: roundRobin, healthyOnly: true }
        UserService { loadBalance: roundRobin, healthyOnly: true }
    }
    resilience('config/task-service/resilience.yaml');

    rdbms db('config/task-service/datasources.yaml') {

        entity Task extends BaseEntity {
            UUID projectId : index;
            UUID assigneeId : index;
            String(200) title : trim;
            Boolean completed = false;
            index(projectId, assigneeId);
        }
    }

    rest_api TaskAPI : basePath("/api/v1/tasks") {
        resource db.Task;
    }
}
```

That's it. Datrix generates the FastAPI app, SQLAlchemy models, Alembic migrations, Pydantic schemas, CRUD endpoints, Docker setup, tests, and monitoring — all production-ready.

Browse the full example: [task-management/](examples/02-domains/task-management/) | [generated output](examples/02-domains/task-management/generated/python-docker/)

## The E-Commerce Example

For something more ambitious: **5 microservices, ~2,500 lines of `.dtrx`** generating **~800 files** of production code:

- **OrderService** — Order lifecycle, idempotency keys, payment coordination
- **ProductService** — Catalog, inventory, reviews (MongoDB), image storage (S3)
- **UserService** — Registration, JWT auth, sessions, preferences
- **PaymentService** — Payment processing, refunds, Stripe webhooks
- **ShippingService** — Multi-carrier tracking, shipment events

Infrastructure included: PostgreSQL (per service), MongoDB, Redis, Kafka, MinIO, Nginx reverse proxy, Prometheus, Grafana, Jaeger tracing — all wired together in `docker-compose.yml`.

Browse the full example: [ecommerce/](examples/02-domains/ecommerce/) | [generated output](examples/02-domains/ecommerce/generated/python-docker/)

---

## What You Can Define in `.dtrx`

| Feature | Example |
|---------|---------|
| Entities with inheritance | `entity Order extends AuditedEntity { ... }` |
| Field validation | `String(200) title : trim, unique;` |
| Computed fields | `Boolean isOverdue := dueDate < now();` |
| Relationships | `UUID authorId -> db.Author;` |
| Enums | `enum OrderStatus { Pending, Confirmed, Shipped }` |
| REST APIs with auth | `resource db.Order : only(list, get), access(admin);` |
| Event-driven messaging | `publish OrderCreated(UUID orderId, Money total);` |
| Caching strategies | `hash OrderCache on db.Order ttl(30m);` |
| Background jobs | `job CleanupExpired cron('0 */6 * * *') { ... }` |
| Lifecycle hooks | `afterCreate { emit OrderCreated(id, total); }` |
| Service discovery | `discovery { PaymentService { loadBalance: roundRobin } }` |
| Storage | `storage images(bucket: 'product-images') { ... }` |
| CQRS | `query GetDashboard -> DashboardView { ... }` |
| Transactions | `transaction { db.Order.save(order); }` |

---

## Architecture

```
.dtrx source files
       |
       v
  +-----------+
  |  Parser   |  .dtrx --> Abstract Syntax Tree
  +-----------+
       |
       v
  +-----------+
  | Semantic  |  Validate, resolve types, check constraints
  | Analysis  |
  +-----------+
       |
       v
  +--------------------+
  | Code Generators    |  Python, TypeScript, SQL, Component
  +--------------------+
       |
       v
  +--------------------+
  | Platform Generators|  Docker, Kubernetes, AWS, Azure
  +--------------------+
       |
       v
  Production-Ready Application
```

## Target Languages & Platforms

| Code Generation | Platform Generation |
|----------------|-------------------|
| Python (FastAPI) | Docker + Compose |
| TypeScript (NestJS) | Kubernetes |
| SQL (PostgreSQL, MySQL) | AWS (CDK + CloudFormation) |
| Component (configs, schemas, docs) | Azure (Bicep + ARM) |

---

## Examples

### Tutorials (41 progressive lessons)

Start from a single entity and build up to a full microservices system with API gateways, CQRS, event-driven architecture, and more.

[Browse tutorials &rarr;](examples/01-tutorial/)

### Domain Examples

Complete, real-world implementations:

| Domain | Services | Description |
|--------|----------|-------------|
| [E-Commerce](examples/02-domains/ecommerce/) | 5 | Orders, payments, shipping, inventory, users |
| [Healthcare](examples/02-domains/healthcare/) | 3 | Patients, appointments, medical records |
| [Blog CMS](examples/02-domains/blog-cms/) | 3 | Authors, articles, comments |
| [Social Platform](examples/02-domains/social-platform/) | 4 | Profiles, posts, messaging, notifications |
| [Learning Management](examples/02-domains/learning-management/) | 3 | Courses, enrollment, assessments |
| [Task Management](examples/02-domains/task-management/) | 3 | Projects, tasks, team collaboration |

---

## Learn More

- [Why Datrix](docs/why-datrix.md) — Datrix vs vibe coding, the AI pairing, and what's under the hood
- [Your First Project](docs/getting-started/first-project.md) — Build a project step by step
- [Architecture Overview](docs/architecture/architecture-overview.md) — System pipeline, repository structure, core principles
- [Design Principles](docs/architecture/design-principles.md) — Fail-fast, exhaustive mappings, immutability
- [Language Reference](docs/reference/language-reference.md) — Full `.dtrx` language guide

---

## Get In Touch

If you're a startup looking to accelerate your backend development — whether you're starting from scratch, scaling an existing system, or trying to bring consistency to a codebase that's grown in too many directions — we'd love to talk.

Datrix is offered as a professional service: we work with your team to model your domain in `.dtrx`, generate the codebase, and hand off a fully working system you own and maintain.

**Contact:** [K Ercan Turkarslan](https://github.com/keturk) | [LinkedIn](https://www.linkedin.com/in/ercanturkarslan/)
