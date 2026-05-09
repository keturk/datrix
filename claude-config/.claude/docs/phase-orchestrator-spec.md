# Phase Orchestrator Specification

**Last Updated:** 2026-05-09
**Version:** 1.0

---

## Overview

The phase orchestrator is the execution engine for delegated skills. When a skill with a `delegation-strategy` is invoked, the orchestrator:

1. Parses the delegation strategy from frontmatter
2. Validates the strategy and extracts phase-specific prompts
3. Executes phases sequentially, spawning 1 or N agents per phase
4. Collects and synthesizes results
5. Reports progress via checkpoint streaming

**Key architectural principles:**
- **Sequential phase execution** — phases run in declaration order (no DAG)
- **Fail-fast** — if any phase fails, stop immediately and report
- **Parallel within phases** — parallelizable phases spawn multiple concurrent agents
- **Checkpoint streaming** — user sees progress as each phase completes
- **Result persistence** — phase outputs saved to `.agent_output/{session_id}/{phase_name}/`

---

## Execution Workflow

### High-Level Flow

```
User invokes skill
    ↓
Orchestrator validates delegation strategy
    ↓
For each phase (sequential):
    ↓
    Orchestrator extracts phase prompt
    ↓
    Orchestrator spawns agent(s) (parallel if phase.parallelizable == true)
    ↓
    Orchestrator waits for all agents to complete
    ↓
    If any agent failed → STOP, report error to user
    ↓
    Orchestrator collects results
    ↓
    Orchestrator emits checkpoint report
    ↓
Next phase
    ↓
Orchestrator synthesizes final report
```

### Detailed Step-by-Step Workflow

#### Step 1: Parse and Validate Skill

**Input:** Skill invocation (skill name + user arguments)

**Actions:**
1. Read the skill file (`{skill_name}/SKILL.md`)
2. Parse YAML frontmatter to extract `delegation-strategy` field
3. If no `delegation-strategy` exists → fall back to monolithic execution (not delegated)
4. Validate the delegation strategy (see Validation Rules below)
5. Parse skill body markdown to extract phase markers

**Validation rules (fail immediately if violated):**
- All `phases[].name` are unique
- All `phases[].model` are one of `"haiku"`, `"sonnet"`, `"opus"`
- All `phases[].max_parallel` (if present) are >= 1
- All required fields (`name`, `model`, `parallelizable`, `description`) are present
- Every `delegation-strategy.phases[].name` has matching `<!-- PHASE: {name} -->` and `<!-- END_PHASE: {name} -->` markers in skill body
- Every `<!-- PHASE: {name} -->` has a matching `<!-- END_PHASE: {name} -->`
- Phase markers do not nest

**Error handling:**
- On validation failure: Emit error message with specific rule violated
- Include skill name, phase name, and invalid value in error
- Do NOT proceed to phase execution

**Output:** Validated delegation strategy object + extracted phase prompts (map: phase_name → prompt_text)

---

#### Step 2: Execute Phases Sequentially

For each phase in `delegation-strategy.phases` (in declaration order):

##### 2a. Extract Phase Prompt

**Input:** Phase definition from delegation strategy

**Actions:**
1. Retrieve phase-specific content from extracted markers (content between `<!-- PHASE: {name} -->` and `<!-- END_PHASE: {name} -->`)
2. Prepend user's skill invocation arguments to phase prompt (so agents know what data to operate on)
3. Validate that phase prompt is non-empty

**Output:** Complete prompt text for this phase

---

##### 2b. Determine Agent Count

**Input:** Phase definition (`parallelizable`, `max_parallel`)

**Algorithm:**
```
if phase.parallelizable == false:
    agent_count = 1
else:
    # Determine actual work item count from user arguments
    # Example: if user provided 5 task files, work_items = 5
    work_item_count = count_work_items(user_arguments, phase)

    # Spawn up to max_parallel agents, but no more than work items
    agent_count = min(work_item_count, phase.max_parallel)
```

