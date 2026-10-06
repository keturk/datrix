# Quick Reference — Ratchet Gates

Gates that pin a count and let it only move one way (or both ways only together with its pin):
generated-file construction sites, out-of-table dependency decisions, capability gaps, slow tests,
and the migration upgrade-op family. Repo-level validation **scripts**, not pytest suites.

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../../quick-reference.md](../../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `gates\ratchet\check-generated-file-ratchet.ps1`

GenDSL ratchet: AST-counts direct `GeneratedFile(...)` constructor calls per `datrix-*` package's `src/` tree and fails if any package's count exceeds its frozen baseline at `scripts/config/generated-file-ratchet.json`. Every emitted file should eventually be declared in genDSL rather than hand-constructed; this ratchet freezes the current count per package and only ever allows it to shrink as later migrations convert hand-coded construction into genDSL declarations. It follows the same AST-scan-and-ratchet shape as `scan\check-import-boundaries.ps1`'s ratchets.

| Mode | Command | Description |
|------|---------|-------------|
| **Run ratchet** | `.\gates\ratchet\check-generated-file-ratchet.ps1` | Scan all packages, fail on regressions |
| **Warning mode** | `.\gates\ratchet\check-generated-file-ratchet.ps1 -Warn` | Report regressions but exit 0 |
| **Show files** | `.\gates\ratchet\check-generated-file-ratchet.ps1 -ShowFiles` | Print each file being scanned |
| **Freeze/tighten baseline** | `.\gates\ratchet\check-generated-file-ratchet.ps1 -UpdateBaseline` | Recompute counts and write the baseline (bootstrap freeze if none exists yet; otherwise only accepts decreases) |
| **Self-test only** | `.\gates\ratchet\check-generated-file-ratchet.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite; skip the real package scan |
| **Custom base dir** | `.\gates\ratchet\check-generated-file-ratchet.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\gates\ratchet\check-generated-file-ratchet.ps1 -Dbg` | Debug logging |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-UpdateBaseline`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements) covers `count_generated_file_constructions`, `discover_packages`, `scan_package`, and `check_ratchet` edge cases -- including the adversarial "regression when above baseline" case, which must produce a message. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation and skips the real scan. `--harness-self-test` (no `.ps1` switch -- diagnostic only) registers one intentionally-failing dummy check to prove the `[OK]`/`[FAIL]` harness itself is not vacuous.

