# Datrix Developer Guide

**The complete guide to building applications with Datrix**

This guide teaches you how to write production-ready Datrix applications, from basic entities to complete microservice architectures with events, caching, and deployment configurations.

---

## Guide Contents

### [Writing Datrix Applications](./writing-datrix-applications.md)
**Start here.** The main guide covering:
- Project structure and setup
- Writing `.dtrx` specification files
- Defining entities, services, and infrastructure blocks
- REST APIs, events, caching, jobs, and CQRS
- Relationships, inheritance, and traits
- Computed fields, validation, and lifecycle hooks
- Best practices for structuring your application

### [Configuration Guide](./configuration-guide.md)
Complete reference for all configuration files:
- System configuration (`config/system.dcfg`)
- Service configuration (`config/<service>.dcfg`)
- Infrastructure configuration sections (`rdbms`, `pubsub`, `cache`, `storage`, `queues`, `jobs`)
- Resilience, discovery, and observability
- Profiles and environment-specific configuration
- Platform-specific settings (Docker, Kubernetes, AWS, Azure)

### [Complete Examples](./complete-examples.md)
Index of **repository** examples under [`examples/`](../../examples/) (feature examples + domain apps), plus short pattern notes:
- Feature series (library system): entities → APIs → events → CQRS, GraphQL, jobs, and more
- Domain folders: blog-cms, ecommerce, healthcare, learning-management, social-platform, task-management

### [Seed Data Guidelines](./seed-data-guidelines.md)
How to declare, manage, and deploy seed data:
- SeedDSL file format (`.dseed`) and declaration syntax
- Reference data, baseline data, and volume data categories
- Profile-aware seeding and production safety
- Field selection rules, trait-specific seeding, type-specific patterns
- Cross-service dependency resolution and seed registries
- Deployment integration (Docker Compose and Kubernetes)
- Seed capture from existing databases

### [Event Contracts](./event-contracts.md)
How to use `ensure` clauses on `publish` events to enforce value-level invariants on event payloads:
- Problem: structurally valid but semantically broken payloads
- `ensure` clause syntax inside event declarations
- Publisher-side enforcement (fail-fast at dispatch)
- Generated contract validation (Python + TypeScript)
- Static analysis (CTR001-CTR003) and runtime assertions
- Design decisions and rationale

### [Database Drift Reconciliation](./database-drift-reconciliation.md)
How to detect and reconcile schema drift in non-ephemeral database environments:
- The problem: recorded vs. live vs. desired schema divergence in shared environments
- Export live snapshots and detect drift offline (no database connection)
- Reconcile with `--adopt` (keep reality) or `--to-desired` (generate DDL)
- Configure guard mode for production safety and reconcile mode for pre-prod flexibility
- Decision D29 and the complete drift/reconcile workflow

### [Patterns and Best Practices](./patterns-and-best-practices.md)
Proven patterns for common scenarios:
- Multi-tenancy implementation
- Soft delete and auditing
- API design patterns
- Event-driven architecture patterns
- Error handling and validation
- Testing strategies
- Deployment considerations

---

## Quick Navigation

**New to Datrix?**
1. Start with [Getting Started](../getting-started/first-project.md) (15 min)
2. Read [Writing Datrix Applications](./writing-datrix-applications.md) (comprehensive)
3. Review [Complete Examples](./complete-examples.md) for patterns
4. Reference [Configuration Guide](./configuration-guide.md) as needed

**Building a specific feature?**
- REST API → [Writing Datrix Applications § REST APIs](./writing-datrix-applications.md#rest-apis)
- Events → [Writing Datrix Applications § Event-Driven Messaging](./writing-datrix-applications.md#event-driven-messaging)
- Event Contracts → [Event Contracts](./event-contracts.md) (`ensure` clauses on publish events)
- Caching → [Writing Datrix Applications § Caching](./writing-datrix-applications.md#caching)
- Jobs → [Writing Datrix Applications § Background Jobs](./writing-datrix-applications.md#background-jobs)
- CQRS → [Writing Datrix Applications § CQRS](./writing-datrix-applications.md#cqrs)
- Seed Data → [Seed Data Guidelines](./seed-data-guidelines.md) (reference data, baseline, volume)
- Database Drift → [Database Drift Reconciliation](./database-drift-reconciliation.md) (guard vs reconcile modes)

**Configuring deployment?**
- [Configuration Guide § System Configuration](./configuration-guide.md#system-configuration)
- [Configuration Guide § Profiles](./configuration-guide.md#profiles-and-environments)
- [Configuration Guide § Platform-Specific](./configuration-guide.md#platform-specific-configuration)

---

## Additional Resources

**Language Reference**
- [Datrix Language Reference](../reference/language-reference.md) — Complete DSL syntax
- [Datrix Syntax Reference](../../../datrix-language/docs/reference/datrix-syntax-reference.md) — Detailed grammar and syntax
- [Field Attributes](../../../datrix-language/docs/reference/field-attributes.md) — All field modifiers
- [Decorators](../../../datrix-language/docs/reference/datrix-decorators.md) — Function and entity decorators
- [Built-in Objects](../../../datrix-language/docs/reference/datrix-builtins.md) — Available utility functions
- [SeedDSL Syntax](../../../datrix-language/docs/reference/seed-dsl-syntax-reference.md) — `.dseed` file format and constructs

**Architecture & Design**
- [Architecture Overview](../architecture/architecture-overview.md) — System pipeline and structure
- [Design Principles](../architecture/design-principles.md) — Core architectural principles
- [Config System](../../../datrix-common/docs/architecture/config-system.md) — Configuration architecture

**CLI & Tools**
- [CLI Commands](../../../datrix-cli/docs/commands.md) — Complete command reference
- [CLI Examples](../../../datrix-cli/docs/examples.md) — Common CLI usage patterns

---

## Document Structure

Each guide document follows this structure:

1. **Overview** — What the document covers
2. **Core Concepts** — Key ideas and terminology
3. **Detailed Sections** — In-depth coverage with examples
4. **Common Patterns** — Reusable patterns and solutions
5. **Troubleshooting** — Common issues and solutions
6. **Reference** — Quick reference tables and checklists

---

## Conventions Used

**Code Examples**

```dtrx
// .dtrx specification files use this syntax
service example.MyService : version('1.0.0') {
    // ...
}
```

```dcfg
# ConfigDSL files use this syntax
config system example.System {
    profile test {
        language: python
        deployment { runtime: docker-compose, provider: local }
    }
}
```

```python
# Generated Python code shown for reference
def example_function() -> str:
    return "generated code"
```

**Callouts**

> **Tip:** Helpful hints and best practices

> **Warning:** Important caveats and things to watch out for

> **Reference:** Links to detailed documentation

**File Paths**
- `.dtrx` files live in `specs/` directory
- Configuration files live in `config/` directory
- Generated code goes in `generated/` directory

---

**Last updated:** April 24, 2026
