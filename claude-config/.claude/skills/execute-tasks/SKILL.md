---
description: Execute implementation tasks from task files — read, implement, verify, mark complete
disable-model-invocation: true
delegation-strategy:
  phases:
    - name: "pre_check"
      model: "haiku"
      parallelizable: false
      description: "Read task files, validate dependencies, identify quality gates"
    - name: "implement"
      model: "sonnet"
      parallelizable: false
      description: "Apply code changes per task specification"
    - name: "verify"
      model: "haiku"
      parallelizable: true
      max_parallel: 5
      description: "Run targeted tests, fix all failures"
    - name: "quality_gate"
      model: "opus"
      parallelizable: false
      description: "Run full suite for final validation"
---

# Execute Tasks

Systematic workflow for implementing tasks from `.tasks/` phase files. Reads each task file, implements it following project standards, verifies the result, fixes all test failures, updates the task file with how it was solved, and marks it complete.

**Assumes all tests are passing before starting.** Does not capture baselines.

## When to Use

- User provides one or more task file paths and asks to implement them
- User says "execute tasks", "implement these tasks", or "work on phase N"
- User points to a `.tasks/phase-{NN}/` directory and wants tasks completed
- After `/generate-tasks` or `/operationalize-design` has produced task files

## How to Invoke

```
/execute-tasks

TASKS:
d:\datrix\datrix-common\.tasks\phase-05\task-05-01-generator-base.md
d:\datrix\datrix-common\.tasks\phase-05\task-05-02-template-loader.md
```

Execute all tasks in a phase:
```
/execute-tasks

PHASE: d:\datrix\datrix-common\.tasks\phase-05\
```

Single task:
```
/execute-tasks

TASK: d:\datrix\datrix-common\.tasks\phase-05\task-05-01-generator-base.md
```

## Prereqs
Read first: CLAUDE.md, MEMORY.md, `datrix-common/docs/contributing/ai-agent-rules.md`.

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

<!-- PHASE: pre_check -->
## Phase 1: Pre-Execution Check

Read all task files, validate dependencies, and plan execution order.

### Steps

For each task file provided in the skill invocation:

1. **Read the task file completely**
2. **Extract metadata:**
   - Title (from `# Task {NN}-{TT}: {Title}`)
   - Dependencies (from `**Depends on:**` field in header)
   - Package (from `**Package:**` field)
   - Category (from `**Category:**` field)
3. **Check dependencies:**
   - For each dependency (e.g., `task-40-01-foo`), verify the dependency task file exists
   - Read the dependency task file and check if title starts with `# COMPLETED:`
   - If NOT completed → mark this task as BLOCKED
4. **Verify referenced files exist:**
   - Read the "Files to Review Before Starting" section
   - Check each file path exists on disk
   - If any file does not exist → mark this as a red flag (will ask user for clarification)
5. **Determine language/generator scope:**
   - From the `**Package:**` field, determine if this is Python or TypeScript
   - Check "Files to Create/Modify" — if they mix .py and .ts files, mark as scope error
6. **Identify quality gate tasks:**
   - If `**Category:** Quality Gate` → mark this task as quality_gate type
   - Quality gate tasks MUST execute LAST among all tasks for the package
7. **Identify verification tasks:**
   - If `**Category:** Verification` → mark this task as verification type
   - Verification tasks are verification-only — they check that implementation was done correctly
   - Verification tasks MUST execute AFTER their dependency implementation/test tasks
   - Verification tasks should ideally be executed in a **different session** than the implementation tasks they verify

### Input

Task file paths from skill invocation (provided by user as TASKS:, PHASE:, or TASK:).

### Output

JSON array of tasks in execution order:

```json
[
  {
    "task_path": "d:\\datrix\\.tasks\\phase-40\\task-40-01.md",
    "task_id": "task-40-01",
    "title": "Define Skill Delegation Metadata Schema",
    "package": ".claude/",
    "category": "Implementation",
    "dependencies": [],
    "language_scope": "documentation",
    "is_quality_gate": false,
    "is_blocked": false,
    "files_to_review": ["d:\\datrix\\.claude\\README.md"],
    "files_to_create": ["d:\\datrix\\.claude\\docs\\skill-delegation-schema.md"],
    "files_to_modify": [],
    "red_flags": []
  },
  {
    "task_path": "d:\\datrix\\.tasks\\phase-40\\task-40-02.md",
    "task_id": "task-40-02",
    "title": "Design Phase Orchestrator Specification",
    "package": ".claude/",
    "category": "Implementation",
    "dependencies": ["task-40-01-skill-metadata-schema"],
    "language_scope": "documentation",
    "is_quality_gate": false,
    "is_blocked": false,
    "files_to_review": ["d:\\datrix\\.claude\\docs\\skill-delegation-schema.md"],
    "files_to_create": ["d:\\datrix\\.claude\\docs\\phase-orchestrator-spec.md"],
    "files_to_modify": [],
    "red_flags": []
  }
]
```

### Error Conditions

- **Dependency not completed:** Task is BLOCKED. Mark `is_blocked: true`, record which dependency is incomplete.
- **Task file does not exist:** Mark as red flag: `"Task file not found at specified path"`
- **Referenced file does not exist:** Mark as red flag: `"File to review does not exist: {path}"`
- **Mixed language scope:** Mark as red flag: `"Task mixes Python and TypeScript files"`

If ANY task has `is_blocked: true` or non-empty `red_flags[]`, STOP and report to user. Do NOT proceed to baseline phase.

### Use the TodoWrite Tool

If more than 5 tasks are provided, create a todo list before completing this phase.
<!-- END_PHASE: pre_check -->

<!-- PHASE: implement -->
## Phase 2: Implementation

For each task (sequentially, in dependency order), read the task specification and apply the required code changes.

### Input

Task metadata from pre_check phase + baseline results from baseline phase.

### Steps

Process tasks one at a time in dependency order. For each task:

#### Step 1: Understand (Read Only — No Edits)

1. **Read the task file completely**
2. **Read ALL files listed in "Files to Review Before Starting"**
3. **Read existing code** in any files that will be modified (use Read tool)
4. **Study existing Datrix implementation patterns** — do NOT reinvent anything
5. **Search for existing functions/utilities** before writing new code (DRY principle)
6. **Check for ambiguities:**
   - If the task requirements are unclear, STOP and ask for clarification
   - Never guess or assume

**End-of-step assessment:**
- Root understanding (one sentence: what this task accomplishes)
- Files to create/modify (exact paths from task file)
- Dependencies satisfied: YES (already validated in pre_check)
- Ambiguities: NONE / {list of questions}

**If ambiguities exist** → STOP, ask questions, WAIT for answers before proceeding to Step 2.

#### Step 2: Implement (Write Code)

Apply the implementation described in the task file:

1. **Create/modify files** as specified in "Files to Create/Modify"
2. **Follow all code skeletons, type hints, and patterns** from the task file
3. **Check for logic map markers:**
   - Before modifying any function or class, search for `@canonical`, `@pattern`, `@boundary`, `@invariant` markers
   - If a marker exists on code you're modifying, update the marker summary/rules
   - If deleting marked code, remove the marker entirely
4. **Apply full type hints** on all functions
5. **Use standard logging:**
   - `logger = logging.getLogger(__name__)`
   - %-style formatting: `logger.info("event key=%s", value)`
6. **Use Jinja2 templates + formatter for code generation:**
   - Never use raw string concatenation (`code += f"class {name}:"`)
   - Use Jinja2 templates + ruff format (Python) / Prettier (TypeScript)
7. **Delete replaced functionality completely:**
   - No dead code
   - No backward-compatibility wrappers
   - One way to do each thing

**Scope discipline:**
- Stay within the task's stated scope
- If implementation grows beyond what the task describes, STOP and report
- Do NOT make "improvements" to surrounding code beyond what the task requires