**Assertions:**
- Direct `GeneratedFile(...)` constructor calls (bare or module-qualified) are counted per package's `src/` tree; `GeneratedFile.from_content(...)` is never counted (a distinct call shape).
- `tests/` directories are never scanned (structural: only `src/` is walked).
- `datrix-codegen-kernel/src/datrix_codegen_kernel/gendsl/executor.py` is excluded (the declared-render path's own internals).
- A package absent from the baseline has an implicit baseline of 0.

**Exit codes:** 0 = every package's count is at or below its frozen baseline (or a successful `-UpdateBaseline` or `-SelfTest`), 1 = a package's count exceeds its frozen baseline (or `-SelfTest`/`--harness-self-test` reports a failing check), 2 = usage error, missing baseline, an attempted baseline increase over an existing baseline, or the automatic self-test step failing on a normal invocation.

---

## `gates\ratchet\dependency-declaration-ratchet-gate.ps1`

Dependency-declaration-only-path ratchet (declarations are the only emission path): a per-language CENSUS of every dependency-**SET** decision site in a registered language that decides dependency package NAMES outside that language's own `<language package>/generation/dependency_tables.py` table -- the completeness proof for the declared-table migration: a language's migration is done when this scan reports ZERO out-of-table sites for that language, never when a hand-written list is exhausted. Target derivation is pure runtime discovery via the installed `datrix.languages` entry points -- never a hardcoded language list -- so a fifth `datrix-codegen-<lang>` package is covered automatically with no edit here. **A language is every package implementing it:** the backend registering its entry point plus each `<backend>-core` distribution the backend requires (derived from the installed requirements by `datrix_testing.target_distributions`); every package's `src/` and `templates/` trees are scanned, against the UNION of their `defaults.yaml` catalogs, so a decision site that moved into a core (which ships no catalog of its own) is still matched against the backend's. A registered language with no `defaults.yaml` at all declares an empty dependency-catalog universe, which is a legitimate zero-site result, not an error.

**The counted unit is a decision SITE, not a bare catalog-name-shaped literal anywhere in the tree.** An earlier version of this scanner flagged any string literal equal to a registered catalog package name, anywhere under `src/` and `templates/`; that over-matched by roughly two orders of magnitude (a cache-ENGINE identifier constant, an import-deduplication helper's module-name constants, and a code template's own `import <pkg>` statement all happen to share a spelling with a real package name without ever deciding a manifest's dependency set) and could never structurally reach zero for a migrated language. Two structural detection passes, neither a text regex over raw source:
- **Python source.** AST-walks every `.py` file under the language's `src/` tree for string-literal `ast.Constant` nodes whose value is a member of that language's registered `DependencyCatalog` package universe (read from the language's own `defaults.yaml`) -- but ONLY when the literal sits inside (a) a `get_dependencies`/`get_npm_dependencies`/`get_nuget_dependencies`/`_collect_*_deps`-shaped function at any nesting depth, or (b) a module-TOP-LEVEL (never class- or function-nested) assignment shaped the same way (e.g. `ENGINE_PACKAGE_NAMES`, `EMAIL_COORDINATES`). Both shapes are recognized by a documented whole-snake_case-token naming vocabulary (`_DEPENDENCY_DECISION_NAME_TOKENS` in the runner module: `dependency`/`dependencies`/`deps`/`package`/`packages`/`coordinate`/`coordinates`), matched as whole tokens, never a substring search or a hardcoded function-name allowlist.
- **Jinja templates.** Parses every `.j2` file under the language's `templates/` tree into its Jinja AST and takes the `nodes.Const` literals that DECIDE a dependency -- a version-map subscript key (the `'pkg'` of `v['pkg']`), the needle of a membership test against a decision-named collection (`'pkg' in deps`), or a literal assigned to a decision-named variable (`{% set npm_deps = [...] %}`) -- for the same catalog-membership match: the structural analogue of the Python pass's decision-span gating. A literal in any other expression position decides nothing and is not counted (a controller template's `qp.pipe == 'uuid'` compares a query parameter's pipe kind that happens to spell a package name). Raw `TemplateData` (a template's literal rendered-output text between tags) is deliberately NOT scanned by containment: it degrades to a text search over a template's entire output, including plain generated code and even doc comments, which is not a dependency-set decision.

This is a naming-shape heuristic, not an exhaustive semantic analysis: under-reporting a genuine decision site named entirely outside the token vocabulary is a known, accepted, documented limitation (extend the vocabulary in the runner module if one is found), preferred over a hardcoded per-function allowlist that would drift silently out of sync with the code it polices.

**This is a REPORT with a decrease-only out-of-table-count baseline, not a check that identifies WHICH package a site decides to require** -- only WHETHER a site decides one at all, outside the one place it is allowed to. A single conceptual site (e.g. the same literal appearing as both a dict key and a sibling function argument on one line) collapses to one `(file, line, literal)` entry, never double-counted.

**A literal passed straight to `DependencyQualifier(...)` is never counted:** it is a qualifier value (an engine or vendor on one axis) selecting rows of the declared table -- the declaration-only path itself -- even when the engine shares a package's spelling (the `redis` engine and the `redis` package).

**Every `.j2` file must parse.** There is no exemption list: a `.j2` file that fails to parse fails the scan loud (a genuine template syntax error is a scan error, never a silently skipped file); a template that parses but references an undefined Jinja global is unaffected (`Environment().parse()` only needs syntactic validity, not a rendering context). The gate names no target and carries no per-language data (its self-test proves that first with `datrix_scripts.registered_targets.self_test_gate_names_no_target`).

**Built-in non-vacuity self-test, every invocation.** Before any real scan is trusted, the script builds a synthetic two-language package tree under a temp directory and proves: it finds exactly the two planted out-of-table sites; a non-qualifying decoy referencing the same planted literal (mirroring the real `resolve_*_engine`/`SUPPORTED_*_ENGINES` false-positive shape) adds no second site -- the narrowing itself; moving one planted literal into a synthetic `<language package>/generation/dependency_tables.py` drops the combined count by exactly one; a synthetic Jinja template's planted literal is detected by the template pass independently of the Python-source pass; the template pass counts a membership test against a decision-named collection and a decision-named `set`, and not an equality test against an unrelated attribute spelling the same name; a fixture language split into a backend and a core has a decision site planted in the core found against the backend's catalog, and missed by a backend-only scan; against the LIVE tree (not synthetic), every registered language's catalog contains every package its declared table names, a real declared name planted into a decision site is reported against that live catalog, and, for every registered language, every reported site is a catalog literal the earlier, over-broad matcher also finds while at least one real catalog literal it finds is excluded (derived from the live tree, never a pinned coordinate); a catalog name passed to `DependencyQualifier(...)` is not counted while a bare literal of the same name in the same function is; and the minimum-language guard refuses a single-language set with exit code 2, never a silent pass. Fails loud (exit 2) if fewer than two languages are registered -- a per-language census over fewer than two languages is vacuous.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the report** | `.\gates\ratchet\dependency-declaration-ratchet-gate.ps1` | Full scan over every registered language, checked against the ratchet baseline |
| **Debug** | `.\gates\ratchet\dependency-declaration-ratchet-gate.ps1 -Dbg` | Debug logging (also lists every out-of-table site found) |
| **Self-test only** | `.\gates\ratchet\dependency-declaration-ratchet-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Freeze/tighten baseline** | `.\gates\ratchet\dependency-declaration-ratchet-gate.ps1 -UpdateBaseline` | Write the live out-of-table count as the new baseline |

**Parameters:** `-Dbg`, `-SelfTest`, `-UpdateBaseline`

**Baseline:** `scripts/config/dependency-declaration-ratchet-baseline.json` -- a decrease-only ratchet on the out-of-table site count, summed across every registered language (a live count HIGHER than the recorded value fails; a decrease never fails). `-UpdateBaseline` is the only writer; do not hand-guess the number.

**Exit codes:** 0 = the report ran and the out-of-table count is at or below the baseline (or a successful `-SelfTest`/`-UpdateBaseline`), 1 = the out-of-table count exceeds the baseline, 2 = the non-vacuity self-test failed, fewer than 2 languages are registered, or a discovery/parse error occurred.

---

## `gates\ratchet\migration-upgrade-op-family-gate.ps1`

Migration upgrade-op family gate: the cross-package half of the upgrade-op duplication census. Six `_build_upgrade_op_for_*` symbols exist once per migration target that carries the family (today python's Alembic migration generator); the census read their bodies and concluded they are genuinely target-specific, so **every private copy must survive** — a later "cleanup" deleting one would be deleting a target's real behaviour. One genuinely shared fact WAS hoisted: the targets reassembled the `INDEX_ADDED` JSON detail into its `SnapshotIndex` with byte-identical semantics and error text, so that parse now lives once in `datrix_codegen_common.algorithms.migration_upgrade_op_index`, each target calls it the exact number of times its own paths need, and none may redefine it. Structural resolution only, never a text match. The gate names no target: every registered `datrix.languages` package (its backend and each language core) is scanned, and the per-language facts live in `scripts/config/migration-upgrade-op-family-baseline.json` -- `carries_divergent_family` and the exact `shared_parser_call_sites` count, hand-authored and reviewed. A language with no entry is held to no family and zero calls, so adding a language needs no edit while it uses neither. A unit test importing several generator packages to compare their bodies is the shape the repo boundary forbids outright; the shared parser's own input/output behaviour stays as a unit test in `datrix-codegen-common`, which owns the function.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\ratchet\migration-upgrade-op-family-gate.ps1` | Run every cross-package check in this family |
| **Debug** | `.\gates\ratchet\migration-upgrade-op-family-gate.ps1 -Dbg` | Debug logging (names each self-test check as it passes) |
| **Self-test only** | `.\gates\ratchet\migration-upgrade-op-family-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Each of the six target-specific symbols is still defined exactly once per recorded carrier; a language not recorded as a carrier that defines any of them fails until it is recorded; a baseline recording no carrier fails as vacuous.
- Each registered language has exactly its recorded number of resolved call sites for `parse_index_added_detail` (a count, not a `>= 1`: a path silently losing its call is the regression this pins, and a new path is reviewed and recorded in the same change), and no language defines `parse_index_added_detail` or the retired `_index_from_index_added_detail`.
- A baseline entry naming a language that is not registered is stale and fails.
- Non-vacuity self-test (every invocation): the gate names no registered target (`datrix_scripts.registered_targets.self_test_gate_names_no_target`); the baseline comparison passes a matching fixture tree and reports exactly one problem per divergence (wrong count, missing family member, unrecorded carrier, stale entry, no carrier), and the loader refuses a malformed entry; the resolver finds a planted direct call, follows a `from … import … as …` alias, and finds a module-qualified `alias.symbol(...)` call; and it does NOT count a same-suffix private wrapper (`_parse_index_added_detail`) or a bare docstring/string mention — both false-positive shapes this chain has been bitten by. The definition scan is proven in both directions too: it finds a planted definition and invents none.

**Exit codes:** 0 = every check holds (or a successful `-SelfTest`), 1 = at least one violation, 2 = the self-test failed, a registered language's package cannot be resolved, or the baseline is missing/malformed.

---

## `gates\ratchet\capability-gap-ledger-gate.ps1`

Capability gap ledger gate. Every target package carries its own gaps as `capability_gaps` rows on its own capability declaration; the declarations ARE the ledger (no separate file). The gate censuses those rows from the live declarations of every registered language, client target and platform, prints the row count, enforces a decrease-only two-directional pin on the total and per-target split (`scripts/config/capability-gap-baseline.toml`), and fails a surface that EVERY distinct implementation of an axis carries a row for (a defect in the shared layer, never a per-target gap: a builtin group obligated on the wrong axis, a config surface with no consumer, or an obligation that should not exist). A row suppresses nothing in any other gate; this gate only counts and bounds the ledger.

The pin fails in both directions: live above a pin (a gap was added), live below a pin (rows removed without lowering the pin in the same change), and a row on a target absent from the pin (pinned at zero). The baseline's `total` must equal the sum of its per-target counts.

Derives its target sets from the installed `datrix.languages`, `datrix.generators` (client targets) and `datrix.platforms` entry points at runtime -- never a hardcoded target literal. Registered names sharing one on-disk package fold into one implementation, so the floor and the shared-layer comparison count distinct implementations.

**Built-in non-vacuity self-test, every invocation.** Plants an over-count, an under-count, a per-target split skew, an unpinned row, a synthetic 2-target axis sharing a surface, folded-implementation cases, the two-implementation floor, malformed baselines and a clean matching case. Fails loud (exit 2) if an axis has fewer than 2 distinct implementations or the baseline is unreadable.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\ratchet\capability-gap-ledger-gate.ps1` | Census every registered target's gap rows and apply the pin and the shared-layer check |
| **Debug** | `.\gates\ratchet\capability-gap-ledger-gate.ps1 -Dbg` | Print every censused row (target, surface, detail) and the total |
| **Self-test only** | `.\gates\ratchet\capability-gap-ledger-gate.ps1 -SelfTest` | Run only the non-vacuity self-test |
| **Alternate pin** | `.\gates\ratchet\capability-gap-ledger-gate.ps1 -BaselinePath <file.toml>` | Compare against another baseline file (proves a raised or lowered pin fails) |

**Parameters:** `-Dbg`, `-SelfTest`, `-BaselinePath`

**Exit codes:** 0 = ledger equals the pin and no surface is carried by every implementation, 1 = a ratchet violation (either direction) or a shared-layer defect, 2 = self-test failed, fewer than 2 distinct implementations on an axis, or the baseline is unreadable or invalid.

---

## `gates\ratchet\slow-test-ratchet-gate.ps1`

**The repo's decrease-only ceiling on test wall time.** Reads the newest FULL run's merged
`timings.json` (written by `datrix_scripts.runner_plugin`, merged by the shared test
runner) for every testable package -- discovered the same way `test.ps1`/`status-tests.ps1` do,
never a hardcoded list -- and fails on:

- **A call ceiling:** any test whose call-phase duration exceeds 30.0s (strict -- 30.0s itself is
  not an offender, 30.1s is).
- **A fixture-replication ceiling:** any session/package/module-scoped fixture set up on more than
  one DISTINCT xdist worker (keyed by the recorded worker id, never by occurrence count -- a
  module-scoped fixture set up twice on the SAME worker is not replication) with a setup duration
  exceeding 5.0s on at least one of those workers (strict -- 5.0s itself is not an offender, 5.1s
  is).

...unless the offending id is listed in `datrix/scripts/config/slow-test-baseline.json` with a
`class` (one of `matrix-in-one-test`, `session-fixture-per-worker`, `whole-corpus-scan`,
`toolchain-compile`) and a written `reason`. A Node package (`datrix-vscode`) carries no
runner_plugin/timings.json -- its merged JUnit XML's own per-`<testcase>` `time` attribute is the
only call-duration signal, so it has no fixture dimension at all.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\ratchet\slow-test-ratchet-gate.ps1` | Check every package's newest full run against the baseline |
| **Self-test** | `.\gates\ratchet\slow-test-ratchet-gate.ps1 -SelfTest` | Prove the detector is non-vacuous, skip the real scan |
| **Seed the baseline** | `.\gates\ratchet\slow-test-ratchet-gate.ps1 -Seed` | Write the baseline from the current offenders (placeholder `class`/`reason` -- hand-edit every entry before commit) |

**Parameters:** `-SelfTest`, `-Seed`, `-Dbg`

**Decrease-only, enforced in every mode against git, not just the working-tree file.** Both check
mode and `-Seed` compare against the baseline **as committed at HEAD** in the `datrix` package's
own git repository (`git -C <repo> show HEAD:scripts/config/slow-test-baseline.json`), never
merely against the file on disk: a key may never be added and a `seconds` value may never
increase relative to what HEAD carries. A path absent at HEAD reads as an empty baseline (first
seed, allowed). Any other git failure fails closed (exit 2) -- decrease-only cannot be verified
without a trustworthy committed reference.

**A stale entry fails the gate.** A baseline entry that no longer measures as an offender must be
REMOVED, never left as harmless cover -- except a `toolchain-compile` entry, which this gate never
drives to zero and is permanently exempt from the staleness check. A baseline entry whose `class`
or `reason` still carries the `-Seed` placeholder (`REPLACE-WITH-REAL-CLASS`/
`REPLACE-WITH-REAL-REASON`) is rejected outright (exit 2) -- it was never hand-classified.

**Fails closed on missing data.** A package with no v2 full run (`index.json` `schema_version >= 2`
and `selection.kind == "full"`) recorded at all -- including a Node package whose `.test_results`
exists but never produced a usable full run -- is reported under `missing_full_run` rather than
silently passing.

**Exit codes:** 0 = no un-baselined offender and no stale entry, 1 = an offender, a stale entry, a
missing full run, or a working-tree baseline that grew relative to HEAD, 2 = an invalid baseline,
an untrusted git read, or `-Seed` would grow the baseline committed at HEAD.
