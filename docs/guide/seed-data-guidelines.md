# Seed Data Guidelines

**How to declare, manage, and deploy seed data in Datrix applications**

---

## Overview

Datrix provides a declarative seed data system that lets project authors specify reference data, baseline environments, and volume test data alongside their `.dtrx` and `.dcfg` files. Seed declarations are written in `.dseed` files using SeedDSL, parsed and validated at compile time, and generate executable seed scripts for each target language.

### Why Seed Data Matters

1. **Production requires reference data.** Lookup tables (countries, currencies, billing plans) are prerequisites for application logic. A newly deployed production environment cannot process its first request until these tables are populated.
2. **Staging needs a baseline.** QA, demos, and integration testing require a functional dataset beyond reference data: seed organizations, users, and domain-specific records.
3. **Repeatability.** Version-controlled seed declarations ensure every developer and every deployment starts from the same known state.

### Seed Categories

| Category | Profiles | Use Case |
|----------|----------|----------|
| `reference` | all (dev, test, stg, **prod**) | Lookup tables, business constants. Application cannot function without these. |
| `baseline` | dev, test, stg | Minimal functional dataset (seed org, admin user, subscriptions). |
| `volume` | stg, load | Realistic-scale data for demos, QA, and load testing. |

---

## Project Setup

### File Organization

Place `.dseed` files in a `seed/` directory alongside your `config/` and `specs/` directories:

```
my-project/
  specs/
    system.dtrx
    auth-service.dtrx
    billing-service.dtrx
  config/
    system.dcfg
    auth-service.dcfg
    billing-service.dcfg
  seed/
    system.dseed               # Registry + shared component seeds
    auth-service.dseed         # Auth service seeds
    billing-service.dseed      # Billing service seeds
```

### Seed Registry

Cross-service seeding requires coordinated identifiers. Declare a `registry` block (typically in `system.dseed`) with shared aliases:

```dseed
registry {
  "seed:acme-org"      = @uuid("acme-org");
  "seed:acme-admin"    = @uuid("acme-admin");
  "seed:acme-billing"  = @uuid("acme-billing");
}
```

All `@ref()` calls across all `.dseed` files resolve against this registry, giving every service a consistent view of cross-service IDs without runtime service calls.

---

## Writing Seed Data

### Reference Data

Reference data populates lookup tables and business constants required by all deployment profiles including production.

**Use builtin seed functions** for framework-maintained datasets:

```dseed
seed shared common.SharedLookups {
  rdbms lookupDb {
    reference {
      Country from Seed.countries();
      Currency from Seed.currencies();
      Timezone from Seed.timezones();
    }
  }
}
```

**Use tabular syntax** for project-specific reference data:

```dseed
seed service ecommerce.BillingService {
  rdbms billingDb {
    reference {
      Plan table on(tier) {
        name,          tier,          rateLimitRpm, dailyQuota, monthlyPriceCents;
        "Free",        "Free",        60,           10000,      0;
        "Basic",       "Basic",       120,          50000,      2900;
        "Pro",         "Pro",         600,          250000,     9900;
        "Enterprise",  "Enterprise",  5000,         5000000,    0;
      }
    }
  }
}
```

### Baseline Data

Baseline data creates a functional starting state for dev and staging environments.

```dseed
seed service ecommerce.AuthService {
  rdbms authDb {
    baseline {
      Organization table {
        id,                    name,        slug,   currentPlan, isActive;
        @ref("seed:acme-org"), "Acme Corp", "acme", "Pro",       true;
      }

      User table {
        id,                      organizationId,        fullName,      email,             passwordHash,           role;
        @ref("seed:acme-admin"), @ref("seed:acme-org"), "Admin User",  "admin@acme.test", @hash("SeedP@ss2024!"), "OrgAdmin";
      }
    }
  }
}
```

### Volume Data

Volume data provides realistic-scale datasets for staging and load testing. Use external files for large datasets:

```dseed
seed service ecommerce.CatalogService {
  rdbms catalogDb {
    volume {
      Product from "seed-data/products-20000.csv";
      ProductVariant from "seed-data/variants-80000.jsonl";
    }
  }
}
```

---

## Field Selection Rules

SeedDSL may provide values for any persisted field the target component stores. Omitted fields use the target's normal default behavior.

| Rule | Example | Behavior |
|------|---------|----------|
| **Persisted fields allowed** | `DateTime createdAt : server = DateTime.now()` | May be provided explicitly. If omitted, normal target defaults apply. |
| **Computed non-persisted fields rejected** | `Boolean isAvailable := status == OrderStatus.Active` | Cannot be seeded (not stored). |
| **Nullable fields optional** | `String(200)? description` | May be omitted. |
| **Default-valued fields optional** | `Boolean isActive = true` | May be omitted (DB default applies). |
| **Required fields mandatory** | `String(100) name : trim` | Must appear in seed data or generation fails. |

