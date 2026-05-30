---
description: Diagnose and fix datrix-codegen-typescript test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen TypeScript

Diagnose and fix failures, errors, and warnings in `datrix-codegen-typescript` from a structured test results `index.json`, trace to root cause in generator/template/transpiler code, fix, and verify — without needing to explore the codebase first.

**Three issue categories (processed in this order):**
1. **Errors** — collection/setup exceptions that prevent tests from running (highest priority)
2. **Failures** — assertion failures in tests that did run
3. **Warnings** — pytest warnings that indicate code quality issues, deprecations, or potential bugs

## How to Invoke

```
/fix-codegen-typescript D:\datrix\datrix-codegen-typescript\.test_results\test-results-20260511-090734\index.json
```

The argument is the absolute path to an `index.json` file inside a `.test_results/test-results-YYYYMMDD-HHMMSS/` directory.

## Prereqs
Read first: CLAUDE.md, `datrix-common/docs/contributing/ai-agent-rules.md`, `test-guidelines/`.

## Scope

- **Language:** TypeScript codegen ONLY. Do NOT cross into Python codegen packages.
- **Package:** `datrix-codegen-typescript` — source at `d:\datrix\datrix-codegen-typescript\`
- **Fix target:** Generator source code, templates, transpiler, or test code — never generated output.
- **Git:** Each project (`datrix-*`) is its own independent git repository. Commits and status are per-project.

---

## Pre-Requisite Context (DO NOT RE-INVESTIGATE)

The following sections describe the project structure, key files, and conventions. Use this information directly — do NOT spend tool calls rediscovering it.

### Test Results Schema (index.json)

```json
{
  "schema_version": 1,
  "project": "datrix-codegen-typescript",
  "timestamp": "ISO datetime",
  "duration_seconds": 290.54,
  "result": "FAILED|PASSED",
  "counts": { "passed": 3137, "failed": 1, "error": 0, "skipped": 0 },
  "failures": [
    {
      "id": 1,
      "test_id": "tests.module.test_file.TestClass::test_method",
      "file": "tests/module/test_file.py",
      "class": "tests.module.test_file.TestClass",
      "function": "test_method",
      "error_type": "AssertionError",
      "error_message": "Full assertion message with diff",
      "source_location": "tests/module/test_file.py:282",
      "log_file": "failures/001-tests-module-test_file-TestClass-test_method.txt"
    }
  ],
  "errors": [
    {
      "id": 1,
      "test_id": "tests.module.test_file.TestClass::test_method",
      "file": "tests/module/test_file.py",
      "class": "tests.module.test_file.TestClass",
      "function": "test_method",
      "error_type": "ImportError",
      "error_message": "Cannot import name X from Y",
      "source_location": "src/module/file.py:15",
      "log_file": "errors/001-tests-module-test_file-TestClass-test_method.txt"
    }
  ],
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
  "error_clusters": [
    {
      "cluster_id": 1,
      "pattern": "Normalized error signature",
      "source_location": "file:line",
      "count": 1,
      "error_ids": [1],
      "representative_error_id": 1
    }
  ],
  "phases": { "Parallel": 0, "Serial": 0 }
}
```

**Companion files** in the same directory:
- `summary.txt` — Human-readable summary (read only if index.json is insufficient)
- `full.log` — Complete pytest output; contains **warnings summary** section and collection/configuration errors
- `failures/NNN-....txt` — Per-failure detail with full traceback, captured stdout/stderr
- `errors/NNN-....txt` — Per-error detail (collection/setup errors)
- `junit-parallel.xml`, `junit-serial.xml` — Raw JUnit XML (rarely needed)

### Warnings (from full.log)

Warnings are **NOT** captured in `index.json`. They appear only in `full.log` inside pytest's warnings summary section:

```
======= warnings summary =======
path/to/file.py:42: DeprecationWarning: some deprecated call
  code_line_that_triggered_it()

path/to/file.py:99: UserWarning: something suspicious
  another_code_line()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======= N passed, M warnings in Xs =======
