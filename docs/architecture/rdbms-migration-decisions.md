# RDBMS Migration Architectural Decisions

**Last Updated:** June 8, 2026

This document records the architectural decisions for Datrix incremental RDBMS schema migrations. For API-level documentation see [RDBMS Migration API](../../../datrix-common/docs/architecture/migration.md). For the adapter protocol see [RdbmsMigrationAdapter](../../../datrix-codegen-common/docs/migration-adapter.md).

---

## Non-Goals

This migration contract intentionally does not:

1. Drop and recreate databases as the normal migration strategy
2. Add startup-time automatic schema mutation as the primary fix
3. Require live database access for normal offline code generation
4. Parse language-specific migration files as canonical schema truth
5. Force every target language to use the same migration tool
6. Design around one downstream application or deployment environment
7. Define NoSQL collection/index migration behavior
8. Define object-storage bucket/prefix/lifecycle migration behavior
9. Define cache, search-index, queue, topic, or stream migration behavior

---

## D1: Incremental Schema Migration Is a Datrix Platform Contract

Language generators render target-native artifacts, but snapshot state, diffing, ledger, retention, and safety policy belong to shared Datrix infrastructure in `datrix-common`.

## D2: Migration Revisions Are Immutable Once Generated

Changing an applied revision file is invalid in every migration system that tracks revision identity. Datrix appends new revisions instead of rewriting historical ones.

## D3: Canonical Snapshots Are the Diff Source of Truth

Datrix does not parse Python, TypeScript, SQL, or future target migration files to infer prior schema state. Snapshots (`schema.json`) are the canonical generation-time baseline.

## D4: Missing Previous State Is a Hard Error When History Exists

Silent baseline regeneration can create deployed schema drift. Datrix fails with an actionable diagnostic instead.

## D5: Target Tools Are Adapter Details

Alembic, MikroORM, Flyway-style SQL, or future migration tools are adapter choices. They do not define the platform migration lifecycle. Current adapters are Python/Alembic and TypeScript/MikroORM.

## D6: Startup Schema Repair Is Not the Primary Migration System

Startup drift repair may later be considered as an optional safety net for narrow nullable-add cases, but it cannot replace generated migration history.

## D7: No New Migration DSL

The implementation uses existing application DSL and config models as the source of desired RDBMS schema. It does not add a migration DSL. The generated snapshot and ledger files are generator state, not author-written DSL.

## D8: State Lives Under App-Root `.datrix`

`schema.json` and `ledger.json` are stored under `{app_dir}/.datrix/rdbms-migrations/{rdbms_id}/`, where `app_dir` is the source application folder that owns the `.dtrx` and config inputs. Migration directories in generated output folders contain target-native migration files only. Changing output folders, profiles, resolved database engines, platforms, owner containers, block aliases, or target languages does not reset migration history for the same logical RDBMS block.

## D8a: RDBMS Migration Streams Are UUID Scoped

A service can have multiple `rdbms` blocks. The `.dcfg` `RdbmsConfig.id` UUID is the logical storage contract identity. The `.dtrx` owner container and block alias are mutable metadata. Migration history is scoped to `rdbms_id`, not to resolved database engine, database name, platform, profile, output folder, owner container, block alias, or target language.

## D9: Language/Adapter Changes Require Explicit Bootstrap for Existing Databases

The canonical Datrix schema revision chain is shared across target languages, profiles, platforms, and RDBMS engines. Runtime migration tools are not shared: Alembic and MikroORM maintain different applied-history tables. When an existing database changes runtime migration tool, Datrix requires explicit generated-output/deployment bootstrap or stamping instead of silently replaying or skipping migrations.

## D10: `schema_hash` Excludes Revision Metadata

`schema_hash` is the logical RDBMS schema hash. It excludes `latest_revision` and the `schema_hash` field itself. Ledger `from_schema_hash` and `to_schema_hash` refer to this logical schema hash.

## D11: Canonical Operations Use a Fixed Vocabulary

`ledger.json` stores canonical Datrix migration operations from a fixed database-agnostic vocabulary. It does not store SQL, Alembic operations, MikroORM code, generated filenames, adapter IDs, active profile, platform, or database engine. Unsupported schema diffs fail before rendering.

**Allowed operations:** `create_table`, `add_column`, `alter_column_nullable`, `alter_column_type`, `add_primary_key`, `add_foreign_key`, `add_index`, `create_enum`, `add_enum_value`, `create_cqrs_view_table`.

**Blocked operations:** `drop_table`, `drop_column`, `drop_primary_key`, `drop_foreign_key`, `drop_index`, enum value removal/rename/reorder, `drop_cqrs_view_table`, arbitrary SQL, target-native migration code.