**STUCK protocol — report, don't fake it:**
- If implementation hits unexpected complexity (e.g., dependencies missing, patterns unclear, design ambiguity), mark the task as BLOCKED — do NOT write stub/placeholder code and mark it complete
- If you cannot figure out the correct implementation after reading the relevant code, STOP and report what you found and what's unclear
- Writing `pass`, `NotImplementedError`, empty method bodies, or trivial stubs that satisfy type checkers but do nothing is **worse than reporting BLOCKED** — it creates invisible debt that wastes future sessions
- A BLOCKED task with a clear explanation is a success. A fake-completed task is a failure.

**Partial completion is NOT completion:**
- If the task says "delete old path, use new path" and you keep both paths → task is NOT complete
- If a dependency (e.g., executor) has `NotImplementedError` and you work around it with legacy code → mark BLOCKED, not COMPLETED
- If you implement a checker/validator but its checks always return true or are placeholder logic → task is NOT complete
- The test for "is this complete?" is: does the code do what the task's acceptance criteria specify, without workarounds, fallbacks, or dual paths?

**Anti-patterns to avoid:**
- NO `dict.get(key, None)` — raise explicit errors
- NO `type_map.get(t, "Any")` — raise on unknown types
- NO bare `except: pass` — always log and re-raise
- NO `# TODO` / `pass` — implement completely
- NO `-> T | None` error returns — raise descriptive errors
- NO mocks/fakes in tests (`MagicMock`, `Mock`, `patch`, `SimpleNamespace`)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

**Best practices:**
- Fail fast and loud: `raise ExplicitError(f"message with context")`
- Provide helpful messages: `"Not found. Available: [...]"`
- Apply full type hints: `def foo(x: str) -> int:`
- Use immutable models: `ConfigDict(frozen=True)`
- Write comprehensive tests (include error and success cases)

#### Step 3: Mark Implementation Complete

For each task, record:
- Files created (list of paths)
- Files modified (list of paths)
- Key design decisions made

**Quality gate tasks:**
Quality gate tasks (identified by `**Category:** Quality Gate`) are verification-only — they have NO implementation step. Skip Step 2 for quality gate tasks.

**Verification tasks:**
Verification tasks (identified by `**Category:** Verification`) are verification-only — they have NO implementation step. Skip Step 2 for verification tasks. They run their own checklist in the verify phase.

### Input Format

For each task:
```json
{
  "task_path": "...",
  "task_id": "...",
  "is_quality_gate": false
}
```

### Output Format

For each task:
```json
{
  "task_path": "d:\\datrix\\.tasks\\phase-40\\task-40-01.md",
  "task_id": "task-40-01",
  "status": "implemented",
  "files_created": ["d:\\datrix\\.claude\\docs\\skill-delegation-schema.md"],
  "files_modified": [],
  "design_decisions": [
    "Schema enforces self-containment requirement for phase prompts",
    "Phase taxonomy table provides clear Haiku/Sonnet/Opus mapping"
  ],
  "ambiguities_encountered": []
}
```

OR (for quality gate):
```json
{
  "task_path": "...",
  "task_id": "...",
  "status": "skipped_implementation",
  "reason": "Quality gate task (verification-only)"
}
```

### Abort Conditions

STOP immediately if:
- Modified more than **double** the files estimated by the task
- About to modify code **outside the task's stated scope**
- Ambiguities cannot be resolved without user input

On abort, report what was completed, what failed, and what cannot proceed.

### Handling Ambiguity

- Never guess or assume when requirements are unclear
- Never make design decisions on behalf of the user — ask first
- If a file referenced in the task does not exist at the given path, STOP and ask
- If the task contradicts existing code patterns, STOP and ask which approach to follow
<!-- END_PHASE: implement -->

<!-- PHASE: verify -->
## Phase 3: Verification

