# Generated Output Stability — the Reference-Example Parity Gate

Datrix is a code generator, so its most important behavioural contract is: **the same
`.dtrx` sources, generated with the same code, produce byte-identical output.** Almost every
refactor in this repo declares "generated output is byte-identical" as its acceptance property.
The **reference-example parity gate** is the automated proof behind that claim. Without it, a
green test suite says nothing about output preservation.

## What the gate protects

For ONE reference example — `PARITY_EXAMPLE_RELPATH` in
`scripts/library/test/reference_example_parity.py` — the gate:

1. Runs the **real generation pipeline** — `datrix_cli.pipeline.generation.GenerationPipeline`,
   the exact code path `generate.ps1` runs, with the same `PipelineConfig` defaults
   (`profile="test"`, `format_output=True`, `validation_level=STANDARD`, no incremental, no
   migrations). It is not a fixture, a stub, or a re-implementation.
2. Hashes **every file in the whole generated output tree** — language sources, SQL, docker
   compose, component scaffolding, docs, scripts — after the post-generation language hooks
   (import-fix and formatting) have run, i.e. the bytes a user actually gets.
3. Compares that per-file sha256 manifest against the stored baseline in
   `datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256`.

Any changed byte in any generated file, and any file that appears or disappears, fails the gate.

Build/install artifacts that are not generated source are excluded from the manifest:
`.datrix/`, `.ruff_cache/`, `.tsc_cache/`, `node_modules/`, `__pycache__/`.

## Where it lives, and why

It is a **repo-level validation script**, not a pytest suite:

| Artifact | Path |
|---|---|
| Gate | `datrix/scripts/test/reference-example-parity-gate.ps1` |
| Re-bless command | `datrix/scripts/test/regen-parity-baselines.ps1` |
| Engine (both modes) | `datrix/scripts/library/test/reference_example_parity.py` |
| Baselines | `datrix/scripts/config/parity-baselines/` |
| Known non-generating examples | `datrix/scripts/config/parity-known-nongenerating.json` |

Two reasons it cannot be a package test:

- **Import boundary.** Calling the real pipeline means importing `datrix_cli`.
  `datrix_codegen_common` is forbidden from importing `datrix_cli` — a rule that explicitly
  applies to its tests too (see
  [import-boundaries.md](../../../datrix-common/docs/architecture/import-boundaries.md)).
- **Repo-level validation is a script.** Cross-cutting checks over the example tree belong in
  `datrix/scripts/test/`, alongside `typescript-whole-system-gate.ps1` and
  `check-generated-file-ratchet.ps1`.

## Sweeps the registered language set — not a fixed matrix

The target generation language is a real CLI input, `datrix generate --language`, forwarded by
`generate.ps1` / `-L` and by `scripts/library/dev/generate.py` — it is not read from
`config/system.dcfg` and the `-L`/`--language` value is not merely an output-path label: it is
the same value passed to `datrix generate` as the actual generation target. Every example is
therefore genuinely generatable in every registered `datrix.languages` target, not just one.

The gate reflects that: for each example it sweeps every currently-registered language
(`target_languages()`, derived at runtime from the installed `datrix.languages` entry points,
never a hardcoded literal), and checks each `(example, language)` pair against its own
`parity-baselines/<example_id>/<language>.sha256` baseline. A future `datrix-codegen-<lang>`
package is swept automatically the moment it registers — no edit to the gate or this doc is
needed.

## One example, not the whole corpus

`datrix/examples/` exists to cover DSL features; this gate exists to detect output drift, and
those two jobs want very different corpus sizes. Drift in a shared template surfaces in the
**first** example that renders it, so additional examples buy redundancy here rather than
coverage — while costing one full pipeline run each, per registered language.

The second cost mattered more. Baselines are whole-tree manifests written at **example**
granularity, so with a broad corpus an intentional one-line change could not be blessed without
simultaneously blessing every unrelated pending delta sitting in the same tree. That turns the
gate from a regression detector into noise the moment two people work in the tree at once.

**The corpus example must generate in every registered language.** This is a real constraint,
not a formality: most examples do not. `03-domains/ecommerce`, for instance, generates in python
alone — dotnet cannot derive a contract-violating value for `.length` on a collection, java does
not transpile struct-level function bodies, and typescript's output fails `tsc` with imports for
modules it never generates. An example that builds in only one language would silently reduce
the gate to a single-language check, with the rest parked in
`parity-known-nongenerating.json`.

