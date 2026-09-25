# Verification Strategy — Targeted Tests Only

**The rule:** an agent runs only the tests related to the code it changed. A whole package
suite is never an agent's act — not inside a fix, not at a wave or phase boundary, not as a
quality gate, not to "check for regressions". There is no gate that sweeps suites. Jon runs
full suites himself, in his own terminal.

`guard-full-suite-runs.py` enforces it for every agent, main session included, with no
override: a `test.ps1` run naming a package without `-Specific`/`-Keyword`/`-Tag`, any
`-All` or `-Rerun`, a tier sweep (`-Unit`/`-Integration`/`-E2E`/`-Fast`/`-Slow`), and every
`affected-gate.ps1` sweep are refused. `instruction-surface-gate.ps1` keeps agent-facing
documents from prescribing one.

Type-checking is not part of verification: never run `mypy` or any standalone type-checker
(`guard-forbidden-commands.py` refuses the binaries, `python -m mypy`, `test\mypy.ps1`,
`library/mypy.py` and the `-Mypy` switch of `affected-gate.ps1`).

This file is git-tracked in the `datrix` repository via the `d:\datrix\.claude` ->
`d:\datrix\datrix\claude-config\.claude` symlink, so an edit through either path modifies
the same tracked file.

## What to run

Every test carries one or more **feature tags** naming the behaviour it exercises (pytest
`tag` marker; Node `#tag` token in the test name). Rules and vocabulary:
`datrix-common/docs/contributing/test-guidelines/feature-tags.md`.

1. **The tests of the files you touched** — the test files you added or edited, and the
   test modules beside the code you edited:
   `test.ps1 <pkg> -Specific "tests/unit/a.py,tests/unit/b.py"` (one session per package;
   `test-single.ps1` for one node id while debugging).
2. **The tests of the behaviour you changed, in every package it reaches** — by tag:
   `test.ps1 <pkg-a> <pkg-b> -Tag <tag>[,<tag>]`. Pick the tags from the tests of the code
   you edited; `test.ps1 <pkg> -ListTags` prints a package's tags and runs nothing. Name
   only packages that carry the tag — a requested tag no test in a package carries fails
   that package, so a misspelling can never shrink a run silently.
3. **A behaviour no tagged test covers is untested.** Write the test in the owning package,
   tag it, and run it. A test proves the invariant forever; a sweep proves it once.

Batch: one `test.ps1` call covers several packages (`-Projects` is variadic) and runs them
sequentially. Never run two `test.ps1` invocations at once — they contend for the shared
venv's package lock.

A `-Tag` selection that keeps every test in a package's whole test tree is refused as a
full suite in disguise; name a narrower tag.

## Which packages a change reaches

A package is reached when its code consumes the changed surface. The unit of impact is the
module/symbol you edited, not the package holding it: importing a package is not consuming
every surface in it.

1. **List the changed surface.** Every module you modified and every public name in it whose
   behaviour, signature or emitted output changed.
2. **Close it over the changed package.** Add every unchanged module in the same package that
   references a surface member — by import *or* by dotted-path string (genDSL
   `resolver_ref`, entry-point targets, registry keys) — repeating until nothing new is
   added. A shared helper you did not edit still carries your change to everyone who calls it.
3. **Find the direct consumers.** Every other package whose `src/`, `tests/` or root
   `conftest.py` references any module/name from step 2, by dotted path or symbol name:

   ```bash
   grep -rlE "build_schema_context|SchemaField|generation\.client_contract" \
     datrix-*/src datrix-*/tests datrix-*/conftest.py --include="*.py" | cut -d/ -f1 | sort -u
   ```

   Prove the matcher non-vacuous: it must find the changed package's own references.
4. **Follow behaviour, not just imports.** A consumer whose emitted output or runtime
   behaviour changes is itself a changed surface for its own consumers. A change that reaches
   a generator reaches every package whose tests run that generator through
   `GenerationPipeline` — today `datrix-common` (its root `conftest.py` generates real
   projects, `target_language` defaulting to python) and `datrix-cli`. These edges come from
   entry-point discovery, so no import scan shows them.

When you cannot decide whether a package is reached, **read until you can** — its tests, its
conftest, what its fixtures generate. Neither "include it to be safe" nor "it's probably
fine" is a decision.

