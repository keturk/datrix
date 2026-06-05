# Database Drift Reconciliation Guide

**Understanding and managing schema divergence in shared database environments**

This guide covers the problem of database schema drift in shared or non-ephemeral environments, the workflow to detect and reconcile drift, and how to configure your system for production safety or pre-production flexibility.

---

## The Problem: Three Sources of Truth

In traditional database migration systems, there is a single source of truth: the migration ledger. But in shared database environments (where multiple teams or deployments may affect a database) or when manual hotfixes and backup restores occur, **three schema snapshots can diverge**:

| Snapshot | Symbol | Source | Meaning |
|----------|--------|--------|---------|
| **Recorded** | `R` | Migration ledger | The schema Datrix knows about (from the latest applied migration) |
| **Desired** | `D` | DSL AST | The schema defined in your `.dtrx` specification |
| **Live** | `L` | Live database catalog | The actual schema currently in the database |

**When divergence happens:**

- A colleague applies a manual hotfix directly to the database → `L ≠ R`
- A backup is restored from a past state → `L ≠ R` and `L ≠ D`
- A partially-applied migration is rolled back in production → `L ≠ R`
- A deployment is skipped in one environment but not another → `L ≠ D` across environments

When Datrix generates new migrations, it plans `R → D`. If the database is actually at `L`, the migration will **collide with the live schema** and fail.

---

## The Solution: Export and Reconcile

Datrix cannot connect to databases directly (keeping credentials in your deployment environment), but it can work with **exported schema snapshots**. The drift/reconcile workflow is:

### 1. Export Live Schema in the Environment

In your deployment environment (where the database is reachable), run an environment-side exporter to reflect the live database catalog into a snapshot file:

```
live-schema-snapshot.json
```

**Where:** This command runs in your environment (not in your CI/CD pipeline touching Datrix).

**What it captures:** Datrix uses this snapshot to detect actual schema state without opening a database connection.

### 2. Run `datrix migrations drift` (Offline)

Bring the live snapshot into Datrix and detect drift:

```bash
datrix migrations drift \
  --app ./my-app \
  --live-snapshot /path/to/live-schema-snapshot.json
```

**Output:** A drift report showing:
- `diff(R, L)` — What changed in the live database since the last recorded revision
- Classification: structural changes, data-loss risks, safe changes
- Options: adopt the drift or converge to desired

**No database connection needed.**

### 3a. Reconcile with `--adopt` (Keep Reality)

If the live divergence is acceptable (intentional hotfixes, approved manual changes):

```bash
datrix migrations reconcile \
  --app ./my-app \
  --live-snapshot /path/to/live-schema-snapshot.json \
  --adopt
```

**Effect:**
- Records the current live schema as an adopted revision
- Moves the recorded baseline `R := L`
- Future migrations will plan from the new baseline

**Use case:** Pre-production or development environments where manual adjustments are expected.

### 3b. Reconcile with `--to-desired` (Generate DDL)

If the live divergence is unintended and you want to converge to desired:

```bash
datrix migrations reconcile \
  --app ./my-app \
  --live-snapshot /path/to/live-schema-snapshot.json \
  --to-desired
```

**Effect:**
- Generates DDL to move the database from `L` to `D`
- Respects existing change policy (blocked changes stay blocked)
- Records a convergence revision in the ledger

**Use case:** Repair unintended drift after you fix the schema definition.

---

## Configuration: Guard vs. Reconcile

The `driftPolicy` selector in your system config determines whether this workflow is required or optional:

### Production: Guard Mode (`mode: "guard"`)

```dcfg
profile production as "prod" extends base {
  driftPolicy {
    mode = "guard";
  }
}
```

**Behavior:**
- Before deployment, you must run `datrix migrations drift` and verify that `L = R = D`
- If drift is detected, reconciliation verbs refuse to run
- The system treats drift as a **red flag**, not something to auto-fix

**Safety:** Production never auto-reconciles. You always review the divergence before deciding what to do.

### Pre-Production: Reconcile Mode (`mode: "reconcile"`)

```dcfg
profile staging as "stg" extends base {
  driftPolicy {
    mode = "reconcile";
  }
}
```

**Behavior:**
- Drift detection and reconciliation verbs are available
- You can `--adopt` divergence or `--to-desired` to repair it
- Supports the full experimental loop: fix spec → regenerate → export snapshot → adopt/converge

**Flexibility:** Pre-production environments can safely try fixes and iterate quickly.

