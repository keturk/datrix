# Fix-Package Playbook (shared by all /fix-* package skills)

Shared workflow for diagnosing and fixing failures, errors, and warnings in a single `datrix-*` package from a structured test-results `index.json` — without exploring the codebase first — and proving the result with the tests of every behaviour the fixes changed (never a whole suite).

The invoking skill (`/fix-{suffix}`) defines these parameters — substitute them everywhere below:
- `{PACKAGE}` — package name (e.g. `datrix-common`)
- `{PACKAGE_PATH}` — `d:\datrix\{PACKAGE}\`
- Package-specific scope, cautions, test-to-source mapping additions, and key-file tables live in the invoking skill, NOT here. Read them there first.

**Three issue categories (processed in this order):**
1. **Errors** — collection/setup exceptions that prevent tests from running (highest priority)
2. **Failures** — assertion failures in tests that did run
3. **Warnings** — pytest warnings indicating quality issues, deprecations, or potential bugs

## Documentation Quick Reference

Full index: `d:\datrix\datrix\docs\doc_index.md`. Mandatory before starting: `d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md` (core) and `d:\datrix\datrix-common\docs\contributing\test-guidelines\`. Quick refs: `d:\datrix\datrix\docs\architecture\architecture-cheat-sheet.md` (map + knowledge-pack index; open the pack for the surface you touch), `design-principles-cheat-sheet.md`. Don't know where something is documented? `powershell -File "d:/datrix/datrix/scripts/dev/ineedtoknow.ps1" "<question>"` gives a brief answer with the file and line range to open.

Each project (`datrix-*`) is its own independent git repository — commits and status are per-project.

---

## Pre-Requisite Context (DO NOT RE-INVESTIGATE)

### Test Results Schema (index.json)

```json
{
  "schema_version": 1,
  "project": "{PACKAGE}",
  "result": "FAILED|PASSED",
  "counts": { "passed": 0, "failed": 0, "error": 0, "skipped": 0 },
  "failures": [
    {
      "id": 1,
      "test_id": "tests.module.test_file.TestClass::test_method",
      "file": "tests/module/test_file.py",
      "error_type": "AssertionError",
      "error_message": "Full assertion message with diff",
      "source_location": "tests/module/test_file.py:282",
      "log_file": "failures/001-tests-module-test_file-TestClass-test_method.txt"
    }
  ],
  "errors": [ "same shape as failures[]; log_file under errors/" ],
  "failure_clusters": [
    {
      "cluster_id": 1,
      "pattern": "Normalized error signature (* replaces literals)",
      "source_location": "file:line",
      "count": 1,
      "failure_ids": [1],
      "representative_failure_id": 1
    }
  ],
  "error_clusters": [ "same shape; representative_error_id / error_ids" ]
}
```

**Companion files** in the same directory:
- `full.log` — complete pytest output; contains the **warnings summary** section and collection/configuration errors
- `failures/NNN-....txt`, `errors/NNN-....txt` — per-item detail with full traceback and captured stdout/stderr
- `summary.txt`, `junit-*.xml` — rarely needed
- `failure-data.json`, `warnings.json`, `run-delta.json` — derived analyses written by the scripts below (present only after you run them)

### Extraction Scripts (use these — do not hand-parse)

Two scripts turn the run directory into compact structured JSON (read `datrix/scripts/test/quick-reference.md` before invoking; a pre-tool hook enforces this):

```bash
# Cluster bundle: families of clusters, one traceback tail per family, a ready-to-run
# test_command per cluster, and an advisory local-model hint for the first 5 families
powershell -File "d:/datrix/datrix/scripts/test/collect-failure-data.ps1" "{run-dir-or-index.json}"
# → {run-dir}\failure-data.json

