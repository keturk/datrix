# Fix-Package Playbook (shared by all /fix-* package skills)

Shared workflow for diagnosing and fixing failures, errors, and warnings in a single `datrix-*` package from a structured test-results `index.json` — without exploring the codebase first.

The invoking skill (`/fix-{suffix}`) defines these parameters — substitute them everywhere below:
- `{PACKAGE}` — package name (e.g. `datrix-common`)
- `{PACKAGE_PATH}` — `d:\datrix\{PACKAGE}\`
- Package-specific scope, cautions, test-to-source mapping additions, and key-file tables live in the invoking skill, NOT here. Read them there first.

**Three issue categories (processed in this order):**
1. **Errors** — collection/setup exceptions that prevent tests from running (highest priority)
2. **Failures** — assertion failures in tests that did run
3. **Warnings** — pytest warnings indicating quality issues, deprecations, or potential bugs

## Documentation Quick Reference

Full index: `d:\datrix\datrix\docs\doc_index.md`. Mandatory before starting: `d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md` and `d:\datrix\datrix-common\docs\contributing\test-guidelines\`. Quick refs: `d:\datrix\datrix\docs\architecture\architecture-cheat-sheet.md`, `design-principles-cheat-sheet.md`.

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
# Cluster bundle: per-cluster representative traceback tail + ready-to-run test_command
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
# Full suite:
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE}
# Fast suite (skip slow tests):
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE} -Fast
```

`failure-data.json` already carries a ready-to-run `test_command` per cluster representative — use it. If you must construct one by hand (e.g. for a non-representative member): dots→`/` for the module path, keep `::` — `tests.module.test_file.TestClass::test_method` → `tests/module/test_file.py::TestClass::test_method`.

---

## Investigation Workflow

### Step 1: Parse Test Results (scripted)

1. Run `collect-failure-data.ps1` on the provided path and read the resulting `failure-data.json` — it contains counts, every cluster (errors first), each cluster's representative with its traceback tail, and a ready `test_command`. Do NOT read `index.json`'s failure arrays or the `failures/` files directly for triage.
2. Triage from its `counts`: `error` > 0 → errors exist (fix first); `failed` > 0 → failures.
3. Work per-cluster from the embedded representative `traceback_tail`. Read the representative's full `log_file` only when the tail is insufficient — never read every file in `failures/`.
4. If `warnings_section_present` is true, run `extract-warnings.ps1` and read `warnings.json` (see above).
5. **More than 5 distinct clusters (errors + failures combined) → STOP and propose splitting into multiple sessions.**

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

Read the file before editing. Smallest possible edit — no debug logging, no unrelated changes. Follow CLAUDE.md code standards.

### Step 7: Verify

Run the originally-failing/erroring test(s) with `test-single.ps1` (command above).
- **PASS** → next cluster. **FAIL (same error)** → fix insufficient, investigate deeper. **FAIL (different error)** → the fix introduced a new issue — undo your edit manually and rethink.

### Step 8: Fix Warnings

After errors and failures: per unique warning in `warnings.json` (file + category), read the source at the warning's line, apply the minimal category-appropriate fix, and re-run the affected test file to confirm the warning is gone.

### Step 9: Final Regression Check

Once, after ALL fixes: `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE} -Fast`

### Step 10: Report

```
FIX-{PACKAGE} COMPLETE
Test results: {index.json path}
Original issues: {E} errors, {F} failures in {C} clusters, {W} warnings
Fixed: {file:line} — {what changed} — {cluster #id / warning category}   (one line each)
Verification: originally-failing tests {PASS/FAIL}; warnings resolved {N}/{total}; regression check {PASS/FAIL} ({pass}/{total})
Unresolved (if any): {cluster/warning} — {reason}
```

## Abort Conditions

STOP immediately if: more than 5 distinct clusters (propose splitting); a fix reveals cascading issues in unrelated subsystems; about to modify code outside `{PACKAGE}`; more than 3 attempts on a single item without convergence; more than 20 unique warnings (propose splitting/batch). On abort, report what was investigated, attempted, and remains.

## Cross-Project Root Cause

If the root cause is in a different project, do NOT fix it directly. Report the finding (project, file:line, why), then invoke `/fix-{suffix}` for that project (drop the `datrix-` prefix: `datrix-codegen-typescript` → `/fix-codegen-typescript`). Hand it a decisive package: the index.json path, the cluster IDs traced there, your root-cause evidence (file:line + reasoning), and what "fixed" looks like — so the receiving skill does not re-triage.

## Anti-Patterns

- **NO exploring the project structure** — read `.project-structure.md` and the context above; don't rediscover it
- **NO hand-parsing what the scripts extract** — `collect-failure-data.ps1` and `extract-warnings.ps1` own the run-dir parsing; read their JSON
- **NO reading every file in failures/** — cluster representatives only, and only when the embedded `traceback_tail` is insufficient
- **NO running the full suite after each fix** — verify individual tests first; one regression check at the end (Step 9)
- **NO cross-package fixes** — hand off via the other project's fix skill
- Plus the CLAUDE.md invariants: no workarounds, no debug scatter, no git restore/checkout/reset/stash/revert (undo edits manually)
