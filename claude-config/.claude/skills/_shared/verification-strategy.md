# Verification Strategy — Affected-Only Test Selection

**Purpose:** run the smallest test sweep that is still *sound* for a given change.
Selection is by provable non-impact (dependency closure), never by sampling or
"probably fine". This governs which package suites a gate runs; it does not relax
any other verification a task requires (design-acceptance checks, parity gates,
mypy).

This file is git-tracked in the `datrix` repository via the `d:\datrix\.claude` ->
`d:\datrix\datrix\claude-config\.claude` symlink, so an edit through either path
modifies the same tracked file.

## The cost model — read it from disk, never from a table here

**Wall times are measured per run and drift; do not trust a frozen table.** Read
`duration_seconds` from the package's newest `<pkg>/.test_results/test-results-*/index.json`.
Wall time is also load-sensitive: datrix-codegen-azure produced 26 s / 105 s / 180 s on
2026-07-29 at an identical test count, purely from machine load. A hardcoded cost table
here went stale by up to 10× in both directions within one day of being written.

Snapshot for orientation only (2026-07-29, idle machine, full suites):
typescript **533 s** · python 97 s · java 95 s · dotnet 75 s · common 68 s · azure 26 s ·
language 25 s · cli 25 s · docker 15 s · codegen-common 12 s · aws 11 s · component 10 s ·
sql 8 s · extensions 5 s. Full 14-package sweep ≈ **17 min sequential**, of which
datrix-codegen-typescript alone is **53%** (its cost is subprocess-heavy `npm install` +
`tsc --noEmit` integration tests, not test count). Test *count* predicts wall time poorly:
datrix-common runs 9,433 tests in 68 s; typescript runs 5,033 in 533 s.

**Reading run durations:** in a package run's `index.json`, `duration_seconds` is
wall clock; `test_time_seconds` is the per-test sum across xdist workers (≈ workers ×
wall). Never treat `test_time_seconds` (or, in runs older than 2026-07-28, the then
mislabeled `duration_seconds`) as wall time.

**Suites run sequentially today.** `test.ps1` loops projects in the foreground
(`datrix/scripts/test/test.ps1:529,547-548`), so a multi-package sweep pays the full
sequential sum even though concurrent runs of *different* packages are safe (see Rules).

## Tiers

1. **Inner loop (while editing):** targeted tests only —
   `test.ps1 <pkg> -Specific "file1,file2"` (one pytest session) or `test-single.ps1`.
