---
description: Diagnose generated code test failures, trace to codegen root causes, implement fixes, and verify
model: claude-sonnet-4-6
delegation-strategy:
  phases:
    - name: "log_parsing"
      model: "haiku"
      parallelizable: true
      max_parallel: 3
      description: "Parse test failure logs and extract structured failure data"
    - name: "root_cause_analysis"
      model: "claude-sonnet-4-6"
      parallelizable: false
      description: "Trace failures to codegen source and build causal chains"
    - name: "fix_planning"
      model: "sonnet"
      parallelizable: false
      description: "Design minimal fixes for each root cause"
    - name: "fix_implementation"
      model: "sonnet"
      parallelizable: false
      description: "Apply fixes one at a time with verification"
    - name: "regeneration"
      model: "haiku"
      parallelizable: true
      max_parallel: 3
      description: "Regenerate affected examples and verify tests pass"
---

# Troubleshoot-and-Fix Pipeline

Autonomous end-to-end pipeline that diagnoses generated code test failures, traces them to codegen root causes, implements fixes, and verifies them against the test suite — all in a single session.

Combines the diagnostic depth of `/troubleshoot-generated` with the fix discipline of `/fix` and the verification rigor of `/fix-tests`.

## When to Use

- User wants both diagnosis AND fix in one pass (instead of two separate sessions)
- User says "troubleshoot and fix", "diagnose and fix", or "find and fix"
- User provides failing test logs and wants the underlying codegen bugs resolved
- After a generation run produces failures that need to be traced back to generators and fixed

## How to Invoke

```
/troubleshoot-and-fix

LOG FOLDERS:
D:\datrix\.generated\python\docker\02-features\05-infrastructure-combinations\multi-database\.test_results\deploy-test-20260303-111315

SCOPE: Python generator only
```

Minimal form:
```
/troubleshoot-and-fix

LOG FOLDER:
D:\datrix\.generated\python\docker\01-foundation\.test_results\unit-tests-20260303-111307
```

## Documentation Quick Reference

For complete documentation index with "When to use" guidance, see [doc_index.md](../../../../../datrix/docs/doc_index.md).

**Essential reads (MANDATORY before starting):**
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) → Core rules, STOP AND THINK principle
- [architecture-overview.md](../../../../../datrix/docs/architecture/architecture-overview.md) → System architecture
- [design-principles.md](../../../../../datrix/docs/architecture/design-principles.md) → Design philosophy

**Quick refs:**
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md)
- [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md)

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

## Scope Check

After reading mandatory documents and BEFORE investigation:

1. **Count log folders** — each is a multi-step investigation
2. **Confirm language scope** — Python or TypeScript? Do NOT cross languages.
3. **If more than 3 distinct failure categories:** STOP and propose splitting.

<!-- PHASE: log_parsing -->
## Phase 1: Log Parsing

Parse test failure logs and extract structured failure data for root cause analysis.

### Steps

For each log folder:

#### Step 1: Start from `index.json` (MANDATORY entry point)

Read **only** `index.json` first. It is the structured index of the entire test run.

**Unit test `index.json`** contains:
- `result`, `counts` — overall pass/fail and totals
- `services[]` — per-service result with `counts` and `log_file` path
- `failures[]` — each failure with `error_message`, `generated_file`, `log_file`, `codegen_hint`
- `failure_clusters[]` — grouped failures with `representative_error_id`, `codegen_hint`

**Deploy test `index.json`** additionally contains:
- `failed_phase` — which pipeline phase failed (docker-build, docker-up, health-check, db-connectivity, spec-tests, integration-tests)
- `phases{}` — result per phase (with `error_message` on failed phases)
- `failures[]` — each failure with `phase`, `failure_type` (logic/transient), `codegen_hint.probable_template`, `codegen_hint.probable_generator`
- `failure_clusters[]` — grouped by pattern with `representative_failure_id`

From `index.json`, extract:
1. Which services failed (skip passing services entirely)
2. The `failure_clusters` — these group related failures by pattern
3. The representative failure from each cluster (read only that one failure log, not all)
4. The `codegen_hint` if present (direct pointer to the generator/template)
5. The `generated_file` if present (direct pointer to broken output)
6. For deploy tests: which `phase` failed — if it's pre-integration (docker-build, health-check), check `deploy-test-output.log` instead of failure logs

**DO NOT** read `summary.txt`, `unit-tests-summary.log`, or full service logs unless `index.json` is insufficient. **DO NOT** read every file in the `failures/` directory — use the cluster representative only.