### Development: Off (Default)

```dcfg
profile development as "dev" extends base {
  // driftPolicy defaults to off; no selector needed
}
```

**Behavior:**
- No workflow machinery required
- Drift commands remain available for manual use
- Full backward compatibility

---

## Example Workflow: Pre-Prod Iteration

You're developing a feature in a shared staging database:

1. **Discover a problem:**
   - You update your `.dtrx` spec with new fields
   - Run `datrix generate --profile staging`
   - The migration planner detects that the live database is at an older state

2. **Export the live snapshot** (in the staging environment):
   ```bash
   # Environment-side exporter (example command; tool-specific)
   datrix-export-schema \
     --connection-string "postgres://user:pass@staging-db:5432/myapp" \
     --output live-schema-snapshot.json
   ```

3. **Detect drift** (in your local Datrix project):
   ```bash
   datrix migrations drift \
     --app ./my-app \
     --live-snapshot live-schema-snapshot.json
   ```
   
   Output shows: older fields are missing, recorded baseline `R` is one revision behind `L`.

4. **Adopt or reconcile:**
   ```bash
   # If you're just documenting reality
   datrix migrations reconcile \
     --app ./my-app \
     --live-snapshot live-schema-snapshot.json \
     --adopt
   ```
   
   Now `R = L`. Generate again and plan fresh migrations.

5. **Or converge if the spec is right:**
   ```bash
   # If the spec fix is correct and staging should match
   datrix migrations reconcile \
     --app ./my-app \
     --live-snapshot live-schema-snapshot.json \
     --to-desired
   ```
   
   The system generates DDL to add the missing fields and executes the migration.

---

## Important Notes

- **Datrix never connects to databases.** All drift detection happens offline against exported snapshots. Credentials and connection strings stay in your deployment environment.
- **Live snapshots are temporary artifacts.** They are generated per-environment and per-point-in-time. They do not need to be committed to version control.
- **Adoption records intent.** When you adopt drift, you're declaring: "This is the reality we've chosen; plan future migrations from here." This is tracked separately from adapter-alignment so it's auditable.
- **Convergence respects policy.** When you reconcile `--to-desired`, the system respects your existing `change_policy` settings. Blocked changes stay blocked; destructive operations are still classified and visible.
- **Non-ephemeral environments only.** In ephemeral environments (containers spun up fresh per deploy), drift should never occur. Use `guard` or `reconcile` only for persistent, shared databases.

---

## Neutral Example: E-commerce Order Service

Suppose you have an order service in staging:

```dtrx
service ecommerce.OrderService : version('1.0.0') {
  entity Order {
    orderId: UUID @pk;
    customerId: UUID;
    createdAt: Timestamp;
    total: Decimal;
  }
}
```

Someone manually adds a status field in staging:

```sql
ALTER TABLE orders ADD COLUMN status VARCHAR(50) DEFAULT 'pending';
```

Now `L ≠ R` (live has status, recorded doesn't). You have two choices:

1. **Adopt it** if this is a temporary experiment:
   ```bash
   datrix migrations reconcile --app . --live-snapshot live-schema-snapshot.json --adopt
   ```
   
   Recorded baseline moves forward. Future migrations plan from this new baseline.

2. **Remove it via `--to-desired`** if the spec is authoritative:
   First, add status to the spec:
   ```dtrx
   entity Order {
     orderId: UUID @pk;
     customerId: UUID;
     createdAt: Timestamp;
     total: Decimal;
     status: String; // added
   }
   ```
   
   Then reconcile:
   ```bash
   datrix migrations reconcile --app . --live-snapshot live-schema-snapshot.json --to-desired
   ```
   
   Datrix generates a migration adding status (correctly) and the database converges to the spec.

---

## See Also

- **[Config DSL Reference — Drift Policy Selector](../reference/config-dsl-reference.md#drift-policy-selector)** — How to configure `driftPolicy` in your `.dcfg` files
- **[RDBMS Migration Decisions (D24–D29)](../architecture/rdbms-migration-decisions.md#database-drift-detection--reconciliation-d24d29)** — Technical rationale and design details
- **[Architecture Overview — Decision 10](../architecture/architecture-overview.md#decision-10-database-drift-detection--reconciliation)** — System-level overview
- **[CLI Migrations Commands](../../../datrix-cli/docs/commands/migrations.md)** — Full command reference
- **[RDBMS Migration API](../../../datrix-common/docs/architecture/migration.md)** — Programmatic migration interface