## D12: Offline Generation Does Not Know Database State

Datrix generation does not infer whether a target database is empty or already populated. Database state is external runtime state, not available to normal offline generation. When a generated output changes runtime migration tool or lacks generated-output migration history for the canonical ledger, Datrix emits deployment-readiness diagnostics and requires explicit bootstrap/stamping.

## D13: Automatic Migrations Are Safe/Additive Only

Datrix-generated automatic migrations do not perform destructive or ambiguous schema changes. Field/table removal, rename, type narrowing, enum removal/rename/reorder, index removal, primary-key changes, and foreign-key removal fail as generation errors before rendering. There is no ConfigDSL or CLI override that converts destructive diffs into automatic generated migrations.

## D14: SQL Files Are Not an Implicit Fallback

`datrix-codegen-sql` is an explicit migration adapter, not the default fallback for target languages without native migration tooling. A target language that emits RDBMS-backed services must declare a native migration renderer, an explicit SQL-file apply strategy, or an explicit no-migration/deployment-readiness failure policy.

## D15: Migration State Paths Are Centralized and Stable

`datrix_common.migration.state_store` is the only code allowed to construct app-level migration state paths. It validates `RdbmsConfig.id` as a UUID, lower-cases it, and uses it as the sole path segment under `.datrix/rdbms-migrations`. Language generators and platform generators must call the state store API instead of hand-building paths.

## D16: RDBMS UUID Is Required and Stable Across Profiles

Every resolved `RdbmsConfig` must contain an `id` UUID authored in ConfigDSL. Normal code generation does not silently generate missing IDs. Within a resolved profile, IDs are unique across service-owned and shared-owned RDBMS blocks. When the same owner-qualified RDBMS block appears in multiple profiles, it must resolve to the same ID.

## D17: Shared-Owned RDBMS Migrations Use Shared Generated Output

Shared-owned RDBMS blocks are first-class migration targets. Their adapter-native migration files are generated under the shared block output tree using `SharedPaths.rdbms_dir`, not under a consuming service. The canonical app-level state path is still keyed only by `rdbms_id`.

## D18: Shared-Owned RDBMS Migrations Are Deployment-Level Apply Units

Shared-owned RDBMS migrations are applied once per `rdbms_id` by platform/deployment wiring. They are not run by each consuming service and are not assigned to one arbitrary service owner. Platform generators create one migration init/job per shared-owned RDBMS block and wire consuming services to wait for it when needed.

## D19: No Legacy Generated-Output Adoption Path

The rollout updates `.dcfg` files with `RdbmsConfig.id` values and regenerates outputs from scratch. Missing app-level state with existing generated migration history remains a hard error, not an implicit adoption flow.

## D20: No Automatic Rename Inference

Datrix does not infer table, field, enum, or index renames from delete/add pairs. Rename-like diffs are generation errors in automatic migration planning.

## D21: Existing-Table Foreign-Key Additions Are Generation Errors

Generated `add_foreign_key` is allowed only for a table created by the same revision or during the initial baseline. Adding a foreign-key constraint to a table that existed in the previous snapshot is a generation error because offline generation cannot validate existing rows.

## D22: Enum Evolution Is Append-Only

Generated enum migration supports enum creation and safe enum value append only. Enum value removal, rename, reorder, or representation-strategy changes are generation errors.

## D23: Rollback Is Not the Deployment Contract

Generated deployment applies migrations forward only. Adapters render rollback bodies only because target migration tools require them or because a deterministic inverse is available. Irreversible generated operations fail loudly in rollback bodies rather than silently no-oping.

---

## Database Drift Detection & Reconciliation (D24–D29)

The migration engine is purely source-driven: every revision diffs a **recorded** baseline (`schema.json`) against a **desired** snapshot built from the AST. It is blind to the **live** database. When a database is changed out-of-band (manual hotfix, restored backup, partially-applied migration, parallel environment), the recorded baseline `R`, the live schema `L`, and the desired schema `D` silently diverge; the engine plans `R → D` and collides with a database already at `L`. The following decisions add the ability to *see* drift (`diff(R, L)`) and *reconcile* it, without making generation require database access. The load-bearing insight: **a live database is just a third source of an `RdbmsSchemaSnapshot`** — once a live snapshot is produced, the existing diff → classify → allocate → ledger pipeline is reusable unchanged.

## D24: The Live Database Is a Third Snapshot Source; Datrix Never Connects To It

An environment-side exporter (running where the database is reachable) reflects the live catalog into an `RdbmsSchemaSnapshot` artifact (`live-schema-snapshot.json`). Datrix-side `drift`/`reconcile` commands **import that artifact** and perform all diff/classify/reconcile work offline. Datrix generation and reconciliation never open a database connection, accept a connection string, or handle credentials — those stay in the deployment environment. Drift is `differ.diff(R, L)`; convergence is `differ.diff(L, D)` — no new diff algorithm and no new change taxonomy are introduced.