For each task (in parallel, up to 5 tasks concurrently), run targeted tests and fix all failures (max 3 attempts per task).

**Assumes all tests were passing before implementation started.**

### Input

Task metadata + implementation results.

For each task:
```json
{
  "task_path": "...",
  "task_id": "...",
  "implementation": {"files_created": [...], "files_modified": [...]},
  "is_quality_gate": false
}
```

### Steps

#### Step 1: Run Tests

**Documentation-only tasks — skip verification.**

For tasks that modified code:

1. **Determine test scope:**
   - Read task file's `## Targeted Tests` section
   - If targeted tests exist AND task is NOT quality gate → run targeted tests only
   - If NO targeted tests OR task IS quality gate → run full suite

2. **Run test commands:**

   **Targeted tests:**
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path}"
   ```

   **Full suite (quality gate or backward compatibility):**
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

3. **Record results:**
   - Total tests
   - Pass count
   - Fail count
   - List of failing test names

#### Step 2: Evaluate Results

```
if all tests pass:
    → verification PASSED
else:
    → verification FAILED, proceed to Step 3 (Fix Failures)
```

#### Step 3: Fix All Failures (max 3 attempts)

If any test failures exist:

1. **Invoke fix workflow:**
   - Read failing test file
   - Understand what the test expects
   - Identify root cause of failure
   - Fix the issue (modify code, update test, or both)
   - Re-run tests

2. **Track each attempt:**

   | Attempt | What was tried | Result |
   |---------|---------------|--------|
   | 1       | {description} | {pass/fail + error} |
   | 2       | {description} | {pass/fail + error} |
   | 3       | {description} | {pass/fail + error} |

3. **Outcomes:**
   - **If all tests pass within 3 attempts** → verification PASSED
   - **If tests still failing after 3 attempts** → verification FAILED (proceed to Step 4)
   - **If a fix introduces additional failures** → STOP immediately, revert the fix attempt, report (do NOT count as successful attempt)

#### Step 4: Verification Failed (if not fixed after 3 attempts)

If tests still fail after 3 fix attempts:

1. **Do NOT mark the task COMPLETED**
2. **Update the task file:**
   - Change title to `# FAILED: Task {NN}-{TT}: {Title}`
   - Add `## Why Failed` section immediately after title:

```markdown
## Why Failed

**Test failures after implementation (not fixed after 3 attempts):**

| Attempt | What was tried | Result |
|---------|---------------|--------|
| 1       | {description} | {error} |
| 2       | {description} | {error} |
| 3       | {description} | {error} |

**Failing tests:**
- {test_name} — {error message}

**Recommendation:** {next steps for human review}
```

3. **Do NOT proceed to mark_complete phase for this task**

#### Step 5: Mark Complete (ONLY if verification passed)

If verification PASSED:

1. **Verify files are non-trivial (anti-stub check):**
   For each file in "Files to Create", confirm:
   - File exists on disk
   - File has >10 lines of non-comment, non-import code
   - No `pass` in function/method bodies (search with grep)
   - No `NotImplementedError` in production code
   - No `# TODO` or `# FIXME` markers
   - No always-true/always-false checks that make validators or checkers functionally useless
   - No legacy/old code paths kept alongside new code when the task requires replacement
   If ANY file fails this check → do NOT mark complete. Either fix the implementation or mark BLOCKED.

2. **Verify tests prove the feature, not the gap:**
   - Tests must NOT assert `NotImplementedError` or `NotImplemented` on production code paths — that codifies the gap as "expected behavior"
   - Tests must NOT only test shallow/happy paths while leaving the core behavior untested
   - If the task requires "X replaces Y", tests must prove X works AND Y is gone — not just that the code doesn't crash

3. **Self-contradiction check on "How Solved" narrative:**
   Before writing the "How Solved" section, re-read the task's acceptance criteria. Then check: does your narrative contain any of these red flags?
   - "remains unchanged" / "original path still used" / "legacy code preserved"
   - "future migration" / "when executor supports X" / "not yet wired"
   - "partial" / "workaround" / "fallback to old path"
   - "dual path" / "both old and new" / "backward compatibility layer"
   If ANY of these appear in your narrative, the task is NOT complete. Mark it BLOCKED with an honest explanation.

