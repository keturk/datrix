---
description: Execute multiple tasks in parallel — evaluate all tasks for blockers, then delegate each to a separate agent
model: claude-sonnet-4-6
disable-model-invocation: true
delegation-strategy:
  phases:
    - name: "pre_check"
      model: "haiku"
      parallelizable: false
      description: "Read all task files, validate dependencies, identify blockers"
    - name: "spawn_agents"
      model: "claude-sonnet-4-6"
      parallelizable: false
      description: "Spawn one agent per task to implement code changes and run targeted tests"
    - name: "verify_and_gate"
      model: "claude-sonnet-4-6"
      parallelizable: false
      description: "Run full suite once per package, attribute failures, fix loop, final validation"
---

# Execute Tasks in Parallel

Parallel execution workflow for implementing multiple independent tasks from `.tasks/` phase files. Evaluates all tasks upfront for blocking issues, then spawns separate agents to execute each task concurrently.

**Assumes all tests are passing before starting.** Does not capture baselines.

**Task model.** Current task sets (from `/generate-tasks` and `/operationalize-design`) are lean: each **implementation task carries its own tests**, so each agent's targeted run already covers the new tests — there are no separate `-tests` tasks. Independent verification lives in the **one per-package quality gate**; standalone `-verify` tasks are legacy (handling for them is retained for older phases). This skill already centralizes the full suite to **once per package** in Phase 3 — keep that; do not add per-task or per-agent full-suite runs.

## When to Use

- User provides **multiple** task file paths and wants parallel execution
- User explicitly says "execute tasks in parallel", "run these tasks concurrently"
- User points to a `.tasks/phase-{NN}/` directory and wants all tasks completed simultaneously
- Multiple independent tasks with no cross-dependencies need to be completed quickly

## When NOT to Use

- Only one task to execute (use `/execute-tasks` instead)
- Tasks have sequential dependencies within the same phase (use `/execute-tasks` instead)
- User wants to see tasks completed one-by-one (use `/execute-tasks` instead)

## How to Invoke

```
/execute-tasks-parallel

TASKS:
d:\datrix\datrix-common\.tasks\phase-05\task-05-01-generator-base.md
d:\datrix\datrix-common\.tasks\phase-05\task-05-02-template-loader.md
d:\datrix\datrix-common\.tasks\phase-05\task-05-03-formatter-integration.md
```

Execute all tasks in a phase:
```
/execute-tasks-parallel

PHASE: d:\datrix\datrix-common\.tasks\phase-05\
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

<!-- PHASE: pre_check -->
## Phase 1: Pre-Execution Check & Blocker Detection

Read all task files, validate dependencies, check for blockers, and determine if parallel execution is possible.

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
   - Verification tasks MUST execute AFTER their dependency implementation/test tasks
   - Verification tasks should ideally be executed in a **different session** than the implementation tasks they verify
   - If both an implementation task and its verification task are in the same batch → mark as ORDERING_REQUIRED
8. **Check for intra-phase dependencies:**
   - If any task depends on another task in the same batch → mark as ORDERING_REQUIRED
   - Tasks with intra-phase dependencies must execute sequentially

### Input

Task file paths from skill invocation (provided by user as TASKS:, PHASE:, or TASK:).

### Output

JSON array of all tasks with blocker analysis:

JSON with `can_parallelize` (bool), `blocking_issues[]`, and `tasks[]` — one entry per task with fields: `task_path`, `task_id`, `title`, `package`, `category`, `dependencies[]`, `language_scope`, `is_quality_gate`, `is_blocked`, `intra_phase_dependencies[]`, `files_to_review[]`, `files_to_create[]`, `files_to_modify[]`, `red_flags[]`.

### Blocker Detection

Mark `can_parallelize: false` and populate `blocking_issues[]` if ANY of these conditions exist:

1. **Cross-task dependencies:** Any task in the batch depends on another task in the batch
   - Add to `blocking_issues`: `"Task {id} depends on task {dependency_id} which is in the same batch"`

2. **Unmet dependencies:** Any task depends on a task that is not COMPLETED
   - Add to `blocking_issues`: `"Task {id} blocked by incomplete dependency: {dependency_id}"`

3. **Missing files:** Any task references files that don't exist
   - Add to `blocking_issues`: `"Task {id} references non-existent file: {file_path}"`

4. **Scope errors:** Any task mixes Python and TypeScript files
   - Add to `blocking_issues`: `"Task {id} has mixed language scope (.py and .ts files)"`

5. **File conflicts:** Multiple tasks modify the same file
   - Add to `blocking_issues`: `"File conflict: {file_path} modified by tasks {id1}, {id2}"`

### Decision Logic

```
if blocking_issues.length > 0:
    can_parallelize = false
    STOP and report blocking issues to user
    Suggest using /execute-tasks for sequential execution OR fixing blockers first