#### Step 2: Read representative failure logs (targeted)

For each failure cluster, read only the representative failure log file (referenced in `index.json` → `failures[].log_file`). This gives the full traceback for diagnosis.

Extract:
- Error message
- Traceback (file paths + line numbers)
- Generated file path (from traceback or `generated_file`)

#### Step 3: Read failing generated code

Read the failing generated code file (from `generated_file` or traceback paths).

Extract:
- Relevant code snippet (the function/class where the error occurred)
- Imports (if ImportError)
- Any obvious structural issues

### Input

Log folder path from skill invocation.

Example:
```json
{
  "log_folder": "D:\\datrix\\.generated\\python\\docker\\01-foundation\\.test_results\\unit-tests-20260303-111307"
}
```

### Output

JSON with structured failure data:

```json
{
  "log_folder": "D:\\datrix\\.generated\\...",
  "test_type": "unit" | "deploy",
  "clusters": [
    {
      "cluster_id": 1,
      "representative_error_id": "failure-001",
      "error_message": "ImportError: cannot import name 'UserRepository' from 'repositories'",
      "traceback": [
        {"file": "src/services/user_service.py", "line": 12, "code": "from repositories import UserRepository"}
      ],
      "generated_file": "D:\\datrix\\.generated\\...\\src\\services\\user_service.py",
      "generated_code_snippet": "from repositories import UserRepository\n\nclass UserService:\n    ...",
      "codegen_hint": {
        "probable_template": "service.py.j2",
        "probable_generator": "service_generator.py"
      },
      "affected_services": ["library"],
      "count": 3
    }
  ],
  "total_failures": 3,
  "unique_clusters": 1
}
```

For deploy tests with pre-integration failures (docker-build, health-check), read `deploy-test-output.log` instead and extract build error messages.

### Notes

- This phase is I/O-heavy (reading JSON + log files) but requires minimal reasoning
- Parallelizable: up to 3 log folders can be parsed concurrently
- Output is consumed by root cause analysis phase (Opus)
<!-- END_PHASE: log_parsing -->

<!-- PHASE: root_cause_analysis -->
## Phase 2: Root Cause Analysis

Trace failures from parsed failure data to codegen source (generator + template) and build causal chains.

### Input

Parsed failure data from log_parsing phase:

```json
{
  "log_folders": [
    {
      "log_folder": "...",
      "clusters": [...]
    }
  ]
}
```

### Steps

For each failure cluster:

#### Step 1: Identify codegen source

1. **If `codegen_hint` exists:**
   - Start with `probable_generator` and `probable_template` from hint
   - Read the generator file and search for the template rendering call
   - Confirm this is the source

2. **If NO `codegen_hint`:**
   - From `generated_file`, determine the generated artifact type (entity model, service, repository, etc.)
   - Infer likely generator from naming patterns (e.g., `UserService` → `service_generator.py`)
   - Search for template that generates this file type

3. **Read the generator file:**
   - Locate the function that renders this template
   - Understand what data is passed to the template
   - Identify where the data comes from (parsed DSL, transformers, etc.)

4. **Read the template file:**
   - Understand the template logic
   - Identify the line that generates the failing code
   - Check template conditionals/loops that control this output

#### Step 2: Trace causal chain

Build a complete causal chain from DSL input to broken output:

```
.dtrx DSL definition
  ↓ parsed by TreeSitterParser
  ↓ transformed by {transformer_name}
  ↓ passed to {generator_function} as {data_structure}
  ↓ template {template_file:line} generates {code_line}
  ↓ broken output: {error in generated code}
```

#### Step 3: Determine root cause and confidence

**Root cause types:**
- Missing validation (generator accepts invalid DSL)
- Incorrect data transformation (transformer produces wrong structure)
- Template logic error (wrong conditional, missing null check)
- Missing feature (DSL syntax not yet implemented)

**Confidence levels:**
- **HIGH:** Clear template bug or generator logic error, fix is obvious
- **MEDIUM:** Root cause identified but fix approach unclear (multiple solutions)
- **LOW:** Cannot determine root cause, or cause is outside codegen scope (e.g., external library issue)

### Output

JSON with root causes:

```json
{
  "root_causes": [
    {
      "root_cause_id": 1,
      "title": "Service generator missing repository import",
      "cluster_ids": [1],
      "generator_file": "d:\\datrix\\datrix-codegen-python\\src\\generators\\service_generator.py",
      "generator_line": 145,
      "template_file": "d:\\datrix\\datrix-codegen-python\\templates\\service.py.j2",
      "template_line": 12,
      "causal_chain": [
        ".dtrx defines service with repository dependency",
        "ServiceTransformer extracts dependencies list",
        "ServiceGenerator passes dependencies to template",
        "Template iterates dependencies but skips imports for repositories (only imports entities)",
        "Generated service.py missing 'from repositories import UserRepository'"
      ],
      "confidence": "HIGH",
      "fix_approach": "Add repository imports to template's import section",
      "affected_examples": ["01-foundation/01-library"]
    }
  ]
}
```

### Confidence Gate

- **HIGH confidence on all root causes** → proceed to fix_planning phase automatically
- **MEDIUM confidence on any root cause** → STOP, present diagnosis, WAIT for user approval
- **LOW confidence** → Write issue report to `d:\datrix\issues\` and STOP

**Issue report format (LOW confidence):**

```markdown
# Codegen Issue: {title}

**Date:** {date}
**Log folder:** {path}
**Confidence:** LOW

## Failure Summary

{error message}
{generated file path}
{cluster count} occurrences

## Investigation

{what was examined}
{why root cause is unclear}

## Recommendation

{manual investigation steps}
{possible causes to explore}
```

Write to: `d:\datrix\issues\codegen-issue-{timestamp}.md`

### End-of-Phase Report

```
ROOT CAUSE ANALYSIS COMPLETE:

Root causes identified: {N}

1. {Root cause title}
   - Generator: {file:line}
   - Template: {file:line}
   - Confidence: HIGH/MEDIUM
   - Affected examples: {list}

2. {Root cause title}
   ...

{If HIGH confidence on all:}
Proceeding to fix planning phase.

{If MEDIUM confidence on any:}
Diagnosis complete with MEDIUM confidence. Review before proceeding?
```
<!-- END_PHASE: root_cause_analysis -->

<!-- PHASE: fix_planning -->
## Phase 3: Fix Planning

Design minimal fixes for each root cause identified in root cause analysis.

### Input

Root causes from root_cause_analysis phase:

```json
{
  "root_causes": [...]
}
```

### Steps

For each root cause:

#### Step 1: Design the fix

1. **State exact files and lines to change:**
   - Generator file: `{path}:{line}` — {what to change}
   - Template file: `{path}:{line}` — {what to change}

2. **Describe the change:**
   - Brief description (1-2 sentences)
   - What was wrong
   - What the fix does

3. **Estimate scope:**
   - **Small:** 1-2 files, <20 lines total
   - **Medium:** 3-5 files, 20-50 lines
   - **Large:** 6+ files or >50 lines

4. **Check for logic map markers:**
   - Search for `@canonical`, `@pattern`, `@boundary`, `@invariant` markers in files to be modified
   - If marker exists on modified code, note that it must be updated

#### Step 2: Validate the fix design

- Ensure fix is minimal (no scope creep)
- Ensure fix addresses root cause (not just symptoms)
- Ensure fix does not introduce new issues (check for side effects)

### Output

JSON with fix plans:

```json
{
  "fix_plans": [
    {
      "root_cause_id": 1,
      "root_cause_title": "Service generator missing repository import",
      "files_to_modify": [
        {
          "file": "d:\\datrix\\datrix-codegen-python\\templates\\service.py.j2",
          "line": 12,
          "change": "Add repository imports to import section (iterate service.repositories, add 'from repositories import {Name}Repository')"
        }
      ],
      "scope": "Small",
      "logic_map_markers": [],
      "estimated_lines_changed": 5
    }
  ],
  "total_files": 1,
  "total_lines": 5,
  "estimated_scope": "Small"
}
```

### Confidence Gate

- **All fixes are Small/Medium scope and clear** → proceed to fix_implementation phase automatically
- **Any fix is Large scope** → STOP, present plan, WAIT for user approval
- **Scope exceeds 2x what diagnosis suggested** → STOP (runaway detection)

**Large scope approval format:**

```
FIX PLAN REQUIRES APPROVAL:

Root cause: {title}
Estimated scope: Large ({N} files, {M} lines)

Files to modify:
- {file:line} — {change}
- {file:line} — {change}

Reason for large scope:
{why this fix is large}

Proceed with this fix?
```

### End-of-Phase Report

```
FIX PLANNING COMPLETE:

1. {Root cause 1 title}
   - Files: {file:line}
   - Change: {description}
   - Scope: Small

2. {Root cause 2 title}
   - Files: {file:line}, {file:line}
   - Change: {description}
   - Scope: Medium

