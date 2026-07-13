---
description: Execute implementation tasks from task files — read, implement, verify, mark complete
model: claude-sonnet-4-6
disable-model-invocation: true
delegation-strategy:
  phases:
    - name: "pre_check"
      model: "haiku"
      parallelizable: false
      description: "Read task files, validate dependencies, identify quality gates"
    - name: "implement"
      model: "claude-sonnet-4-6"
      parallelizable: false
      description: "Apply code changes per task specification"
    - name: "verify"
      model: "haiku"
      parallelizable: true
      max_parallel: 5
      description: "Run targeted tests, fix all failures"
    - name: "quality_gate"
      model: "claude-sonnet-4-6"
      parallelizable: false
      description: "Run full suite for final validation"
---

# Execute Tasks

Systematic workflow for implementing tasks from `.tasks/` phase files. Reads each task file, implements it following project standards, verifies the result, fixes all test failures, updates the task file with how it was solved, and marks it complete.

**Assumes all tests are passing before starting.** Does not capture baselines.

**Task model.** Current task sets (from `/generate-tasks` and `/operationalize-design`) are lean: each **implementation task carries its own tests** (its `## Tests` / `## Targeted Tests`), so the verify phase's targeted run already exercises the new tests — there are no separate `-tests` tasks. Independent verification lives in the **one per-package quality gate** (run as the `quality_gate` phase here). Standalone `-verify` tasks are legacy; the verification-task handling below remains so older phases that still contain them execute correctly. This skill already runs targeted tests per task and the full suite **once** in the quality gate phase — keep that split; do not add per-task full-suite runs.

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

## Delegation Constraints

When phases are delegated to sub-agents (per the delegation-strategy metadata):

- **max_turns:** Set `max_turns: 40` on each delegated agent. Do NOT leave agents uncapped — unbounded agents become unmonitorable.
- **Background delegation + genuine polling (NOT completion notifications):** Spawn each delegated agent with `run_in_background: true` and drive it with the **Agent Progress Polling Protocol** (read `d:\datrix\datrix\claude-config\.claude\agent-templates\agent-progress-polling-protocol.md`). Do NOT wait passively for a completion notification and do NOT assume the agent is working. Every ~5 minutes, perform a **genuine** check of each in-flight agent — its status **and** the on-disk artifacts it is supposed to be producing — and classify it (completed / progressing / stalled / errored). Record each agent's `task_id` and assigned `files_to_create`/`files_to_modify`, and snapshot those files' line counts at dispatch.
- **BLOCKED from a delegated agent → adjudicate it; never relay it, never stop on it.** Run the **Blocker Adjudication Protocol** (`d:\datrix\.claude\skills\_shared\blocker-adjudication-protocol.md`) — read it; it is binding:
  1. **Form check** — all four parts of the execution-contract §3 proof, substantively (verbatim error text; a fix the agent actually **wrote and ran**, as `file:line` — analysis is not an attempt; why it failed; a literal `B1`/`B2`/`B3`/`B4`). Missing any → malformed; skip to step 3.
  2. **Investigate it yourself, through the code and the docs.** A well-formed proof is still an assertion. Reproduce the error in the same context; open the `file:line` and verify the attempted fix is real and aimed at the root cause; trace the root cause yourself; read the design/architecture docs governing that surface; test the claimed B-code against what you found (legitimacy table, protocol §3). Delegate the reading and the repro if you like — **never the verdict.**
  3. **ILLEGITIMATE (the common case) → correct and re-dispatch.** Fresh agent, original task **plus** the correction packet (protocol §4): its claim quoted back, the finding that kills it (your `file:line` or command + output), what it missed, the path forward. The task is **not** failed and **not** blocked — it is still in flight. Max two such re-dispatches; on a third, do the root-cause analysis yourself and dispatch a directed implementer.
  4. **LEGITIMATE → Fable adjudication.** Spawn a **Fable** decision agent (`subagent_type: "general-purpose"`, `model: "fable"`, `effort: "high"`, `run_in_background: false`) with the protocol §5 prompt. It returns one binding decision — **A** not-actually-blocked / **B** fix-elsewhere / **C** amend-task / **D** resequence / **E** spawn-follow-up / **F** ask-user — and you **execute it** (protocol §5 table). **Only F reaches the user**; A–E keep the run moving. Verify with the `acceptance_check` it specifies.
