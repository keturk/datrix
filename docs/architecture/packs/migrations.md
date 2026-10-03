# Pack: RDBMS Migration Contract

**Read when:** you touch schema snapshots, the migration ledger, revisions, `migrations { }` config, a migration adapter (Alembic/MikroORM/SQL), rebaseline, or `commit_migration_state`.
**Not for:** startup readiness of the generated service ([runtime-and-deploy.md](./runtime-and-deploy.md)).
**Core map:** [architecture-cheat-sheet.md](../architecture-cheat-sheet.md)

Incremental, language-neutral, UUID-scoped. State lives under `{app_dir}/.datrix/rdbms-migrations/{rdbms_id}/`: `schema.json` (canonical snapshot) and `ledger.json` (ordered revision chain of database-agnostic operations).

- Every `RdbmsConfig` requires `id: UUID` in ConfigDSL. Revisions are immutable and append-only (`GeneratedFile.retention = "append_only"` protects them from manifest cleanup). Destructive changes are generation errors, with no override.
- State reaches disk only when the whole run succeeds: generators stage commits in the run's `MigrationStateTransaction` (`CodegenContext.migration_state_transaction`) and the last stage, `commit_migration_state`, writes them. A failed, dry, or `--only` run leaves `.datrix/rdbms-migrations/<profile>/` byte-identical.
- `RdbmsMigrationAdapter` protocol in `datrix-codegen-common` (Python/Alembic, TypeScript/MikroORM, SQL are adapters). Shared-owned migrations use `SharedPaths.rdbms_dir`, one apply unit per `rdbms_id`.
- A ledger belongs to the language that sealed it (every revision is one language's rendering, replayed verbatim): a second `--language` against it is refused (`guard_foreign_language_ledger`), naming both remedies (`migrations rebaseline --language`, or no ledger).
- `migrations { enabled; ledger }` per profile, both default on. `ledger = false` runs stateless (fresh baseline every generation, nothing under `.datrix/`); every reference example declares it, and the parity gate fails a run that leaves a ledger behind.

Decision logs: [Decision 8](../architecture-overview.md#decision-8-incremental-rdbms-schema-migrations-adopted), [rdbms-migration-decisions.md](../rdbms-migration-decisions.md).
