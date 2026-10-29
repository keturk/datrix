# RDBMS Schema Architectural Decisions

**Last Updated:** October 28, 2026

This document records the architectural decisions for the Datrix RDBMS schema, from the earlier migration chains to the schema converge. For API-level documentation see [RDBMS Schema API](../../../datrix-common/docs/architecture/rdbms-schema.md).

**Status:** The revision ledger, migration history, language migration adapters, migration state and drift tooling that D1–D43 built are deleted. D44 states the model in force; each decision carries its own status line.
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

**Status:** In force as amended: the snapshot, diff, change policy and convergence planner are shared (`datrix-rdbms-schema`); no ledger or retention state is kept (D44).

Language generators render target-native artifacts, but snapshot state, diffing, ledger, retention, and safety policy belong to shared Datrix infrastructure in `datrix-common`.

## D2: Migration Revisions Are Immutable Once Generated

**Status:** Retired with the revision files (D44).

Changing an applied revision file is invalid in every migration system that tracks revision identity. Datrix appends new revisions instead of rewriting historical ones.

## D3: Canonical Snapshots Are the Diff Source of Truth

**Status:** In force as amended: the converge diffs the reflected `L` against the freshly built `D` (D44).

Datrix does not parse Python, TypeScript, SQL, or future target migration files to infer prior schema state. Snapshots (`schema.json`) are the canonical generation-time baseline.

## D4: Missing Previous State Is a Hard Error When History Exists

**Status:** Retired with the migration state (D44).

Silent baseline regeneration can create deployed schema drift. Datrix fails with an actionable diagnostic instead.

## D5: Target Tools Are Adapter Details

**Status:** Retired with the adapters (D44).

Alembic, MikroORM, Flyway-style SQL, or future migration tools are adapter choices. They do not define the platform migration lifecycle. Current adapters are Python/Alembic and TypeScript/MikroORM; each further language package ships its own.

## D6: Startup Schema Repair Is Not the Primary Migration System

**Status:** Retired (D44): the deploy's converge is the migration system; no service changes the schema at startup.

Startup drift repair may later be considered as an optional safety net for narrow nullable-add cases, but it cannot replace generated migration history.

## D7: No New Migration DSL

**Status:** In force; there are no snapshot or ledger state files (D44).

The implementation uses existing application DSL and config models as the source of desired RDBMS schema. It does not add a migration DSL. The generated snapshot and ledger files are generator state, not author-written DSL.

## D8: State Lives Under App-Root `.datrix`

**Status:** Retired with the migration state (D44).

`schema.json` and `ledger.json` are stored under `{app_dir}/.datrix/rdbms-migrations/{target}/{rdbms_id}/`, where `app_dir` is the source application folder that owns the `.dtrx` and config inputs and `target` is the concrete deployable profile name (see D35–D38). Migration directories in generated output folders contain target-native migration files only. Changing output folders, resolved database engines, platforms, owner containers, block aliases, or target languages does not reset migration history for the same logical RDBMS block on a given target. **Profile is now load-bearing in the state path** — it is the `target` segment — because one logical block deploys to N independently-wiped databases (one per target); see D35.

## D8a: RDBMS Migration Streams Are UUID + Target Scoped

**Status:** Retired with the migration state (D44); `rdbms_id` stays the block's identity (D16).

A service can have multiple `rdbms` blocks. The `.dcfg` `RdbmsConfig.id` UUID is the logical storage contract identity. The `.dtrx` owner container and block alias are mutable metadata. Migration history is scoped to `(rdbms_id, target)` — the UUID plus the concrete profile name — not to resolved database engine, database name, platform, output folder, owner container, block alias, or target language. The `rdbms_id` remains the stable logical identity across profiles (D16); the `target` dimension partitions one logical block's append-only history into one independent lifetime per deployment environment (D35).

## D9: Language/Adapter Changes Require Explicit Bootstrap for Existing Databases

**Status:** Retired with the adapters (D44).

The canonical Datrix schema revision chain is shared across target languages, profiles, platforms, and RDBMS engines. Runtime migration tools are not shared: Alembic and MikroORM maintain different applied-history tables. When an existing database changes runtime migration tool, Datrix requires explicit generated-output/deployment bootstrap or stamping instead of silently replaying or skipping migrations.

## D10: `schema_hash` Excludes Revision Metadata

**Status:** Retired (D44): a snapshot stores no hash or revision; `compute_schema_hash` is computed on demand.

`schema_hash` is the logical RDBMS schema hash. It excludes `latest_revision` and the `schema_hash` field itself. Ledger `from_schema_hash` and `to_schema_hash` refer to this logical schema hash.

## D11: Canonical Operations Use a Fixed Vocabulary

