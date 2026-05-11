---
description: Execute multiple tasks in parallel — evaluate all tasks for blockers, then delegate each to a separate agent
disable-model-invocation: true
delegation-strategy:
  phases:
    - name: "pre_check"
      model: "haiku"
      parallelizable: false
      description: "Read all task files, validate dependencies, identify blockers"
    - name: "spawn_agents"
      model: "sonnet"
      parallelizable: false
      description: "Spawn one agent per task to execute baseline→implement→verify in parallel"
    - name: "quality_gate"
      model: "opus"
      parallelizable: false
      description: "Run full suite and mypy for final validation across all tasks"
---

# Execute Tasks in Parallel

Parallel execution workflow for implementing multiple independent tasks from `.tasks/` phase files. Evaluates all tasks upfront for blocking issues, then spawns separate agents to execute each task concurrently.

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

## Mandatory Reading (BEFORE any work)

Before doing ANY work, read these documents in full:

1. **`d:\datrix\.claude\CLAUDE.md`** — Project rules. All rules apply throughout.
2. **`C:\Users\KErca\.claude\projects\d--datrix\memory\MEMORY.md`** — Persistent memory.
3. **`d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md`** — Full contributing rules (index with links to sub-documents under `ai-agent-rules/`).

### Project Structure (DYNAMIC — read from generated file)

Before implementing, read the project structure file for each target package's source, test, and template directory trees:

- **`d:\datrix\{package-name}\.project-structure.md`**

Where `{package-name}` is determined from the task file's `**Package:**` field (e.g., `datrix-codegen-python`, `datrix-common`).

If the file is missing or stale, regenerate it:
```bash
powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}
```

<!-- PHASE: pre_check -->
## Phase 1: Pre-Execution Check & Blocker Detection

Read all task files, validate dependencies, check for blockers, and determine if parallel execution is possible.

### Mandatory Reading

Before proceeding, read these documents in full:

1. **`d:\datrix\.claude\CLAUDE.md`** — Project rules
2. **`C:\Users\KErca\.claude\projects\d--datrix\memory\MEMORY.md`** — Persistent memory
3. **`d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md`** — Contributing rules

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
7. **Check for intra-phase dependencies:**
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
## Phase 2: Spawn Parallel Task Agents

For each task (all in parallel), spawn a dedicated agent to execute baseline→implement→verify workflow.

### Input

JSON from pre_check phase with task metadata and confirmation that `can_parallelize: true`.

### Steps

1. **For each task in the batch, spawn a Task agent with subagent_type="general-purpose":**

   **Agent task description format:**
   ```
   Execute single task: {task_id}
   ```

   **Agent prompt template:**
   ```
   You are executing a SINGLE task from a parallel batch. Your scope is LIMITED to this one task only.

   TASK FILE: {task_path}

   Your workflow:
   1. Baseline: Capture test baseline before implementation
   2. Implement: Read task file, apply code changes per specification
   3. Verify: Run targeted tests, compare to baseline, fix failures (max 3 attempts)

   CRITICAL RULES:
   - Read and follow ALL rules in d:\datrix\.claude\CLAUDE.md
   - Stay within this task's scope — do NOT modify files outside this task
   - If you encounter ambiguities, STOP and report them
   - Mark the task COMPLETED only if verification passes
   - Mark the task FAILED if verification fails after 3 attempts

   --- BASELINE PHASE ---

   1. Read the task file at: {task_path}
   2. Determine if task is documentation-only (all files are .md/.rst/.txt/.adoc)
   3. If documentation-only → skip baseline
   4. If code task → run targeted tests from "## Targeted Tests" section:
      powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package} -Specific "{test-path}"
   5. Record baseline results: total tests, pass count, fail count, pre-existing failures

   --- IMPLEMENTATION PHASE ---

   Step 1: Understand (Read Only)
   - Read task file completely
   - Read ALL files listed in "Files to Review Before Starting"
   - Read existing code in files to be modified
   - Search for existing functions/utilities (DRY principle)
   - If ambiguities found → STOP and report

   Step 2: Implement (Write Code)
   - Create/modify files as specified in task
   - Follow all code skeletons, type hints, patterns from task file
   - Apply full type hints (`mypy --strict` must pass)
   - Use standard logging: `logger = logging.getLogger(__name__)`, %-style formatting
   - Use Jinja2 templates + formatter for code generation (NO raw string concatenation)
   - Delete replaced functionality completely (no dead code, no backward-compatibility wrappers)
   - Check for logic map markers before modifying code

   Anti-patterns to AVOID:
   - NO dict.get(key, None) — raise explicit errors
   - NO type_map.get(t, "Any") — raise on unknown types
   - NO bare except: pass
   - NO # TODO / pass
   - NO -> T | None error returns
   - NO mocks/fakes in tests

   Step 3: Record implementation results

   --- VERIFICATION PHASE ---

   1. Run targeted tests (or full suite if no targeted tests specified)
   2. Compare results to baseline
   3. If new failures detected → invoke fix workflow (max 3 attempts):
      - Read failing test
      - Identify root cause
      - Fix the issue
      - Re-run tests
      - Track each attempt
   4. If fixed within 3 attempts → mark COMPLETED
   5. If NOT fixed after 3 attempts → mark FAILED
   6. Update task file:
      - COMPLETED: Change title to "# COMPLETED: Task {NN}-{TT}: {Title}", add "## How Solved" section
      - FAILED: Change title to "# FAILED: Task {NN}-{TT}: {Title}", add "## Why Failed" section

   --- OUTPUT FORMAT ---

   Return a JSON report:
   {
     "task_id": "{task_id}",
     "task_path": "{task_path}",
     "status": "COMPLETED" | "FAILED" | "BLOCKED",
     "baseline_results": {
       "skip_baseline": true/false,
       "total_tests": N,
       "pass_count": N,
       "fail_count": N,
       "pre_existing_failures": [...]
     },
     "implementation_results": {
       "files_created": [...],
       "files_modified": [...],
       "design_decisions": [...]
     },
     "verification_results": {
       "tests_run": N,
       "tests_passing": N,
       "tests_failing": N,
       "new_failures": [...],
       "fix_attempts": N,
       "fix_attempt_log": [...]
     },
     "errors": []
   }
   ```