# Warnings: deduplicated, grouped by category+file, parsed from full.log
powershell -File "d:/datrix/datrix/scripts/test/extract-warnings.ps1" "{run-dir-or-index.json}"
# → {run-dir}\warnings.json
```

### Warnings (from warnings.json)

Warnings are NOT in `index.json`. Run `extract-warnings.ps1` (above) and read `warnings.json` — each entry has file, line, category, message, triggering code line, and a dedup `count` (parameterized tests repeat warnings; the script already deduplicates). An empty `warnings` list means the run had no warnings section — skip Step 8.

Category → fix: `DeprecationWarning`/`PendingDeprecationWarning` → migrate to current API; `UserWarning` → investigate intent; `RuntimeWarning` → fix underlying math/logic; `SyntaxWarning` → fix syntax; `ResourceWarning` → add proper cleanup (context managers/close).

### Project Structure

Read `{PACKAGE_PATH}.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {PACKAGE}`.

### Test-to-Source Mapping Convention

`tests/unit/test_{module}.py` → `src/.../{module}.py`; `test_{module}_coverage.py` → `src/.../_{module}.py` (internal helper). The invoking skill may list package-specific mappings and key entry points — use those first.

### Running Tests

```bash
# Single test:
powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "tests/path/to/test_file.py::TestClass::test_method" -Project {PACKAGE} -VerboseOutput
# Batched targeted set:
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE} -Specific "tests/unit/test_a.py,tests/unit/test_b.py"
# The tests of a behaviour, by feature tag, in every package it reaches:
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE} {other-package} -Tag {tag}
# The tags a package carries (runs nothing):
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE} -ListTags
```

Never run a whole-package suite, in the fix loop or after it — verify each fix with its own tests, and the whole job with Step 9's tagged tests. Never a tier switch (`-Fast`, `-Unit`, …), `-All`, `-Rerun`, several packages without `-Tag`/`-Specific`, or `affected-gate.ps1`.

`failure-data.json` already carries a ready-to-run `test_command` per cluster representative — use it. If you must construct one by hand (e.g. for a non-representative member): dots→`/` for the module path, keep `::` — `tests.module.test_file.TestClass::test_method` → `tests/module/test_file.py::TestClass::test_method`.

---

## Investigation Workflow

### Step 1: Parse Test Results (scripted)

1. Run `collect-failure-data.ps1` on the provided path and read the resulting `failure-data.json` — it contains counts, `families` (clusters sharing one normalized pattern, errors first), every cluster with its representative and a ready `test_command`. Do NOT read `index.json`'s failure arrays or the `failures/` files directly for triage.
2. Triage from its `counts`: `error` > 0 → errors exist (fix first); `failed` > 0 → failures.
3. **Work per family, not per cluster.** A family is one assertion or error raised from several tests, so it is one root cause until the evidence says otherwise. Only the family's first cluster carries `traceback_tail`; the others say `traceback_tail_in_cluster: {id}` and keep their own `log_file`. Read a representative's full `log_file` only when the tail is insufficient — never read every file in `failures/`. An `error_message` ending in `[message cut: ...]` is whole in that entry's `log_file`.
4. **A family's `hint` is a hypothesis, not a finding.** When `hint.source` names a model, a local model read the traceback and the source around its frames and proposed a defect site and cause. Use it to decide what to open first, then confirm it against the code yourself before any edit — never edit on a hint alone, and never quote it as a root cause. `source: "unavailable"` (no local server answered) or `"skipped"` (past the hint limit) means work from the traceback as usual.
5. If `warnings_section_present` is true, run `extract-warnings.ps1` and read `warnings.json` (see above).
6. **More than 5 distinct families (errors + failures combined) → STOP and propose splitting into multiple sessions.**

### Step 2: Fix Errors first

Errors prevent tests from running. Common causes: `ImportError`/`ModuleNotFoundError` → missing/renamed module; `AttributeError` at collection → renamed/removed symbol; `TypeError` at collection → fixture/helper signature change (`conftest.py` or source); `SyntaxError` → file in traceback; fixture errors → `conftest.py` hierarchy.

Per cluster representative: read its `log_file` traceback → identify root cause (errors usually point at the broken line) → read and fix the source → verify the affected test(s).

### Step 3: Understand Failures

Per failure cluster representative: read the test at `source_location`; understand what it sets up, what it asserts, and actual vs. expected from the error message.

### Step 4: Trace to Source

Identify the source module under test (mapping convention + invoking skill's tables) → read it → trace the code path producing the wrong output → identify the **root cause**.

### Step 5: Determine Fix Location

- **Source bug** → fix source.
- **Test expectation outdated** (intentional behavior change) → update the test — ONLY if you confirmed current output is correct.
- **Test setup wrong** (missing fixture data, wrong input) → fix the setup.

### Step 6: Apply Fix

Read the file before editing. The **smallest correct** edit — no debug logging, no unrelated changes. Follow CLAUDE.md code standards.

**"Smallest correct" is one phrase, not two options.** Two rules bind every fix here (`_shared/execution-contract.md` §13–§14):

- **Never choose a less secure option when a more secure one is available**, and never disable, loosen, or exempt a security control to turn a red test green. If a test fails *against* a control, the control is the requirement and the thing failing it is the defect. Controls fail **closed**: a guard that cannot evaluate its input denies. This binds emitted templates as hard as generator source — an insecure default ships once per generated project, forever.
- **The size of a fix is set by the defect, not by your budget.** No "quick fix for now", no "minimal change to get it green", no "harden it later" — and none of those become acceptable because you said them honestly or because context was short. There is no later. If the correct fix is bigger than the cluster suggested, make it and report the expansion.

### Step 7: Verify

Run the originally-failing/erroring test(s) with `test-single.ps1` (command above).
- **PASS** → next cluster. **FAIL (same error)** → fix insufficient, investigate deeper. **FAIL (different error)** → the fix introduced a new issue — undo your edit manually and rethink.

### Step 8: Fix Warnings

After errors and failures: per unique warning in `warnings.json` (file + category), read the source at the warning's line, apply the minimal category-appropriate fix, and re-run the affected test file to confirm the warning is gone.

### Step 9: Final Regression Check — the tests of what you changed

Once, after ALL fixes (the dispatcher does it once over the union when fixes were dispatched):

1. Re-run every originally-failing test plus every test file you added or edited, batched per package with `-Specific`.
2. Name the behaviours your fixes changed and run their feature tags in `{PACKAGE}` and in every other package the fixes reach — per "Which packages a change reaches" in `d:\datrix\.claude\skills\_shared\verification-strategy.md` (for a shared-layer fix in `datrix-common`, `datrix-codegen-common`, `datrix-language`, or a shared contract: the packages whose code or tests reference the changed surface or an unchanged caller of it, plus the pipeline-running packages when a generator's behaviour changed):
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE} {consumer1} {consumer2} -Tag {tag1},{tag2}
   ```
