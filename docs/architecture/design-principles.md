# Datrix Design Principles

**Last Updated:** March 16, 2026

---

## Core Philosophy

Datrix is built on proven software engineering principles that ensure:
- **Reliable code generation** - Cannot generate broken code
- **Type safety** - Exhaustive type checking and validation
- **Maintainability** - Clear, modular architecture
- **Developer experience** - Fast feedback with helpful errors

---

## Architectural Principles

### 1. Fail Fast, Fail Loud

**Principle:** Errors should be caught at generation time, not runtime.

**Why:**
- Faster feedback loop
- Clear error messages with context
- No broken code reaches users
- Reduces debugging time

**Application:** The codebase raises explicit errors with context (e.g. entity not found with available names and suggestions). No silent fallbacks or `None` returns for lookup failures.

**Benefits:**
- ✅ Cannot continue with invalid state
- ✅ Error includes helpful suggestions
- ✅ Caught during generation, not deployment

---

### 2. Templates + Formatter for Code Generation

**Principle:** Use Jinja2 templates with ruff format for Python code formatting, and Prettier for TypeScript.

**Why:**
- Templates are readable and look like the output
- ruff format (Python) and Prettier (TypeScript) check formatting consistency
- Generated code is no longer auto-formatted; formatting is checked and warnings are surfaced instead
- Easy to maintain and modify
- Reusable template macros

**Application:** Generators use Jinja2 (e.g. `PackageLoader` for templates), render to raw code, and validate syntax before output. Model templates emit a Pydantic model class keyed by entity name, with conditional imports (e.g. UUID when needed) and one field per entity field. Templates should produce well-formatted output; ruff format / Prettier check formatting. Raw string concatenation is not used. See the codebase for template files (e.g. `model.py.j2` in datrix-codegen-python).

**Key Insight:** Templates should produce well-formatted output; ruff format --check catches formatting issues.

**When to Use Each Approach:**

| Approach | When to Use |
|----------|-------------|
| **Jinja2 Templates** | Generating boilerplate code (models, schemas, routes), output structure is well-defined, readability of template matters |
| **AST Builders** | Programmatically transforming existing code, dynamic structure based on complex conditions, need fine-grained control over AST nodes |

**Template Structure:**

- `datrix-codegen-python/src/datrix_codegen_python/templates/` — Jinja2 templates organized into domain subdirectories (`entity/`, `api/`, `service/`, `persistence/`, `messaging/`, `cross_cutting/`, `project/`)
- `generators/` — Generator classes organized into matching domain subdirectories

**Benefits:**
- ✅ Templates are readable and maintainable
- ✅ Consistent formatting via ruff format/Prettier
- ✅ Validation during formatting
- ✅ Reusable template macros

---

### 3. Exhaustive Type Mappings

**Principle:** All type mappings must be explicit. No defaults, no fallbacks.

**Why:**
- Prevents silent bugs
- Forces complete implementation
- Clear error messages
- Easy to add new types

**Application:** Type mappings are exhaustive: every Datrix type has an explicit mapping per target language. Unmapped types raise an error (e.g. `UnmappedTypeError`) with available types listed. No default or fallback to `Any`.

**Benefits:**
- ✅ No silent bugs
- ✅ Forces complete implementation
- ✅ Helpful error messages
- ✅ Easy to find missing mappings

---

### 4. Immutability

**Principle:** The Application (AST model) is immutable after creation.

**Why:**
- Thread-safe
- Predictable behavior
- Prevents accidental modifications
- Easier to reason about

**Application:** The Application (AST) model is immutable: AST classes are frozen (Pydantic v2). Modifying a parsed entity or service raises `FrozenInstanceError`. Generators are read-only and iterate over services and blocks without mutating the AST.

**Benefits:**
- ✅ Thread-safe generation
- ✅ No side effects
- ✅ Cacheable results
- ✅ Easy to parallelize

---

### 5. Single Responsibility

**Principle:** Each repository/module has ONE clear purpose.