**Work item determination (phase-specific):**
- For `/execute-tasks` baseline phase: number of task files provided
- For `/troubleshoot-and-fix` log_parsing phase: number of log folders provided
- For non-parallelizable phases: always 1

**Output:** Number of agents to spawn for this phase

---

##### 2c. Spawn Agent(s)

**Input:** Phase definition, phase prompt, agent count

**Actions:**
1. Use Claude Code's `Task` tool to spawn agents
2. Set `model` parameter based on `phase.model` (maps to Task tool's `"haiku"`, `"sonnet"`, `"opus"`)
3. Set `description` to phase description from delegation strategy
4. If `agent_count > 1`: invoke multiple Task tool calls **in a single message** (parallel execution)
5. Pass phase-specific prompt to each agent

**Agent prompt structure:**
```
{Phase-specific instructions from phase markers}

---

# Context

Skill invocation: {user_arguments}
Phase: {phase.name}
Work item: {work_item_identifier}  # for parallel agents only

---

# Output Format

{Expected output format from phase prompt, typically JSON}
```

**Parallelization:**
- If phase is parallelizable: Create one agent per work item (up to `max_parallel`)
- All agents for a phase are spawned concurrently (single message with multiple Task tool calls)
- Each agent receives the same phase prompt but different work item context

**Output:** List of agent task IDs

---

##### 2d. Wait for Completion

**Input:** List of agent task IDs

**Actions:**
1. Use `TaskOutput` tool to wait for all agents to complete (blocking)
2. Collect result from each agent
3. Check agent exit status

**Output:** List of agent results (one per agent)

---

##### 2e. Check for Failures

**Input:** List of agent results

**Algorithm:**
```
for each agent_result in results:
    if agent_result.status == "failed":
        emit_error_report(phase, agent_result)
        STOP  # Do NOT proceed to next phase
```

**Error report format:**
```
PHASE FAILED — {phase.name}

Agent: {agent_id}
Work item: {work_item_identifier}
Status: FAILED

Error output:
{agent_result.output}

Recommendation: Review the phase prompt and work item. Fix the issue and re-invoke the skill.
```

**Output:** If any agent failed → abort entire skill execution. Otherwise, proceed.

---

##### 2f. Collect Results

**Input:** List of agent results (all successful)

**Actions:**
1. Parse each agent's output (typically JSON for structured data)
2. Aggregate results for the phase (structure depends on phase type)
3. Persist aggregated results to `.agent_output/{session_id}/{phase_name}/results.json`

**Aggregation patterns:**

**Single-agent phases (sequential):**
```json
{
  "phase": "pre_check",
  "agent_count": 1,
  "result": {
    // Single agent's output
  }
}
```

**Multi-agent phases (parallel):**
```json
{
  "phase": "baseline",
  "agent_count": 5,
  "results": [
    {"work_item": "task-40-01", "result": {...}},
    {"work_item": "task-40-02", "result": {...}},
    ...
  ]
}
```

**Output:** Phase result object (persisted to disk)

---

##### 2g. Emit Checkpoint Report

**Input:** Phase result object

**Actions:**
1. Format checkpoint report based on phase type
2. Emit to user (visible in conversation)

**Checkpoint format:**
```
CHECKPOINT — Phase {N}: {phase.name}
Status: COMPLETED
Model: {phase.model}
Agents: {agent_count} ({parallelizable ? "parallel" : "sequential"})
Results: {success_count}/{total_count} successful
{Phase-specific summary}
```

**Phase-specific summary examples:**

**Baseline capture:**
```
  - task-40-01: 12/12 tests passing
  - task-40-02: 8/8 tests passing
  - task-40-03: 15/15 tests passing (2 pre-existing failures)
```

**Verification:**
```
  - task-40-01: PASSED (12/12 tests passing)
  - task-40-02: PASSED (8/8 tests passing)
  - task-40-03: FAILED (13/15 tests passing, 2 new failures)
```

**Quality gate:**
```
Full suite: 185/185 tests passing
mypy --strict: clean
No new failures detected.
```

**Output:** Checkpoint report emitted to user

---

#### Step 3: Synthesize Final Report

**Input:** All phase results

**Actions:**
1. Aggregate key metrics across all phases (see Delegation Metrics Spec)
2. Format final report with:
   - Overall status (COMPLETED or FAILED)
   - Phase execution summary
   - Performance metrics (cost, latency if instrumented)
   - Final outcome

**Final report format:**
```
EXECUTION COMPLETE — {skill_name}

Overall Status: {COMPLETED | FAILED}

Phases executed: {N}/{total}
{For each phase: name, status, agent count, duration}

{Skill-specific final summary}

Performance Metrics:
- Cost: ${total_cost} (estimated ${monolithic_cost} monolithic, {savings}% reduction)
- Latency: {total_duration}s (estimated {monolithic_duration}s monolithic, {savings}% reduction)
- Phases successful: {success_count}/{total_count}
```

**Output:** Final report emitted to user

---

## Agent Spawning Logic

### Non-Parallelizable Phases

```python
# Spawn 1 agent with specified model
task_id = Task(
    subagent_type="general-purpose",
    model=phase.model,  # "haiku", "sonnet", or "opus"
    description=phase.description,
    prompt=phase_prompt
)

# Wait for completion
result = TaskOutput(task_id=task_id, block=True)

# Check status
if result.status == "failed":
    STOP_AND_REPORT_ERROR
```

### Parallelizable Phases

```python
# Determine work items from user arguments
work_items = extract_work_items(user_arguments, phase)

# Limit to max_parallel
agent_count = min(len(work_items), phase.max_parallel)
work_items = work_items[:agent_count]

# Spawn all agents in a single message (parallel)
task_ids = []
for work_item in work_items:
    task_id = Task(
        subagent_type="general-purpose",
        model=phase.model,
        description=f"{phase.description} — {work_item}",
        prompt=build_phase_prompt(phase_prompt, work_item)
    )
    task_ids.append(task_id)

# Wait for all to complete
results = []
for task_id in task_ids:
    result = TaskOutput(task_id=task_id, block=True)
    if result.status == "failed":
        STOP_AND_REPORT_ERROR
    results.append(result)
```

---

## Phase Prompt Extraction Algorithm

### Input
- Skill body markdown (full text)
- Phase name

### Algorithm

```python
def extract_phase_prompt(skill_body: str, phase_name: str) -> str:
    # Build marker patterns
    start_marker = f"<!-- PHASE: {phase_name} -->"
    end_marker = f"<!-- END_PHASE: {phase_name} -->"

    # Find start and end positions
    start_pos = skill_body.find(start_marker)
    if start_pos == -1:
        raise ValidationError(
            f"Phase '{phase_name}' declared in delegation-strategy "
            f"but no matching PHASE marker found in skill body"
        )

    end_pos = skill_body.find(end_marker, start_pos)
    if end_pos == -1:
        raise ValidationError(
            f"Phase '{phase_name}' has PHASE marker but no matching END_PHASE marker"
        )

    # Extract content between markers (exclude markers themselves)
    start_content = start_pos + len(start_marker)
    phase_content = skill_body[start_content:end_pos].strip()

    if not phase_content:
        raise ValidationError(
            f"Phase '{phase_name}' has empty content between markers"
        )

    return phase_content
```

### Output
Phase-specific prompt text (content between markers)

---

## Result Synthesis Patterns

### Structured Data (JSON)

Phases that return structured data (e.g., baseline test results, failure clusters) should output valid JSON.

**Agent output:**
```json
{
  "work_item": "task-40-01",
  "total_tests": 12,
  "pass_count": 12,
  "fail_count": 0,
  "pre_existing_failures": []
}
```

**Orchestrator aggregation (parallel phase):**
```json
{
  "phase": "baseline",
  "results": [
    {"work_item": "task-40-01", "total_tests": 12, ...},
    {"work_item": "task-40-02", "total_tests": 8, ...}
  ]
}
```

### Reports (Markdown)

Phases that produce human-readable reports (e.g., root cause analysis, fix plans) should output markdown.

**Agent output:**
```markdown
## Root Cause Analysis

**Cluster #1:** ImportError in generated entity files

**Causal chain:**
1. `.dtrx` defines entity with relationship to undefined service
2. `entity_generator.py` does not validate relationship targets
3. Template `entity.py.j2` generates import statement for undefined module
4. Generated file fails on import

**Confidence:** HIGH
**Fix location:** `src/generators/entity_generator.py:142`
```

**Orchestrator aggregation:**
Concatenate all agent reports with separator.

---

## Failure Handling

### Validation Failures (Before Execution)

**When:** During Step 1 (Parse and Validate)

**Action:**
- Emit error message with specific validation rule violated
- Include skill name, phase name, invalid value
- Do NOT proceed to phase execution

**Example:**
```
VALIDATION FAILED — /execute-tasks

Delegation strategy invalid:
- Phase 'baseline' missing required field 'model'
- Phase 'verify' has invalid model value 'gpt-4' (must be one of: haiku, sonnet, opus)

Fix the delegation-strategy in execute-tasks/SKILL.md and retry.
```

### Agent Failures (During Execution)

**When:** During Step 2e (Check for Failures)

**Action:**
- Emit phase failure report with agent ID, work item, error output
- STOP immediately — do NOT proceed to next phase
- Recommend next steps

**Example:**
```
PHASE FAILED — baseline

Phase: baseline
Agent: agent-baseline-3
Work item: task-40-03
Status: FAILED

Error output:
Targeted test command failed:
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Specific "tests/unit/test_foo.py"

Error: File 'tests/unit/test_foo.py' does not exist.

Recommendation: Check the task file's "Targeted Tests" section. Verify that test file paths are correct.
```

### Phase Result Failures (Semantic Failures)

**When:** A phase completes successfully but reports a semantic failure (e.g., verification phase detects new test failures)

**Action:**
- This is NOT an orchestrator failure — the phase succeeded in checking
- Phase result includes failure status
- Orchestrator continues to next phase (or stops if phase prompt says to STOP)

**Example (from verification phase):**
```
CHECKPOINT — Phase 4: Verification
Status: COMPLETED
Agents: 5 (parallel)
Results: 4/5 successful, 1 failed

Semantic failures:
  - task-40-03: FAILED (13/15 tests passing, 2 new failures)
    Fix attempts: 3/3 exhausted

Next action: Review task-40-03 manually and re-run after fixing.
```

---

## Progress Visibility

### Checkpoint Streaming

After each phase completes, emit a checkpoint report to the user. This provides real-time visibility into skill execution.

**Timing:** Immediately after Step 2g (Emit Checkpoint Report)

**Format:** See "Checkpoint format" in Step 2g above

**Purpose:**
- Show user that progress is being made
- Allow user to abort if a phase produces unexpected results
- Provide debugging context if later phases fail

### Final Report

After all phases complete, emit a final report summarizing the entire skill execution.

**Timing:** After Step 3 (Synthesize Final Report)

**Format:** See "Final report format" in Step 3 above

**Purpose:**
- Summarize overall outcome (success or failure)
- Report performance metrics (cost, latency)
- Provide actionable next steps if skill failed

---

## Result Persistence

All phase outputs should be persisted to disk for debugging and analysis.

**Directory structure:**
```
.agent_output/
  {session_id}/
    {phase_name}/
      results.json          # Aggregated phase results
      agent-{N}-output.txt  # Raw agent output (for debugging)
    metrics.jsonl           # Performance metrics (see Delegation Metrics Spec)
    final-report.md         # Synthesized final report
```

**File formats:**
- `results.json` — Structured JSON (phase-specific schema)
- `agent-{N}-output.txt` — Raw text output from agent
- `metrics.jsonl` — JSON Lines format (one metric event per line)
- `final-report.md` — Markdown report

---

## Example: Complete Execution Trace

**Skill:** `/execute-tasks` with 3 task files

**Delegation strategy:**
```yaml
delegation-strategy:
  phases:
    - name: "pre_check"
      model: "haiku"
      parallelizable: false
      description: "Read task files, validate dependencies"
    - name: "baseline"
      model: "haiku"
      parallelizable: true
      max_parallel: 5
      description: "Capture test baselines per task"
    - name: "implement"
      model: "sonnet"
      parallelizable: false
      description: "Apply code changes per task"
```

**Execution trace:**

```
[User invocation]
/execute-tasks
TASKS:
task-40-01.md
task-40-02.md
task-40-03.md

[Orchestrator: Step 1 — Parse and Validate]
✓ Delegation strategy parsed
✓ 3 phases validated
✓ Phase markers extracted

[Orchestrator: Step 2 — Execute Phase 1: pre_check]
Model: haiku
Agents: 1 (sequential)
[Agent spawned: agent-pre-check-1]
[Agent completed]

CHECKPOINT — Phase 1: pre_check
Status: COMPLETED
Model: haiku
Agents: 1 (sequential)
Results: 1/1 successful

Tasks in execution order:
  - task-40-01 (no dependencies)
  - task-40-02 (depends on task-40-01)
  - task-40-03 (depends on task-40-02)

[Orchestrator: Step 2 — Execute Phase 2: baseline]
Model: haiku
Agents: 3 (parallel, max 5)
[3 agents spawned in single message: agent-baseline-1, agent-baseline-2, agent-baseline-3]
[All agents completed]

CHECKPOINT — Phase 2: baseline
Status: COMPLETED
Model: haiku
Agents: 3 (parallel)
Results: 3/3 successful
  - task-40-01: 12/12 tests passing
  - task-40-02: 8/8 tests passing
  - task-40-03: 15/15 tests passing

[Orchestrator: Step 2 — Execute Phase 3: implement]
Model: sonnet
Agents: 1 (sequential)
[Agent spawned: agent-implement-1]
[Agent processes all 3 tasks sequentially]
[Agent completed]

CHECKPOINT — Phase 3: implement
Status: COMPLETED
Model: sonnet
Agents: 1 (sequential)
Results: 1/1 successful

Tasks implemented:
  - task-40-01: 2 files modified
  - task-40-02: 3 files created, 1 file modified
  - task-40-03: 1 file modified

[Orchestrator: Step 3 — Synthesize Final Report]

EXECUTION COMPLETE — /execute-tasks

Overall Status: COMPLETED

Phases executed: 3/3
1. pre_check (haiku, 1 agent, 8s)
2. baseline (haiku, 3 agents, 12s)
3. implement (sonnet, 1 agent, 145s)

Tasks completed: 3/3
  - task-40-01: COMPLETED
  - task-40-02: COMPLETED
  - task-40-03: COMPLETED

Performance Metrics:
- Cost: $0.42 (estimated $2.80 monolithic, 85% reduction)
- Latency: 165s (estimated 180s monolithic, 8% reduction)
- Phases successful: 3/3
```

---

## Related Documentation

- [Skill Delegation Metadata Schema](skill-delegation-schema.md) — Frontmatter and phase marker definitions
- [Skill Authoring Guide: Delegation](skill-authoring-guide-delegation.md) — Best practices for creating delegated skills
- [Delegation Performance Metrics](delegation-metrics-spec.md) — Cost, latency, and quality tracking

---

**Questions or feedback?** See `.claude/README.md` § Skill Delegation Architecture.