else:
    can_parallelize = true
    Proceed to spawn_agents phase
```

### Output Format for Blockers

If blockers found:

```
PARALLEL EXECUTION BLOCKED

Cannot execute tasks in parallel due to the following issues:

1. Task 40-02 depends on task 40-01 which is in the same batch
2. File conflict: src/core/generator.py modified by task-40-03 and task-40-05

RECOMMENDATION:
- Use /execute-tasks for sequential execution, OR
- Split tasks into groups without dependencies/conflicts
- For tasks with dependencies: execute task-40-01 first, then run task-40-02 separately

Would you like me to:
1. Execute these tasks sequentially using /execute-tasks?
2. Help you split them into independent batches?
3. Fix the blockers first?
```

### Use the TodoWrite Tool

If more than 5 tasks are provided, create a todo list before completing this phase.
<!-- END_PHASE: pre_check -->

<!-- PHASE: spawn_agents -->
## Phase 2: Spawn Parallel Implementation Agents

For each task (all in parallel), spawn a dedicated agent to implement code changes and run targeted tests. Agents run ONLY the targeted tests listed in their task file — the full test suite is centralized in Phase 3 to avoid N parallel full-suite executions.

### Input

JSON from pre_check phase with task metadata and confirmation that `can_parallelize: true`.

### Steps

### Delegation Constraints

- **max_turns:** Set `max_turns: 40` on each spawned agent. Do NOT leave agents uncapped — an agent that runs for hundreds of turns without returning is unmonitorable.
- **Background agents + genuine polling (NOT completion notifications):** Spawn every agent with `run_in_background: true` and drive them with the **Agent Progress Polling Protocol** (read `d:\datrix\datrix\claude-config\.claude\agent-templates\agent-progress-polling-protocol.md`). Do NOT wait passively for completion notifications and do NOT assume an agent is working. Every ~5 minutes, perform a **genuine** check of every in-flight agent — its status **and** the on-disk artifacts it is supposed to be producing — and classify it (completed / progressing / stalled / errored). Background dispatch is what makes this polling possible; the agents still execute concurrently.
- **Question relay (surfaced at poll time):** If a poll's genuine check finds an agent BLOCKED or NEEDS_CONTEXT with questions/ambiguities, the orchestrator MUST immediately relay those questions to the user via `AskUserQuestion`. After receiving answers, re-dispatch the agent (in background) with the context. Do NOT silently skip blocked agents or guess answers on behalf of the user.
- **Stalled agents:** An agent whose assigned files have not changed across two consecutive polls (~10 min), or that the poll shows is hung/looping, is investigated — `TaskStop` it and re-dispatch with corrective context or mark BLOCKED. Never leave a stalled agent counted as in-flight.
- **Progress reporting:** Emit the one-line poll heartbeat each cycle, and a fuller progress summary once all agents reach a terminal state (before proceeding to the quality gate phase). If any agent is still outstanding, report which tasks are pending and the evidence of what's holding them up.

1. **For each task in the batch, spawn a Task agent with subagent_type="general-purpose":**

   **Agent task description format:**
   ```
   Execute single task: {task_id}
   ```

   **Critical Task tool parameters:**
   - `max_turns: 40` — hard limit per agent
   - `run_in_background: true` — required so each agent can be polled while running (Agent Progress Polling Protocol). Record each agent's `task_id` and assigned `files_to_create`/`files_to_modify`, and snapshot those files' line counts at dispatch.

   **Agent prompt template:**

   Read `d:\datrix\datrix\claude-config\.claude\agent-templates\task-implementation-agent.md` and substitute `{task_path}` with the actual task file path.

   **Additional context to prepend:**
   ```
   You are executing a SINGLE task from a parallel batch. Your scope is LIMITED to this one task only.

   IMPORTANT: You implement code AND run ONLY targeted tests for your task.
   Do NOT run the full test suite — the orchestrator runs it once after ALL agents
   complete, to avoid N parallel full-suite executions.

   TEST-INVOKE RULES (a PreToolUse hook hard-blocks violations):
   - Never pass -NoSave or -VerboseOutput to test.ps1 (they hide saved progress / burn tokens).
   - Never call pytest (or python -m pytest) directly — use test.ps1 / test-single.ps1.
   - Never run mypy or any standalone type-checker — write typed code, but don't run a type-check command.
   ```

   **See the template file for:**
   - Complete workflow steps (UNDERSTAND → IMPLEMENT → SELF-CHECK → RUN TARGETED TESTS → RETURN RESULTS)
   - Anti-patterns to avoid
   - Self-check protocol
   - STUCK protocol
   - JSON result format

2. **Spawn all agents in parallel** using a single message with multiple Task tool calls (all `run_in_background: true`, `max_turns: 40`)

3. **Drive the agents per the Delegation Constraints above** (genuine 5-minute polls, never passive waiting). As each poll detects a completion, collect: status (IMPLEMENTED / BLOCKED / NEEDS_CONTEXT / FAILED), files created/modified, targeted test results (pass/fail, fix attempts), and any questions.

4. **Handle non-IMPLEMENTED results at the poll that surfaces them:**
   - **Spec gap / missing user input** (NEEDS_CONTEXT) → `AskUserQuestion`, then re-dispatch with the answer; do NOT proceed to the quality gate with questions outstanding
   - **Technical ambiguity** (BLOCKED/NEEDS_CONTEXT on a design choice or unclear root cause) → **Decision Escalation Protocol** (below); re-dispatch with Opus's recommendation
   - **Hard blocker** (missing dependency/file/prereq) → record the failure, report, do not re-attempt
   - **Stalled** (per the polling protocol) → `TaskStop` + re-dispatch with corrective context, or mark BLOCKED

5. **When all agents reach a terminal state**, emit the checkpoint (below) and proceed directly to Phase 3 — agents already ran targeted tests.

### Model Selection (per task — cheapest model that can do it correctly)

- `model: "haiku"` — documentation-only tasks, AND trivial mechanical code tasks with no design judgment (pure renames, moving a named constant, single-import/single-symbol edits, mechanical signature propagation)
- `model: "claude-sonnet-4-6"` — all substantive code tasks (default when in doubt — doubt means Sonnet, not Haiku)
- `model: "opus"` — only a genuinely hard/cross-cutting implementation (rare in a parallel batch)

### Output Format

JSON with `agents_spawned`, `agents_implemented`, and `results[]` — one entry per task: `task_id`, `status`, `files_created[]`, `files_modified[]`, `targeted_tests` (`ran`, `passed`, `fix_attempts`, `test_commands[]`, or `no_targeted_tests: true`).

### Checkpoint Reporting

After all agents reach a terminal state, emit a lean summary: `IMPLEMENTATION PHASE COMPLETE — {implemented}/{spawned}`, one line per task (`✓ {task_id}: targeted tests {PASSED/FAILED/none} ({N} fix attempts)`), then proceed to the quality gate. List details only for non-IMPLEMENTED tasks.

### Error Handling

If a poll detects an agent crashed, timed out, hit `max_turns`, or stalled (no assigned-artifact change across two consecutive polls):
- Record the error in results
- `TaskStop` it if still in-flight, then mark task as BLOCKED with explanation (e.g., "Agent hit max_turns limit — task may need to be broken down or retried")
- Report the issue to the user immediately — do NOT silently skip and do NOT assume it is still working
- Continue polling the other agents
- Report the issue in quality gate phase

If a poll finds an agent with questions (NEEDS_CONTEXT):
- Relay questions to user via AskUserQuestion
- Re-dispatch the agent (background) after user provides answers
- If user cannot answer, mark task BLOCKED
<!-- END_PHASE: spawn_agents -->

<!-- PHASE: verify_and_gate -->
## Phase 3: Centralized Verification & Quality Gate

The orchestrator runs the full test suite **once** per affected package — not per task. This avoids N parallel full-suite executions that waste resources and risk conflicts.

### Why Centralized

- Agents already ran targeted tests for their own task scope
- The full suite catches cross-task integration issues, import breakage, and regressions
- Running it once (not per-agent) saves cost and avoids parallel pytest conflicts

### Input

Implementation results from all agents + task metadata from pre_check.

```json
{
  "tasks": [
    {"task_id": "task-40-01", "status": "IMPLEMENTED", "package": ".claude/"},
    {"task_id": "task-40-02", "status": "IMPLEMENTED", "package": "datrix-codegen-python"},
    {"task_id": "task-40-03", "status": "FAILED", "package": "datrix-codegen-python"}
  ]
}
```

### Steps

#### Step 1: Identify Full Suite Test Commands

1. **Determine affected packages:**
   - Group tasks by `package` field
   - Skip documentation-only packages (no tests to run)
   - For each package with code tasks, identify the full suite command

2. **Identify full test suite commands:**
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

3. **Pause and inform user:**
   - STOP and tell the user exactly what test commands to run for quality gate
   - Include the exact command(s) for each affected package
   - Wait for user to run the tests and provide results
   - User will paste the test output back to you
   - DO NOT proceed until user provides test results

4. **Resume after user provides test results:**
   - Parse the test output provided by user
   - Record total tests, pass count, fail count
   - List all failing test names + error messages

#### Step 2: Attribute Failures to Tasks

For each test failure:

1. Extract the failing test file path and error message
2. Cross-reference against each task's files_created and files_modified
3. Check the task's `## Targeted Tests` section — does this test appear there?
4. Assign attribution: `likely_source_task: "task-{NN}-{TT}"`
5. If a failure cannot be attributed to any task → flag as "pre-existing or environmental"

