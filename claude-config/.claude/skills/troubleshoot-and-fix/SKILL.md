---
description: Diagnose generated code test failures, trace to codegen root causes, implement fixes, and verify
delegation-strategy:
  phases:
    - name: "log_parsing"
      model: "haiku"
      parallelizable: true
      max_parallel: 3
      description: "Parse test failure logs and extract structured failure data"
    - name: "root_cause_analysis"
      model: "opus"
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

## Mandatory Reading (BEFORE any work)

Before doing ANY work, read these documents in full:

1. **`d:\datrix\.claude\CLAUDE.md`** — Project rules. All rules apply throughout.
2. **`C:\Users\KErca\.claude\projects\d--datrix\memory\MEMORY.md`** — Persistent memory.
3. **`d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md`** — Full contributing rules (index with links to sub-documents under `ai-agent-rules/`).

## Scope Check

After reading mandatory documents and BEFORE investigation:

1. **Count log folders** — each is a multi-step investigation
2. **Confirm language scope** — Python or TypeScript? Do NOT cross languages.
3. **If more than 3 distinct failure categories:** STOP and propose splitting.

<!-- PHASE: log_parsing -->
## Phase 1: Log Parsing

Parse test failure logs and extract structured failure data for root cause analysis.

### Mandatory Reading

Before proceeding, read these documents in full:

1. **`d:\datrix\.claude\CLAUDE.md`** — Project rules
2. **`C:\Users\KErca\.claude\projects\d--datrix\memory\MEMORY.md`** — Persistent memory
3. **`d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md`** — Contributing rules

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

#### Step B: Run Codegen Package Tests

Run tests for the affected codegen package:

```
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
```

**Determine package name from file path:**
- `datrix-codegen-python/...` → `datrix-codegen-python`
- `datrix-codegen-typescript/...` → `datrix-codegen-typescript`
- etc.

**Assess results:**
- **If tests pass:** Report success, move to next root cause
- **If tests FAIL:** Assess whether failure is related to the fix:
  - Related → adjust fix (max 3 attempts per root cause)
  - Unrelated → STOP and report (this is a critical error)

#### Step C: Checkpoint Report

After each fix (successful or failed):

```
CHECKPOINT — Root Cause #{N}: {title}
Status: FIXED / FAILED (attempt {X}/3)
Changed: {file:line} — {what changed}
Tests: {pass}/{total} passing
```

**If tests PASS:**
```
CHECKPOINT — Root Cause #1: Service generator missing repository import
Status: FIXED
Changed: templates/service.py.j2:12 — Added repository imports
Tests: 42/42 passing
```

**If tests FAIL (related to fix, will retry):**
```
CHECKPOINT — Root Cause #1: Service generator missing repository import
Status: FAILED (attempt 1/3)
Changed: templates/service.py.j2:12 — Added repository imports
Tests: 40/42 passing

New failures:
- test_service_with_multiple_repos — AssertionError: Expected 2 imports, got 1

Adjusting fix (attempt 2/3)...
```

**If tests FAIL (unrelated, STOP):**
```
CHECKPOINT — Root Cause #1: Service generator missing repository import
Status: FAILED (unrelated test failures introduced)
Changed: templates/service.py.j2:12 — Added repository imports
Tests: 35/42 passing

Unrelated failures introduced:
- test_entity_generator — ImportError (NOT related to service generator)
- test_repository_generator — SyntaxError (NOT related to service generator)

STOPPING: Fix introduced cascading failures in unrelated generators.
Reverting change and reporting to user.
```

**WAIT for user decision.**

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
- **NO batch-fixing** — one root cause at a time with verification

### Best Practices

- Fail fast and loud: if tests fail unexpectedly, STOP and report
- Read before editing: always use Read tool to see current code state
- Minimal edits: change only what fix plan specifies
- Update markers: maintain logic map markers on modified code

### End-of-Phase Report

```
FIX IMPLEMENTATION COMPLETE:

Fixes applied: {N}
Fixes failed: {N}

Changes made:
1. {file:line} — {what changed} — fixes {root cause title}
2. {file:line} — {what changed} — fixes {root cause title}

Codegen package tests: {pass}/{total} PASS

{If any failed:}
Unresolved:
- {root cause title} — reason: {why}
```
<!-- END_PHASE: fix_implementation -->

<!-- PHASE: regeneration -->
## Phase 5: Regeneration and Verification

Regenerate affected examples and verify that originally-failing tests now pass.

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

- **NO fixing generated code directly** — always fix the generator/template
- **NO debug scatter** — zero temporary logging
- **NO cross-language fixes** — stay in the declared scope
- **NO guessing** — read the code at every phase boundary
- **NO skipping regeneration** — always verify the fix produces correct output
- **NO batch-fixing** — one root cause at a time with verification