Narrowing the EXAMPLE corpus never narrows the LANGUAGE sweep, and it does not remove targeted
capability from other gates: an explicit `-Example` still selects any example in the tree, which
is how `ingress-migration-conformance-gate.ps1` blesses the identity example as its own
byte-level proof.

## Non-vacuity is enforced on every run

A gate that cannot fail is worse than no gate, because it looks like protection. Before trusting
any comparison, every run of the gate:

1. takes a genuinely generated output tree,
2. copies it and mutates **one byte of one file**,
3. requires that the manifest comparison reports **exactly that path** as `CHANGED` and renders a
   unified diff showing the mutated content.

If the comparator does not bite, the gate exits non-zero regardless of how the examples compared.
The gate also fails loud if a post-generation tool (e.g. `ruff`) was not resolvable on `PATH`,
because a skipped formatting hook silently changes the generated bytes — such output must never
be compared or blessed.

## How to read a failure

```
  PARITY DRIFT  example=01-foundation
    changed=3 added=0 removed=0
    CHANGED (3):
      library_book_service/src/library_book_service/models/book_db/base_entity.py
      library_book_service/src/library_book_service/models/book_db/book.py
      library_book_service/src/library_book_service/models/book_db/category.py
    CONTENT DIFF (baseline -> current), first 3:
      --- baseline/library_book_service/src/library_book_service/models/book_db/base_entity.py
      +++ current/library_book_service/src/library_book_service/models/book_db/base_entity.py
      @@ -1,5 +1,5 @@
       """BaseEntity ORM model.
       Database: bookDb (postgres)
      -Auto-generated by datrix-codegen-python. Do not edit manually.
      +Auto-generated by datrix-codegen-python. Do not edit manually. NON-VACUITY-PROBE
       """
    Current output: D:\datrix\.test-output\parity-current\01-foundation
```

- **`CHANGED` / `ADDED` / `REMOVED`** list *every* affected path, not just the first.
- **`CONTENT DIFF`** is a real unified diff, rendered against the local baseline cache written by
  the last re-bless (`.test-output/parity-baseline-cache/`). If that cache is absent (a fresh
  clone, or `.test-output` was cleaned) the gate says so explicitly and still gives you the full
  path lists plus the freshly generated tree on disk — it never silently degrades.
- **`Current output`** is the tree the gate just generated. Open the changed paths under it to
  read the new content directly.

Then do the only thing that matters: **explain the diff.**

- Does it match an intentional change you (or a landed task) made to a generator or template?
  → re-bless that example.
- Can you not explain it? → **it is a bug, not a baseline update.** Do not re-bless it.

## The re-bless command

```powershell
# The normal case: re-bless the corpus example, once per registered language.
powershell -File "d:/datrix/datrix/scripts/test/regen-parity-baselines.ps1"

# Any other example by name -- for a gate that blesses its own byte-level proof.
powershell -File "d:/datrix/datrix/scripts/test/regen-parity-baselines.ps1" -Example "02-features/01-core-data-modeling/identity"
```

`regen-parity-baselines.ps1` is the **only** sanctioned baseline writer. The gate never writes
baselines (no auto-heal). With a one-example corpus a re-bless is cheap and its blast radius is
a single baseline directory, rather than every example's tree at once.

Always review the resulting baseline diff before committing. An unexpected baseline change is a
generator regression, not a baseline update.

## Known non-generating examples

`datrix/scripts/config/parity-known-nongenerating.json` lists examples the **real generator cannot
build today**, each with a reason and a follow-up identifier, under a pinned `expected_count`
(currently 17: 2 bare `example_id` entries plus 15 `example_id::language` entries surfaced once
baseline-blessing swept every registered language across the examples exercising cross-language
surfaces). This is a deliberately maintained scope boundary, not an auto-heal:

- Listed examples are reported **loudly on every run** — never silently skipped.
- The allowlist only converts a genuine *generation failure* into a skip. It never hides output
  drift: a listed `(example, language)` pair that does generate is still hash-compared, and one
  that has a baseline is still expected to match it.
- Adding or removing an entry requires updating `expected_count` in the same change, so the set
  cannot grow silently.

Every current entry names an example outside the gate's corpus, so none of them is reachable by a
default run today. The file is kept, and still validated on every run, because each entry is a
written record of a real, reproduced generator defect — deleting them would destroy that record,
not resolve it. An entry becomes live again the moment its example is used, whether as the corpus
or via an explicit `-Example`.