**Why:**
- Easier to understand
- Easier to test
- Clear ownership
- Independent evolution

**Application:**

**Repository Organization:**
- `datrix-common`: Foundation and code generation framework (AST model, types, errors, config, semantic analysis, plugin protocols, pipeline) - ONE PURPOSE
- `datrix-language`: Parser and CST-to-AST transformers (AST model lives in datrix-common) - ONE PURPOSE
- `datrix-codegen-component`: Platform-agnostic component generation - ONE PURPOSE
- `datrix-codegen-python`: Python code generation - ONE PURPOSE
- `datrix-codegen-docker`: Docker generation - ONE PURPOSE

**Module Organization:** Each package keeps one concern per module (e.g. models, routes, services, tests). One generator class per concern; platform-specific generation (e.g. Docker) lives in a separate package, not mixed with metrics or other concerns.

---

### 6. Dependency Inversion

**Principle:** Depend on abstractions, not concretions.

**Why:**
- Easier to swap implementations
- Better testing (swap real implementations)
- Loose coupling
- Plugin architecture

**Application:** Generators depend on abstractions (e.g. a formatter interface); concrete implementations (Ruff for Python, Prettier for TypeScript) live in the codebase and can be swapped. See `datrix_common` and generator packages for the interfaces.

**Benefits:**
- ✅ Easy to add new formatters
- ✅ Easy to test (swap formatter implementations)
- ✅ User choice of formatter
- ✅ No tight coupling

---

### 7. Explicit Over Implicit

**Principle:** Be explicit about requirements and behavior. No magic.

**Why:**
- Easier to understand
- No surprises
- Better error messages
- Self-documenting

**Application:** Types and configuration are explicit. Fields must declare their type; no inference from names (e.g. `_id` → UUID). Generators receive all required parameters (app, output_dir, versions); no magic defaults. The codebase uses explicit types and constructor arguments throughout.

---

## Language Design Principles

### 1. Platform Independence

**Principle:** DSL code should be platform-agnostic.

**Application:**
```datrix
// Same DSL works for all platforms (excerpt from examples/01-tutorial/01-basic-entity)
service library.BookService : version('1.0.0') {
 rdbms db('config/book-service/datasources.yaml') {
 abstract entity BaseEntity {
 @UUID id : primaryKey = uuid();
 @UDateTime createdAt = utcNow();
 @UDateTime updatedAt = utcNow();
 }
 entity Book extends BaseEntity {
 String(200) title;
 String(20) isbn;
 String(100) author;
 Int publicationYear;
 }
 }
}

// Platform selection via config (system-config.yaml: language, hosting), not CLI flags:
// Set hosting: docker | kubernetes | aws | azure in the active profile, then:
// datrix generate --source system.dtrx --output ./generated
```

**Generated Differences:**
- Docker: Creates Dockerfile + docker-compose.yml
- Kubernetes: Creates Deployment + Service manifests
- AWS: Creates ECS task definitions
- **Business logic: Identical across all platforms**

---

### 2. DRY (Don't Repeat Yourself)

**Principle:** Define once, use everywhere.

**Application:**

**Inheritance:** (inside an rdbms block; see [examples/01-tutorial/01-basic-entity](../../examples/01-tutorial/01-basic-entity/))
```datrix
abstract entity BaseEntity {
 @UUID id : primaryKey = uuid();
 @UDateTime createdAt = utcNow();
 @UDateTime updatedAt = utcNow();
}

// Inherit everywhere - no repetition
entity User extends BaseEntity { }
entity Order extends BaseEntity { }
entity Product extends BaseEntity { }
```

**Struct Reuse:** (structs and entities inside service blocks; see [examples/01-tutorial/13-structs](../../examples/01-tutorial/13-structs/))
```datrix
struct Address {
 String street;
 String city;
 String state;
 String zipCode;
}

entity User extends BaseEntity {
 Address shippingAddress; // Reuse
 Address billingAddress; // Reuse
}
```

---

### 3. Service as Unit of Deployment

**Principle:** Each service owns its infrastructure and business logic. The DSL makes service boundaries explicit.

