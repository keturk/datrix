# Generated Output Stability — the Reference-Example Parity Gate

Datrix is a code generator, so its most important behavioural contract is: **the same
`.dtrx` sources, generated with the same code, produce byte-identical output.** Almost every
refactor in this repo declares "generated output is byte-identical" as its acceptance property.
The **reference-example parity gate** is the automated proof behind that claim. Without it, a
green test suite says nothing about output preservation.

## What the gate protects

For every example `system.dtrx` under `datrix/examples/`, the gate:

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

Baseline *coverage* is separate from what the gate is capable of sweeping, and today it is
partial: of the 53 examples with baselines, only `01-foundation` is blessed in all four
currently-registered languages (python, typescript, dotnet, java); `04-languages-typescript-service`
is blessed in typescript only; every other example is blessed in python only. This is a coverage
gap, not a design limit — a missing baseline for a language the gate sweeps is reported as a
loud **failure**, never silently skipped, which is exactly why the gap is visible instead of
quietly assumed away. Closing it means re-blessing an example in more languages
(`regen-parity-baselines.ps1 -Example <id>`), not changing the gate.

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
# The normal case: one intentional change -> re-bless the one affected example.
powershell -File "d:/datrix/datrix/scripts/test/regen-parity-baselines.ps1" -Example "01-foundation"

# Only for a change that legitimately moves every example's output.
powershell -File "d:/datrix/datrix/scripts/test/regen-parity-baselines.ps1"
```

`regen-parity-baselines.ps1` is the **only** sanctioned baseline writer. The gate never writes
baselines (no auto-heal). Baselines are **per example**, which is what keeps the gate cheap to
keep green: an intentional change to one example re-blesses one example, not all 53.

Always review the resulting baseline diff before committing. An unexpected baseline change is a
generator regression, not a baseline update.

## Known non-generating examples

`datrix/scripts/config/parity-known-nongenerating.json` lists examples the **real generator cannot
build today**, each with a reason and a follow-up identifier, under a pinned `expected_count`
(currently 2). This is a deliberately maintained scope boundary, not an auto-heal:

- Listed examples are reported **loudly on every run** — never silently skipped.
- The allowlist only converts a genuine *generation failure* into a skip. It never hides output
  drift: a listed `(example, language)` pair that does generate is still hash-compared, and one
  that has a baseline is still expected to match it.
- Adding or removing an entry requires updating `expected_count` in the same change, so the set
  cannot grow silently.

Since the gate sweeps every registered language per example, an entry's key controls how far its
skip reaches:

- A bare `example_id` applies to **every** language the gate sweeps for that example — for a
  failure at config-resolution/deployment-plan-building time, before any language-specific codegen
  stage runs. Both current entries are this form.
- An `example_id::language` key applies to **one** language only — for a defect confined to one
  language's own codegen stage while the same example generates fine in every other registered
  language. The named language must itself be a registered `datrix.languages` target.

## Running it

```powershell
# Full gate (all examples, ~4 minutes).
powershell -File "d:/datrix/datrix/scripts/test/reference-example-parity-gate.ps1"

# One example, while iterating on a generator.
powershell -File "d:/datrix/datrix/scripts/test/reference-example-parity-gate.ps1" -Example "01-foundation"
```

Exit codes: `0` = every example matches its baseline and the comparator is non-vacuous;
`1` = drift, missing baseline, generation failure, or self-test failure; `2` = usage/config error.

See `datrix/scripts/test/quick-reference.md` for the full parameter reference.