3. A changed behaviour no tagged test covers gets a new, tagged test now.

Consuming packages get the tag runs above, never their whole suites.

**Step 9 is the proof; no whole-suite run follows it** (Jon runs full suites himself). A **FAILED** run here is your input: it writes a new `.test_results/test-results-*/` run, so return to Step 1 with its `index.json` and work every cluster it reports, whether your fixes caused it or it was already there (a failure you found is yours). Then Steps 7–9 again. The turn ends when every originally-failing test and every changed behaviour's tags pass, or at a valid B1–B4 blocker with its four-part proof — never at "the originally reported clusters pass" while a tagged test of a behaviour you changed is red.

### Step 10: Report

```
FIX-{PACKAGE} COMPLETE
Test results: {index.json path}
Original issues: {E} errors, {F} failures in {C} clusters, {W} warnings
Fixed: {file:line} — {what changed} — {cluster #id / warning category}   (one line each)
Verification: originally-failing tests {PASS/FAIL}; warnings resolved {N}/{total}; regression check {PASS/FAIL} ({pass}/{total}; tags {list} over packages {list})
Unresolved (if any): {cluster/warning} — {reason}
```

## Abort Conditions

STOP immediately if: more than 5 distinct clusters (propose splitting); a fix reveals cascading issues in unrelated subsystems; about to modify code outside `{PACKAGE}`; more than 3 attempts on a single item without convergence; more than 20 unique warnings (propose splitting/batch). On abort, report what was investigated, attempted, and remains.

## Cross-Project Root Cause

If the root cause is in a different project, do NOT fix it directly. Report the finding (project, file:line, why), then invoke `/fix-{suffix}` for that project (drop the `datrix-` prefix: `datrix-codegen-typescript` → `/fix-codegen-typescript`). Hand it a decisive package: the index.json path, the cluster IDs traced there, your root-cause evidence (file:line + reasoning), and what "fixed" looks like — so the receiving skill does not re-triage.

## Anti-Patterns

- **NO exploring the project structure** — read `.project-structure.md` and the context above; don't rediscover it
- **NO hand-parsing what the scripts extract** — `collect-failure-data.ps1` and `extract-warnings.ps1` own the run-dir parsing; read their JSON
- **NO reading every file in failures/** — family representatives only, and only when the embedded `traceback_tail` is insufficient
- **NO editing on a hint** — a family `hint` says where to look first; the code you read says what is wrong
- **NO whole-suite runs, ever** — verify individual tests per fix; one tag-based regression check (Step 9) is the proof
- **NO cross-package fixes** — hand off via the other project's fix skill
- **NO security downgrade to reach green** — no disabled/loosened auth, TLS, CORS, permission, or validation check; no hardcoded or logged secret; no fail-open guard; no widened permission. The control is the requirement (§13)
- **NO expedient fix** — nothing whose justification is "for now", "temporary", "minimal to get it green", or "to save context". Fix what the defect deserves (§14)
- Plus the CLAUDE.md invariants: no workarounds, no debug scatter, no git restore/checkout/reset/stash/revert (undo edits manually)