2. **Task / wave gate:** `affected-gate.ps1 -Projects <changed>` — derives the
   affected set (changed packages + reverse-dependency closure, via
   `affected-set.ps1`'s own closure module) and runs it CONCURRENTLY under a
   worker budget, returning one verdict. Add `-Mypy` to also run `mypy.ps1`
   for each changed package inside the same budget.
3. **Phase boundary / pre-commit:** `affected-gate.ps1 -Projects <all changes
   so far>` + the repo-level gates whose surface was touched (see "Repo
   gates"). NOT an unconditional `-All`.
4. **Full `-All` sweep:** `affected-gate.ps1 -All` — only when explicitly
   requested, or as a scheduled background/nightly run. Never as a reflex, and
   **never as the way to re-verify after a follow-up edit** — re-run only the
   packages whose suites can actually observe that edit. A change touching a
   `datrix-common` *surface* is NOT grounds for `-All`: scope by surface (next
   section), not by package name. Two full sweeps to verify one fix is a defect
   in method.

## The affected set

`affected(change) = changed packages ∪ consumers of the CHANGED SURFACE`, whose
package-level upper bound is the reverse-dependency closure of each changed
package. The dependency graph is **actual imports (src, tests, and each
package's root-level conftest.py) plus declared pyproject deps** — derived
automatically by `affected-set.ps1`
(`d:\datrix\datrix\scripts\test\affected-set.ps1`), never hand-maintained.
Re-run the command below whenever you need a fresh table; do not hand-edit the
rows.

**Scope by surface, not by package.** The unit of impact is the symbol/module you
edited, not the package that contains it. `datrix-common` holds many unrelated
surfaces, and importing the package is not the same as consuming the surface: a
change to the runtime-requirements manifest is observable in azure/aws/docker
(+ cli, which runs the pipeline) and in nothing else, so python/typescript/java/
dotnet/sql/component/extensions are provably unaffected and must not be swept.
Find the real consumers by grepping for the changed symbol, not the package:

```bash
# consumers of a SURFACE = files importing the symbol you actually changed
grep -rlE "(from|import).*(runtime_requirements|PreflightAction)" \
  datrix-*/src datrix-*/tests --include="*.py" | cut -d/ -f1 | sort -u
```

The table below is the **package-level** closure — a fallback upper bound for a
change whose surface genuinely spans a package (a base model every consumer
constructs, a pipeline stage every generator runs). Use the surface grep first;
fall back to the table only when the surface really is that broad.

Reverse-closure table (a dated snapshot of a real run of `affected-set.ps1 -All`,
verified 2026-07-30 — re-run the command below to refresh; do not hand-edit the
rows):

```bash
powershell -File "d:/datrix/datrix/scripts/test/affected-set.ps1" -All
```

| Changed package | Also run (closure upper bound) |
|---|---|
| datrix-common | **everything** (all 14) — **narrow it by surface first** |
| datrix-language | all except datrix-extensions (13) — **incl. datrix-common** |
| datrix-codegen-common | itself + all codegen-*, datrix-cli (12) |
| datrix-codegen-component | itself, dotnet, java, python, cli, **datrix-common** (6) |
| datrix-codegen-sql | itself, typescript, codegen-common, cli (4) |
| datrix-cli | itself, codegen-java, **datrix-common** (3) |
| datrix-extensions | itself, codegen-aws, codegen-component (3) |
| datrix-codegen-docker | itself, **datrix-common** (2) |
| datrix-codegen-python / -typescript | itself, cli (2 each) |
| datrix-codegen-aws / -azure / -dotnet / -java | itself only (1) |
| datrix (examples/, scripts/) | no package suites — repo gates only (below) |

**The datrix-common root-conftest edge (verified 2026-07-29).** datrix-common is a real
*consumer* too, not only a dependency: `datrix-common/conftest.py:18-20` imports
`datrix_cli.pipeline.generation.GenerationPipeline` and `datrix_language.registration`,
and its dev extra installs datrix-language, datrix-codegen-component, and
datrix-codegen-docker (`datrix-common/pyproject.toml:31-33`) because its suite runs the
real pipeline, which discovers installed generator plugins. So a change in language, cli,
component, or docker can break datrix-common's suite — include it in those closures.
A closure derivation that scans only `src/` and `tests/` **misses this edge**: the file is
a package-root `conftest.py`, outside both trees.

Canonical derivation is `affected-set.ps1` (above); the manual method below
documents what it does and remains a fallback.

Derivation (run from workspace root, bash):

```bash
# consumers of package X = packages whose src/, tests/, OR root conftest.py imports X.
# The root conftest.py is NOT under src/ or tests/ — omitting it hides real edges.
grep -rlE "^\s*(from|import) datrix_codegen_common" \
  datrix-*/src datrix-*/tests datrix-*/conftest.py \
  --include="*.py" | cut -d/ -f1 | sort -u
```

Compute the closure transitively (a consumer's consumers are also affected).
When in doubt about an edge, include the package — over-inclusion costs minutes,
under-inclusion costs a missed regression.

## Do not chase finer-grained selection (measured, 2026-07-29)

Package granularity is the floor; per-area or per-module selection inside
`datrix-common` does **not** work, and re-deriving this is wasted effort:

- 86% of datrix-common's LOC (104,620 / 121,677) is ONE import cycle spanning 17
  top-level areas (`datrix_model ↔ config ↔ plugin ↔ generation ↔ transpiler ↔ semantic ↔ …`),
  so every consumer reaches the whole core transitively.
- Replaying all 343 commits that touched `src/datrix_common` in 2026: perfect per-area
  selection still leaves the *median* commit at 12 of 13 consumer suites, and under
  strictly-sound (transitive) selection **97% of commits still require the full sweep**.
- `semantic` is unavoidable for every consumer regardless of imports, because the shared
  testkit runs the analyzer (`datrix_common/testing/parsing.py:16`).
- datrix-codegen-common has the same shape (9-subtree cycle, 70% of its LOC; 99% of its
  196 commits need the full 11-package closure under sound selection).

The lever is making the sweep cheap (concurrency + fixing the dominant suite), not making
the closure smaller.

## Repo gates (cheap, broad nets — use them instead of over-sweeping)

- **`reference-example-parity-gate.ps1`** (~4 min): byte-level manifest of ALL
  examples × all registered languages through the real pipeline. Run it whenever a
  codegen package, codegen-common, language, common, or `datrix/examples` changed.
  For an intended-output-neutral refactor it is *stronger* evidence than consumer
  unit suites; for intended output changes, re-bless deliberately per its docs.
- Other gates only when their surface was touched: `shared-library-gate` /
  `test-tooling-parsing-gate` / `review-library-gate` (datrix/scripts/library),
  `check-docs-conformance` (architecture docs), `check-generated-file-ratchet`
  (GeneratedFile call sites), `type-mapping-completeness` (type registry/mappings),
  `supported-domain-parity-gate` (domain registration), `gendsl-corpus-resolution-gate`
  (genDSL definitions).

## Rules

- The CLAUDE.md **cross-surface impact rule is unchanged**: touching a shared layer
  means passing every consuming package's suite — the closure table above IS that
  consumer list, computed instead of guessed. Affected-only never means "skip a
  consumer".
- Orchestrated runs (task-orchestrator, execute-tasks[-parallel]): per-task agents run
  targeted tests only; the orchestrator's gate runs the affected set once per
  wave/phase. A multi-phase run's first boundary sweeps the affected set of all
  changes so far — not unconditionally ALL packages.
- A failure in any affected-set suite is yours to fix regardless of which package it
  appears in (execution contract §2).
- Different packages' suites may run concurrently (each writes its own
  `.test_results/`; orchestrator gates fire them in one message and read the verdict
  via `gate-verdict.ps1`). Never launch overlapping runs of the SAME package.
