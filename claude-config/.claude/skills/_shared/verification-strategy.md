# Verification Strategy — Affected-Only Test Selection

**Purpose:** run the smallest test sweep that is still *sound* for a given change.
Selection is by provable non-impact (dependency closure), never by sampling or
"probably fine". This governs which package suites a gate runs; it does not relax
any other verification a task requires (design-acceptance checks, parity gates,
mypy).

## The cost model (measured 2026-07-28, full suites, wall clock)

| Package | Tests | Wall | | Package | Tests | Wall |
|---|---|---|---|---|---|---|
| datrix-codegen-java | ~1,600 | 5.7 min | | datrix-codegen-typescript | ~4,400 | 1.3 min |
| datrix-codegen-python | ~8,300 | 5.5 min | | datrix-common | ~9,400 | 0.9 min |
| datrix-codegen-azure | ~2,900 | 4.1 min | | datrix-language | ~2,400 | 0.6 min |
| datrix-codegen-dotnet | ~2,800 | 1.7 min | | datrix-codegen-docker | ~1,700 | 0.5 min |
| datrix-cli | ~1,200 | 1.5 min | | others (aws, sql, common², comp., ext.) | | < 0.5 min each |

Full 14-package sweep ≈ **22 min** sequential. An affected-only sweep for a typical
leaf-package change is **seconds to a few minutes**.

**Reading run durations:** in a package run's `index.json`, `duration_seconds` is
wall clock; `test_time_seconds` is the per-test sum across xdist workers (≈ workers ×
wall). Never treat `test_time_seconds` (or, in runs older than 2026-07-28, the then
mislabeled `duration_seconds`) as wall time.

## Tiers

1. **Inner loop (while editing):** targeted tests only —
   `test.ps1 <pkg> -Specific "file1,file2"` (one pytest session) or `test-single.ps1`.
2. **Task / wave gate:** the **affected set** (below) — full suite of every changed
   package plus every package in its reverse-dependency closure. Add
   `mypy.ps1` for each changed package.
3. **Phase boundary / pre-commit:** affected set + the repo-level gates whose surface
   was touched (see "Repo gates"). NOT an unconditional `-All`.
4. **Full `-All` sweep:** only when the affected set already *is* everything
   (a `datrix-common` change), when explicitly requested, or as a scheduled
   background/nightly run. Never as a reflex.

## The affected set

`affected(change) = changed packages ∪ reverse-dependency closure of each`,
where the dependency graph is **actual imports (src AND tests) plus declared
pyproject deps** — pyproject alone under-declares (verified 2026-07-28: several
packages import `datrix_codegen_common` without declaring it).

Reverse-closure table (derived 2026-07-28 — re-derive with the commands below if
packages or imports may have changed):

| Changed package | Also run (closure) |
|---|---|
| datrix-common | **everything** (all 14) |
| datrix-language | all except datrix-common, datrix-extensions (12) |
| datrix-codegen-common | itself + all codegen-*, datrix-cli (11) |
| datrix-codegen-component | itself, dotnet, java, python, cli (5) |
| datrix-codegen-sql | itself, typescript, codegen-common, cli (4) |
| datrix-cli | itself, codegen-java (its tests run the real pipeline via datrix_cli) |
| datrix-codegen-python / -typescript | itself, cli (cli tests import them) |
| datrix-extensions | itself, codegen-aws (aws tests import it) |
| datrix-codegen-aws / -azure / -docker / -dotnet / -java | itself only |
| datrix (examples/, scripts/) | no package suites — repo gates only (below) |

Derivation (run from workspace root, bash):

```bash
# consumers of package X = packages whose src/ or tests/ import X's module name
grep -rlE "^\s*(from|import) datrix_codegen_common" datrix-*/src datrix-*/tests \
  --include="*.py" | cut -d/ -f1 | sort -u
```

Compute the closure transitively (a consumer's consumers are also affected).
When in doubt about an edge, include the package — over-inclusion costs minutes,
under-inclusion costs a missed regression.

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
