# Verification Strategy — Affected-Only Test Selection

**Purpose:** run the smallest test sweep that is still *sound* for a given change.
Selection is by provable non-impact (dependency closure), never by sampling or
"probably fine". This governs which package suites a gate runs; it does not relax
any other verification a task requires (design-acceptance checks, parity gates).
Type-checking is **not** part of any tier: never run `mypy` or any standalone
type-checker. `guard-forbidden-commands.py` enforces this — the binaries, the
`python -m mypy` form, `test\mypy.ps1`, `library/mypy.py` and
`affected-gate.ps1 -Mypy` are all refused from an agent tool call.

This file is git-tracked in the `datrix` repository via the `d:\datrix\.claude` ->
`d:\datrix\datrix\claude-config\.claude` symlink, so an edit through either path
modifies the same tracked file.

## The cost model — read it from disk, never from a table here

**Wall times are measured per run and drift; do not trust a frozen table.** Read
`duration_seconds` from the package's newest `<pkg>/.test_results/test-results-*/index.json`.
Wall time is also load-sensitive: datrix-codegen-azure produced 26 s / 105 s / 180 s on
2026-07-29 at an identical test count, purely from machine load. A hardcoded cost table
here went stale by up to 10× in both directions within one day of being written.

Snapshot for orientation only (2026-09-23, median over every full run recorded
2026-09-11 → 09-23, 12 logical cores): python **1,185 s** · codegen-common 518 s (one full
run) · typescript 464 s · dotnet 377 s · azure 325 s · java 232 s · aws 230 s · common 205 s · cli 152 s ·
docker 131 s · language 104 s · angular 87 s · component 71 s · sql 69 s · vscode 27 s ·
extensions 6 s. Sum of medians ≈ **70 min sequential**; the concurrent `affected-gate.ps1`
run of 2026-09-18 over 14 packages took ≈ 35 min, with datrix-codegen-python its tail.
The CPU the tests themselves consume is ≈ 12,000–13,000 CPU-s once xdist contention is
deflated (datrix-codegen-python used 4,478 CPU-s at 4 workers and 7,589 CPU-s at 12 for the
same suite), a lower bound of ≈ 17–18 min on 12 cores. The same suite ranged 680 s–2,150 s
wall across runs at one test count, so load, not code, sets most of the spread. Test *count*
still predicts wall time poorly: datrix-common runs 11,634 tests in 139 s.

**A worker's first test carries one-time per-process costs.** In the 2026-09-23 runs of
datrix-codegen-{sql,component,docker,angular,dotnet,java}, each xdist worker's first test took
43–72 s while the median of every other test on that worker was under 0.5 s — the lazy
first-use cost of plugin discovery inside the first generation, paid once per worker. Read
per-test timings with that in mind: a slow *first* test says nothing about that test.

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
   worker budget, returning one verdict. Never pass `-Mypy` — type-checking is
   not part of regular verification, and the harness refuses the switch.
3. **Phase boundary / pre-commit:** `affected-gate.ps1 -Projects <all changes
   so far>` + the repo-level gates whose surface was touched (see "Repo
   gates"). NOT an unconditional `-All`. Re-verification after a follow-up edit
   is the gate over the SAME set — never a second full sweep; an unchanged cone
   comes back `CARRIED` at near-zero cost, so repeating the gate is cheap by
   construction, not merely permitted.
4. **Full `-All` sweep:** `affected-gate.ps1 -All` — only when explicitly
   requested, or as a scheduled background/nightly run. Never as a reflex, and
   **never as the way to re-verify after a follow-up edit** — re-run only the
   packages whose suites can actually observe that edit. A change touching a
   `datrix-common` *surface* is NOT grounds for `-All`: scope by surface (next
   section), not by package name. Two full sweeps to verify one fix is a defect
   in method. Even a scheduled `-All` sweep benefits from carry: a package whose
   fingerprint has not moved since its last green full run comes back `CARRIED`
   with no child launched, so a nightly `-All` costs only what actually changed
   (`-NoCarry` runs every package regardless, for a flakiness hunt).

**One door, two roles.** `affected-gate.ps1` is the only whole-suite entry point:
tiers 2–4 never name a bare `test.ps1` package run, a tier switch such as `-Fast`,
or one `test.ps1` per package fired by hand. The gate derives the closure, carries
each package whose newest green full run (under 24 h old) still matches its
suite-input fingerprint (verdict `CARRIED`, no child launched, pinned to that
run), runs the rest concurrently under a worker budget, and appends one
completion row (`ran`, `carried`, `overall`) to `D:\datrix\.tmp\full-suite-audit.jsonl`.
Tiers 2–4 are **main-session** acts: write `D:\datrix\.tmp\full-suite-ticket.json`
first (`{"packages": [...every package passed to -Projects, or "*" for -All],
"reason": "<at least 10 characters>", "granted_by": "orchestrator" | "jon",
"expires_epoch": <now + at most 6h>}`), because `guard-full-suite-runs.py` blocks
the gate without it. A **dispatched subagent** runs tier 1 only, reports the
packages it changed, and never runs the gate — the guard blocks it
unconditionally; the dispatcher runs the gate once over the union.

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
- **Execution-based selection fails the same way (measured 2026-09-23).** Recording every
  code object entered (`sys.monitoring` `PY_START`) during real pipeline runs: one
  generation executes 38–48% of datrix-common's 615 source files (`01-foundation` →
  python 237, → typescript 232; `cqrs` → python 294, → java 280) and 22–42% of
  datrix-codegen-common's 423. Of the 150 commits to `datrix-common/src` since 2026-07-01,
  **121 (81%) touched a file every pipeline-running test executes** — and those tests are
  where the suite time is (datrix-codegen-python `tests/integration/{generators,service}`
  alone is 1,492 of 7,589 CPU-s). Per-test selection would leave the first sweep after a
  shared change essentially intact. The recording itself costs ≈ 3%, which makes it useful
  for fingerprinting a whole suite's inputs, not for selecting inside one.

