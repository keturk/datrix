---
description: Fully automated multi-wave task orchestrator with dependency analysis and test gating
model: opus
---

# Task Orchestrator

Fully automated multi-wave task orchestrator. Accepts a set of tasks (individual files, multiple files, or an entire phase directory), analyzes dependencies, topologically sorts tasks into execution waves, and executes each wave with parallel agents. Runs test suites automatically between waves. No human intervention except on task failure after exhausting fix attempts.

**Key differences from `/execute-tasks-parallel`:**
- Dependency-aware grouping (builds a DAG, topologically sorts into waves)
- Automated test execution (runs full suite via Bash, does not ask user)
- Automatic wave advancement (no human intervention between waves)
- Handles tasks with cross-dependencies (separates into waves instead of blocking)

## When to Use

- User provides **many tasks** (5+) with cross-dependencies and wants full automation
- User says "orchestrate", "run all tasks", "execute phase", "run everything"
- User provides a `.tasks/phase-{NN}/` directory and wants hands-off execution
- Tasks span multiple waves of dependencies and the user does not want to manage groups manually

## When NOT to Use

- Only 1-3 independent tasks (use `/execute-tasks-parallel` instead — simpler, lower cost)
- User wants manual control between groups (use `/execute-tasks-parallel` for one group at a time)
- User wants to see tasks one-by-one (use `/execute-tasks` instead)

## How to Invoke

**Most common usage — entire phase (recommended):**
```
/task-orchestrator

PHASE: 36
```
Or with full path:
```
/task-orchestrator

PHASE: d:\datrix\datrix\.tasks\phase-36\
```

**Note:** When you provide a PHASE (not individual task files), the orchestrator will automatically discover all tasks by:
1. First checking for `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` (if it exists, uses that)
2. Otherwise, globbing for `task-*.md` files across all package directories in that phase

You DO NOT need to provide the list of tasks — the orchestrator discovers them automatically.

---

Individual tasks (less common):
```
/task-orchestrator

TASKS:
d:\datrix\datrix-common\.tasks\phase-07\task-07-01-base-class.md
d:\datrix\datrix-common\.tasks\phase-07\task-07-02-template-loader.md
d:\datrix\datrix-common\.tasks\phase-07\task-07-03-formatter.md
d:\datrix\datrix-common\.tasks\phase-07\task-07-04-integration.md
```

Multiple phases:
```
/task-orchestrator

PHASES: 34, 35, 36
```
Or with full paths:
```
/task-orchestrator

PHASES:
d:\datrix\datrix\.tasks\phase-34\
d:\datrix\datrix\.tasks\phase-35\
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

### Test Quick Reference
Read `d:/datrix/datrix/scripts/test/quick-reference.md` before running any test commands.

---

## Step 1: Discover and Read All Tasks

### 1a. Parse Input

Accept task paths in these formats:

- **TASK:** single file path
- **TASKS:** newline-separated list of file paths
- **PHASE:** single directory path — glob for `task-*.md` files within it
- **PHASES:** newline-separated list of directory paths — glob for `task-*.md` in each

**Important:** When a PHASE is provided (not individual tasks), ALWAYS check for a consolidated dependencies.md file at `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` BEFORE reading individual task files. This file contains pre-computed task metadata and dependencies.

If a PHASE directory is given:
1. Extract the phase number from the directory path (e.g., "36" from `phase-36`)
2. Check if `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` exists
3. If it exists, use it (see step 1b)
4. If it doesn't exist, use Glob to find all `task-*.md` files in that directory

### 1b. Read Task Metadata

**IMPORTANT:** The orchestrator automatically discovers tasks when a PHASE is provided. The user does NOT need to provide a list of task files.

**Discovery process for each phase:**

1. **First, check for consolidated dependencies file:**
   - Location: `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md`
   - This is a phase-level file (NOT in individual package directories)
   - If it exists:
     - Try to parse it as JSON (new format with full metadata)
     - If JSON parsing succeeds: extract task_id, task_path, title, is_completed, package, dependencies, category
     - If JSON parsing fails (simple text format): parse as line-separated task paths grouped by "Group N" headers
       - Extract task paths from each group
       - Groups represent dependency waves (Group 1 = no dependencies, Group 2 = depends on Group 1, etc.)
       - Still need to read task files to get full metadata (title, package, category, is_completed)
       - Use group numbers to infer dependency structure
   - Skip reading for dependency graph construction if JSON format is used

2. **If dependencies.md doesn't exist, fall back to discovering tasks across packages:**
   - Glob for `task-*.md` files in:
     - `d:\datrix\datrix-common\.tasks\phase-{NN}\`
     - `d:\datrix\datrix-codegen-python\.tasks\phase-{NN}\`
     - `d:\datrix\datrix-codegen-aws\.tasks\phase-{NN}\`
     - `d:\datrix\datrix-extensions\.tasks\phase-{NN}\`
     - `d:\datrix\datrix-projects\.tasks\phase-{NN}\`
     - etc. (all packages with `.tasks` directories)
   - Read each task file to extract metadata (see below)

**Dependencies.md schema:**

See `d:\datrix\datrix\claude-config\.claude\agent-templates\dependencies-format.md` for the JSON schema.

2. **Metadata extraction (when reading task files manually):**
   - `task_id` — from filename (e.g., `task-07-01` from `task-07-01-base-class.md`)
   - `title` — from `# Task {NN}-{TT}: {Title}` heading
   - `is_completed` — title starts with `# COMPLETED:`
   - `package` — from `**Package:**` field
   - `dependencies` — from `**Depends on:**` field (list of task ID slugs, or "None")
   - `category` — from header (Implementation / Tests / Documentation / Quality Gate / Verification)

