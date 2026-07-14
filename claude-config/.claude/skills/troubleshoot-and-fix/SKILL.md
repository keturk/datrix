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

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` for the mandatory documentation reads and the Project Structure step.

## Scope Check

After reading mandatory documents and BEFORE investigation:

1. **Count log folders** — each is a multi-step investigation
2. **Confirm language scope** — Python or TypeScript? Do NOT cross languages.
3. **If more than 3 distinct failure categories:** STOP and propose splitting.

**Checkpoint discipline:** After each phase below, emit a lean checkpoint — phase name, counts (causes/files/fixes), and any blocker — one line per data point. Do not use a mad-lib narrative template; the compact form is sufficient for the orchestrator and the user to track progress.

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

**Extraction is scripted.** Run the collector on the log folder and read the resulting `failure-data.json` — it contains the clusters, each cluster's representative (error message, traceback tail, `codegen_hint`, `generated_file`), member test ids, and counts (read `datrix/scripts/test/quick-reference.md` before invoking; a pre-tool hook enforces this):

```bash
powershell -File "d:/datrix/datrix/scripts/test/collect-failure-data.ps1" "{log-folder}"
```

Then read directly from `index.json` ONLY the small top-level fields the collector does not re-emit:
1. `services[]` — which services failed (skip passing services entirely)
2. For deploy tests: `failed_phase` and `phases{}` — if the failed phase is pre-integration (docker-build, health-check), check `deploy-test-output.log` instead of failure logs

**DO NOT** read `index.json`'s `failures[]`/`failure_clusters[]` arrays by hand, `summary.txt`, `unit-tests-summary.log`, or full service logs unless the collector output is insufficient. **DO NOT** read every file in the `failures/` directory — use the cluster representative only.

#### Step 2: Representative tracebacks (mostly embedded)

`failure-data.json` already embeds each representative's traceback tail. Read the representative's full log file (its `log_file`, relative to the run dir) only when the tail is insufficient for diagnosis.

Extract per cluster:
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

Structured failure data, one entry per cluster:
- `log_folder` — the folder this data was parsed from
- `test_type` — `unit` or `deploy`
- `clusters[].cluster_id` — cluster identifier
- `clusters[].representative_error_id` — the failure chosen to represent the cluster
- `clusters[].error_message` — the representative error text
- `clusters[].traceback` — file/line/code entries leading to the failure
- `clusters[].generated_file` — path to the broken generated file
- `clusters[].generated_code_snippet` — the relevant broken code
- `clusters[].codegen_hint.probable_template` / `probable_generator` — pre-identified suspects
- `clusters[].affected_services` — services hit by this cluster
- `clusters[].count` — occurrences of this cluster
- `total_failures`, `unique_clusters` — totals across all clusters

For deploy tests with pre-integration failures (docker-build, health-check), read `deploy-test-output.log` instead and extract build error messages.

### Notes

- This phase is now mostly scripted: one `collect-failure-data.ps1` call per log folder replaces the bulk of the JSON/log reading; what remains is assembling the per-cluster snippets
- Parallelizable: up to 3 log folders can be parsed concurrently (rarely needed now — prefer sequential script calls over spawning parse agents)
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

Root causes, one entry per identified cause:
- `root_cause_id` — identifier
- `title` — short description
- `cluster_ids` — which clusters from Phase 1 this explains
- `generator_file` / `generator_line` — the generator source location
- `template_file` / `template_line` — the template source location
- `causal_chain` — ordered list from `.dtrx` definition through transformer/generator/template to the broken output
- `confidence` — HIGH / MEDIUM / LOW
- `fix_approach` — one-sentence description of the fix
- `affected_examples` — examples this root cause affects

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

Fix plans, one entry per root cause:
- `root_cause_id` / `root_cause_title` — which root cause this plans for
- `files_to_modify[].file` / `line` / `change` — exact edit locations and descriptions
- `scope` — Small / Medium / Large
- `logic_map_markers` — markers found on code to be modified
- `estimated_lines_changed` — rough line count
- `total_files`, `total_lines`, `estimated_scope` — totals across all fix plans

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

After each fix, emit the generic lean checkpoint (per the Checkpoint discipline note above): root cause #, status (FIXED / FAILED / DEFERRED), file:line changed, and verification result (tests now passing / deferred to final run / still failing — attempt N/3).

### Output

Fix results, one entry per root cause:
- `root_cause_id` — which root cause
- `status` — FIXED / FAILED
- `files_modified` — files changed
- `attempts` — attempts used
- `tests_passing` / `tests_total` — verification counts (when directly verifiable)
- `reason`, `last_error` — present only when `status` is FAILED
- `fixes_applied`, `fixes_failed` — totals across all root causes

(Abort conditions and anti-patterns for this phase are covered by the pipeline-wide sections at the end of this document — nothing phase-specific to add here.)

### Best Practices

- Fail fast and loud: if originally-failing tests still fail, STOP and report
- Read before editing: always use Read tool to see current code state
- Minimal edits: change only what fix plan specifies
- Update markers: maintain logic map markers on modified code
- Defer verification when tests require generation (e2e tests)
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

#### Step 2: Assess Results (scripted)

When a pre-fix run directory for the same package exists, compute the comparison with the delta script instead of eyeballing counts:

```bash
powershell -File "d:/datrix/datrix/scripts/test/classify-run-delta.ps1" -Previous "{pre-fix-run-dir}" -Current "{new-run-dir}"
```

Its verdict maps directly onto the criteria below (`run-delta.json` in the new run dir carries the `now_passing` / `still_failing` / `new_failures` lists). Without a comparable previous run, assess manually:

**SUCCESS criteria** (delta verdict `SUCCESS`):
- All originally-failing tests now PASS
- No new test failures introduced
- Test count increased or stayed the same (if tests were added/fixed)

**PARTIAL SUCCESS criteria** (delta verdict `PARTIAL`):
- Some originally-failing tests now PASS
- Some originally-failing tests still FAIL with SAME error (incomplete fix)
- No new unrelated failures

**REGRESSION criteria** (delta verdict `REGRESSION`, or a still-failing test whose error changed):
- New test failures introduced that weren't in original failure set
- Originally-failing tests now fail with DIFFERENT error
- Test count decreased (tests broken by fix)

#### Step 3: Handle Results

Report one template with the applicable status:
```
FULL TEST VERIFICATION: {SUCCESS | PARTIAL | REGRESSION}