```

**To extract warnings:** Read `full.log` and search for the `warnings summary` section (delimited by `=` lines). Parse each warning entry which contains: file path, line number, warning category, message, and the triggering code line.

**Common warning categories to fix:**
- `DeprecationWarning` — Using deprecated API; update to current API
- `PendingDeprecationWarning` — Will be deprecated; plan migration
- `UserWarning` — Explicit warnings from code; investigate intent
- `RuntimeWarning` — Runtime issues (overflow, invalid value); fix underlying math/logic
- `SyntaxWarning` — Suspicious syntax; fix the syntax
- `ResourceWarning` — Unclosed files/connections; add proper cleanup

### Project Structure
Read `d:\datrix\datrix-codegen-typescript\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" datrix-codegen-typescript`.

### Test-to-Source Mapping Convention

| Test file path | Source file path |
|---|---|
| `tests/unit/generators/entity/test_entity_generator.py` | `src/.../generators/entity/entity_generator.py` |
| `tests/unit/generators/api/test_endpoint_decorators_coverage.py` | `src/.../generators/api/_endpoint_decorators.py` |
| `tests/unit/transpiler/test_operators.py` | `src/.../transpiler/operators.py` |
| `tests/transpiler/test_ts_statements_coverage.py` | `src/.../transpiler/_transpiler_statements.py` + `_transpiler_expressions.py` |
| `tests/unit/test_validation.py` | `src/.../validation.py` |
| `tests/unit/test_type_resolver_coverage.py` | `src/.../type_resolver.py` |

**Pattern:** `test_{source_module_name}.py` or `test_{source_module_name}_{scenario}.py`

For `_coverage` test files, they typically test internal helper modules (prefixed with `_`).

### Critical Test Helper: ts_test_deps.py

Located at `tests/unit/generators/ts_test_deps.py`. Provides:

```python
build_template_generator()              # Returns TemplateGenerator with TS templates
build_ts_deps(service, app)             # Returns (TemplateGenerator, Transpiler, TypeResolver, OrmResolver, ServicePaths)
get_service(app, qualified_name)        # Lookup service by name
build_ts_entity_orchestrator(...)       # Returns EntityOrchestrator for tests
build_ts_schema_orchestrator(...)       # Returns SchemaOrchestrator for tests
build_ts_service_layer_orchestrator(...) # Returns ServiceLayerOrchestrator
build_ts_pubsub_orchestrator(...)       # Returns PubsubOrchestrator
build_ts_queue_orchestrator(...)        # Returns QueueOrchestrator
```

### Key Entry Points

| File | Purpose |
|---|---|
| `plugin.py` | `TypeScriptGenerator` — main entry, creates transpiler, resolvers, orchestrators |
| `registry.py` | `TS_SUB_GENERATORS` — ordered list of sub-generators with feature gates |
| `type_resolver.py` | `TypeScriptTypeResolver` — Datrix types → TS types |
| `type_mappings.py` | `TYPESCRIPT_TYPE_MAP` — static type mapping dictionary |
| `profile.py` | `TS_PROFILE` — `LanguageProfile` for `SharedTranspiler` |
| `transpiler/ts_transpiler.py` | `SharedTranspilerTS` — DSL → TS visitor-based transpiler |
| `transpiler/builtins.py` | `TypeScriptBuiltinMethodMapper` — builtin method → TS code |

### Pipeline Architecture

```
.dtrx DSL → TreeSitterParser + Transformers → Application (validated AST)
  → TypeScriptGenerator.generate(app, output_dir)
    → For each Service:
        → Build: TemplateGenerator, SharedTranspilerTS, TypeScriptTypeResolver, OrmResolver
        → ServiceOrchestrator.generate_for_service()
            → EntityOrchestrator, SchemaOrchestrator, EndpointOrchestrator, ...
            → Each orchestrator: build context → render template → validate output
        → ProjectGenerator (package.json, tsconfig, app.module, main.ts)
    → generate_project_level(app):
        → LanguageWorkspaceGenerator, DeploymentTestGenerator, DocGenerator
```

### Running Tests