Total estimated scope: {N} files, {M} line changes

{If all Small/Medium:}
Proceeding to fix implementation phase.

{If any Large:}
Large-scope fix detected. Approval required before proceeding.
```
<!-- END_PHASE: fix_planning -->

<!-- PHASE: fix_implementation -->
## Phase 4: Fix Implementation

Apply fixes one at a time with verification between each fix.

### Input

Fix plans from fix_planning phase:

```json
{
  "fix_plans": [...]
}
```

### Steps

Process fixes in priority order (highest-confidence first). For each fix:

#### Step A: Apply Fix

1. **Read the file(s) to be modified** (use Read tool)
2. **Make the smallest possible edit** (use Edit tool)
   - Follow the exact change description from fix plan
   - NO debug logging (no print(), no logger.warning(), no temporary instrumentation)
   - NO unrelated changes (stay within stated scope)
3. **Update logic map markers** if they exist on modified code:
   - If marker exists, update the summary/rules
   - If deleting marked code, remove the marker entirely

#### Step B: Verify Fix Against Originally-Failing Tests

**IMPORTANT:** Do NOT run the full test suite after each fix. Instead, verify the fix resolves the originally-failing tests.

**Verification strategy:**

1. **If originally-failing tests can be run directly** (unit/integration tests with specific test IDs):
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "{test-path}::{test-name}" -Project {package-name}
   ```
   Run each originally-failing test individually to confirm the fix resolves it.

2. **If originally-failing tests require generation** (e2e tests that generate code):
   - Skip running tests after each individual fix
   - Proceed to next fix
   - Run full test suite ONLY after ALL fixes are applied (in Step C below)

**Assess results (for directly-runnable tests only):**
- **If originally-failing test(s) now PASS:** Report success, move to next root cause
- **If originally-failing test(s) still FAIL:** Assess whether new failure is related to the fix:
  - Related → adjust fix (max 3 attempts per root cause)
  - Same error as before → fix incomplete, investigate further
  - Different error → fix introduced regression, investigate

**For fixes that cannot be verified individually:** Simply report "Fix applied, verification deferred to final test run"

#### Step C: Checkpoint Report

After each fix:

```
CHECKPOINT — Root Cause #{N}: {title}
Status: FIXED / FAILED / DEFERRED
Changed: {file:line} — {what changed}
Verification: {result}
```

**If originally-failing tests were verified and PASS:**
```
CHECKPOINT — Root Cause #1: Import path incorrect
Status: FIXED
Changed: python_visitor_expressions.py:393 — Changed import from base to entity
Verification: 2 originally-failing tests now PASS
```

**If verification was deferred (e2e tests requiring generation):**
```
CHECKPOINT — Root Cause #2: PolyString not converted to str
Status: FIXED (verification deferred)
Changed: _entity_relationships.py:578 — Added str() conversion
Verification: Deferred to final test run (requires generation)
```

**If originally-failing tests still FAIL (will retry):**
```
CHECKPOINT — Root Cause #1: Import path incorrect
Status: FAILED (attempt 1/3)
Changed: python_visitor_expressions.py:393 — Changed import from base to entity
Verification: Originally-failing tests still fail with same error

Adjusting fix (attempt 2/3)...
```

### Output

JSON with fix results:

```json
{
  "fix_results": [
    {
      "root_cause_id": 1,
      "status": "FIXED",
      "files_modified": ["templates/service.py.j2"],
      "attempts": 1,
      "tests_passing": 42,
      "tests_total": 42
    },
    {
      "root_cause_id": 2,
      "status": "FAILED",
      "files_modified": [],
      "attempts": 3,
      "reason": "Could not fix within 3 attempts",
      "last_error": "AssertionError: Generated code missing async keyword"
    }
  ],
  "fixes_applied": 1,
  "fixes_failed": 1
}
```

### Abort Conditions

STOP immediately if:
- Modified more than **double** the estimated number of files
- Working for **more than 3 attempts** on a single root cause without convergence
- Fix reveals **cascading issues** in unrelated subsystems
- New test failures appear in **different codegen package** than the one being modified
- About to modify code **outside stated language/generator scope**

On abort, report what was fixed, what failed, and what remains.

### Anti-Patterns

- **NO fixing generated code directly** — always fix the generator/template
- **NO debug scatter** — zero temporary logging
- **NO cross-language fixes** — stay in the declared scope (Python or TypeScript)
- **NO running full test suite after each fix** — verify originally-failing tests only, run full suite AFTER all fixes
- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