### Minimal Seed Declarations

Seed declarations can be minimal — only required fields plus any fields where the desired value differs from the default:

```dseed
// Only required fields — isActive defaults to true, userLimit defaults to 5
authDb.Organization table {
  id,                   name,        slug;
  @uuid("acme-org"),    "Acme Corp", "acme";
}
```

---

## Trait-Specific Seeding

Traits add fields and behaviors. Each built-in trait has defined seeding semantics:

| Trait | Fields Added | Seed Behavior |
|-------|-------------|---------------|
| `Tenantable` | `UUID tenantId : index` | Must be present or derivable from an explicit tenant context. |
| `Auditable` | `UUID? createdBy`, `UUID? updatedBy` | Persisted fields may be explicitly seeded; omitted fields use defaults. |
| `SoftDeletable` | `DateTime? deletedAt`, `UUID? deletedBy`, computed `Boolean isDeleted` | Persisted fields may be seeded; non-persisted computed `isDeleted` cannot be seeded. |
| `Sluggable` | `String slug : unique, lowercase` | **Required in seed data.** The slug is a natural key used for upsert conflict detection. |
| Custom traits | Trait-declared fields | Follow standard field selection rules. |

---

## Type-Specific Patterns

### Enum Values

Enum values are referenced by their variant name (unqualified within the entity's context):

```dseed
authDb.User table {
  fullName,        email,                role;
  "Admin User",    "admin@acme.test",    "OrgAdmin";
}
```

The generator maps string enum names to their target-language representation. With explicit `value()`, the explicit string is used; without, the ordinal or name is used depending on DB mapping configuration.

### Scalar Types and Constraints

Custom scalar types impose validation constraints. Seed data must satisfy these constraints:

```dseed
// Scalar ISBN requires pattern "^[0-9\\-]{10,13}$"
catalogDb.Book table {
  title,                  isbn;
  "Domain-Driven Design", "978-0321125217";
}
```

Invalid seed data produces a compile-time error with a diagnostic message.

### Password Fields

The `Password` semantic type requires pre-computed hashes. Use `@hash()`:

```dseed
authDb.User table {
  fullName,       email,               passwordHash;
  "Admin User",   "admin@acme.test",   @hash("SeedP@ss2024!");
}
```

The generator pre-computes the hash at generation time using the configured security policy for the target field.

### Geometry / Geospatial Fields

Use `@geo()` for GeoJSON strings:

```dseed
warehouseDb.DeliveryZone table {
  name,             boundary,                                              maxRadiusKm;
  "Downtown Zone",  @geo('{"type":"Polygon","coordinates":[[[...]]]}'),    15;
}
```

### JSON and Map Fields

Use `@json()` for structured literals:

```dseed
orderDb.Order table {
  orderNumber,    metadata,                                    tags;
  "ORD-001",      @json('{"source": "web", "priority": 1}'),  @json('["express", "fragile"]');
}
```

---

## Seed Data and Application State

### Lifecycle Hooks Are Bypassed

Target-native seeding writes directly to the storage target, NOT through the entity's domain layer. This means:

- **Lifecycle hooks** (`beforeCreate`, `afterCreate`, etc.) are NOT triggered
- **Validation blocks** are NOT executed (seed authors ensure data correctness)
- **Event subscribers** are NOT notified

### Denormalized Fields Must Be Explicit

If lifecycle hooks or event subscribers normally maintain denormalized state, seed data must include those values explicitly:

```dseed
// Organization.currentPlan is normally updated by BillingEvents subscription.
// In seed data, it must be explicitly set:
authDb.Organization table {
  id,                    name,        slug,   currentPlan;
  @uuid("acme-org"),     "Acme Corp", "acme", "Pro";
}
```

### Hook-Maintained Computed Fields

If seed data for one entity implies state changes on another entity (e.g., `Warehouse.hasRefrigeratedZone` maintained by `StorageZone` hooks), the seed declaration must include the corresponding rows/fields explicitly. SeedDSL does not infer or repair business semantics.

### CQRS Views After Seeding

Services with CQRS `view` blocks maintain read-optimized projections normally updated via domain events. Target-native seeding bypasses these events. After seeding, use the `--rebuild-views` flag on the seed runner to populate CQRS views from source entities.

### Cache Warming After Seeding

Services with `cache` blocks can optionally pre-warm caches after seeding:

```bash
datrix seed --profile stg --warm-cache
```

This is generated as a separate maintenance phase, not part of the main idempotent seed flow.

---

## Constraints and Relationships

### Upsert Conflict Keys

The upsert conflict target is determined by:

1. **Primary key** — Default conflict target
2. **Single-field `unique` constraint** — Preferred for natural key upserts (e.g., `slug`)
3. **Composite unique index** — `index(field1, field2) : unique`

Use `on(...)` for explicit conflict key specification when inference is ambiguous:

```dseed
reference {
  catalogDb.ProductTag table on(productId, tagId) {
    productId,                                    tagId;
    @lookup(Product, {sku: "SKU-001"}),           @lookup(Tag, {name: "Featured"});
  }
}
```

### Cascade Relationships and Ordering

Entities with cascade relationships imply parent-child ordering. The seed generator topologically sorts entities by foreign key dependencies, inserting parents before children regardless of declaration order.

### Fulltext Indexes

After bulk seeding, the generator emits a post-seed `ANALYZE` statement for PostgreSQL to ensure query planner statistics are current.

---

## Cross-Service Dependencies

The seed runner resolves execution order from the service dependency graph derived from `@ref()` and `@lookup()` declarations:

```
Phase 1 — Reference (all profiles including prod):
  1. SharedLookups       → Countries, Currencies, Timezones
  2. BillingService      → Plans
  3. AuthService         → Roles, Permissions

Phase 2 — Baseline (dev, test, stg only):
  4. AuthService         → Organization, User, ApiKey
  5. BillingService      → BillingAccount, Subscription
  6. InventoryService    → Warehouse, StockLevel

Phase 3 — Volume (stg, load only):
  7. CatalogService      → Products, Variants
  8. OrderService        → Orders, LineItems
```

Circular dependencies are a compile-time error.

---

## Configuration

### Profile Category Mapping

Projects can override the default category-to-profile mapping in `system.dcfg`:

```dcfg
config system ecommerce.System {
  base {
    seed {
      categories {
        reference = ["dev", "test", "stg", "prod"];
        baseline  = ["dev", "test", "stg"];
        volume    = ["stg"];
      }
    }
  }
}
```

### Production Safety

`datrix seed --profile prod` runs **only reference data** by default. Baseline and volume categories are rejected for production unless explicitly overridden with `--force`. This ensures running `datrix seed` in a production deployment pipeline is always safe.

---

## Deployment Integration

### Generated Seed Scripts

Each codegen package emits seed scripts in its target language. Output structure per owner/component:

```
src/{service}/
  persistence/
    seeds/
      seed-<component>.<ext>   # Per-component seed function
    seed-runner.<ext>           # Orchestrator: runs owned components in order
  seed_data/                    # Embedded reference datasets (from Seed.* builtins)
```

### Docker Compose

Generated Docker Compose output includes seed services that run after migrations:

```yaml
services:
  billing-service-seed:
    command: ["python", "-m", "billing.persistence.seeds.seed_runner"]
    depends_on:
      billing-service-migrate:
        condition: service_completed_successfully
    restart: "no"
```

### Kubernetes

Generated Kubernetes output includes seed Jobs alongside existing init Jobs:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: billing-service-seed
spec:
  backoffLimit: 3
  template:
    spec:
      containers:
        - name: seed
          command: ["python", "-m", "billing.persistence.seeds.seed_runner"]
      restartPolicy: Never
```

---

## Idempotency

All seed operations are idempotent. Re-running a seed script does not duplicate data:

| Target | Strategy |
|--------|----------|
| PostgreSQL | `INSERT ... ON CONFLICT (key) DO NOTHING` |
| MySQL/MariaDB | `INSERT IGNORE` or `ON DUPLICATE KEY UPDATE` |
| MongoDB/DocumentDB | `_id` or declared unique key with upsert filter |
| DynamoDB | Partition/sort key conditional put |
| Storage | Object key policy (`overwrite`, `ifMissing`, or checksum match) |

---

## Seed Capture

Capture existing database state into SeedDSL declarations:

```bash
# Capture one service
datrix seed capture --profile dev --service billing-service --category baseline

# Capture specific RDBMS components
datrix seed capture --profile stg --service order-service --rdbms orderDb,fulfillmentDb

# Capture all services
datrix seed capture --profile stg --all-services --category baseline
```

Capture rules:
- Tenant boundaries are respected; either `--tenant` or `--all-tenants` is required for multi-tenant systems
- Secrets and credential-like fields are redacted by default
- Production capture is read-only and defaults to `--category reference`
- Foreign keys are converted to `@ref()` or `@lookup()` where stable natural keys are available

---

## See Also

- [SeedDSL Syntax Reference](../../../datrix-language/docs/reference/seed-dsl-syntax-reference.md) — Complete `.dseed` file format
- [Seed Builtin Functions](../../../datrix-language/docs/reference/datrix-builtins.md#seed) — `Seed.*` builtin reference
- [CLI Seed Command](../../../datrix-cli/docs/commands/seed.md) — CLI execution and capture
- [Configuration Guide](configuration-guide.md) — Profile and seed configuration
