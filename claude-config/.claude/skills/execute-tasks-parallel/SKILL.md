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

```json
{
  "can_parallelize": true,
  "blocking_issues": [],
  "tasks": [
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
      "intra_phase_dependencies": [],
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
      "intra_phase_dependencies": ["task-40-01"],
      "files_to_review": ["d:\\datrix\\.claude\\docs\\skill-delegation-schema.md"],
      "files_to_create": ["d:\\datrix\\.claude\\docs\\phase-orchestrator-spec.md"],
      "files_to_modify": [],
      "red_flags": []
    }
  ]
}
```

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

- **max_turns:** Set `max_turns: 40` on each spawned agent. Do NOT leave agents uncapped — an agent that runs for hundreds of turns without returning is unmonitorable and blocks question relay.
- **No background agents:** Do NOT use `run_in_background: true`. Spawn agents in the foreground so the orchestrator can receive their results (including questions and status) promptly. Since multiple foreground agents are spawned in a single message, they still execute concurrently.
- **Question relay:** If an agent returns with status BLOCKED or NEEDS_CONTEXT and includes questions/ambiguities, the orchestrator MUST immediately relay those questions to the user via `AskUserQuestion`. After receiving answers, resume the agent with the context. Do NOT silently skip blocked agents or guess answers on behalf of the user.
- **Progress reporting:** After all agents return (or after resuming any that had questions), emit a progress summary to the user before proceeding to the quality gate phase. If any agent is still outstanding, report which tasks are pending and what's holding them up.

1. **For each task in the batch, spawn a Task agent with subagent_type="general-purpose":**

   **Agent task description format:**
   ```
   Execute single task: {task_id}
   ```

   **Critical Task tool parameters:**
   - `max_turns: 40` — hard limit per agent
   - Do NOT set `run_in_background: true`

   **Agent prompt template:**

   Read `d:\datrix\datrix\claude-config\.claude\agent-templates\task-implementation-agent.md` and substitute `{task_path}` with the actual task file path.

   **Additional context to prepend:**
   ```
   You are executing a SINGLE task from a parallel batch. Your scope is LIMITED to this one task only.

   IMPORTANT: You implement code AND run ONLY targeted tests for your task.
   Do NOT run the full test suite — the orchestrator runs it once after ALL agents
   complete, to avoid N parallel full-suite executions.
   ```

   **See the template file for:**
   - Complete workflow steps (UNDERSTAND → IMPLEMENT → SELF-CHECK → RUN TARGETED TESTS → RETURN RESULTS)
   - Anti-patterns to avoid
   - Self-check protocol
   - STUCK protocol
   - JSON result format

2. **Spawn all agents in parallel** using a single message with multiple Task tool calls (all foreground, `max_turns: 40`)

3. **Collect results as agents return:**
   - Task status (IMPLEMENTED / BLOCKED / NEEDS_CONTEXT / FAILED)
   - Files created/modified
   - Targeted test results (pass/fail, fix attempts made)
   - Any errors or questions encountered

4. **Handle agent questions immediately:**
   - If ANY agent returns with **spec gap or missing user input** (NEEDS_CONTEXT — unclear requirement, missing path, credential): use `AskUserQuestion` to relay to the user; resume the agent after receiving answers; do NOT proceed to quality gate while questions are outstanding
   - If ANY agent returns with **technical ambiguity** (BLOCKED or NEEDS_CONTEXT with a design choice, conflicting patterns, or unclear root cause): invoke the **Decision Escalation Protocol** — spawn an Opus 4.8 agent to analyze and recommend; resume the implementation agent with Opus's recommendation
   - If ANY agent returns with a **hard blocker** (BLOCKED due to missing dependency, missing file, incomplete prereq): record the failure, report to user, do not re-attempt

5. **Report progress to user** after all agents have returned (or been resumed and re-completed):
   - Which tasks completed implementation
   - Brief summary of each result including targeted test outcomes
   - Which targeted tests passed/failed per agent
   - Proceed directly to Phase 3 (quality gate) — agents already ran targeted tests

### Model Selection

- Use `model: "claude-sonnet-4-6"` for code implementation tasks
- Use `model: "haiku"` for documentation-only tasks