Separate failures into:
- **Known failures:** Already reported by agents during targeted tests (agent status = FAILED)
- **New failures:** Discovered only in the full suite (integration/cross-task issues)

#### Step 3: Fix Loop (Max 3 Attempts Per Attributed Task)

For each NEW failure (not already known from agent targeted tests):

1. **Read the failing test** and the source code it exercises
2. **Identify root cause** — which task's changes broke this test?
3. **Fix the issue** (modify code — stay within the attributed task's scope)
4. **Run the specific failing test directly:**
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{failing-test-path}"
   ```
   Capture the output and parse results. Do NOT stop to ask the user for specific/targeted tests.
5. Track each attempt in a table

| Attempt | Task | What was tried | Result |
|---------|------|---------------|--------|
| 1       | task-40-03 | Fixed import path in generator_base.py | PASS |
| 2       | task-40-04 | Updated validate_all → validate method call | FAIL — new error |

**Stop conditions:**
- **First attempt fails** and root cause is unclear → immediately invoke the **Decision Escalation Protocol** (Opus 4.8 extra-high-effort agent with full context: task spec, the failed attempt, exact failures); implement Opus's recommendation; if still failing → mark that task FAILED
- A fix introduces additional failures → revert the fix attempt immediately, then invoke the **Decision Escalation Protocol** before continuing
- Fix reveals cascading issues in unrelated subsystems → invoke the **Decision Escalation Protocol** to determine correct fix scope; if Opus recommends stopping → STOP, report to user

#### Step 4: Final Validation

After all fix attempts are exhausted:

1. **Identify full suite command** for each affected package (to confirm fixes + catch regressions)
2. **STOP and tell user what test commands to run**
3. **Wait for user to provide test results**
4. **Parse results and compare against Step 1 results** — are we better, same, or worse?

#### Step 5: Mark Tasks Complete / Failed

For each task with status IMPLEMENTED:

- Apply the shared **completion-eligibility checklist**: read and follow `d:\datrix\.claude\skills\_shared\completion-eligibility.md` (4 conditions — tests green / not-BLOCKED-terminal / How-Solved clean / design-acceptance proven by a check YOU run; `complete.ps1` + proof-of-work on pass; BLOCKED recorded honestly with a tracked follow-up on fail). For this skill, condition #1's governing gate is the Phase-3 full suite for the package.

- **If tests still fail after fix loop:**
  - Update task file: change title to `# FAILED: Task {NN}-{TT}: {Title}`
  - Add `## Why Failed` section with fix attempt log and failing tests
  - Status → FAILED

For tasks that agents already marked FAILED (targeted test failures):
- Keep status as FAILED — do not re-attempt in this phase
- Report to user for separate attention

### Output Format

JSON with `status` (PASSED/FAILED), `packages_tested[]`, `full_suite_runs`, `results_per_package[]` (`package`, `total_tests`, `tests_passing`, `tests_failing`, and on failure `known_failures[]` + `new_failures[]` with `test_name`, `error`, `likely_source_task`, `fix_attempts`, `fix_result`), `tasks_completed[]`, `tasks_failed[]`, `fixes_made[]`.

Emit a lean checkpoint: `VERIFICATION & QUALITY GATE — {package}: {PASSED|FAILED}, {passing}/{total}`. On PASS list completed task IDs one per line. On FAIL list only the unresolved failures (test, error, likely source task, fix attempts) and a one-line recommendation each — do not restate passing results.

### Notes

- Full suite runs at most TWICE: once to find failures, once to validate fixes
- If Step 1 finds zero failures → skip Steps 3-4, go straight to Step 5 (mark all IMPLEMENTED tasks as COMPLETED)
- Failed quality gate does NOT automatically re-run tasks beyond the fix loop — report to user for decision
<!-- END_PHASE: verify_and_gate -->

## Final Report

After all phases complete, report only essential status:

```
Tasks completed: {N}/{total}
Tasks failed: {N}
Full suite: PASSED / FAILED

Completed:
- Task {NN}-{TT}: {Title}
- Task {NN}-{TT}: {Title}

Failed (if any):
- Task {NN}-{TT}: {Title} — {why}
```

## Decision Escalation Protocol

Read and follow `d:\datrix\.claude\skills\_shared\decision-escalation-protocol.md` — it defines when to escalate (technical ambiguity, failed first fix with unclear root cause, cascading failures) vs. not (hard blockers → STOP and report; obvious fixes → fix directly; missing user input → ask), the exact Opus 4.8 xhigh agent parameters + prompt, and the implement-exactly-what-Opus-recommended rule.

---

## Advantages Over Sequential Execution

- **Speed:** Tasks execute concurrently, reducing wall-clock time
- **Isolation:** Each task has its own agent context, preventing interference
- **Failure containment:** One failed task doesn't block others
- **Scalability:** Can handle large batches efficiently

## Limitations

- **Cannot handle cross-task dependencies:** Tasks must be independent
- **File conflicts:** Multiple tasks cannot modify the same file
- **Integration issues detected late:** Only caught in quality gate phase
- **Higher cost:** More agents = more API calls (but faster wall-clock time)

## When to Fall Back to Sequential

Use `/execute-tasks` instead if:
- Tasks have dependencies on each other
- Tasks modify the same files
- You want to see tasks complete one-by-one for learning/debugging
- Integration issues are expected and need careful incremental testing

## Anti-Patterns

- **NO assuming agents are working** — background agents are driven by the Agent Progress Polling Protocol: a genuine status + on-disk artifact check every ~5 minutes. Never report an agent as "in progress" without that evidence, and never rely on a completion notification to learn an agent finished.
- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