### Best Practices

- Fail fast and loud: if originally-failing tests still fail, STOP and report
- Read before editing: always use Read tool to see current code state
- Minimal edits: change only what fix plan specifies
- Update markers: maintain logic map markers on modified code
- Defer verification when tests require generation (e2e tests)

### End-of-Phase Report

```
FIX IMPLEMENTATION COMPLETE:

Fixes applied: {N}
Fixes failed: {N}

Changes made:
1. {file:line} — {what changed} — fixes {root cause title} — {verification status}
2. {file:line} — {what changed} — fixes {root cause title} — {verification status}

{If any fixes need deferred verification:}
Some fixes require full test suite run to verify (e2e tests that depend on generation).

Proceeding to full test suite verification...
```
<!-- END_PHASE: fix_implementation -->

<!-- PHASE: full_test_verification -->
## Phase 4.5: Full Test Suite Verification

**IMPORTANT:** This phase runs AFTER all fixes are applied to verify:
1. Originally-failing tests now pass
2. No new test failures were introduced

### Input

All applied fixes from fix_implementation phase.

### Steps

#### Step 1: Run Full Codegen Package Test Suite

Run the complete test suite for the affected codegen package:

```
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Fast
```

**Determine package name from file path:**
- `datrix-codegen-python/...` → `datrix-codegen-python`
- `datrix-codegen-typescript/...` → `datrix-codegen-typescript`
- `datrix-codegen-common/...` → `datrix-codegen-common`
- etc.

#### Step 2: Assess Results

Compare results to original failures:

**SUCCESS criteria:**
- All originally-failing tests now PASS
- No new test failures introduced
- Test count increased or stayed the same (if tests were added/fixed)

**PARTIAL SUCCESS criteria:**
- Some originally-failing tests now PASS
- Some originally-failing tests still FAIL with SAME error (incomplete fix)
- No new unrelated failures

**REGRESSION criteria:**
- New test failures introduced that weren't in original failure set
- Originally-failing tests now fail with DIFFERENT error
- Test count decreased (tests broken by fix)

#### Step 3: Handle Results

**If SUCCESS:**
```
FULL TEST VERIFICATION: PASS

Originally failing: {N} tests
Now passing: {N} tests
New failures: 0

All fixes verified successfully.
Proceeding to regeneration phase.
```

**If PARTIAL SUCCESS:**
```
FULL TEST VERIFICATION: PARTIAL

Originally failing: {N} tests
Now passing: {M} tests ({M < N})
Still failing: {K} tests (same errors)
New failures: 0

Fixed root causes: {list}
Unresolved root causes: {list}

Proceed to regeneration for successfully-fixed issues, or debug remaining failures?
```
WAIT for user decision.

**If REGRESSION:**
```
FULL TEST VERIFICATION: REGRESSION DETECTED

Originally failing: {N} tests
Now passing: {M} tests
New failures: {K} tests

New failures introduced:
- {test name} — {error}
- {test name} — {error}

STOPPING: Fixes introduced new failures.
Analysis needed before proceeding.
```
WAIT for user decision.

### Output

```json
{
  "verification_status": "SUCCESS" | "PARTIAL" | "REGRESSION",
  "originally_failing_count": 12,
  "now_passing_count": 12,
  "new_failures_count": 0,
  "tests_total": 3934,
  "tests_passing": 3934
}
```

### End-of-Phase Report

```
FULL TEST SUITE VERIFICATION COMPLETE:

Test suite: {package-name}
Result: {SUCCESS / PARTIAL / REGRESSION}

Originally failing: {N} tests → Now passing: {M} tests
New failures: {K} tests
Total: {pass}/{total} PASS

{If SUCCESS:}
All originally-failing tests now pass. No regressions detected.

{If PARTIAL:}
Progress made but some issues remain. See unresolved root causes above.

{If REGRESSION:}
Fixes introduced new failures. Review and adjust before proceeding.
```
<!-- END_PHASE: full_test_verification -->

<!-- PHASE: regeneration -->
## Phase 5: Regeneration and Verification (Optional)

**Note:** This phase is OPTIONAL and only needed for deploy test failures or when explicitly requested. For unit/integration test failures that were verified in Phase 4.5, this phase can be skipped.

Regenerate affected examples and verify generated code is correct.

### Input

Fix results from fix_implementation phase + original log folder paths:

```json
{
  "fix_results": [...],
  "affected_examples": ["01-foundation/01-library", "02-features/05-infra"],
  "original_log_folders": [...]
}
```