## D25: Comparison Requires One Shared Canonicalization Layer

A live catalog and a source AST describe the same schema differently (implicit PK indexes, backing FK indexes, default-literal formatting, type aliases such as `VARCHAR(255)` vs `String(255)`, identifier casing, index column ordering). Both the source-built and the imported live snapshot pass through one shared canonicalization layer before diffing, or drift detection drowns in false positives. Equivalent schemas must canonicalize to zero drift.

## D26: Adopted Revisions Are a Distinct Classification and Ledger Operation

Reconciliation never edits a frozen revision or rewrites the ledger hash chain — it **appends**. Adopting drift introduces a new ledger classification `"adopted"` (not an overloaded `"baseline"` with a `source` marker) and a new explicit non-DDL canonical operation `adopt_live_schema`, and bumps the ledger schema version. An adopted revision records an auditable schema-hash transition ("at revision N we observed reality had drifted to `L` and adopted it"); its operation details are metadata only (`strategy`, `live_snapshot_hash`, `schema_hash_after`) and must not force destructive observed drift (e.g. a dropped column) into canonical DDL operations, which the ledger intentionally rejects.

## D27: Reality Can Be Recorded; Data Loss Cannot Be Generated

Two operations are not conflated. **Adopt** *records* what the database already is (`R := L`) — documenting an observed drop is stating fact, so it is safe even when the observed drift is destructive; it runs no DDL. **Converge** *generates DDL* to move the database from `L` to `D` and is gated by `change_policy` exactly as source-driven migrations are — `blocked` stays blocked, and no flag suppresses destructive-DDL classification (this honors the existing `change_policy` anti-pattern). Renames are not inferred (inherits D20).

## D28: Live Snapshot Alignment Is Recorded Separately From Adapter Alignment

Reconciliation records that Datrix imported a live snapshot and used it against a canonical revision in a separate file `.datrix/generated-output-state/{rdbms_id}/live-snapshot-alignment.json`, a sibling of the `adapter-alignment.json` precedent (D9) — never overloading it. The record is format/versioned and includes at least `rdbms_id`, `revision`, `schema_hash`, `live_snapshot_hash`, `strategy`, and `recorded_at`. It must not store credentials, connection strings, hostnames, or other deployment secrets.

## D29: Drift Is a Production Guard and a Pre-Prod Reconcile Path