**Example** (a change to `SchemaField` and the entity create/update derivation in
`datrix-codegen-common`): reached — the backends that render request schemas (python,
typescript, dotnet, java), the Angular client that renders the contract's input models, and
`datrix-common` + `datrix-cli`, whose tests generate python projects through the pipeline.
Not reached: aws, azure, docker, sql, component. The run is the tags of that behaviour
(`input-validation`, `rest-api`, `frontend-client`, …) across the reached packages.

`affected-set.ps1 -All` prints the import closure of every package (src, tests, root
conftest, declared deps). It is where step 3 starts looking, never the answer.

**The datrix-common root-conftest edge.** `datrix-common/conftest.py` imports
`datrix_cli.pipeline.generation.GenerationPipeline` and `datrix_language.registration`, and
its dev extra installs datrix-language, datrix-codegen-component and datrix-codegen-docker,
because its tests run the real pipeline. A change in language, cli, component, docker, or
any generator its conftest selects can therefore break datrix-common tests. A scan of `src/`
and `tests/` alone misses this edge: the file is a package-root `conftest.py`.

## Repo gates (cheap static nets)

Static scans (`dev/semgrep.ps1`, `dev/libcst.ps1`, `dev/check-import-boundaries.ps1`,
`dev/check-debug-artifacts.ps1`, `dev/check-docs.ps1`) and the repo-level gates run no
package test suite. Run the ones whose surface you touched, for a question you can name
(execution contract §12.5 holds the surface→check table); whole-package anti-pattern scans
need a `-Rule` or a stated question (`guard-untargeted-scans.py`).

- **There is no stored-baseline output gate and no bless step.** The repo keeps no snapshot
  of generated output (`datrix/docs/architecture/generated-output-stability.md`). An
  "output-neutral" or "byte-identical" claim is proven by a test in the owning package that
  renders the construct for a fixture and asserts its output — never by a corpus hash and
  never by re-recording a baseline.
- **`artifact-role-parity-gate.ps1`** (seconds, reads only): cross-language presence of every
  domain role, read from the pipeline manifests in the local `.generated/` corpus. It refuses
  to run until every registered language's corpus is complete (`generate.ps1 -All -L
  <language>`, which Jon runs — blocked for agents).
- **`behaviour-parity-gate.ps1`** (~1 min): groups functions into roles by shared-typed
  signature or normalized name and fails a role whose members carry the same behaviour
  skeleton, or split into more than one skeleton group once every package declaring the
  construct unsupported is set aside. Run it when a language codegen package,
  codegen-common, or common changed.
- Other gates only when their surface was touched: `shared-library-gate` /
  `test-tooling-parsing-gate` / `review-library-gate` (datrix/scripts/library),
  `instruction-surface-gate` (agent-facing documents), `check-docs-conformance`
  (architecture docs), `check-generated-file-ratchet` (GeneratedFile call sites),
  `type-mapping-completeness` (type registry/mappings), `supported-domain-parity-gate`
  (domain registration), `gendsl-corpus-resolution-gate` (genDSL definitions).

## Rules

- The CLAUDE.md **cross-surface impact rule**: touching a shared layer means running the
  tests of the changed behaviour in every package the change *reaches* — by tag, established
  by the procedure above. It never means sweeping those packages' suites.
- Orchestrated runs (task-orchestrator, execute-tasks[-parallel]): each task names its
  targeted tests (`## Targeted Tests`: files and tags, per package). Task agents run exactly
  those and report the packages, surface and tags they touched. The orchestrator's wave test
  gate re-runs the union of the wave's targeted tests once, batched per package. No phase
  boundary and no quality-gate step runs a suite.
- A failure in any test you ran is yours to fix regardless of which package it appears in
  (execution contract §2).
- **Reach for a test run only after cheaper rungs** (execution contract §12.1). Reading the
  source, parsing the emitted artifact, and one targeted test each settle a question faster
  than a larger run; a generation or deploy settles it slowest of all. For a
  producer/consumer seam, the sound check is a **set difference computed in code** — a
  validator or a test.
- **A verification you run twice for the same information is spend, not rigour**
  (execution contract §11). Green does not decay because you edited an unrelated file.
  Prefer the narrowest form that settles the question: `-Specific` over `-Tag` over a wider
  tag set, and a unit test over a regeneration whenever the emitted artifact is not itself
  the deliverable.
- **A long run belongs in the background, and the harness tells you when it lands.** Launch
  it with `run_in_background`, end the turn, resume on the notification. Never hold a turn
  open with an `until … sleep` poll loop (execution contract §11.1).