**Single test (from bash):**
```bash
powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "tests/path/to/test_file.py::TestClass::test_method" -Project datrix-codegen-typescript -VerboseOutput
```

**Full suite (from bash):**
```bash
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-codegen-typescript
```

**Fast suite (skip slow tests):**
```bash
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-codegen-typescript -Fast
```

---

## Investigation Workflow

### Step 1: Parse Test Results

1. **Read `index.json`** at the provided path.
2. **Triage the three categories** — determine what needs fixing:
   - Check `counts.error` — if > 0, errors exist (highest priority)
   - Check `counts.failed` — if > 0, failures exist
   - Note: warnings require reading `full.log` (Step 1b)
3. **For errors:** Extract `error_clusters` from index.json. For each cluster, note `representative_error_id` and look up its entry in `errors[]`. Read the representative error's `log_file` (relative to the index.json directory).
4. **For failures:** Extract `failure_clusters` from index.json. For each cluster, note `representative_failure_id` and look up its entry in `failures[]`. Read the representative failure's `log_file`.
5. If there are more than 5 distinct clusters (errors + failures combined): STOP and propose splitting into multiple sessions.

#### Step 1b: Extract Warnings

1. **Read `full.log`** from the same directory as index.json.
2. **Search for the warnings summary section** — look for lines matching `= warnings summary =` (delimited by `=` characters).
3. **Parse each warning entry:** Extract file path, line number, warning category (e.g., `DeprecationWarning`), and message.
4. **Group warnings by category and source file** — deduplicate identical warnings that appear multiple times (pytest often repeats warnings from parameterized tests).
5. **Skip if no warnings section found** — not all test runs produce warnings.

### Step 2: Fix Errors (if any)

Errors prevent tests from running at all. Fix these first.

**Common error types and where to look:**

| Error Type | Likely Cause | Where to Look |
|---|---|---|
| `ImportError` / `ModuleNotFoundError` | Missing or renamed module/class | Source module at import path |
| `AttributeError` during collection | Class/function renamed or removed | Source module referenced in traceback |
| `TypeError` during collection | Signature change in fixture or helper | `conftest.py`, `ts_test_deps.py`, or source |
| `SyntaxError` | Broken Python syntax | File referenced in traceback |
| `FixtureError` | Missing or broken pytest fixture | `conftest.py` hierarchy |

For each error cluster representative:

1. **Read the error's `log_file`** to get the full traceback.
2. **Identify the root cause** from the traceback — errors usually point directly to the broken line.
3. **Read the broken source file** and fix it.
4. **Verify** by running the affected test(s).

### Step 3: Fix Failures (if any)

For each failure cluster representative:

1. **Read the test file** at the `source_location` from index.json.
2. Find the test class and method. Understand:
   - What is the test setting up? (DSL fixtures, mock data, orchestrators)
   - What is being asserted? (generated code content, structure, imports)
   - What is the actual vs. expected value from the error message?

### Step 4: Trace Failures to Source

Based on the test and error:

1. **Identify the source module being tested** using the test-to-source mapping convention above.
2. **Read the source module** — the generator, template, transpiler, or helper being tested.
3. **Trace the code path** that produces the incorrect output:
   - For generator tests: generator function → template context → template rendering
   - For transpiler tests: visitor method → expression/statement handling → code emission
   - For type resolution tests: type resolver → type mapping → output type string
4. **Identify the root cause:**
   - Wrong logic in generator/transpiler code?
   - Missing case in a conditional/match?
   - Template error (Jinja2)?
   - Incorrect type mapping?
   - Test expectation outdated after intentional change?

### Step 5: Determine Fix Location

Decide WHERE the fix belongs:

- **Generator/transpiler/template bug** → Fix the source code.
- **Test expectation outdated** (intentional behavior change) → Update the test. But ONLY if you can confirm the current output is correct.
- **Test setup wrong** (missing fixture data, wrong DSL input) → Fix the test setup.

### Step 6: Apply Fix