**Application:**
- Each service declares its own data stores via named blocks: `rdbms db('path')`, `cache redis('path')`, `nosql docdb('path')`, `storage store('path')`, `pubsub mq('path')`
- Config is externalized and profile-based (YAML/JSON). Top-level keys are profile names (`development`, `production`); the generator selects the key from the system profile
- One statement per concern: registration, resilience, and each integration type are separate config statements; deployment-related settings (replicas, resources, healthCheck) live in service-config YAML, not in the DSL

---

### 4. Named Data Blocks and Block-Qualified Access

**Principle:** All data blocks require a user-chosen block name, enabling block-qualified access from outside the block.

**Named Block Syntax:**
```datrix
rdbms db('config/datasources.yaml') { ... }
nosql docdb('config/nosql.yaml') { ... }
cache redis('config/cache.yaml') { ... }
storage store('config/storage.yaml') { ... }
pubsub mq('config/pubsub.yaml') { ... }
```

**Access Rules:**
- **Inside the same block:** Bare names (e.g., `belongsTo Author`, `extends BaseEntity`)
- **Outside the block:** Use `blockname.Thing` (e.g., `resource db.Book`, `db.User.findOrFail(id)`, `redis.SessionCache.set(...)`)
- **Enums, structs, constants:** Live at service level (directly inside `service { }`), always bare names
- **Transactions:** Explicitly name the block they scope: `transaction(db) { ... }`

---

### 5. Progressive Disclosure

**Principle:** Simple things should be simple, complex things should be possible.

**Application:**

**Simple entity (minimal syntax; inside rdbms block):**
```datrix
entity User extends BaseEntity {
 String(100) name;
 Email email;
}
```

**Complex entity (when needed; see [examples/01-tutorial/08-authentication/book-service.dtrx](../../examples/01-tutorial/08-authentication/book-service.dtrx) for User with Auth.hashPassword in beforeCreate):**
```datrix
entity User extends BaseEntity {
 Email email : unique;
 Password passwordHash;
 String(100) firstName;
 String(100) lastName;
 UserRole role = UserRole.Customer;

 String fullName := "{firstName} {lastName}";

 validate {
 if (firstName.trim().isEmpty())
 ValidationError("First name is required");
 }

 beforeCreate {
 passwordHash = Auth.hashPassword(passwordHash);
 }

 afterCreate {
 emit UserRegistered(id, email);
 }
}
```

---

## Code Generation Principles

### 1. Generate Idiomatic Code

**Principle:** Generated code should follow language best practices.

**Application:** Generated Python uses type hints, Pydantic models, and async/await where appropriate (e.g. FastAPI). Generated TypeScript uses interfaces, async/await, and framework conventions (e.g. NestJS decorators). The generators produce idiomatic code per language and framework.

---

### 2. No Dead Code

**Principle:** Only generate code that will be used.

**Application:** Only code that is used is generated. Utilities (e.g. case conversion) are emitted only when the Application requires them. The codebase does not generate unused helpers "just in case."

---

### 3. Readable Generated Code

**Principle:** Generated code should be readable by humans.

**Application:** Generated code is structured for readability: docstrings, type hints, clear names, and consistent formatting. Models and routes follow a logical structure. The generators enforce these via templates and formatting checks.

**Features:**
- ✅ Docstrings
- ✅ Type hints
- ✅ Clear variable names
- ✅ Proper formatting
- ✅ Logical structure

---

## Summary

Datrix design principles ensure:

1. **Reliability** - Fail fast, no broken code
2. **Type Safety** - Exhaustive mappings, no implicit conversions
3. **Maintainability** - Template-based generation, single responsibility, immutable AST model
4. **Developer Experience** - Clear errors, readable code, helpful messages
5. **Language Quality** - Platform-independent, DRY, progressive disclosure
6. **Code Quality** - Idiomatic, no dead code, readable output

These principles guide all architectural and implementation decisions in the Datrix project.

---

**Last Updated:** March 16, 2026