### Output Format

```json
{
  "agents_spawned": 3,
  "agents_implemented": 3,
  "results": [
    {
      "task_id": "task-40-01",
      "status": "IMPLEMENTED",
      "files_created": ["d:\\datrix\\.claude\\docs\\skill-delegation-schema.md"],
      "files_modified": [],
      "targeted_tests": {"ran": false, "no_targeted_tests": true}
    },
    {
      "task_id": "task-40-02",
      "status": "IMPLEMENTED",
      "files_created": ["d:\\datrix\\.claude\\docs\\phase-orchestrator-spec.md"],
      "files_modified": [],
      "targeted_tests": {
        "ran": true,
        "passed": true,
        "fix_attempts": 0,
        "test_commands": ["powershell -File \"d:/datrix/datrix/scripts/test/test.ps1\" datrix-common -Specific \"tests/unit/test_phase_orchestrator.py\""]
      }
    },
    {
      "task_id": "task-40-03",
      "status": "IMPLEMENTED",
      "files_created": ["src/generators/entity_generator.py"],
      "files_modified": ["src/core/generator_base.py"],
      "targeted_tests": {
        "ran": true,
        "passed": true,
        "fix_attempts": 1,
        "test_commands": ["powershell -File \"d:/datrix/datrix/scripts/test/test.ps1\" datrix-codegen-python -Specific \"tests/unit/test_entity_generator.py\""]
      }
    }
  ]
}
```

### Checkpoint Reporting

After all agents complete, emit a summary to the user:

```
IMPLEMENTATION PHASE COMPLETE

Agents spawned: 3
Implemented: 3

IMPLEMENTED (targeted tests passed by agents):
✓ Task 40-01: Define Skill Delegation Metadata Schema
  - Files created: skill-delegation-schema.md
  - No targeted tests defined

✓ Task 40-02: Design Phase Orchestrator Specification
  - Files created: phase-orchestrator-spec.md
  - Targeted tests: PASSED

✓ Task 40-03: Implement Entity Generator
  - Files created: entity_generator.py
  - Files modified: generator_base.py
  - Targeted tests: PASSED (1 fix attempt)

Proceeding to full-suite quality gate...
```

### Error Handling

If an agent crashes, times out, or hits `max_turns`:
- Record the error in results
- Mark task as BLOCKED with explanation (e.g., "Agent hit max_turns limit — task may need to be broken down or retried")
- Report the issue to the user immediately — do NOT silently skip
- Continue with other agents
- Report the issue in quality gate phase

If an agent returns with questions (NEEDS_CONTEXT):
- Relay questions to user via AskUserQuestion
- Resume agent after user provides answers
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
- **First attempt fails** and root cause is unclear → immediately invoke the **Decision Escalation Protocol** (Opus 4.8 agent with full context: task spec, the failed attempt, exact failures); implement Opus's recommendation; if still failing → mark that task FAILED
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

- **If all tests pass (including full suite):**
  - Mark task as completed using the script:
    ```bash
    powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "{task_path}"
    ```
    This changes the title from `# Task {NN}-{TT}: {Title}` to `# COMPLETED: Task {NN}-{TT}: {Title}`.
  - Add `## How Solved` section with proof-of-work (raw pytest output from final full suite, file line counts)
  - Status → COMPLETED

- **If tests still fail after fix loop:**
  - Update task file: change title to `# FAILED: Task {NN}-{TT}: {Title}`
  - Add `## Why Failed` section with fix attempt log and failing tests
  - Status → FAILED

For tasks that agents already marked FAILED (targeted test failures):
- Keep status as FAILED — do not re-attempt in this phase
- Report to user for separate attention

### Output Format

**If verification PASSED:**

```json
{
  "status": "PASSED",
  "packages_tested": ["datrix-codegen-python"],
  "full_suite_runs": 2,
  "results_per_package": [
    {
      "package": "datrix-codegen-python",
      "total_tests": 185,
      "tests_passing": 185,
      "tests_failing": 0
    }
  ],
  "tasks_completed": ["task-40-01", "task-40-02"],
  "tasks_failed": ["task-40-03"],
  "fix_loop_applied": true,
  "fixes_made": [
    {"task": "task-40-02", "test": "test_integration_x", "attempt": 1, "result": "fixed"}
  ]
}
```