1. **Read the file to be modified** (mandatory before editing).
2. **Make the smallest possible edit** — no debug logging, no unrelated changes.
3. Follow all rules from CLAUDE.md: type hints, no Any, no magic constants, cognitive complexity ≤15.

### Step 7: Verify

Run the originally-failing/erroring test(s):

```bash
powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "{test_file}::{TestClass}::{test_method}" -Project datrix-codegen-typescript -VerboseOutput
```

**Construct the test path from index.json `test_id`:**
- `test_id`: `tests.transpiler.test_ts_statements_coverage.TestTypeResolution::test_unresolved_ref_type`
- Convert dots to `/` for the module path, keep `::` for class/method: `tests/transpiler/test_ts_statements_coverage.py::TestTypeResolution::test_unresolved_ref_type`

**Assess results:**
- **PASS:** Report success, move to next cluster.
- **FAIL (same error):** Fix was insufficient — investigate deeper.
- **FAIL (different error):** Fix introduced a new issue — revert and rethink.

### Step 8: Fix Warnings (if any)

After errors and failures are resolved, address warnings:

1. **For each unique warning** (grouped by file + category):
   - Read the source file at the warning's line number.
   - Determine the fix based on category:
     - `DeprecationWarning` → Replace deprecated API call with current API
     - `UserWarning` → Investigate if the warning indicates a real issue or can be suppressed with proper fix
     - `RuntimeWarning` → Fix the underlying logic (overflow, invalid value, etc.)
     - `SyntaxWarning` → Fix the syntax issue
     - `ResourceWarning` → Add proper resource cleanup (context managers, close calls)
   - Apply the minimal fix.

2. **Verify warnings are resolved** by running the affected test file and checking output for remaining warnings:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "{test_file}" -Project datrix-codegen-typescript -VerboseOutput
   ```
   Check the output for the specific warning — it should no longer appear.

### Step 9: Final Regression Check

After all errors, failures, and warnings are fixed, run the full suite:
```bash
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-codegen-typescript -Fast
```

### Step 10: Report

```
FIX-CODEGEN-TYPESCRIPT COMPLETE

Test results: {index.json path}
Original issues: {E} errors, {F} failures in {C} clusters, {W} warnings

Errors fixed:
1. {file:line} — {what changed} — fixes error cluster #{id}

Failures fixed:
1. {file:line} — {what changed} — fixes failure cluster #{id}

Warnings fixed:
1. {file:line} — {category}: {what changed}

Verification:
- Originally erroring tests: {PASS/FAIL}
- Originally failing tests: {PASS/FAIL}
- Warnings resolved: {N}/{total}
- Full suite regression check: {PASS/FAIL} ({pass}/{total})

Unresolved (if any):
- Error cluster #{id}: {reason}
- Failure cluster #{id}: {reason}
- Warning: {file:line} — {reason}
```

## Cross-Project Root Cause

If investigation reveals the root cause is in a different project, do NOT fix it directly. Instead:

1. Report the finding: which project contains the root cause, which file/line, and why.
2. Activate the fix skill for that project by invoking `/fix-{suffix}` where the suffix drops the `datrix-` prefix (e.g., `datrix-common` → `/fix-common`, `datrix-codegen-python` → `/fix-codegen-python`).
3. The activated skill will handle fixing the root cause in its own project scope.

## Abort Conditions

STOP immediately if:

- More than **5 distinct clusters** (errors + failures combined) — propose splitting
- Fix reveals **cascading issues** in unrelated subsystems
- About to modify code **outside datrix-codegen-typescript**
- Working for **more than 3 attempts** on a single error/failure without convergence
- Warnings exceed **20 unique instances** — propose splitting or batch approach

On abort, report what was investigated, what was attempted, and what remains.

## Anti-Patterns

- **NO exploring the project structure** — read `.project-structure.md` and the context above, don't rediscover it
- **NO reading every file in failures/** — use cluster representatives only
- **NO debug scatter** — zero temporary logging
- **NO fixing generated output** — always fix generator/template/transpiler source
- **NO cross-package fixes** — activate the other project's fix skill instead
- **NO running full suite after each fix** — verify individual tests first
- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
