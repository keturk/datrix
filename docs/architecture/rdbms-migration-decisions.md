# RDBMS Migration Architectural Decisions

**Last Updated:** June 1, 2026

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

## See Also

- [Architecture Overview — Decision 8](architecture-overview.md#decision-8-incremental-rdbms-schema-migrations) — Rationale and summary
- [RDBMS Migration API](../../../datrix-common/docs/architecture/migration.md) — Shared module documentation
- [RdbmsMigrationAdapter Protocol](../../../datrix-codegen-common/docs/migration-adapter.md) — Adapter contract
- [CLI Migrations Commands](../../../datrix-cli/docs/commands/migrations.md) — CLI surface
- [Config DSL Reference — RDBMS ID](../reference/config-dsl-reference.md#rdbms-migration-identity) — ConfigDSL `id` field