2. **Spawn all agents in parallel** using a single message with multiple Task tool calls

3. **Wait for all agents to complete**

4. **Collect results from each agent:**
   - Task status (COMPLETED / FAILED / BLOCKED)
   - Files created/modified
   - Test results
   - Any errors encountered

### Model Selection

- Use `model: "sonnet"` for code implementation tasks
- Use `model: "haiku"` for documentation-only tasks
- Let each agent choose sub-models for its phases (baseline=haiku, implement=sonnet, verify=haiku)

### Output Format

```json
{
  "agents_spawned": 3,
  "agents_completed": 3,
  "agents_failed": 0,
  "results": [
    {
      "task_id": "task-40-01",
      "status": "COMPLETED",
      "files_created": ["d:\\datrix\\.claude\\docs\\skill-delegation-schema.md"],
      "files_modified": [],
      "tests_run": 0,
      "tests_passing": 0,
      "baseline_skipped": true
    },
    {
      "task_id": "task-40-02",
      "status": "COMPLETED",
      "files_created": ["d:\\datrix\\.claude\\docs\\phase-orchestrator-spec.md"],
      "files_modified": [],
      "tests_run": 0,
      "tests_passing": 0,
      "baseline_skipped": true
    },
    {
      "task_id": "task-40-03",
      "status": "FAILED",
      "files_created": ["src/generators/entity_generator.py"],
      "files_modified": ["src/core/generator_base.py"],
      "tests_run": 15,
      "tests_passing": 13,
      "tests_failing": 2,
      "new_failures": ["test_entity_relationships", "test_field_inheritance"],
      "fix_attempts": 3,
      "recommendation": "Review entity relationship logic"
    }
  ]
}
```

### Checkpoint Reporting

After all agents complete, emit a summary:

```
PARALLEL EXECUTION COMPLETE

Agents spawned: 3
Agents completed: 2
Agents failed: 1

COMPLETED:
✓ Task 40-01: Define Skill Delegation Metadata Schema
  - Files created: skill-delegation-schema.md
  - Documentation-only (no tests)

✓ Task 40-02: Design Phase Orchestrator Specification
  - Files created: phase-orchestrator-spec.md
  - Documentation-only (no tests)

FAILED:
✗ Task 40-03: Implement Entity Generator
  - Files created: entity_generator.py
  - Files modified: generator_base.py
  - Tests: 13/15 passing (2 new failures after 3 fix attempts)
  - Failing tests:
    • test_entity_relationships — AssertionError: Expected bidirectional refs
    • test_field_inheritance — AttributeError: 'Field' has no 'parent'
  - Recommendation: Review entity relationship logic

Proceeding to quality gate phase...
```

### Error Handling

If an agent crashes or times out:
- Record the error in results
- Mark task as BLOCKED
- Continue with other agents
- Report the issue in quality gate phase
<!-- END_PHASE: spawn_agents -->

<!-- PHASE: quality_gate -->
## Phase 3: Quality Gate

Run the full test suite and mypy for all affected package(s) to catch cross-task integration issues.

### Input

Results from all spawned agents:

```json
{
  "tasks": [
    {"task_id": "task-40-01", "status": "COMPLETED", "package": ".claude/"},
    {"task_id": "task-40-02", "status": "COMPLETED", "package": ".claude/"},
    {"task_id": "task-40-03", "status": "FAILED", "package": "datrix-codegen-python"}
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

   **Type checking:**
   ```
   mypy --strict src/{package_underscored}/
   ```

   (Note: Skip mypy for documentation-only packages like `.claude/`)

3. **Analyze results:**
   - Compare to initial baseline (from pre_check phase if captured)
   - Identify any NEW failures not reported by individual task agents
   - Attribute failures to likely source tasks

4. **Cross-reference failures:**
   - For each new failure, extract the failing test file path
   - Check which task modified code related to that test
   - Report attribution

### Output Format

**If quality gate PASSED:**

```json
{
  "status": "COMPLETED",
  "packages_tested": ["datrix-codegen-python", ".claude/"],
  "results_per_package": [
    {
      "package": "datrix-codegen-python",
      "total_tests": 185,
      "tests_passing": 183,
      "tests_failing": 2,
      "mypy_status": "clean",
      "known_failures": ["test_entity_relationships", "test_field_inheritance"],
      "new_failures_detected": []
    },
    {
      "package": ".claude/",
      "total_tests": 0,
      "documentation_only": true,
      "mypy_status": "skipped"
    }
  ]
}
```

Emit:
```
QUALITY GATE — All Packages
Status: PASSED

Package: datrix-codegen-python
  Tests: 183/185 passing
  Known failures: 2 (from Task 40-03, already reported)
  New failures: none detected
  mypy: clean

Package: .claude/
  Documentation-only (no tests)

✓ No integration issues detected.
```

**If quality gate FAILED:**

```json
{
  "status": "FAILED",
  "packages_tested": ["datrix-codegen-python"],
  "results_per_package": [
    {
      "package": "datrix-codegen-python",
      "total_tests": 185,
      "tests_passing": 180,
      "tests_failing": 5,
      "mypy_status": "2 errors",
      "known_failures": ["test_entity_relationships", "test_field_inheritance"],
      "new_failures_detected": [
        {
          "test_name": "test_service_generator_integration",
          "error": "ImportError: cannot import name 'GeneratorBase'",
          "likely_source_task": "task-40-03",
          "reason": "Task 40-03 modified generator_base.py"
        },
        {
          "test_name": "test_field_validator",
          "error": "AttributeError: 'FieldValidator' object has no attribute 'validate_all'",
          "likely_source_task": "task-40-04",
          "reason": "Task 40-04 refactored FieldValidator interface"
        }
      ],
      "mypy_errors": [
        {
          "file": "src/generators/entity_generator.py",
          "line": 45,
          "error": "Incompatible return type",
          "likely_source_task": "task-40-03"
        }
      ]
    }
  ]
}
```

Emit:
```
QUALITY GATE — datrix-codegen-python
Status: FAILED (integration issues detected)

Tests: 180/185 passing
Known failures from task verification: 2
NEW failures detected: 3

New failures (not reported by task agents):
✗ test_service_generator_integration
  ImportError: cannot import name 'GeneratorBase'
  Likely source: Task 40-03 (modified generator_base.py)
  Impact: Service generator now broken due to base class changes

✗ test_field_validator
  AttributeError: 'FieldValidator' object has no attribute 'validate_all'
  Likely source: Task 40-04 (refactored FieldValidator interface)
  Impact: Field validation broken in downstream code

mypy errors: 2
✗ src/generators/entity_generator.py:45 — Incompatible return type
  Likely source: Task 40-03

RECOMMENDATION:
1. Task 40-03 introduced breaking changes to GeneratorBase — needs interface fix
2. Task 40-04 broke FieldValidator contract — needs compatibility layer or downstream updates
3. Re-run failed tasks with fixes, then re-run quality gate
```

### Notes

- Quality gate runs AFTER all parallel task agents complete
- It's the ONLY place to catch integration issues between tasks
- Failed quality gate does NOT automatically re-run tasks — report to user for decision
<!-- END_PHASE: quality_gate -->

## Final Report

After all phases complete:

```
PARALLEL EXECUTION COMPLETE

Tasks processed: {N}
Tasks completed: {N}
Tasks failed: {N}
Quality gate: PASSED / FAILED

SUMMARY:

Completed:
✓ Task 40-01: Define Skill Delegation Metadata Schema
  Files: skill-delegation-schema.md (created)

✓ Task 40-02: Design Phase Orchestrator Specification
  Files: phase-orchestrator-spec.md (created)

Failed:
✗ Task 40-03: Implement Entity Generator
  Files: entity_generator.py (created), generator_base.py (modified)
  Reason: 2 test failures after 3 fix attempts

Integration Issues (Quality Gate):
✗ 3 new failures detected across package
✗ 2 mypy errors
  See quality gate report above for details

NEXT STEPS:
1. Review and fix Task 40-03 failures
2. Address integration issues from quality gate
3. Re-run quality gate to verify fixes

Performance Metrics:
- Wall-clock time: {duration}s
- Estimated sequential time: {estimated_sequential}s
- Time savings: {savings}%
- Total cost: ${total_cost}
```

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