The lever is making the sweep cheap (concurrency, removing waste inside each suite, and never
buying the same suite twice for unchanged inputs), not making the closure smaller.

## Repo gates (cheap, broad nets — use them instead of over-sweeping)

Static scans (`dev/semgrep.ps1`, `dev/libcst.ps1`, `dev/check-import-boundaries.ps1`,
`dev/check-debug-artifacts.ps1`, `dev/check-docs.ps1`) sit BELOW every tier above in cost and ABOVE
them in speed — run the ones whose surface you touched before reaching for a suite, never after.
Execution contract §12.5 holds the surface→check table.

- **There is no stored-baseline output gate and no bless step.** The repo keeps no
  snapshot of generated output (`datrix/docs/architecture/generated-output-stability.md`).
  An "output-neutral" or "byte-identical" claim is proven by a test in the owning package
  that renders the construct for a fixture and asserts its output, plus the affected
  closure's suites — never by a corpus hash and never by re-recording a baseline.
- **`artifact-role-parity-gate.ps1`** (seconds, reads only): cross-language presence of
  every domain role, read from the pipeline manifests in the local `.generated/` corpus.
  Phase-boundary only: it refuses to run until every registered language's corpus is
  complete (`generate.ps1 -All -L <language>`, which Jon runs — blocked for agents).
- **`behaviour-parity-gate.ps1`** (~1 min): groups functions into roles by shared-typed
  signature or normalized name (language tokens stripped) and fails a role whose members carry
  the same behaviour skeleton, or whose members split into more than one skeleton group once
  every package declaring the construct unsupported is set aside (no reference language; the
  failure names every group). Run it when a language codegen package, codegen-common, or
  common changed.
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
  targeted tests only and report the packages they changed; the orchestrator's
  gate runs the affected set once, at the quality gate / phase boundary. Every boundary of a
  multi-phase run passes the affected set of all changes so far to the gate,
  which carries whatever did not change — not unconditionally ALL packages.
- A failure in any affected-set suite is yours to fix regardless of which package it
  appears in (execution contract §2).
- Different packages' suites may run concurrently (each writes its own
  `.test_results/`; `affected-gate.ps1` launches them under one worker budget and
  reads the verdict through `gate-verdict.ps1`'s own evaluation). Never launch
  overlapping runs of the SAME package.
- **A suite is not the first rung — it is the fifth** (execution contract §12.1). Reading the source,
  parsing the emitted artifact, and running one targeted test each settle a question faster and
  earlier than any suite, and a generation or a deploy settles it slowest of all. Pick the highest
  rung that can actually falsify the claim; a tier here is what you run once that rung is a suite.
  For a producer/consumer seam (emitted keys vs. consumed keys), the sound check is a **set
  difference computed in code** — a validator or a test — not a sweep that happens to go green.
- **A verification you run twice for the same information is spend, not rigour**
  (execution contract §11). Green does not decay because you edited an unrelated file,
  so re-running a passing suite as punctuation buys nothing. Verify when your change
  could plausibly affect the target — and prefer the narrowest form that settles it:
  `-Specific` over `-Keyword` over a whole suite, and a unit test over a regeneration
  whenever the emitted artifact is not itself the deliverable.
- **A long run belongs in the background, and the harness tells you when it lands.**
  Launch it with `run_in_background`, end the turn, resume on the notification. Never
  hold a turn open with an `until … sleep` poll loop waiting on your own run — see
  execution contract §11.1 for why that is both wasted spend and a guard being routed
  around.
