# Domain Examples

This directory contains complete, production-ready domain implementations demonstrating real-world microservices architectures in Datrix.

## Available Domains

| Domain | Services | Description |
|--------|----------|-------------|
| [blog-cms](blog-cms/) | Author, Content, Comment | Content management platform for blogs and articles |
| [ecommerce](ecommerce/) | User, Product, Order, Payment, Shipping | Full e-commerce platform with checkout flow |
| [healthcare](healthcare/) | Patient, Appointment, Medical Record | Healthcare system for patient management |
| [learning-management](learning-management/) | Course, Enrollment, Student | Educational platform for online courses |
| [social-platform](social-platform/) | User, Post, Notification | Social networking with feeds and notifications |
| [task-management](task-management/) | User, Project, Task | Project and task tracking system |

## Domain Structure

Each domain follows a consistent structure:

```
domain-name/
├── system.dtrx           # Entry point with system configuration
├── common.dtrx           # Shared types and utilities (if applicable)
├── service-1.dtrx        # First microservice
├── service-2.dtrx        # Second microservice
└── config/               # YAML configuration files
    ├── discovery.yaml
    ├── gateway.yaml
    └── observability.yaml
```

## Usage

Generate code from any domain:

```bash
# Generate Python services
datrix generate examples/02-domains/ecommerce/system.dtrx -l python -p docker

# Generate TypeScript services
datrix generate examples/02-domains/healthcare/system.dtrx -l typescript -p kubernetes
```

## Common Patterns

All domain examples demonstrate:

- **Service independence**: Each service owns its data and can be deployed separately
- **Event-driven communication**: Services publish and subscribe to domain events
- **API gateway**: Unified entry point for external clients
- **Authentication**: JWT-based auth with role-based authorization
- **Observability**: Logging, metrics, and distributed tracing configuration