Since the gate sweeps every registered language per example, an entry's key controls how far its
skip reaches:

- A bare `example_id` applies to **every** language the gate sweeps for that example — for a
  failure at config-resolution/deployment-plan-building time, before any language-specific codegen
  stage runs. Two current entries are this form.
- An `example_id::language` key applies to **one** language only — for a defect confined to one
  language's own codegen stage while the same example generates fine in every other registered
  language. The named language must itself be a registered `datrix.languages` target. The
  remaining fifteen current entries are this form, each a real, language-specific generation
  defect (dotnet/java-only), never a blanket "language X can't build example Y."

## Two output-neutrality instruments, not one

The parity gate above answers one question: **has output drifted from what a committed baseline
blessed?** It is standing drift detection — it sweeps every registered `datrix.languages` target
at runtime, enforces its own non-vacuity every run, and turns red the moment a change alters any
byte of any file compared to the stored baseline. Everything above describes that instrument.

It does not answer a different, earlier question: **does the change I am currently holding alter
output at all, before it lands and before any baseline is blessed?** That is
`datrix/scripts/dev/byte-identity-generate.ps1`. It generates one example twice — a "before" code
state (a read-only `git archive` snapshot of named packages at a given ref, via `-BeforeRef` +
`-Packages`, or a caller-supplied tree via `-BeforeTree`) against the current working tree — into
two fixed, equal-length output roots, then byte-diffs the two trees. `-Language` is validated at
runtime against the registered language set, exactly like the gate's own sweep, never a hardcoded
list.

**When to reach for which:** the parity gate asks "has output drifted from what we blessed?";
byte identity asks "does the change I am holding alter output at all?" A refactor whose whole
claim is behaviour preservation wants byte identity *before* it commits and the parity gate
*afterwards* — the gate can only compare against a baseline that already exists, and re-blessing
before proving neutrality would bless the very drift the gate exists to catch.

A change that touches a **shared** package (`datrix-common`, `datrix-codegen-common`, or any
contract every generator consumes) must be checked across **every registered language it
reaches**, not just the languages the author happens to be working in. A shared helper consumed
by a language package the author never ran is exactly how an "output-neutral" refactor ships a
diff — the same cross-surface blind spot the parity gate's own language sweep exists to close.

`datrix/scripts/dev/compare-generated.ps1` is **not** a byte-identity tool: it compares
`.generated` against `.generated_saved` at feature level — presence of known content patterns,
not a byte-level diff. Reaching for it to back a byte-identity claim proves nothing; use
`byte-identity-generate.ps1` for that.

## Stating acceptance for a performance or structure refactor

A refactor whose purpose is removing redundant work — recomputing a value once instead of once
per iteration, hoisting an invariant out of a loop — states its acceptance property as
**correctness-plus-structure, not a timing number.** There is no benchmark harness anywhere under
`datrix/scripts/`, no profile establishing that generation is slow, and no designated "large
project" fixture. A numeric bar with no harness, no baseline, and no fixture to run it against is
an unprovable acceptance property, and building one to gate a handful of localized cleanups costs
more than the cleanups themselves.

The provable form has two halves:

- **(a) Generated output is byte-identical** — proven by the two instruments above: byte identity
  before the change lands, the parity gate on every run afterward.
- **(b) The work is done once rather than N times** — proven by object-identity tests (a snapshot
  built once per service is the *same* object across that service's per-entity passes, and a
  different service yields a different object) together with deleting the per-iteration rebuild
  path those tests would otherwise still exercise. Both halves matter: the positive test proves
  reuse happens, the deletion proves it is the *only* path left.

"Computed once" is a property directly observable in tests. It needs no production counters and
no debug log lines — instrumenting an invariant already proven in tests is dead weight, not
evidence.

## Running it

```powershell
# The gate: the corpus example, once per registered language.
powershell -File "d:/datrix/datrix/scripts/test/reference-example-parity-gate.ps1"

# Any other example by name, while iterating on a generator.
powershell -File "d:/datrix/datrix/scripts/test/reference-example-parity-gate.ps1" -Example "02-features/01-core-data-modeling/identity"
```

Exit codes: `0` = every example matches its baseline and the comparator is non-vacuous;
`1` = drift, missing baseline, generation failure, or self-test failure; `2` = usage/config error.

See `datrix/scripts/test/quick-reference.md` for the full parameter reference.