2. **Update the task file:**
   - Change title from `# Task {NN}-{TT}: {Title}` to `# COMPLETED: Task {NN}-{TT}: {Title}`
   - Add `## How Solved` section immediately after title with **mandatory proof-of-work**:

```markdown
## How Solved

- **`{file_path}`** — {implementation summary}
- **Design decisions:** {key decisions made}
- **Test coverage:** {test summary}

### Proof of Work

**pytest output:**
```
{paste RAW pytest output here — full output, not a summary}
```

**Files created (with line counts):**
- `{file_path}` — {N} lines (non-comment, non-blank)
```

The proof-of-work section is **mandatory**. A task without raw test output in its "How Solved" section is NOT considered properly completed. This evidence allows independent verification without re-running the tools.

**Example:**

```markdown
## How Solved

- **`src/generators/entity_generator.py`** — Implemented EntityGenerator with Jinja2 template rendering, field type mapping, and relationship handling.
- **`templates/entity.py.j2`** — Created Jinja2 template for Python entity models with full type annotation support.
- **`tests/unit/test_entity_generator.py`** — 12 tests covering: basic entity, all field types, relationships, error cases.
- **Design decision:** Used composition over inheritance for generator mixins, matching existing pattern in ServiceGenerator.

### Proof of Work

**pytest output:**
```
tests/unit/test_entity_generator.py::TestEntityGenerator::test_basic_entity PASSED
tests/unit/test_entity_generator.py::TestEntityGenerator::test_field_types PASSED
... (full output)
12 passed in 1.23s
```

**Files created (with line counts):**
- `src/generators/entity_generator.py` — 187 lines
- `templates/entity.py.j2` — 45 lines
- `tests/unit/test_entity_generator.py` — 203 lines
```

**Quality gate tasks:**

For quality gates, the "How Solved" section reports with **mandatory raw output**:

**Example (quality gate):**

```markdown
## How Solved

- **Full test suite:** 185/185 passing
- No files created or modified.

### Proof of Work

**pytest output:**
```
{paste RAW full test suite output}
```
```

**Verification tasks:**

Verification tasks (identified by `**Category:** Verification`) follow their own checklist defined in the task file. They do NOT implement code — they verify that implementation tasks were completed correctly. The "How Solved" section must include:
- Result of each verification checklist item (pass/fail)
- Raw pytest output
- For each file checked: line count and stub-check result
- If ANY check fails: mark the task FAILED and identify which implementation task needs rework

### Output Format

For each task:

**If verification PASSED:**
```json
{
  "task_path": "...",
  "task_id": "...",
  "status": "COMPLETED",
  "tests_run": 12,
  "tests_passing": 12,
  "tests_failing": 0,
  "failures": [],
  "fix_attempts": 0,
  "files_created": [...],
  "files_modified": [...]
}
```

**If verification FAILED:**
```json
{
  "task_path": "...",
  "task_id": "...",
  "status": "FAILED",
  "tests_run": 15,
  "tests_passing": 13,
  "tests_failing": 2,
  "failures": ["test_entity_relationships", "test_field_inheritance"],
  "fix_attempts": 3,
  "fix_attempt_log": [
    {"attempt": 1, "tried": "...", "result": "..."},
    {"attempt": 2, "tried": "...", "result": "..."},
    {"attempt": 3, "tried": "...", "result": "..."}
  ],
  "recommendation": "Review entity relationship logic. Tests expect bidirectional refs but implementation only creates forward refs."
}
```

### Checkpoint Report

After verifying each task, emit:

**If COMPLETED:**
```
CHECKPOINT — Task {NN}-{TT}: {Title}
Status: COMPLETED
Files created: {list}
Files modified: {list}
Tests: {pass}/{total} passing
```