### Steps

For each affected example:

#### Step 1: Regenerate the example

Run the generation script:

```
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -TestSet {test-set} -L {language}
```

**Determine test set and language from example path:**
- `01-foundation/01-library` → `-TestSet foundation -L python`
- `02-features/...` → `-TestSet features -L python`

Record:
- Generation output (success/failure)
- Files regenerated (count)

#### Step 2: Verify originally-failing tests

**For unit test failures:**

Run unit tests on regenerated output:
```
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
```

Compare to original failure:
- **If tests now PASS:** Success (fix worked)
- **If tests still FAIL:** Check if failure is the same as before:
  - Same failure → fix did NOT resolve issue
  - Different failure → fix introduced regression

**For deploy test failures:**

Regeneration is complete. Report that deploy test is recommended (deploy tests are too costly to run in this phase):

```
Example regenerated: {example}
Deploy test RECOMMENDED (not run in this phase due to cost)
```

#### Step 3: Check for debug artifacts

Run the debug artifact check:

```
powershell -File "d:/datrix/datrix/scripts/dev/check-debug-artifacts.ps1" {affected-packages}
```

**Determine affected packages from fix results:**
- If `datrix-codegen-python` was modified → check Python-generated examples
- If `datrix-codegen-typescript` was modified → check TypeScript-generated examples

Report:
- CLEAN (no debug artifacts)
- FOUND (list debug artifacts detected)

### Output

JSON per example:

```json
{
  "example": "01-foundation/01-library",
  "regeneration_status": "SUCCESS",
  "files_regenerated": 42,
  "test_type": "unit",
  "tests_passing": 12,
  "tests_total": 12,
  "originally_failing_tests": "PASS",
  "debug_artifacts": "CLEAN"
}
```

OR (for deploy tests):

```json
{
  "example": "02-features/05-infra",
  "regeneration_status": "SUCCESS",
  "files_regenerated": 87,
  "test_type": "deploy",
  "deploy_test_recommendation": "Run deploy test to verify health-check phase now passes",
  "debug_artifacts": "CLEAN"
}
```

### Checkpoint Report

For each example:

```
CHECKPOINT — Example: {example}
Status: REGENERATED
Files regenerated: {N}
Tests: {pass}/{total} PASS / DEPLOY TEST RECOMMENDED
Debug artifacts: CLEAN
```

### End-of-Phase Report

```
REGENERATION COMPLETE:

Examples regenerated: {N}

1. {example 1}
   - Files: {N} regenerated
   - Tests: {pass}/{total} PASS

2. {example 2}
   - Files: {N} regenerated
   - Tests: DEPLOY TEST RECOMMENDED

Debug artifact check: CLEAN

{If any tests still failing:}
Unresolved failures:
- {example} — {test name} — {error} (same as original / different failure)
```
<!-- END_PHASE: regeneration -->

## Final Report

After all phases complete:

```
TROUBLESHOOT-AND-FIX COMPLETE

Root causes diagnosed: {N}
Fixes applied: {N}
Fixes failed: {N}

Changes made:
1. {file:line} — {what changed} — fixes {root cause title}
2. {file:line} — {what changed} — fixes {root cause title}

Verification:
- Codegen package tests: {pass}/{total} PASS
- Regenerated examples: {N}
- Originally failing tests: {PASS / NEEDS_DEPLOY_TEST}

Unresolved (if any):
- {root cause that could not be fixed} — reason: {why}

Performance Metrics (if instrumented):
- Cost: ${total_cost}
- Latency: {total_duration}s
- Phases successful: {success_count}/{total_count}
```

## Abort Conditions

STOP the pipeline immediately if:

- Modified more than **double** the estimated number of files
- Working for **more than 5 fix attempts** without convergence
- Fix reveals **cascading issues** in unrelated subsystems
- About to modify code **outside stated language/generator scope**
- New test failures appear that are **unrelated** to the root cause

On abort, write a partial issue report to `d:\datrix\issues\` documenting what was diagnosed, what was attempted, and what remains.

## Anti-Patterns

- **NO exploring the project structure** — read `.project-structure.md` for the target package, don't rediscover it
- **NO fixing generated code directly** — always fix the generator/template
- **NO debug scatter** — zero temporary logging
- **NO cross-language fixes** — stay in the declared scope
- **NO guessing** — read the code at every phase boundary
- **NO skipping regeneration** — always verify the fix produces correct output
- **NO batch-fixing** — one root cause at a time with verification
- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