Originally failing: {N} tests
Now passing: {M} tests
New failures: {K} tests
Fixed root causes: {list}
Unresolved root causes: {list, if any}
New failures introduced: {list, if REGRESSION}
```
- **SUCCESS** (`M == N`, `K == 0`): all fixes verified, proceed to regeneration phase.
- **PARTIAL** (`M < N`, `K == 0`, remaining failures same error as before): WAIT for user decision — proceed to regeneration for fixed issues, or debug remaining failures.
- **REGRESSION** (`K > 0`, or an originally-failing test now fails with a different error): STOP — fixes introduced new failures, analysis needed. WAIT for user decision.

### Output

- `verification_status` — SUCCESS / PARTIAL / REGRESSION
- `originally_failing_count`, `now_passing_count`, `new_failures_count` — counts driving the status above
- `tests_total`, `tests_passing` — full suite totals
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

The full-suite gate already ran in Phase 4.5 — here, run ONLY the originally-failing scoped tests against the regenerated output:
```
powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "{test-path}::{test-name}" -Project {package-name}
```
(or `test.ps1 {package-name} -Specific "{pattern}"` if scoping by pattern rather than a single test ID)

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

Per example:
- `example` — example name
- `regeneration_status` — SUCCESS / FAILURE
- `files_regenerated` — count
- `test_type` — unit / deploy
- `tests_passing` / `tests_total` — unit tests only
- `originally_failing_tests` — PASS / still failing (unit tests only)
- `deploy_test_recommendation` — present for deploy tests instead of test counts (deploy tests are not run in this phase due to cost)
- `debug_artifacts` — CLEAN / FOUND (list)

After each example, emit the generic lean checkpoint (per the Checkpoint discipline note above).
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
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