3. **Skip completed tasks** — if `is_completed == true`, exclude from execution but keep in the graph (dependencies of other tasks may reference them)

4. **Read additional metadata when spawning agents:**
   When spawning an agent for a task, read the full task file to extract:
   - `targeted_tests` — from `## Targeted Tests` section
   - `files_to_review` — from `## Files to Review Before Starting`
   - `files_to_create` — from `## Files to Create`
   - `files_to_modify` — paths extracted from task body

### 1c. Validate

- If ANY referenced dependency task file does not exist on disk → STOP, report missing file
- If ANY task mixes `.py` and `.ts` files in files to create/modify → STOP, report scope error
- If zero non-completed tasks remain → report "All tasks already completed" and exit

---

## Step 2: Build Dependency DAG and Plan Waves

### 2a. Build the Directed Acyclic Graph

For each non-completed task:
1. Parse the `**Depends on:**` field to get dependency slugs
2. For each dependency slug:
   - Find the matching task in the full task list (completed or not)
   - If the dependency is completed → treat as satisfied (no edge needed)
   - If the dependency is NOT completed AND is in the task set → add a directed edge: dependency → this task
   - If the dependency is NOT completed AND is NOT in the task set → STOP, report "Task {id} depends on {dep_id} which is not completed and not in the provided task set"

### 2b. Detect Cycles

Run cycle detection on the graph. If a cycle is found:
- STOP immediately
- Report: `"Dependency cycle detected: {task_a} → {task_b} → ... → {task_a}"`
- List all tasks in the cycle
- Exit

### 2c. Topological Sort into Waves (Phase-Sequential)

**Phase ordering is a hard constraint.** When tasks span multiple phases (e.g., `phase-34` and `phase-35`), ALL tasks in the earlier phase must complete before ANY task in the later phase begins. This ensures correctness when later phases depend on earlier phase outputs.

**Algorithm:**

1. **Group tasks by phase number** (extracted from file path: `.tasks/phase-{NN}/`)
2. **Sort phases numerically** (phase 34 before phase 35)
3. **Within each phase**, apply topological sort using Kahn's algorithm:

```
For each phase (in numeric order):
    remaining = non-completed tasks in this phase
    local_wave = 0
    while remaining is not empty:
        ready = tasks in remaining whose dependencies are ALL either:
          - completed (already done before this run)
          - assigned to a previous wave (any earlier wave, including from earlier phases)
        if ready is empty:
            ERROR: cycle detected (should have been caught in 2b)
        assign all ready tasks to wave {global_wave_counter}
        global_wave_counter += 1
        local_wave += 1
```

4. **Phase boundaries are wave boundaries** — even if a task in phase 35 has no dependencies, it cannot start until ALL phase 34 waves are complete

**Example with 2 phases:**
```
Phase 34 (tasks 34-01 through 34-10):
  Wave 1: task-34-01, task-34-02, task-34-03 (no dependencies)
  Wave 2: task-34-04, task-34-05 (depend on wave 1)
  Wave 3: task-34-06 through task-34-10 (depend on wave 2)

--- PHASE BOUNDARY (all phase 34 must complete before phase 35 starts) ---

Phase 35 (tasks 35-01 through 35-05):
  Wave 4: task-35-01, task-35-02 (depend on phase 34 tasks, now completed)
  Wave 5: task-35-03, task-35-04, task-35-05 (depend on wave 4)
```