- **Question relay (surfaced at poll time):** If a poll's genuine check finds a delegated agent with a **NEEDS_CONTEXT** question that only the user can answer (a credential, a spec gap, a genuine product decision), relay it via `AskUserQuestion` **with your recommendation**, then re-dispatch the agent (background) with the answer. A **technical** ambiguity is not a user question — that is yours to resolve (Decision Escalation Protocol). Do NOT guess answers or silently skip the agent.
- **Stalled agents:** A delegated agent whose assigned files have not changed across two consecutive polls (~10 min), or that the poll shows is hung, is investigated — `TaskStop` it and **re-dispatch** with corrective context. A hung or turn-exhausted agent is an *agent* failure, not a *task* blocker; never record it as BLOCKED. Never leave a stalled agent counted as in-flight.
- **Progress reporting:** Emit the one-line poll heartbeat each cycle, and a brief status update after each phase (or each task within a phase). Do NOT run through all phases silently and dump a wall of text at the end.
- **Test execution split:** Delegated agents run ONLY targeted tests (from each task's `## Targeted Tests` section). The orchestrator runs the full test suite once in the quality gate phase. This prevents redundant full-suite runs when multiple tasks are being processed. If a task has no targeted tests section, the agent skips test execution and reports `no_targeted_tests: true`.

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

JSON array of tasks in execution order — one entry per task with fields: `task_path`, `task_id`, `title`, `package`, `category`, `dependencies[]`, `language_scope`, `is_quality_gate`, `is_blocked`, `files_to_review[]`, `files_to_create[]`, `files_to_modify[]`, `red_flags[]`.

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

**If ambiguities exist:**
- **Spec gap or missing user input** (unclear requirement, missing path, credential) → STOP, ask user, WAIT for answers before proceeding to Step 2
- **Technical design ambiguity** (conflicting patterns, multiple valid architectural approaches) → invoke the **Decision Escalation Protocol** (Opus 4.8 extra-high-effort agent); proceed to Step 2 using Opus's recommendation

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

**Scope discipline — expand, don't abandon** (execution-contract §4):
- The task's file list is the **expected surface, not a fence**. If the root cause lies outside it, **follow it and fix it there**, then report the expansion under `scope_expansion`.
- Growing beyond the task's estimate is **not** a stopping condition — an estimate is a prediction, not a permission slip.
- Do NOT make unrelated "improvements" to surrounding code. (Following a root cause is not an improvement — it is the job.)

**STUCK protocol — fix it; BLOCKED is a claim you must prove** (execution-contract §1–§3):
- **Your default outcome is: the problem is fixed.** Not investigated, not reported.
- **These are NOT blockers — they are the work:** missing dependency (**implement it**), missing file (**create it**), patterns unclear (**read more**), root cause unclear (**keep reading**), scope grew (**do the work**), failure is pre-existing (**it's yours now**), lives in another package (**go fix it there**), no test covers it (**write one**).
- **Design ambiguity → escalate, don't stop.** Escalation (`_shared/decision-escalation-protocol.md`) is how you *keep going*. Returning BLOCKED on a technical ambiguity without escalating first is an invalid report.
- **A valid BLOCKED needs all four:** verbatim error text; the fix you actually wrote and ran (`file:line` — analysis alone is **not** an attempt); why it failed; and the `B1`/`B2`/`B3`/`B4` code. **Missing any → the report is rejected and the task is re-dispatched to you.**
- Writing `pass`, `NotImplementedError`, empty method bodies, or trivial stubs that satisfy type checkers but do nothing is the **worst** outcome — invisible debt that wastes future sessions.
- **An unproven BLOCKED is the second-worst** — it burns a whole turn and produces nothing. A *proven* blocker is a fact; a *fixed* problem is the job.

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

For each task (in parallel, up to 5 tasks concurrently), run targeted tests and fix all failures. If the first fix attempt fails, escalate immediately to Opus 4.8 at extra-high effort (Decision Escalation Protocol).

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

#### Step 1: Identify Required Tests

**Documentation-only tasks — skip verification.**

For tasks that modified code:

1. **Determine test scope:**
   - Read task file's `## Targeted Tests` section
   - If targeted tests exist AND task is NOT quality gate → identify targeted tests
   - If NO targeted tests OR task IS quality gate → identify full suite requirement

2. **Execute or request tests:**

   **Targeted tests — run them yourself:**
   Run each targeted test command directly:
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path}"
   ```
   Capture the output and parse results. Do NOT stop to ask the user for targeted tests.

   **Test-invocation rules (a PreToolUse hook hard-blocks violations):**
   - **Never pass `-NoSave`** — it hides the saved progress Jon reads. Always let results save.
   - **Never pass `-VerboseOutput`** — it burns tokens for no benefit; read the run's `index.json` / `full.log` for detail.
   - **Never call `pytest` (or `python -m pytest`) directly** — always go through `test.ps1` / `test-single.ps1`.
   - **Never run `mypy`** (or any standalone type-checker) — write fully type-hinted code, but do not invoke a type-check command; it only burns tokens/turns.

   **Full suite (quality gate or backward compatibility) — ask user:**
   STOP and tell the user the full suite needs to be run:
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```
   Wait for user to run the tests and provide results. DO NOT proceed until user provides test output.

#### Step 2: Evaluate Test Results

**For targeted tests:** Parse the test output you captured in Step 1.
**For full suite:** Parse the test output provided by the user.

1. **Parse the test results:**
   - Extract total tests, pass count, fail count
   - List failing test names and error messages

2. **Evaluate results:**
   ```
   if all tests pass:
       → verification PASSED
   else:
       → verification FAILED, proceed to Step 3 (Fix Failures)
   ```

#### Step 3: Fix All Failures

If any test failures exist:

1. **Invoke fix workflow:**
   - Read failing test file
   - Understand what the test expects
   - Identify root cause of failure
   - Fix the issue (modify code, update test, or both)

2. **After each fix attempt, re-run the relevant tests:**

   **Targeted tests — run them yourself:**
   Re-run the targeted test commands directly and parse the output. Do NOT stop to ask the user.

   **Full suite — ask user:**
   STOP and tell the user which full-suite command to run. Wait for user to provide results.

3. **Track each attempt:**

   | Attempt | What was tried | Result |
   |---------|---------------|--------|
   | 1       | {description} | {pass/fail + error} |
   | 2       | {description} | {pass/fail + error} |
   | 3       | {description} | {pass/fail + error} |

4. **Outcomes:**
   - **If the first fix attempt passes** → verification PASSED
   - **If the first fix attempt fails** → immediately invoke the **Decision Escalation Protocol** (Opus 4.8 extra-high-effort agent with full context: task spec, the failed attempt, exact failures); implement Opus's recommendation; if still failing → verification FAILED (proceed to Step 4)
   - **If a fix introduces additional failures** → revert immediately, then invoke the **Decision Escalation Protocol** before any further attempt

#### Step 4: Verification Failed (if Opus-assisted attempt also fails)

If tests still fail after the Opus-assisted attempt:

1. **Do NOT mark the task COMPLETED**
2. **Update the task file:**
   - Change title to `# FAILED: Task {NN}-{TT}: {Title}`
   - Add `## Why Failed` section immediately after title:

```markdown
## Why Failed

**Test failures after implementation (not fixed after Opus-assisted attempt):**

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

3. **Design-acceptance verification + self-contradiction check (MANDATORY — suite-green is not enough):**
   Apply conditions 3 and 4 of the shared checklist `d:\datrix\.claude\skills\_shared\completion-eligibility.md`: prove the task's `**Design acceptance property:**` with an executable negative + positive check (command + output pasted into "How Solved"; for "X replaces Y", Y is gone everywhere on the surface), and scan your "How Solved" narrative for the BLOCKED/partial/workaround/dual-path red-flag phrases. Any unproven property or red-flag phrase → the task is **not complete** and must not be marked COMPLETED. It is also **not automatically BLOCKED**: run the **Blocker Adjudication Protocol** (`_shared/blocker-adjudication-protocol.md`) on the underlying obstacle — investigate it, and if it survives, let the **Fable** adjudicator decide what happens instead. A task is only recorded as blocked after that adjudication, with the confirmed B-code and Fable's decision attached.

2. **Mark task as completed using the script:**
   ```bash
   powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "{task_path}"
   ```
   This changes the title from `# Task {NN}-{TT}: {Title}` to `# COMPLETED: Task {NN}-{TT}: {Title}`.

3. **Add `## How Solved` section immediately after title with **mandatory proof-of-work**:

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

**Design-acceptance proof** (the invariant from `**Design acceptance property:**`, proven — not asserted):
```
{paste the negative + positive check commands AND their output —
 e.g. the grep showing the old pattern is gone, and the check showing the new path is exercised}
```

**Files created (with line counts):**
- `{file_path}` — {N} lines (non-comment, non-blank)
```

The proof-of-work section is **mandatory**. A task without raw test output in its "How Solved" section is NOT considered properly completed. This evidence allows independent verification without re-running the tools.

**Quality gate tasks:** mark complete via `complete.ps1` as above, then add a "How Solved" whose Proof of Work is the RAW full-suite output (no files created/modified).

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
Status: FAILED (verification failed after Opus-assisted attempt)
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
- First fix attempt failed and Opus-assisted attempt also failed
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

2. **For each package, identify test command:**

   **Full test suite:**
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

3. **Pause execution and inform user:**
   - STOP and tell the user exactly what test commands need to be run for quality gate
   - Include the exact command(s) to execute for each affected package
   - Wait for user to run the tests and provide results
   - User will paste the test output back to you
   - DO NOT proceed until user provides test results

4. **Resume after user provides test results:**
   - Parse the test output provided by user
   - Extract total tests, pass count, fail count, failing test names

5. **Attribute failures (if any):**
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

After all phases complete, report only essential status:

```
Tasks completed: {N}/{total}
Tasks failed: {N}

Completed:
- Task {NN}-{TT}: {Title}
- Task {NN}-{TT}: {Title}

Failed (if any):
- Task {NN}-{TT}: {Title} — {why}
```

## Blocker Adjudication Protocol

Read and follow `d:\datrix\.claude\skills\_shared\blocker-adjudication-protocol.md` whenever a delegated agent reports BLOCKED. **You never stop on it and you never relay it.** Investigate the claim yourself against the code and the docs; a bogus blocker (the common case) gets the agent corrected and re-dispatched; a confirmed one goes to a **Fable** adjudicator (`model: "fable"`, `effort: "high"`) whose decision you then carry out. A four-part proof is not true just because it has four parts.

## Decision Escalation Protocol

This protocol is for problems **you** hit (a failing fix, an unclear root cause, an architectural conflict). A **delegated agent's BLOCKED report** goes through the Blocker Adjudication Protocol above instead — and if that confirms the blocker, the decision belongs to Fable, not to an Opus escalation.

Read and follow `d:\datrix\.claude\skills\_shared\decision-escalation-protocol.md` — it defines when to escalate (technical design ambiguity in Step 1, failed first fix with unclear root cause, systemic/cascading failures, architectural conflicts) vs. not (obvious fixes → fix directly; genuine B1/B3 blockers → the only things that stop work), the exact Opus 4.8 xhigh agent parameters + prompt, and the implement-exactly-what-Opus-recommended rule. **Escalation is not an exit — it is how you keep going.** Note that missing dependencies/files/prereqs and unclear root causes are **work**, not blockers: implement, create, keep reading.

---

## Anti-Patterns

- **NO relaying a BLOCKED report** — a delegated agent's BLOCKED is a claim, not a verdict, and the agent that hit the wall is the party least able to see over it. Investigate it yourself through the code and the docs; correct the agent if it is bogus; route it to a **Fable** adjudicator if it is real (`_shared/blocker-adjudication-protocol.md`). Passing an unexamined blocker up to the user is the skill doing nothing.
- **NO assuming a delegated agent is working** — when a phase is delegated to a background sub-agent, drive it with the Agent Progress Polling Protocol: a genuine status + on-disk artifact check every ~5 minutes. Never report an agent as "in progress" without that evidence, and never rely on a completion notification to learn it finished.
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