A per-environment policy selector (default off) splits behavior. **Production** treats drift as a guard: export a live snapshot in the target environment, run `detect_drift` offline against it, and refuse (or loudly warn) when `L` ≠ expected — never auto-reconcile. **Pre-prod** gains the reconcile verbs and the recommended loop (fix generator → regenerate → export live snapshot → `drift --live-snapshot` → `reconcile --adopt` or `--to-desired`). The selector controls whether exported live snapshots are required for the guard/reconcile workflow; it never grants Datrix database connectivity. First-implementation reflector scope is Postgres, MySQL, and MariaDB, with MariaDB routed through the MySQL-family reflector and reverse type map unless real MariaDB catalog tests prove a branch is required (inherits the SQL dialect's MariaDB→MySQL mapping).

---

## Regime-Aware Migration Lifecycle (D30–D34)

The migration engine treats every database as a persistent, append-only one. That assumption is correct for production databases with real data, but actively harmful for pre-production and ephemeral databases whose schema is still being designed and whose instances are routinely wiped. The following decisions introduce a **regime** distinction: when a database is declared disposable or pre-production, schema changes that would normally block generation can trigger an explicit reset-and-rebaseline operation instead, letting agents move fast without corrupting the desired specification.

## D30: Rebaseline (`R := D`) Is a First-Class, Policy-Gated Operation

A new `rebaseline` operation explicitly sets the recorded baseline to the desired schema. It runs no DDL, opens no database connection, and is **refused in `guard` mode**. Rebaseline starts a fresh ledger generation (a new `0001_initial` = `D`) rather than editing any frozen revision, and records `rebaselined_from` provenance containing the prior ledger identity, reason, and timestamp for auditability.

**Rationale:** The wipe-and-redeploy lifecycle has no live schema worth preserving and no persistent migration history to protect. Today's recovery mechanism is a manual, unaudited `rm -rf` of the state directory. Making rebaseline a first-class, gated framework operation replaces that ad-hoc approach with an explicit, audited one that records the decision and the prior state for investigation if needed.

## D31: Generation Is Regime-Aware; the Classifier Is Not Weakened

`generate` resolves the `driftPolicy.mode` for the target block at generation time and dispatches on it at the single `classified.blocked` site in the orchestrator. In `off` and `guard` modes, a blocked diff raises `GenerationError` unchanged. In `reconcile` mode, a blocked diff raises with an actionable message naming both `rebaseline` (wipe regime) and `reconcile --to-desired` (keep regime) as operator choices. In `ephemeral` mode, a blocked diff automatically invokes `rebaseline` (R := D) in-process, logs the action, and continues to render a fresh baseline.

**Rationale:** The `change_policy.classify_diff` classification is the single source of truth for *what* a diff is (baseline / safe / risky / blocked). What changes is the *consequence* of the `blocked` outcome, which is now a regime-dependent dispatch. Safe and risky changes flow through the normal incremental allocate-and-append path in all regimes (no weakening, no early classification shortcuts). This separates "what the change is" (stable, reviewable policy) from "what we do about it in this environment" (regime).

## D32: A Fourth `ephemeral` Mode for Disposable Databases; Blocked-Only Auto-Rebaseline

A new `driftPolicy.mode = "ephemeral"` is added to the configuration model and decision flow. In `ephemeral` mode, auto-rebaseline triggers **only on the `blocked` classification** — the one outcome that breaks generation and requires an explicit decision. Safe and risky diffs continue through the normal incremental allocate-and-append path, identical to `off` mode. Default `driftPolicy.mode` remains `off`; `guard`, `reconcile`, and `ephemeral` semantics are all distinct and explicitly chosen per profile.

**Rationale:** Dev and Docker-local databases are thrown away every run; requiring an explicit `rebaseline` command by hand there is pure friction that slows iteration. Scoping auto-rebaseline to the `blocked` classification keeps the behavior minimal and predictable: additive changes (nullable adds, index adds) still build a clean, replayable incremental chain that applies cleanly to a fresh database, and only an otherwise-fatal destructive block collapses to a fresh `D` baseline. Rebaselining *every* diff would cause unnecessary history churn with no benefit on a database that replays the full chain from empty anyway.

## D33: Pre-Prod Never Auto-Rebaselines; Keep-vs-Wipe Is Operator-Chosen

In `reconcile` mode, generation that would block fails with a message offering exactly two operator choices: `rebaseline` (wipe regime — discard and start from `D`) or `reconcile --to-desired` (keep regime — export live schema `L`, converge with an additive migration from `L → D`). The system does not automatically pick one path over the other.

**Rationale:** Pre-production environments sometimes hold staging data worth keeping to verify a fix (e.g., a full-fidelity test dataset prepared for integration testing). Silently discarding it on the next schema change would be the same class of error as today's silent generation block — the operator lost data without realizing it. By surfacing the choice explicitly and requiring a deliberate action, reconcile mode honors the operator's intent: if the data is disposable, `rebaseline --all` followed by `generate` is two explicit commands; if the data is valuable, `reconcile --to-desired` preserves it with a real, audited migration.

## D34: Rebaseline Provenance Is Recorded, Not Executed (Ledger v3)

When a ledger is rebaselined, it records a top-level `rebaselined_from` field containing metadata about the prior ledger: its hash, the ID of its latest revision, a human-readable reason (from `--reason` CLI flag), and `recorded_at` timestamp. This provenance is written at `LEDGER_VERSION = 3` (`READABLE_LEDGER_VERSIONS = {1,2,3}` in code). Provenance is metadata only — it is never replayed as DDL, never converted to migration operations, and never carries secrets or connection details.

**Rationale:** A reset that leaves no trace is indistinguishable from silent data corruption or a tooling bug. Recording the decision keeps "we deliberately reset `R` to `D` at time T for reason X by operator Y" fully auditable and recoverable for investigation. The v3 bump is a clean additive field independent of 016's already-shipped v2 (`adopted`/`adopt_live_schema`). Reading code writes v3, reads any of {1,2,3}, and a ledger lacking `rebaselined_from` is transparently treated as pre-v3 with no behavior change — the field is entirely optional and its absence does not break anything.

---

## See Also

- [Architecture Overview — Decision 8](architecture-overview.md#decision-8-incremental-rdbms-schema-migrations) — Rationale and summary
- [RDBMS Migration API](../../../datrix-common/docs/architecture/migration.md) — Shared module documentation
- [RdbmsMigrationAdapter Protocol](../../../datrix-codegen-common/docs/migration-adapter.md) — Adapter contract
- [CLI Migrations Commands](../../../datrix-cli/docs/commands/migrations.md) — CLI surface
- [Config DSL Reference — RDBMS ID](../reference/config-dsl-reference.md#rdbms-migration-identity) — ConfigDSL `id` field
