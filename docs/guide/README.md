# Datrix Developer Guide

**The complete guide to building applications with Datrix**

This guide teaches you how to write production-ready Datrix applications, from basic entities to complete microservice architectures with events, caching, and deployment configurations.

---

## Guide Contents

### 📘 [Writing Datrix Applications](./writing-datrix-applications.md)
**Start here.** The main guide covering:
- Project structure and setup
- Writing `.dtrx` specification files
- Defining entities, services, and infrastructure blocks
- REST APIs, events, caching, jobs, and CQRS
- Relationships, inheritance, and traits
- Computed fields, validation, and lifecycle hooks
- Best practices for structuring your application

### ⚙️ [Configuration Guide](./configuration-guide.md)
Complete reference for all configuration files:
- System configuration (`system-config.yaml`)
- Service configuration (`*-config.yaml`)
- Datasources configuration (`datasources.yaml`)
- Infrastructure configuration (pubsub, cache, storage, jobs)
- Resilience, discovery, and observability
- Profiles and environment-specific configuration
- Platform-specific settings (Docker, Kubernetes, AWS, Azure)

### 💡 [Complete Examples](./complete-examples.md)
Working examples you can copy and adapt:
- Blog service with posts and comments
- E-commerce system with orders and payments
- Event-driven microservices architecture
- Multi-tenant SaaS application
- CQRS pattern implementation

### 🎯 [Patterns and Best Practices](./patterns-and-best-practices.md)
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
1. Start with [Getting Started Tutorial](../getting-started/first-project.md) (15 min)
2. Read [Writing Datrix Applications](./writing-datrix-applications.md) (comprehensive)
3. Review [Complete Examples](./complete-examples.md) for patterns
4. Reference [Configuration Guide](./configuration-guide.md) as needed

**Building a specific feature?**
- REST API → [Writing Datrix Applications § REST APIs](./writing-datrix-applications.md#rest-apis)
- Events → [Writing Datrix Applications § Event-Driven Messaging](./writing-datrix-applications.md#event-driven-messaging)
- Caching → [Writing Datrix Applications § Caching](./writing-datrix-applications.md#caching)
- Jobs → [Writing Datrix Applications § Background Jobs](./writing-datrix-applications.md#background-jobs)
- CQRS → [Writing Datrix Applications § CQRS](./writing-datrix-applications.md#cqrs)

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

```yaml
# YAML configuration files use this syntax
test:
  language: python
  hosting: docker
```

```python
# Generated Python code shown for reference
def example_function() -> str:
    return "generated code"
```

**Callouts**

> **💡 Tip:** Helpful hints and best practices

> **⚠️ Warning:** Important caveats and things to watch out for

> **📖 Reference:** Links to detailed documentation

**File Paths**
- `.dtrx` files live in `specs/` directory
- Configuration files live in `config/` directory
- Generated code goes in `generated/` directory

---

## Contributing

Found an error or want to improve these guides?
- Report issues at https://github.com/anthropics/datrix/issues
- Submit improvements via pull requests
- Follow the [Contribution Guidelines](../../../datrix-common/docs/contributing/ai-agent-rules.md)

---

**Last Updated:** 2026-03-28
