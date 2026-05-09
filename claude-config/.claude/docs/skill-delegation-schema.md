# Skill Delegation Metadata Schema

**Last Updated:** 2026-05-09
**Version:** 1.0

---

## Overview

This document defines the YAML frontmatter schema for skill delegation strategies. The delegation architecture enables skills to decompose into phases, each running on an appropriate model (Haiku/Sonnet/Opus) with optional parallel execution.

Skills using the delegation architecture declare their phase structure in frontmatter and use HTML comment markers to delimit phase-specific content in the skill body.

---

## Frontmatter Schema

### `delegation-strategy` Field

The `delegation-strategy` field is an optional object added to skill frontmatter. When present, it signals to the Claude Code skill execution system that the skill should be executed using the phase orchestrator rather than as a monolithic prompt.

```yaml
---
description: Brief description of what this skill does
delegation-strategy:
  phases:
    - name: "phase_name"
      model: "haiku" | "sonnet" | "opus"
      parallelizable: true | false
      max_parallel: <integer>  # optional, defaults to 1
      description: "Brief description of what this phase does"
---
```

### Field Definitions

#### `delegation-strategy.phases` (required array)

Array of phase definitions. Phases execute in the order declared (sequential execution).

**Constraints:**
- Must contain at least 1 phase
- Recommended maximum: 7 phases (for maintainability)

#### `phases[].name` (required string)

Unique identifier for this phase within the skill.

**Constraints:**
- Must be unique within the skill
- Must match the phase markers in the skill body (see Phase Markers section)
- Recommended format: `snake_case` (e.g., `pre_check`, `baseline_capture`, `verify`)
- Maximum length: 50 characters

**Examples:**
- `"pre_check"`
- `"log_parsing"`
- `"root_cause_analysis"`
- `"verify"`

#### `phases[].model` (required string)

The Claude model to use for agents executing this phase.

**Valid values:**
- `"haiku"` — Fast, cost-efficient model for mechanical tasks
- `"sonnet"` — Balanced model for integrative tasks
- `"opus"` — Most capable model for architectural tasks

**Model selection guide (see Phase Taxonomy below):**
- Haiku: Log parsing, file operations, test execution, structured data extraction
- Sonnet: Multi-file edits, pattern application, template rendering
- Opus: Root cause diagnosis, design decisions, ambiguity resolution

#### `phases[].parallelizable` (required boolean)

Whether this phase can spawn multiple concurrent agents.

**Values:**
- `true` — Multiple agents can execute this phase concurrently (up to `max_parallel`)
- `false` — Only one agent executes this phase sequentially

**When to use `true`:**
- Phase operates on independent work items (e.g., multiple tasks, files, or log folders)
- Work items do NOT depend on each other
- I/O-heavy operations (file reading, test execution, code generation)

**When to use `false`:**
- Phase requires architectural decisions or design choices
- Work items depend on previous results
- Single logical operation (e.g., synthesizing a final report)

#### `phases[].max_parallel` (optional integer, default: 1)

Maximum number of concurrent agents to spawn for this phase.

**Constraints:**
- Must be >= 1
- Only relevant when `parallelizable: true`
- Ignored when `parallelizable: false` (always runs 1 agent)

**Recommendations:**
- For typical workloads: 3-5
- For I/O-bound tasks with many work items: 5-10
- Consider API rate limits and context window constraints

**Examples:**
```yaml
# Sequential phase (only 1 agent regardless of max_parallel)
parallelizable: false
max_parallel: 1  # optional, ignored

# Parallel phase with up to 5 concurrent agents
parallelizable: true
max_parallel: 5
```

#### `phases[].description` (required string)

Brief human-readable description of what this phase does.

**Guidelines:**
- Keep concise (1 sentence, max 120 characters)
- Focus on WHAT the phase does, not HOW
- Used in checkpoint reporting and debugging output

**Examples:**
- `"Read task files and validate dependencies"`
- `"Capture test baselines per task"`
- `"Apply code changes per task specification"`
- `"Parse failure logs and extract error clusters"`

---

## Phase Markers

Phase markers are HTML comments in the skill body that delimit phase-specific content. The orchestrator extracts content between matching markers and passes it to agents for that phase.

### Marker Syntax

```markdown
<!-- PHASE: {name} -->
{Phase-specific instructions, steps, and context}
<!-- END_PHASE: {name} -->
```

### Rules

1. **Matching names:** Phase marker `{name}` MUST exactly match `delegation-strategy.phases[].name` from frontmatter
2. **Pairing:** Every `PHASE:` marker MUST have a corresponding `END_PHASE:` marker with the same name
3. **Nesting:** Phase markers MUST NOT be nested (flat structure only)
4. **Order:** Marker order in the skill body SHOULD match phase order in frontmatter (for readability)
5. **Self-containment:** Content between markers MUST be fully self-contained — no references to "see above" or other phases

### Example

**Frontmatter:**
```yaml
---
description: Execute implementation tasks from task files
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
---
```