### 2d. File Conflict Detection Within Waves

For each wave, check if any two tasks modify the same file:
- Extract `files_to_create` and `files_to_modify` for each task in the wave
- If overlap found: split conflicting tasks into sequential sub-batches within the wave
  - Sub-batch A: first task touching the file
  - Sub-batch B: second task touching the file (executes after A completes)

### 2e. Quality Gate & Verification Task Ordering

- Quality gate tasks (`**Category:** Quality Gate`) → move to the LAST wave
- Verification tasks (`**Category:** Verification`) → must be in a wave AFTER their dependency tasks

### 2f. Present Execution Plan

Use **TodoWrite** to create the wave execution plan (one todo per wave).

Output a lean execution plan — task IDs + wave assignments, no per-task dependency annotations:

```
PLAN: {N} tasks, {W} waves, {P} phases

Wave 1 ({N}): task-34-01, task-34-02, task-34-03
Wave 2 ({N}): task-34-06, task-34-07
...
Wave {W} ({N}): task-35-05

Executing...
```

Do NOT wait for user confirmation — proceed directly to execution. The plan is informational.

---

## Step 3: Wave Execution Loop

Execute each wave sequentially. Within each wave, execute tasks in parallel (up to 3 agents at a time).

### State Tracking

Maintain these state variables throughout the loop:

- `completed_tasks[]` — tasks that passed all checks and were marked complete
- `failed_tasks[]` — tasks that failed after 3 fix attempts
- `skipped_tasks[]` — tasks skipped because a dependency failed
- `current_wave` — wave number being executed

### For Each Wave:

#### 3a. Check for Skipped Tasks

Before executing a wave, check if any task in this wave depends on a `failed_task`:
- If yes, add it to `skipped_tasks` with reason: `"Dependency {dep_id} failed"`
- Transitively skip all downstream tasks that depend on skipped tasks
- Remove skipped tasks from the wave
- If the entire wave is skipped → emit checkpoint and move to next wave

#### 3b. Spawn Implementation Agents

Batch tasks in the wave into sub-groups of **3** (max parallel agents).

For each sub-group, spawn agents in a **single message** (multiple Task tool calls, all foreground):

**Task tool parameters:**
- `subagent_type: "general-purpose"`
- `model: "opus"` for code tasks, `"haiku"` for documentation-only tasks
- `max_turns: 40`
- Do NOT set `run_in_background: true`
- `description: "Implement task: {task_id}"`

**Agent prompt template:**

Read `d:\datrix\datrix\claude-config\.claude\agent-templates\task-implementation-agent.md` and substitute `{task_path}` with the actual task file path. The template contains:
- Standard workflow (UNDERSTAND → IMPLEMENT → SELF-CHECK → RUN TARGETED TESTS → RETURN RESULTS)
- Anti-patterns to avoid
- Self-check protocol (anti-stub check, test quality check, self-contradiction check)
- STUCK protocol (report BLOCKED instead of faking completion)
- JSON result format

**Template substitutions:**
- `{task_path}` → actual task file path
- `{task_id}` → task identifier (e.g., "task-34-01")
- `{package-name}` → package name from task metadata

Wait for all agents in the sub-group to complete before spawning the next sub-group.

#### 3c. Collect Agent Results

For each returned agent:
1. Parse the JSON report from the agent's output
2. Record status: IMPLEMENTED / BLOCKED / NEEDS_CONTEXT / FAILED
3. If **NEEDS_CONTEXT**: relay questions to user via `AskUserQuestion`, then re-spawn the agent with the answer
4. If **BLOCKED**: record the reason, add to `failed_tasks`
5. If **FAILED**: record targeted test failures, add to `failed_tasks`

Emit a brief progress report after all agents in the sub-group complete.

#### 3d. Run Full Test Suite Per Package

After ALL tasks in the wave have been implemented (all sub-groups done):

1. Group completed tasks in this wave by `package`
2. For each affected package, run the full test suite **directly via Bash**:

   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

   Include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash tool description.

3. Parse the test output:
   - Total tests, passed, failed
   - List of failing test names + error messages