**Status:** Retired with the ledger (D44).

`ledger.json` stores canonical Datrix migration operations from a fixed database-agnostic vocabulary. It does not store SQL, Alembic operations, MikroORM code, generated filenames, adapter IDs, active profile, platform, or database engine. Unsupported schema diffs fail before rendering.

**Allowed operations:** `create_table`, `add_column`, `alter_column_nullable`, `alter_column_type`, `alter_column_default`, `alter_column_unique`, `add_primary_key`, `add_foreign_key`, `reassert_foreign_key`, `rename_foreign_key`, `add_index`, `rename_index`, `create_enum`, `add_enum_value`, `relabel_enum_value`, `create_cqrs_view_table`, `relocate_schema`, `set_comment` (plus the non-DDL `adopt_live_schema` marker). The diff-change-to-operation mapping is `datrix_rdbms_schema.revision_ledger.CHANGE_KIND_TO_LEDGER_OP`, read by the orchestrator and by drift reconciliation alike.

**Blocked operations:** `drop_table`, `drop_column`, `drop_primary_key`, `drop_foreign_key`, `drop_index`, enum value removal/rename/reorder, `drop_cqrs_view_table`, arbitrary SQL, target-native migration code.

## D12: Offline Generation Does Not Know Database State

**Status:** In force for generation; the deploy reflects the database (D44), so no bootstrap or stamping exists.

Datrix generation does not infer whether a target database is empty or already populated. Database state is external runtime state, not available to normal offline generation: generation writes `D`, and the deploy's schema client reads the database into `L` when it converges.

## D13: Automatic Migrations Are Safe/Additive Only

**Status:** In force as amended: each change's outcome is `convergence_outcome` (D44).

A deploy applies a destructive change only when the operator approves it. The removal of a table, column, index, unique constraint, foreign key or enum type `D` no longer declares, and a type narrowing, need approval: without it the deploy is refused before anything applies, naming each change and the switch, and with it the change runs in the contract phase and the removed object's data goes with it. A check `D`'s rules no longer derive is dropped without approval. Removing or reordering an enum member is never applied. The one override is the deploy's command-line `--approved` switch, and it approves the plan of the one run it is given to, never a later plan; no `.dcfg` value, environment variable or DSL element approves anything, and no list of approved objects exists (`datrix-rdbms-schema/docs/architecture.md` § Convergence outcomes).

## D14: SQL Files Are Not an Implicit Fallback

**Status:** Retired with the adapters (D44).

`datrix-codegen-sql` is an explicit migration adapter, not the default fallback for target languages without native migration tooling. A target language that emits RDBMS-backed services must declare a native migration renderer, an explicit SQL-file apply strategy, or an explicit no-migration/deployment-readiness failure policy.

## D15: Migration State Paths Are Centralized and Stable

**Status:** Retired with the migration state store (D44).

The migration state store was the only code allowed to construct app-level migration state paths. It validates `RdbmsConfig.id` as a UUID and lower-cases it, validates the `target` (concrete profile name) as a filesystem-safe segment, and uses `{target}/{rdbms_id}` as the path segments under `.datrix/rdbms-migrations` (see D35–D37). Language generators and platform generators must call the state store API (`block_dir(rdbms_id, target)`, `load(rdbms_id, target)`) instead of hand-building paths.

## D16: RDBMS UUID Is Required and Stable Across Profiles

**Status:** In force.

Every resolved `RdbmsConfig` must contain an `id` UUID authored in `.dcfg`. Normal code generation does not silently generate missing IDs. Within a resolved profile, IDs are unique across service-owned and shared-owned RDBMS blocks. When the same owner-qualified RDBMS block appears in multiple profiles, it must resolve to the same ID. `load_service_config` and `load_shared_config` enforce this when the config loads: they resolve every profile of the `.dcfg` and reject a block whose ID differs between profiles with `RDBMS_ID_UNSTABLE`, naming the block, the profiles and the IDs. A block absent from some profiles is allowed.

## D17: Shared-Owned RDBMS Migrations Use Shared Generated Output

**Status:** Retired with the adapters and the migration state (D44); D18 states how a shared block's schema is converged.

Shared-owned RDBMS blocks are first-class migration targets. Their adapter-native migration files are generated under the shared block output tree using `SharedPaths.rdbms_dir`, not under a consuming service. The canonical app-level state path is keyed by `(rdbms_id, target)` (see D35) — one shared block has one independent state lifetime per deployment target.

## D18: Shared-Owned RDBMS Migrations Are One Chain Per `rdbms_id`, Applied By One Writer Under One Lock

**Status:** In force; the converge (D44) is the one writer.