**If FAILED:**
```
CHECKPOINT — Task {NN}-{TT}: {Title}
Status: FAILED (verification failed after 3 fix attempts)
Files created: {list}
Files modified: {list}
Tests: {pass}/{total} passing

Fix attempts:
1. {what was tried} — {result}
2. {what was tried} — {result}
3. {what was tried} — {result}

Failing tests:
- {test_name} — {error}

Recommendation: {next steps}
```

### Abort Conditions

STOP immediately if:
- Working for more than 3 fix attempts on test failures
- A fix attempt introduces additional failures
- Fix reveals cascading issues in unrelated subsystems
- Test failures appear in a different package than the one being modified

On abort, report what was completed, what failed, and what remains.
<!-- END_PHASE: verify -->

<!-- PHASE: quality_gate -->
## Phase 4: Quality Gate

Run the full test suite for the affected package(s) to catch cross-task integration issues.

### Input

Verification results from all tasks:

```json
{
  "tasks": [
    {"task_id": "task-40-01", "status": "COMPLETED", "package": ".claude/"},
    {"task_id": "task-40-02", "status": "COMPLETED", "package": ".claude/"},
    {"task_id": "task-40-03", "status": "FAILED", "package": ".claude/"}
  ]
}
```

### Steps

1. **Determine affected packages:**
   - Group tasks by `package` field
   - For each unique package, prepare to run full suite

2. **For each package, run:**

   **Full test suite:**
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

3. **Attribute failures (if any):**
   - For each new failure, extract the failing test file path
   - Cross-reference against each task's `## Targeted Tests` section
   - Report which task likely introduced the failure

### Output Format

**If quality gate PASSED:**

```json
{
  "status": "COMPLETED",
  "packages_tested": [".claude/"],
  "total_tests": 185,
  "tests_passing": 185,
  "tests_failing": 0
}
```

Emit:
```
CHECKPOINT — Quality Gate — {package-name}
Status: COMPLETED
Tests: 185/185 passing
```

**If quality gate FAILED:**

```json
{
  "status": "FAILED",
  "packages_tested": [".claude/"],
  "total_tests": 185,
  "tests_passing": 183,
  "tests_failing": 2,
  "failures": [
    {
      "test_name": "test_phase_marker_extraction",
      "error": "AssertionError: Expected 5 phases, got 4",
      "likely_source_task": "task-40-03-refactor-execute-tasks-skill"
    }
  ]
}
```

Emit:
```
CHECKPOINT — Quality Gate — {package-name}
Status: FAILED
Tests: 183/185 passing

Failures:
- test_phase_marker_extraction — AssertionError: Expected 5 phases, got 4
  Likely source: Task 40-03 (Refactor /execute-tasks Skill for Delegation)

Recommendation: Re-run task-40-03 with /fix-tests, then re-run quality gate.
```

### Notes

- Quality gate runs AFTER all individual task verifications
- It catches integration issues that might not appear in targeted tests
- If quality gate fails, report which tasks likely introduced the failures
<!-- END_PHASE: quality_gate -->

## Final Report

After all phases complete:

```
EXECUTION COMPLETE

Tasks completed: {N}/{total}
Tasks failed: {N}
Tasks skipped: {N} (dependency not met / blocked)

Completed:
1. Task {NN}-{TT}: {Title} — {files changed summary}
2. Task {NN}-{TT}: {Title} — {files changed summary}

Failed (if any):
- Task {NN}-{TT}: {Title} — Reason: {why}

Remaining (if any):
- Task {NN}-{TT}: {Title} — Blocked by: {what}

Performance Metrics (if instrumented):
- Cost: ${total_cost} (estimated ${monolithic_cost} monolithic, {savings}% reduction)
- Latency: {total_duration}s (estimated {monolithic_duration}s monolithic, {savings}% reduction)
- Phases successful: {success_count}/{total_count}
```