**Skill body:**
```markdown
<!-- PHASE: pre_check -->
## Pre-Execution Check

Read all task files and validate dependencies.

### Steps

1. Read each task file listed in the invocation
2. Extract `**Depends on:**` field from each task header
3. Verify that all dependencies are marked `COMPLETED:` in their task files
4. If any dependency is NOT completed, STOP and report

### Input

Task file paths from skill invocation arguments.

### Output

JSON array of tasks in execution order:
```json
[
  {
    "task_path": "d:\\datrix\\.tasks\\phase-40\\task-40-01.md",
    "dependencies": [],
    "files_to_read": ["d:\\datrix\\.claude\\README.md"]
  }
]
```

### Error Conditions

- Dependency not completed → STOP, report which task is blocked
- Task file does not exist → STOP, report invalid path
<!-- END_PHASE: pre_check -->

<!-- PHASE: baseline -->
## Baseline Test Capture

For each task, capture the test baseline before implementation.

### Steps

1. Read the task file at the given path
2. Extract the `## Targeted Tests` section
3. If no targeted tests section exists, determine package name and run full suite
4. Run each test command listed:
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package} -Specific "{test-path}"
   ```
5. Record: total tests, pass count, fail count, names of pre-existing failures

### Input

JSON: `{task_path: string}`

### Output

JSON:
```json
{
  "task_path": "d:\\datrix\\...",
  "total_tests": 12,
  "pass_count": 12,
  "fail_count": 0,
  "pre_existing_failures": []
}
```

### Notes

- This baseline is used in the verification phase to distinguish new failures from pre-existing ones
- Skip this phase for documentation-only tasks (tasks touching only .md files)
<!-- END_PHASE: baseline -->
```

---

## Phase Taxonomy

Use this taxonomy to assign the appropriate model to each phase.

| Phase Type | Model | Examples | Characteristics |
|------------|-------|----------|-----------------|
| **Mechanical** | Haiku | Log parsing, file reading, test execution, structured data extraction, baseline capture | I/O-heavy, deterministic, minimal reasoning required |
| **Integrative** | Sonnet | Multi-file edits, pattern application, template rendering, code refactoring | Requires understanding context across files, applying patterns |
| **Architectural** | Opus | Root cause diagnosis, design decisions, ambiguity resolution, architectural planning | Requires deep reasoning, handling ambiguity, making design tradeoffs |

**Cost implications:**
- Haiku: ~$0.25 per million tokens (input)
- Sonnet: ~$3 per million tokens (input)
- Opus: ~$15 per million tokens (input)

**Latency implications:**
- Haiku: Fastest
- Sonnet: Moderate
- Opus: Slowest (but most capable)

**Best practice:** Use the smallest model capable of the task. Over-using Opus for mechanical tasks wastes cost and latency.

---

## Validation Rules

The skill execution system MUST validate delegation strategies before executing phases:

1. **Unique phase names:** All `phases[].name` values are unique within the skill
2. **Valid models:** All `phases[].model` values are one of `"haiku"`, `"sonnet"`, `"opus"`
3. **Valid max_parallel:** All `phases[].max_parallel` values (if present) are >= 1
4. **Required fields:** All phases have `name`, `model`, `parallelizable`, and `description`
5. **Marker matching:** Every `delegation-strategy.phases[].name` has corresponding `<!-- PHASE: {name} -->` and `<!-- END_PHASE: {name} -->` markers in the skill body
6. **Marker pairing:** Every `<!-- PHASE: {name} -->` has a matching `<!-- END_PHASE: {name} -->`
7. **No nested markers:** Phase markers do not nest

**On validation failure:** Skill invocation MUST fail immediately with a clear error message indicating which validation rule was violated.

---

## Complete Example

This example shows a complete delegated skill with frontmatter and phase markers.

```markdown
---
description: Execute implementation tasks from task files
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
      description: "Apply code changes per task specification"
    - name: "verify"
      model: "haiku"
      parallelizable: true
      max_parallel: 5
      description: "Run targeted tests, compare to baseline"
    - name: "quality_gate"
      model: "opus"
      parallelizable: false
      description: "Run full suite and mypy for final validation"
---

# Execute Tasks

Systematic workflow for implementing tasks from task files.

## When to Use

- User provides task file paths and asks to implement them
- User says "execute tasks" or "work on phase N"

<!-- PHASE: pre_check -->
## Pre-Execution Check

Read all task files and validate dependencies.

[Self-contained instructions with steps, input/output specs, error conditions]
<!-- END_PHASE: pre_check -->

<!-- PHASE: baseline -->
## Baseline Test Capture

Capture test baselines before implementation.

[Self-contained instructions...]
<!-- END_PHASE: baseline -->

<!-- PHASE: implement -->
## Implementation

Apply code changes per task specification.

[Self-contained instructions...]
<!-- END_PHASE: implement -->

<!-- PHASE: verify -->
## Verification

Run targeted tests and compare to baseline.

[Self-contained instructions...]
<!-- END_PHASE: verify -->

<!-- PHASE: quality_gate -->
## Quality Gate

Run full suite and mypy for final validation.

[Self-contained instructions...]
<!-- END_PHASE: quality_gate -->
```

---

## Migration from Monolithic Skills

To convert an existing monolithic skill to use delegation:

1. **Identify natural phase boundaries** in the existing workflow (e.g., Read → Analyze → Plan → Implement → Verify)
2. **Assign models per phase** using the Phase Taxonomy table
3. **Determine parallelizability** for each phase (can work items run concurrently?)
4. **Add `delegation-strategy` to frontmatter** with phase definitions
5. **Wrap existing content with phase markers** in the skill body
6. **Ensure self-containment** — each phase prompt should be fully standalone
7. **Test**: Invoke the refactored skill and compare output to the monolithic version

---

## Related Documentation

- [Phase Orchestrator Specification](phase-orchestrator-spec.md) — Execution engine for delegated skills
- [Skill Authoring Guide: Delegation](skill-authoring-guide-delegation.md) — Best practices for creating delegated skills
- [Delegation Performance Metrics](delegation-metrics-spec.md) — Measuring cost, latency, and quality improvements

---

**Questions or feedback?** See `.claude/README.md` § Skill Delegation Architecture.