A shared container's RDBMS block is one schema per `rdbms_id` (D17), converged once by the deploy's schema client (`converge_schema_blocks`) under one advisory lock the block's dialect derives from the lower-case `rdbms_id` (`SQLDialect.session_lock_sql`; PostgreSQL `hashtext`), so concurrent deploys serialize. The block's chain applier, the first consumer by qualified name holding `readwrite` (`shared_chain_applier`; a block every consumer only reads is SHR014), only names the block's owner. No service migrates and none holds the block's owner login: every consumer, reader or writer, connects as a login of its own that holds data rights and no DDL right. A reader therefore holds a credential that only reads, and a second writer creates no tables whose owner the other roles cannot read. Shared-block seeds run only in a consumer that holds `readwrite` access, inside the same lock; a `readonly` consumer never seeds.

No platform creates a migration init container, job or in-process step for any block, owned or shared, and a service is a consumer only through a resolved `uses` directive -- never by one of its own blocks sharing a `config.id`. The platform fact `run_migrations_at_startup` no longer exists; the one startup fact left is whether the service seeds in its own process (`run_seeds_at_startup`, read through the kernel's `service_runs_startup_seeds_in_process`).

## D19: No Legacy Generated-Output Adoption Path

**Status:** Retired with the migration state (D44).

The rollout updates `.dcfg` files with `RdbmsConfig.id` values and regenerates outputs from scratch. Missing app-level state with existing generated migration history remains a hard error, not an implicit adoption flow.

## D20: No Automatic Rename Inference

**Status:** In force.

Datrix does not infer table, field, enum, or index renames from delete/add pairs. Rename-like diffs are generation errors in automatic migration planning.

## D21: Existing-Table Foreign-Key Additions Are Generation Errors

**Status:** Superseded (D44): the classifier calls the addition `blocked` and `convergence_outcome` applies it as risky; the constraint is validated over the rows and an orphan row fails the apply, naming it.

Generated `add_foreign_key` is allowed only for a table created by the same revision or during the initial baseline. Adding a foreign-key constraint to a table that existed in the previous snapshot is a generation error because offline generation cannot validate existing rows.

## D22: Enum Evolution Is Append-Only

**Status:** In force as amended: a member's stored label may also change (`ENUM_VALUE_RELABELED`, rendered by the kernel); removal and reorder are never applied.

Generated enum migration supports enum creation and safe enum value append only. Enum value removal, rename, reorder, or representation-strategy changes are generation errors.

## D23: A Rollback Is a Deploy of the Earlier Output

**Status:** In force as amended by D44: there are no rollback bodies; a rollback converges the database to the earlier release's `D`.

There is no rollback path and nothing records which release a database last held. Rolling back is deploying the earlier release's generated output, which converges the database to the earlier `D` through the one converge (D44). What the later release added and the earlier `D` does not declare -- its tables, columns, indexes, unique constraints and foreign keys, with their data -- is removed, and a column the later release widened is narrowed back, only when the deploy is run with `--approved`; without it the rollback is refused, naming each object and the switch. `deploy --plan --approved` prints exactly what the rollback would remove before anything runs. The checks the later release derived from its rules are definition-named checks the earlier `D` does not state, and are dropped without approval. Deploying the later output again converges forward, recreating what was removed, empty.

**Rejected: render a reverse script with each release.** It is a second path that has to be kept in step with the converge and is never exercised until it is needed; the converge already computes the reverse from the two sides it reads.

---

## Database Drift Detection & Reconciliation (D24–D29)

The migration engine is purely source-driven: every revision diffs a **recorded** baseline (`schema.json`) against a **desired** snapshot built from the AST. It is blind to the **live** database. When a database is changed out-of-band (manual hotfix, restored backup, partially-applied migration, parallel environment), the recorded baseline `R`, the live schema `L`, and the desired schema `D` silently diverge; the engine plans `R → D` and collides with a database already at `L`. The following decisions add the ability to *see* drift (`diff(R, L)`) and *reconcile* it, without making generation require database access. The load-bearing insight: **a live database is just a third source of an `RdbmsSchemaSnapshot`** — once a live snapshot is produced, the existing diff → classify → allocate → ledger pipeline is reusable unchanged.

## D24: The Live Database Is a Third Snapshot Source; Datrix Never Connects To It

**Status:** Retired (D44): the deploy's schema client reflects the live catalog itself; there is no exporter, artifact or `drift`/`reconcile` command. Generation still opens no database connection.

An environment-side exporter (running where the database is reachable) reflects the live catalog into an `RdbmsSchemaSnapshot` artifact (`live-schema-snapshot.json`). Datrix-side `drift`/`reconcile` commands **import that artifact** and perform all diff/classify/reconcile work offline. Datrix generation and reconciliation never open a database connection, accept a connection string, or handle credentials — those stay in the deployment environment. Drift is `differ.diff(R, L)`; convergence is `differ.diff(L, D)` — no new diff algorithm and no new change taxonomy are introduced.

## D25: Comparison Requires One Shared Canonicalization Layer

**Status:** In force: `canonicalize_snapshot` and `prepare_live_for_comparison` are the layer (D44).

A live catalog and a source AST describe the same schema differently (implicit PK indexes, backing FK indexes, default-literal formatting, type aliases such as `VARCHAR(255)` vs `String(255)`, identifier casing, index column ordering). Both the source-built and the imported live snapshot pass through one shared canonicalization layer before diffing, or drift detection drowns in false positives. Equivalent schemas must canonicalize to zero drift.

## D26: Adopted Revisions Are a Distinct Classification and Ledger Operation

**Status:** Retired with the ledger (D44).

Reconciliation never edits a frozen revision or rewrites the ledger hash chain — it **appends**. Adopting drift introduces a new ledger classification `"adopted"` (not an overloaded `"baseline"` with a `source` marker) and a new explicit non-DDL canonical operation `adopt_live_schema`, and bumps the ledger schema version. An adopted revision records an auditable schema-hash transition ("at revision N we observed reality had drifted to `L` and adopted it"); its operation details are metadata only (`strategy`, `live_snapshot_hash`, `schema_hash_after`) and must not force destructive observed drift (e.g. a dropped column) into canonical DDL operations, which the ledger intentionally rejects.

## D27: Reality Can Be Recorded; Data Loss Cannot Be Generated

**Status:** In force for the converge (D44); there is no adopt operation.

Two operations are not conflated. **Adopt** *records* what the database already is (`R := L`) — documenting an observed drop is stating fact, so it is safe even when the observed drift is destructive; it runs no DDL. **Converge** *generates DDL* to move the database from `L` to `D` and is gated by `change_policy` exactly as source-driven migrations are — `blocked` stays blocked, and no flag suppresses destructive-DDL classification (this honors the existing `change_policy` anti-pattern). Renames are not inferred (inherits D20).

## D28: Live Snapshot Alignment Is Recorded Separately From Adapter Alignment

**Status:** Retired with the live-snapshot artifact (D44).

Reconciliation records that Datrix imported a live snapshot and used it against a canonical revision in a separate file `.datrix/generated-output-state/{rdbms_id}/live-snapshot-alignment.json`, a sibling of the `adapter-alignment.json` precedent (D9) — never overloading it. The record is format/versioned and includes at least `rdbms_id`, `revision`, `schema_hash`, `live_snapshot_hash`, `strategy`, and `recorded_at`. It must not store credentials, connection strings, hostnames, or other deployment secrets.

## D29: Drift Is a Production Guard and a Pre-Prod Reconcile Path

**Status:** Retired (D44): every deploy converges `L` to `D`.

A per-environment policy selector (default off) splits behavior. **Production** treats drift as a guard: export a live snapshot in the target environment, run `detect_drift` offline against it, and refuse (or loudly warn) when `L` ≠ expected — never auto-reconcile. **Pre-prod** gains the reconcile verbs and the recommended loop (fix generator → regenerate → export live snapshot → `drift --live-snapshot` → `reconcile --adopt` or `--to-desired`). The selector controls whether exported live snapshots are required for the guard/reconcile workflow; it never grants Datrix database connectivity. Reflector scope is every registered RDBMS engine (PostgreSQL).

---

## Regime-Aware Migration Lifecycle (D30–D34)

The migration engine treats every database as a persistent, append-only one. That assumption is correct for production databases with real data, but actively harmful for pre-production and ephemeral databases whose schema is still being designed and whose instances are routinely wiped. The following decisions introduce a **regime** distinction: when a database is declared disposable or pre-production, schema changes that would normally block generation can trigger an explicit reset-and-rebaseline operation instead, letting agents move fast without corrupting the desired specification.

## D30: Rebaseline (`R := D`) Is a First-Class, Policy-Gated Operation

**Status:** Retired with the ledger (D44): there is no recorded baseline to reset.

A new `rebaseline` operation explicitly sets the recorded baseline to the desired schema. It runs no DDL, opens no database connection, requires the operator to state that the database is wiped or disposable (`--assume-wiped`), and is **refused in `guard` mode** (a live database's chain is carried forward instead, D43). Rebaseline starts a fresh ledger generation (a new `0001_initial` = `D`) rather than editing any frozen revision, and records `rebaselined_from` provenance containing the prior ledger identity, reason, and timestamp for auditability.

**Rationale:** The wipe-and-redeploy lifecycle has no live schema worth preserving and no persistent migration history to protect. Today's recovery mechanism is a manual, unaudited `rm -rf` of the state directory. Making rebaseline a first-class, gated framework operation replaces that ad-hoc approach with an explicit, audited one that records the decision and the prior state for investigation if needed.

## D31: Generation Is Regime-Aware; the Classifier Is Not Weakened

**Status:** Retired with the drift policy (D44): generation plans no schema change; the deploy's `convergence_outcome` is the one gate.

`generate` resolves the `driftPolicy.mode` for the target block at generation time and dispatches on it at the single `classified.blocked` site in the orchestrator. In `off` and `guard` modes, a blocked diff raises `GenerationError` unchanged. In `reconcile` mode, a blocked diff raises with an actionable message naming both `rebaseline` (wipe regime) and `reconcile --to-desired` (keep regime) as operator choices. In `ephemeral` mode, a blocked diff automatically invokes `rebaseline` (R := D) in-process, logs the action, and continues to render a fresh baseline.

**Rationale:** The `change_policy.classify_diff` classification is the single source of truth for *what* a diff is (baseline / safe / risky / blocked). What changes is the *consequence* of the `blocked` outcome, which is now a regime-dependent dispatch. Safe and risky changes flow through the normal incremental allocate-and-append path in all regimes (no weakening, no early classification shortcuts). This separates "what the change is" (stable, reviewable policy) from "what we do about it in this environment" (regime).

## D32: A Fourth `ephemeral` Mode for Disposable Databases; Blocked-Only Auto-Rebaseline

**Status:** Retired with the drift policy (D44): a profile declaring `driftPolicy` is refused when the config loads.

A new `driftPolicy.mode = "ephemeral"` is added to the configuration model and decision flow. In `ephemeral` mode, auto-rebaseline triggers **only on the `blocked` classification** — the one outcome that breaks generation and requires an explicit decision. Safe and risky diffs continue through the normal incremental allocate-and-append path, identical to `off` mode. Default `driftPolicy.mode` remains `off`; `guard`, `reconcile`, and `ephemeral` semantics are all distinct and explicitly chosen per profile.

**Rationale:** Dev and Docker-local databases are thrown away every run; requiring an explicit `rebaseline` command by hand there is pure friction that slows iteration. Scoping auto-rebaseline to the `blocked` classification keeps the behavior minimal and predictable: additive changes (nullable adds, index adds) still build a clean, replayable incremental chain that applies cleanly to a fresh database, and only an otherwise-fatal destructive block collapses to a fresh `D` baseline. Rebaselining *every* diff would cause unnecessary history churn with no benefit on a database that replays the full chain from empty anyway.

## D33: Pre-Prod Never Auto-Rebaselines; Keep-vs-Wipe Is Operator-Chosen

**Status:** Retired with the ledger and the drift policy (D44).

In `reconcile` mode, generation that would block fails with a message offering exactly two operator choices: `rebaseline` (wipe regime — discard and start from `D`) or `reconcile --to-desired` (keep regime — export live schema `L`, converge with an additive migration from `L → D`). The system does not automatically pick one path over the other.

**Rationale:** Pre-production environments sometimes hold staging data worth keeping to verify a fix (e.g., a full-fidelity test dataset prepared for integration testing). Silently discarding it on the next schema change would be the same class of error as today's silent generation block — the operator lost data without realizing it. By surfacing the choice explicitly and requiring a deliberate action, reconcile mode honors the operator's intent: if the data is disposable, `rebaseline --all` followed by `generate` is two explicit commands; if the data is valuable, `reconcile --to-desired` preserves it with a real, audited migration.

## D34: Rebaseline Provenance Is Recorded, Not Executed (Ledger v3)

**Status:** Retired with the ledger (D44).

When a ledger is rebaselined, it records a top-level `rebaselined_from` field containing metadata about the prior ledger: its hash, the ID of its latest revision, a human-readable reason (from `--reason` CLI flag), and `recorded_at` timestamp. This provenance is written at `LEDGER_VERSION = 3` (`READABLE_LEDGER_VERSIONS = {1,2,3}` in code). Provenance is metadata only — it is never replayed as DDL, never converted to migration operations, and never carries secrets or connection details.

**Rationale:** A reset that leaves no trace is indistinguishable from silent data corruption or a tooling bug. Recording the decision keeps "we deliberately reset `R` to `D` at time T for reason X by operator Y" fully auditable and recoverable for investigation. The v3 bump is a clean additive field independent of 016's already-shipped v2 (`adopted`/`adopt_live_schema`). Reading code writes v3, reads any of {1,2,3}, and a ledger lacking `rebaselined_from` is transparently treated as pre-v3 with no behavior change — the field is entirely optional and its absence does not break anything.

---

## Target-Scoped Migration State (D35–D38)

D8/D8a/D15 keyed app-level migration state by `rdbms_id` alone, on the premise that one `rdbms_id` maps to one database lifetime. That premise holds for single-environment deployments but breaks when one logical block is deployed to multiple, independently-managed databases (e.g. a staging Postgres and an Azure Postgres wiped or preserved on separate schedules). The shared key is harmless for the append-only **keep-additive** path — the ledger is never pruned and each live database tracks its own position in its own `alembic_version` table — but it breaks on **rebaseline** (`R := D`, D30): rebaselining to wipe one environment prunes the shared `revisions/` set that another environment's live database still references, causing that environment's next deploy to fail with *"Can't locate revision."* The following decisions re-key state by `(rdbms_id, target)` so the append-only-per-database-lifetime principle (D30–D34) holds for the multi-target reality.

## D35: Migration State Is Keyed by `(rdbms_id, target)`

**Status:** Retired with the migration state store (D44).

App-level migration state lives at `{app_dir}/.datrix/rdbms-migrations/{target}/{rdbms_id}/`. The unit of append-only history is one *physical database's* lifetime; two deployment targets of the same block are two lifetimes with two independent ledgers and revision sets. Rebaseline is therefore target-scoped: wiping one target prunes only that target's `revisions/` and leaves every other target byte-identical. This supersedes the `rdbms_id`-only key in D8a/D15. Only the *authoring-side* state gains the target dimension — the alembic runtime model is unchanged (each live database already owns its `alembic_version`).

## D36: `target` Is the Concrete Profile Name

**Status:** Retired with the migration state store (D44).

The `target` segment is the **concrete profile name** — the identifier before `as "alias"` in the `.dcfg` `profile <name> as "<alias>"` declaration (e.g. `development`, `test`, `staging`, `production`) — never the short alias. This is the system's existing and only profile-identity convention: config resolution matches profiles by concrete name exclusively (`p.name == name`), raises a hard error on no match, and never matches aliases (aliases populate interpolation context only). The CLI `--profile` value and the orchestrator's resolved profile are both already concrete names threaded through this same resolution, so using the profile directly as the directory segment requires no new canonicalization. **Constraint:** if two profiles ever target the same physical database, they must share a `target` key — out of scope, recorded as a documented limitation.

## D37: Layout Groups by Target, Then Block

**Status:** Retired with the migration state store (D44).

The path is `{target}/{rdbms_id}/`, so wiping or rebaselining a target is a single-directory operation and each lifetime's history is physically isolated. The inverse `{rdbms_id}/{target}/` is rejected: it scatters a target's lifetime across every block directory, turning a wipe into a multi-directory sweep.

## D38: Existing State Is Relocated, Not Regenerated

**Status:** Retired with the migration state store (D44): no migration state exists to key or relocate.

A guarded, idempotent `relocate-state` operation seeds the target-scoped layout from existing shared `{rdbms_id}/` state. It discovers the declared deployable targets by parsing the application's `.dcfg` profiles (not a flag list or hard-coded default), copies each existing block directory into every declared target's slot (copy-not-move until byte-identity is verified, then removes the legacy directory), is idempotent (existing target-scoped state is skipped, not overwritten), and refuses-and-reports any `{rdbms_id}/` directory that maps to no declared target. Regeneration is rejected because it would silently rewrite history; faithful relocation preserves the recorded baseline and is auditable. After the layout change, `load(rdbms_id, target)` raises `MigrationStateUnrelocatedLayoutError` (naming the `relocate-state` command) when it finds legacy-layout state and no target-scoped state — there is no silent fallback to the legacy path.

---

## Boot-Path Readiness and Chain-Owned Schema (D39–D41)

D1–D38 govern what a migration *contains* and how its history is kept. They say nothing about the two moments where a correct migration still fails: the moment the runner first opens a connection, and the moment a revision references a database object that the chain never created. Both were contracts recorded in a docstring or in a neighbouring target's behaviour, with nothing in code comparing the two sides — so both shipped as silent disagreements between artifacts emitted by different packages, invisible to every package's own suite.

## D39: Every Target's Migration Entrypoint Owns a Bounded Readiness Contract

**Status:** Retired with the generated migration runners (D44): the deploy's schema client converges every block.

A migration runner waits for the database to accept connections, over a bounded retry, before running any DDL. This is required on **every** language target and is not discharged by a container health check: a health check is a container-platform mechanism, and a managed relational instance on a cloud platform has none, so per-runner readiness is the only mechanism there.

The bound is **one declaration** — an attempt count and a delay between attempts, living once in the shared codegen layer and consumed by each target's migration renderer. It is not re-spelled per language: two targets independently grew the same two values without either being wrong, which is precisely the drift this rule exists to close, and a third target having no loop at all is what made the omission visible.

**A readiness failure carries the driver's own exception as its cause, and the entrypoint that reports it prints the exception chain.** A connection pool configured not to fail fast surfaces an unreachable database as an opaque timeout with the real error discarded; the operator then sees a pool's stopwatch instead of `Connection refused`, `password authentication failed`, or `database "…" does not exist`. Propagating the cause and printing the chain are a pair — either alone still truncates the diagnosis at the outermost frame. The message a failure names must be built without the credential; it is never "improved" by interpolating a resolved one.

## D40: The Migration Chain Is the Only Schema-Creation Mechanism

**Status:** In force as amended by D44: the deploy's converge is the only schema-creation mechanism.

Schema DDL is emitted into the migration chain and nowhere else. A database container's initialisation directory exists only for a container-hosted database; a managed instance has no such hook, so a target that depended on initialisation-script DDL would work on one platform and fail on every other. This is the same reasoning that makes the migration adapter the sole owner of foreign-key action DDL.

A schema surface emitted outside the chain is therefore not merely redundant, it is unrealizable as a general mechanism, and it is **deleted rather than deprecated** — the standing rule for a config or generated surface no target consumes. Deletion is pinned by a check that the generated initialisation script contains no type-creation statement, so a platform-local schema mechanism cannot return through the one platform that has somewhere to put it.

## D41: Every Type an Emitted Migration References Is Created by That Migration Chain

**Status:** In force as amended by D44: the kernel's `render_schema` and `render_convergence` create every type a statement they render references; there are no revisions or downgrades.

For an emitted revision, the set of non-builtin type names referenced by a column declaration minus the set created by a type-creation statement is **empty**. The comparison is computed by parsing the emitted artifact, not by reading it, so it holds for any type added later rather than for the one that motivated it.

Where a dialect represents an enumeration as a native database type, the baseline creates each distinct type it references **before** the first table that references it, ordered deterministically by type name so the emitted revision is stable across runs, and in an idempotent form so a re-applied baseline against a database that already carries the type does not abort the chain. The corresponding downgrade drops the type **after** the table drops that reference it. Type-creation ordering is a property of the emitted revision, not of the canonical vocabulary: this adds no operation to D11's fixed ledger vocabulary, changes no snapshot or ledger format, and is confined to the adapter whose dialect needs it. The member labels the snapshot already carries are the input; nothing has to be threaded into a shared contract consumed by every adapter.

Two obligations travel with the type. **The language-runtime mapping is registered wherever the emitted service constructs its data source** — creating the type while leaving every query on those columns failing is not a fix, and the mapping must use the same type name and the same label spelling the migration emitted. And **the type name and its labels have one home per language package**: the resolver that puts the type name in a column and the builder that creates the type call one function, and the persisted label literal is a per-language fact with a per-language home, since importing another language package's copy would cross a package boundary to share a convention rather than a contract.

**Labels and type names are DSL-authored text interpolated into SQL**, emitted through the canonical literal-quoting home and as a quoted identifier respectively — never by concatenation. The statement is emitted once into a migration that ships with every generated project and runs with schema-modifying privileges, which is the whole reason this is stated as a rule rather than left to the call site.

**A renderer that meets an operation kind it does not recognise raises.** An operation-dispatch chain with no final branch renders an unrecognised kind as nothing at all — a silently dropped migration step, which is the worst available outcome for an append-only history. The fail-loud branch lands *before* any new operation kind is added to that renderer, never in the same change and never after.

## D42: A Foreign Key Is Created, Named Once, States Both Actions, and Is Replaced When Its Actions Drift

**Status:** In force as amended by D44 and by the differ owning every comparison of `L` with `D`: a key whose actions changed is replaced (`FOREIGN_KEY_REPLACED`: dropped under exactly the name `L` holds it by, then `D`'s key added under `D`'s name, validated, in the expand phase), and a key `L` holds under another name with the same actions is renamed (`FOREIGN_KEY_RENAMED`); both are reported by `compute_snapshot_diff`, never once for every key.

Every foreign-key constraint is named by one function (`fk_<table>_<columns>`, `datrix_rdbms_schema.foreign_key_naming`), and the snapshot records the realized name, so a drop or re-assertion targets what the database holds. Every baseline creates every key the snapshot records, an entity added later gets its keys in the same revision, and every constraint states `ON DELETE` and `ON UPDATE` from the DSL (default `restrict`) through the one shared keyword spelling -- a constraint with no clause means `NO ACTION`, which is neither the default nor anything an author declared. Referential integrity is therefore enforced on every database a Datrix adapter builds; a Python baseline once created none.

An action is part of the constraint a database enforces, so a change to `onDelete`/`onUpdate` on an existing key is a change (`FOREIGN_KEY_REPLACED`), where the differ used to alter the schema hash and plan nothing. The change carries `D`'s key as its subject and the name `L` holds as `old_value`, so exactly that name is dropped and the key added under the shared name. On PostgreSQL the new constraint is added `NOT VALID` and then validated. A row with no parent fails the revision, naming the constraint; no row is deleted to make it pass. Replacement is classified `risky`, never blocked (it moves and loses no row) -- D21 is unchanged: a *new* key on an existing table is still a generation error.

A relationship change is matched to its constraint by the full (columns, referred table, referred columns) tuple, never by the table alone: an entity with a `createdBy` and an `updatedBy` user holds two keys to one table.

**Rejected: reflect the deployed catalog at generation time to find drifted keys.** The generator has no database connection; the deploy's converge reads the live catalog instead (D44), and the differ replaces exactly the keys whose actions differ.

## D43: A Live Database's Unreadable Chain Is Carried Forward (`R := R`), Never Reset on an Assumption

**Status:** Retired with the ledger (D44): there is no recorded chain to carry or reset.

A chain holding revisions recorded before the ledger recorded the statements each one runs cannot be audited, so generation refuses it. Resetting it (D30, `R := D`) is honest only for a database that is gone or disposable, and the command cannot verify that, so a reset requires the operator to state it (`--assume-wiped`). A long-lived database gets a second operation instead: `rebaseline --rdbms-id <id> --live-snapshot <file>` carries the chain forward. The exported live schema must equal the recorded schema `R`; the new baseline builds exactly `R` under a fresh id; and the ledger (v6) records `rebaselined_from.carried_revision`, the chain's last revision with a revision file — the retired id that database's migration runner records. Each language's generated runner moves a history whose latest recorded revision is the carried one onto the baseline under the apply lock, without DDL; any other history of retired ids stays refused. A fresh database runs the baseline as usual.

Because it resets nothing — the database keeps every object, and the recorded schema is unchanged — the carry-forward is permitted in every drift mode, `guard` included; D30's guard refusal applies to the reset alone. A live schema that differs from `R` is refused: the drift is reconciled first (D27), then the chain is carried.

**Rejected: let `reconcile --to-desired` describe the old chain.** It appends a revision on top of the unreadable one; the records below it stay undescribed and the audit still refuses.

**Rejected: assume the database is wiped.** Recording a baseline no database ran leaves the history describing DDL the database never executed, which the next incremental revision builds on.

---

## D44: Every Deploy Converges the Live Catalog to the Declared Schema; No History Is Kept

Generation builds the desired snapshot `D` (`schema.json`) fresh on every run and writes it into each block's schema tool. The deploy's schema client reflects the live catalog into `L`, prepares it for comparison (`prepare_live_for_comparison`: enums aligned with `D`, `L` given `D`'s member values wherever a label matches, its identity fields taken from `D`), and converges it: `convergence_changes(L, D, approved, facts)` builds the changes, `convergence_outcome` puts each in one outcome (applied safe, applied risky, needs approval, never applied), and the kernel renders the applied ones (`render_convergence`; an empty database gets `render_schema`). No revision ledger, revision files, recorded baseline, migration state, drift policy or live-snapshot artifact exists, and no generator writes migration state.

An object `L` holds and `D` does not declare is an undeclared object (`undeclared_object_changes`); `removal_outcomes` refuses its removal until the deploy is run with `--approved`, except a definition-named check and a Datrix trigger whose declaration was removed, which are dropped without it. A refused change stops the deploy before anything applies, so a database holding objects an earlier release declared -- the tables an older migration runner kept its history in among them -- is converged only once the operator has read the refusals and approved the drop. A rollback is a deploy of the earlier output, converged the same way (D23).

One snapshot format is read: `SCHEMA_VERSION`. A snapshot of any other format or version is refused, naming both and telling the user to regenerate it; nothing is kept for snapshots recorded under older rules, and the differ compares every field on every call. A snapshot stores no hash: `compute_schema_hash` is computed on demand.

---

## See Also

- [Architecture Overview — Decision 8](architecture-overview.md#decision-8-incremental-rdbms-schema-migrations-adopted) — Rationale and summary
- [Architecture Overview — Decision 45](architecture-overview.md#decision-45-a-generated-service-must-be-able-to-reach-its-database--probe-transport-migration-readiness-and-chain-owned-schema-approved--implementation-in-progress) — Boot-path contracts these decisions detail
- [RDBMS Schema API](../../../datrix-common/docs/architecture/rdbms-schema.md) — Shared module documentation
- [Config Document Reference — RDBMS ID](../reference/dcfg-reference.md#rdbms-migration-identity) — `.dcfg` `id` field