Emit:
```
VERIFICATION & QUALITY GATE — datrix-codegen-python
Status: PASSED

Full suite: 185/185 passing
Full suite runs: 2 (initial + post-fix validation)

Tasks now COMPLETED:
✓ Task 40-01: Define Skill Delegation Metadata Schema
✓ Task 40-02: Design Phase Orchestrator Specification (1 integration fix applied)

Tasks FAILED (from agent phase — not re-attempted):
✗ Task 40-03: Implement Entity Generator — 2 targeted test failures
```

**If verification FAILED:**

```json
{
  "status": "FAILED",
  "packages_tested": ["datrix-codegen-python"],
  "full_suite_runs": 2,
  "results_per_package": [
    {
      "package": "datrix-codegen-python",
      "total_tests": 185,
      "tests_passing": 180,
      "tests_failing": 5,
      "known_failures": ["test_entity_relationships", "test_field_inheritance"],
      "new_failures": [
        {
          "test_name": "test_service_generator_integration",
          "error": "ImportError: cannot import name 'GeneratorBase'",
          "likely_source_task": "task-40-03",
          "fix_attempts": 3,
          "fix_result": "not_fixed"
        }
      ]
    }
  ]
}
```

Emit:
```
VERIFICATION & QUALITY GATE — datrix-codegen-python
Status: FAILED

Full suite: 180/185 passing
Known failures (agent phase): 2
New failures (integration): 3 (1 fixed, 2 not fixed after 3 attempts)

Not fixed:
✗ test_service_generator_integration
  ImportError: cannot import name 'GeneratorBase'
  Source: Task 40-03 (modified generator_base.py)
  Fix attempts: 3 — not resolved

RECOMMENDATION:
1. Task 40-03 needs manual review — GeneratorBase interface change broke downstream
2. Re-run with /fix-tests after manual correction
```

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

When execution reaches a genuine design or architectural decision — one where multiple valid approaches exist, root cause is unclear after investigation, or the right fix scope is ambiguous — escalate to an Opus 4.8 agent **before** asking the user or marking a task failed.

### When to Escalate

**DO escalate for:**
- An agent returns BLOCKED or NEEDS_CONTEXT with a **technical ambiguity** (design choice, conflicting patterns, unclear root cause) — not a hard blocker
- The Phase 3 first fix attempt fails and root cause is unclear
- A fix introduces additional failures, suggesting a systemic issue
- Cascading failures across unrelated code — correct scope of fix is unclear

**Do NOT escalate for:**
- Hard blockers: missing dependency, incomplete prereq task, missing file → STOP and report immediately
- Simple errors with obvious fixes → fix directly
- Missing user-supplied input → ask user directly

### How to Escalate

Spawn a subagent via the Agent tool:

```
subagent_type: "general-purpose"
model: "opus"
description: "Opus decision: {brief problem description}"
```

**Opus agent prompt:**
```
You are a senior architect making a high-stakes implementation decision. Do NOT implement — analyze and recommend only.

CONTEXT:
Task: {task_id} — {title}
Objective: {what the task was supposed to accomplish}

PROBLEM:
{exact error, conflict, or ambiguity — be specific}

WHAT WAS TRIED:
{each fix attempt or approach considered, with outcome}

RELEVANT CODE (key excerpts):
{file paths and actual code snippets}

YOUR TASK:
Analyze for long-term correctness. Do NOT suggest workarounds, band-aids, or "good enough for now" solutions. Consider:
- Root cause (not symptom)
- Impact on other components
- Consistency with existing patterns
- Long-term maintainability

Return:
1. Root cause analysis (2-3 sentences)
2. Recommended approach — concrete, step-by-step instructions
3. Exact files to modify and what changes to make
4. Why this is the right long-term choice (not the quick fix)
5. Any risks or prerequisites

Be specific. The implementing agent will follow your recommendation directly.
```

### After Opus Returns

- Resume with the current model (Sonnet) and implement exactly what Opus recommended
- Do NOT improvise beyond the recommendation
- If Opus recommends stopping and asking the user, surface Opus's full analysis as context when asking

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

- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