4. If ALL tests pass → proceed to 3f (mark complete)
5. If tests fail → proceed to 3e (attribute & fix)

#### 3e. Attribute Failures and Fix Loop

For each test failure from the full suite:

1. **Attribute:** Cross-reference the failing test file against `files_created` and `files_modified` from tasks in this wave
2. **Read:** Read the failing test and the code it tests
3. **Fix:** Modify the code (stay within the attributed task's scope)
4. **Verify:** Re-run the specific failing test:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{failing-test-path}"
   ```
   Include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash tool description.
5. **Repeat:** Max 3 fix attempts per attributed task

**Stop conditions:**
- 3 attempts with no progress on a task → mark that task FAILED
- A fix introduces new failures → revert the fix attempt manually (edit back), report
- Cascading issues in unrelated subsystems → STOP, report

After fix loop, re-run full suite once to verify no regressions:
```bash
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
```

#### 3f. Handle Failures (Pause & Ask)

If any task still fails after 3 fix attempts:

Use `AskUserQuestion` to ask the user:
```
Task {task_id} ({title}) failed after 3 fix attempts.

Failing tests:
- {test_name}: {error_message}

Options:
1. Continue — skip this task and all tasks that depend on it, proceed with next wave
2. Stop — halt orchestration, emit final report with current progress
```

- If **Continue**: add task to `failed_tasks`, compute transitive dependents and add to `skipped_tasks`
- If **Stop**: emit final report (Step 4) and halt execution

#### 3g. Mark Tasks Complete

For each successfully verified task in this wave:

1. Mark as completed:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "{task_path}"
   ```
   Include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash tool description.

2. Add `## How Solved` section to the task file with proof-of-work:
   - Files created/modified (with line counts)
   - Raw test output (summary from full suite)
   - Design decisions

3. Add to `completed_tasks`

#### 3h. Wave Checkpoint

Emit a lean checkpoint and update TodoWrite:

```
Wave {N}/{total}: {completed} done, {failed} failed, {skipped} skipped | {package}: {passed}/{total} passing
```

If failed or skipped tasks exist, list only those (one ID per line). Do NOT list completed tasks — success is the default.

Mark the wave's todo as completed in TodoWrite.

---

## Step 4: Final Report

After all waves are executed (or execution is halted by user), emit a lean report:

```
DONE: {COMPLETED|PARTIAL|HALTED} — {completed}/{total} tasks, {waves_executed}/{total_waves} waves
Tests: {package}: {passed}/{total} | {package}: {passed}/{total}
Failed: {task-id} — {reason}  (only if any)
Skipped: {task-id} — blocked by {dep}  (only if any)
```

Do NOT list completed tasks — success is the default. Only list failures and skips.

---

## Anti-Patterns & Safety Rules

All rules from `d:\datrix\.claude\CLAUDE.md` apply. Key rules for the orchestrator:

- **NO workarounds** — fix root causes, not symptoms. If something is broken, trace to root cause
- **NO git reverts** — never use `git checkout`, `git restore`, `git reset`, `git stash`, `git revert`
- **NO debug scatter** — zero temporary logging statements left behind
- **NO mocks in tests** — `unittest.mock`, `MagicMock`, `SimpleNamespace` all banned
- **NO temporary files outside designated folders** — use `D:\datrix\.scripts\`, `D:\datrix\.test-output\`, `D:\datrix\.tmp\`
- **Test execution via PowerShell scripts only** — always use `test.ps1`, never call pytest directly
- **VERIFIED_AGAINST_QUICK_REFERENCE** — include in all Bash descriptions for script invocations
- **Logic map** — check `d:/datrix/.logic-map/markers.db` before modifying code with markers
- **Project domain isolation** — no customer/project domain language in framework packages

## Error Recovery

### Agent crashes or hits max_turns
- Mark task as BLOCKED with reason: "Agent exceeded max_turns — task may need to be broken down"
- Continue with remaining tasks in the wave
- Report in wave checkpoint

### Test infrastructure failure
- If `test.ps1` itself errors (not test failures, but script errors):
  - Retry once
  - If still fails → STOP and report: "Test infrastructure failure for package {name}"
  - Ask user whether to continue (skip test verification) or stop

### Partial wave completion
- If some tasks in a wave succeed and others fail:
  - Mark successes as COMPLETED
  - Mark failures as FAILED
  - Ask user about continuing (as per 3f)
  - Next wave processes only tasks whose dependencies are all in `completed_tasks`
