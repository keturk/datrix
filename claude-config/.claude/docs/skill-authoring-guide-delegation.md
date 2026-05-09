# Skill Authoring Guide: Delegation

**Last Updated:** 2026-05-09
**Version:** 1.0

---

## Overview

This guide explains how to author skills using the delegation architecture. Delegation allows skills to decompose into phases, each running on an appropriate model (Haiku/Sonnet/Opus) with optional parallel execution.

**Why use delegation?**
- **Cost reduction:** 50-90% savings by using Haiku for mechanical tasks instead of Opus for everything
- **Latency improvement:** 20%+ reduction via parallel phase execution
- **Quality preservation:** Model specialization improves outcomes (Haiku for I/O, Opus for reasoning)

---

## When to Use Delegation

### Use delegation when your skill has:

✅ **3+ distinct phases** with different cognitive demands
- Example: `/execute-tasks` has pre-check → baseline → implement → verify → quality gate

✅ **Parallelizable work** (multiple independent tasks, files, or log folders)
- Example: baseline capture for 5 tasks can run concurrently (Haiku agents × 5)

✅ **I/O-heavy phases** that don't need Opus-level reasoning
- Example: reading test logs and extracting failure clusters (Haiku) vs. tracing root causes (Opus)

### Avoid delegation when:

❌ **Single-phase skill** (no natural decomposition)
- Example: `/imports` just looks up canonical import paths — no phases

❌ **All phases require architectural reasoning** (no cost/latency benefit)
- If every phase needs Opus, delegation adds overhead without benefit

❌ **Phases are tightly coupled** (each depends on previous phase's detailed output)
- Delegation works best when phases have clean interfaces (structured JSON outputs)

---

## Phase Taxonomy and Model Selection

Use this taxonomy to assign the right model to each phase:

| Phase Type | Model | Characteristics | Examples |
|------------|-------|-----------------|----------|
| **Mechanical** | Haiku | I/O-heavy, deterministic, minimal reasoning required | Log parsing, file reading, test execution, structured data extraction, baseline capture |
| **Integrative** | Sonnet | Requires understanding context across files, applying patterns | Multi-file edits, pattern application, template rendering, code refactoring |
| **Architectural** | Opus | Requires deep reasoning, handling ambiguity, making design tradeoffs | Root cause diagnosis, design decisions, ambiguity resolution, architectural planning |

### Cost Implications

| Model | Input (per MTok) | Output (per MTok) | Use Case |
|-------|------------------|-------------------|----------|
| Haiku | $0.25 | $1.25 | Mechanical tasks |
| Sonnet | $3.00 | $15.00 | Integrative tasks |
| Opus | $15.00 | $75.00 | Architectural tasks |

**Best practice:** Use the smallest model capable of the task. Over-using Opus for mechanical tasks wastes cost and latency.

### Latency Implications

- **Haiku:** Fastest (use for I/O-bound tasks)
- **Sonnet:** Moderate (balanced speed and capability)
- **Opus:** Slowest but most capable (use sparingly for high-value reasoning)

**Parallelization:** Haiku tasks with parallel execution can process 3-5 work items concurrently with minimal latency increase.

---

## Decomposition Guidelines

### Identify Natural Phase Boundaries

Good phase boundaries have:
1. **Clear input/output contracts** (structured JSON or markdown reports)
2. **Minimal coupling** between phases (each phase is self-contained)
3. **Distinct cognitive demands** (different phase taxonomy types)

**Example: `/execute-tasks` decomposition:**

| Phase | Type | Model | Boundary |
|-------|------|-------|----------|
| pre_check | Mechanical | Haiku | Input: task file paths → Output: validated task metadata JSON |
| baseline | Mechanical | Haiku | Input: task metadata → Output: test baseline results JSON |
| implement | Integrative | Sonnet | Input: task metadata + baseline → Output: files created/modified list |
| verify | Mechanical | Haiku | Input: task metadata + baseline + implementation → Output: test results JSON |
| quality_gate | Architectural | Opus | Input: all verification results → Output: final report |

**Key insight:** Each phase has a single responsibility and produces structured output for the next phase.

### Keep Phases Sequential Initially

The initial delegation architecture supports **sequential phase execution only** (no DAG).

- Phases execute in the order declared in frontmatter
- Each phase can access outputs from ALL previous phases
- No parallel dependencies between phases (only within phases)

**Future:** DAG-based dependencies may be added if needed, but sequential execution handles 90% of use cases.

### Ensure Phases Have Clear Inputs/Outputs

Each phase should define:
- **Input format:** What data does this phase receive? (preferably JSON schema)
- **Output format:** What data does this phase produce? (preferably JSON schema)
- **Error conditions:** What causes this phase to fail?

**Example (baseline phase input/output):**

```markdown
### Input

JSON from pre_check phase with task metadata. For each task:

{
  "task_path": "d:\\...",
  "task_id": "task-40-01",
  "package": ".claude/"
}

### Output

JSON per task:

{
  "task_path": "d:\\...",
  "task_id": "task-40-01",
  "total_tests": 12,
  "pass_count": 12,
  "pre_existing_failures": []
}
```

### Each Phase Should Be Independently Testable

A well-designed phase can be tested in isolation by:
1. Providing sample input JSON
2. Running the phase prompt
3. Verifying output JSON matches schema

This makes debugging easier when phases fail.

---

## Writing Phase Prompts

### Self-Containment Requirement (CRITICAL)

Each phase prompt MUST be fully self-contained. Agents executing a phase receive ONLY the phase-specific content (between `<!-- PHASE: {name} -->` markers), not the full skill document.

**BAD (references external content):**

```markdown
<!-- PHASE: baseline -->
## Baseline Test Capture

Follow the workflow described in Phase 1 above to capture test baselines.
<!-- END_PHASE: baseline -->
```

❌ Agents won't see "Phase 1 above" — they only see content between markers.

**GOOD (fully self-contained):**

```markdown
<!-- PHASE: baseline -->
## Baseline Test Capture

For each task, capture the test baseline before implementation.

### Steps

1. Read the task file at the given path
2. Extract the `## Targeted Tests` section
3. Run each test command listed:
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package} -Specific "{test-path}"
   ```
4. Record: total tests, pass count, fail count, names of pre-existing failures

### Input

JSON: `{task_path: string}`

### Output

JSON:
{
  "task_path": "...",
  "total_tests": 12,
  "pass_count": 12,
  "pre_existing_failures": []
}
<!-- END_PHASE: baseline -->
```

✅ Agents have all information needed to execute the phase.

### Include All Context Needed

Phase prompts should include:
- **File paths** (absolute paths for scripts, tools, configs)
- **Command syntax** (exact bash/powershell commands to run)
- **Validation rules** (what makes output valid or invalid)
- **Error conditions** (what to do when things go wrong)

**Example:**

```markdown
### Steps

1. Run the full test suite:
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

2. Also run mypy:
   ```
   mypy --strict src/{package_underscored}/
   ```

3. Record results:
   - Total tests
   - Pass count
   - Fail count

### Error Conditions

- If test command fails (e.g., package not found) → record error in output JSON
- If mypy fails → include mypy errors in output
```

### Use Structured Outputs (JSON)

Prefer JSON for phase outputs when possible:
- Machine-readable (orchestrator can parse and route to next phase)
- Schema-validatable (can enforce contracts)
- Easy to aggregate (parallel phase outputs combine into arrays)

**Exception:** Reports for human consumption (e.g., final reports, root cause analyses) can use markdown.

---

## Frontmatter Schema

### Basic Structure

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

### Field Guidelines

#### `phases[].name`

- Use `snake_case` (e.g., `pre_check`, `baseline`, `verify`)
- Keep concise (max 50 characters)
- Must match phase markers exactly

#### `phases[].model`

- Choose based on phase taxonomy (see table above)
- Prefer smaller models when possible (cost/latency)
- Reserve Opus for high-value reasoning

#### `phases[].parallelizable`

- `true` if phase operates on independent work items (tasks, files, logs)
- `false` if phase requires sequential execution or makes design decisions

**When to use `true`:**
- Phase processes N independent items (e.g., N task files)
- Items do NOT depend on each other
- I/O-heavy operations (reading files, running tests)

**When to use `false`:**
- Phase makes architectural decisions
- Items depend on previous results
- Single logical operation

#### `phases[].max_parallel`

- Only relevant when `parallelizable: true`
- Defaults to 1 if omitted
- Typical values: 3-5 for most workloads
- Consider API rate limits and context window constraints

#### `phases[].description`

- One sentence (max 120 characters)
- Focus on WHAT the phase does, not HOW
- Used in checkpoint reporting and debugging

---

## Phase Markers

### Marker Syntax

```markdown
<!-- PHASE: {name} -->
{Phase-specific instructions, steps, and context}
<!-- END_PHASE: {name} -->
```

### Rules

1. **Matching names:** Marker `{name}` MUST match `delegation-strategy.phases[].name` from frontmatter
2. **Pairing:** Every `PHASE:` marker MUST have a matching `END_PHASE:` marker
3. **Nesting:** Phase markers MUST NOT be nested (flat structure only)
4. **Order:** Marker order in skill body SHOULD match phase order in frontmatter (for readability)

---

## Best Practices

### 1. Parallelize I/O-Heavy Phases

Phases that read/write files, run tests, or execute commands can often run in parallel:

```yaml
- name: "baseline"
  model: "haiku"
  parallelizable: true
  max_parallel: 5
  description: "Capture test baselines per task"
```

**ROI:** If each task takes 10s to baseline, 5 tasks take 10s (parallel) vs. 50s (sequential) — 80% latency reduction.

### 2. Keep Architectural Decisions Sequential

Phases that make design decisions or resolve ambiguity should be sequential (Opus):

```yaml
- name: "root_cause_analysis"
  model: "opus"
  parallelizable: false
  description: "Trace failures to codegen source and build causal chains"
```

**Why:** Architectural reasoning benefits from full context and should not be rushed.

### 3. Limit `max_parallel` Based on Typical Workload

For most skills:
- **3-5 concurrent agents** is optimal (balances parallelism vs. API rate limits)
- **Don't over-parallelize** (10+ agents may hit rate limits or overwhelm context window)

**Example:** `/execute-tasks` uses `max_parallel: 5` because most phase invocations have 3-7 tasks.

### 4. Persist Phase Outputs for Debugging

The orchestrator persists phase outputs to `.agent_output/{session_id}/{phase_name}/`. This enables:
- Post-mortem debugging when skills fail
- Performance analysis (token counts, latency per phase)
- Regression testing (compare outputs across skill versions)

**No action required by skill authors** — orchestrator handles persistence automatically.

### 5. Use Checkpoint Reporting for Progress Visibility

Each phase should emit a checkpoint report after completion. Format:

```
CHECKPOINT — Phase {N}: {phase.name}
Status: COMPLETED / FAILED
Model: {phase.model}
Agents: {agent_count} ({parallelizable ? "parallel" : "sequential"})
Results: {success_count}/{total_count} successful
{Phase-specific summary}
```

**Why:** Users see real-time progress and can abort if a phase produces unexpected results.

---

## Migration Checklist

Converting an existing monolithic skill to delegated:

### Step 1: Identify Phase Boundaries

- [ ] Read the entire skill and identify natural workflow steps
- [ ] Look for transitions like: Read → Analyze → Plan → Implement → Verify
- [ ] Ensure each phase has a single responsibility

### Step 2: Assign Models Per Phase Taxonomy

- [ ] For each phase, determine: Mechanical / Integrative / Architectural
- [ ] Assign model: Haiku / Sonnet / Opus
- [ ] Validate: did you over-use Opus? (should be <20% of phases)

### Step 3: Determine Parallelizability

- [ ] For each phase, ask: can work items run concurrently?
- [ ] Set `parallelizable: true` if yes, `false` if no
- [ ] Set `max_parallel` for parallel phases (typical: 3-5)

### Step 4: Add `delegation-strategy` to Frontmatter

- [ ] Add `delegation-strategy` field to YAML frontmatter
- [ ] Define all phases with `name`, `model`, `parallelizable`, `max_parallel`, `description`
- [ ] Validate: phase names are unique, models are valid (haiku/sonnet/opus)

### Step 5: Write Self-Contained Phase Prompts

- [ ] For each phase, extract relevant content from monolithic skill
- [ ] Make phase prompt fully self-contained (no "see above" references)
- [ ] Add input/output schemas (preferably JSON)
- [ ] Add steps, error conditions, examples

### Step 6: Add Phase Markers to Skill Body

- [ ] Wrap each phase's content with `<!-- PHASE: {name} -->` and `<!-- END_PHASE: {name} -->`
- [ ] Validate: marker names match frontmatter phase names
- [ ] Validate: all markers are paired (no orphan PHASE or END_PHASE)
- [ ] Order markers to match frontmatter phase order (for readability)

### Step 7: Validate and Test

- [ ] Invoke the refactored skill with real arguments
- [ ] Compare output to monolithic version (should be functionally identical)
- [ ] Check checkpoint reports (do they match expected phase flow?)
- [ ] Measure cost and latency (did delegation deliver savings?)

---

## Complete Example: Before/After

### Before (Monolithic Skill)

```markdown
---
description: Execute implementation tasks from task files
---

# Execute Tasks

Systematic workflow for implementing tasks.

## Pre-Execution Check

Read all task files and validate dependencies.
[200 lines of monolithic instructions...]

## Execution Loop

For each task:
1. Understand
2. Implement
3. Verify

[200 more lines...]
```

**Issues:**
- 405 lines of dense instructions
- All executed by single Opus agent (high cost, high latency)
- No parallelization (5 tasks processed sequentially)

### After (Delegated Skill)

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
      description: "Apply code changes per task"
    - name: "verify"
      model: "haiku"
      parallelizable: true
      max_parallel: 5
      description: "Run targeted tests, compare to baseline"
    - name: "quality_gate"
      model: "opus"
      parallelizable: false
      description: "Run full suite and mypy"
---

# Execute Tasks

Systematic workflow for implementing tasks.

<!-- PHASE: pre_check -->
## Phase 1: Pre-Execution Check

Read all task files and validate dependencies.

### Steps

1. Read the task file at task_path
2. Extract dependencies from `**Depends on:**` field
3. Verify dependencies are marked COMPLETED
4. If blocked → STOP and report

### Input

Task file paths from skill invocation.

### Output

JSON array:
[
  {
    "task_path": "...",
    "dependencies": [],
    "is_blocked": false
  }
]
<!-- END_PHASE: pre_check -->

<!-- PHASE: baseline -->
## Phase 2: Baseline Test Capture

For each task, capture test baseline.

[Self-contained instructions with input/output schemas...]
<!-- END_PHASE: baseline -->

[... 3 more phases ...]
```

**Improvements:**
- 5 phases with clear boundaries
- Haiku for I/O (pre_check, baseline, verify)
- Sonnet for implementation (integrative)
- Opus only for quality gate (final validation)
- Baseline and verify run in parallel (up to 5 tasks concurrently)

**ROI:**
- Cost: 85% reduction (~$2.80 → ~$0.42 for 5 tasks)
- Latency: 8% reduction (parallel baseline/verify)
- Quality: Unchanged (model specialization maintains accuracy)

---

## Decision Trees

### Should I Use Delegation?

```
Does your skill have 3+ distinct phases?
├─ No → Use monolithic skill
└─ Yes → Continue

Do phases have different cognitive demands (mechanical vs. integrative vs. architectural)?
├─ No → Use monolithic skill (delegation adds overhead without benefit)
└─ Yes → Continue

Does your skill process multiple independent work items (tasks, files, logs)?
├─ No → Continue (parallelization not required, but delegation may still reduce cost)
└─ Yes → Use delegation (cost + latency + parallelization benefits)

Does your skill have I/O-heavy phases that don't need Opus?
├─ No → Use monolithic skill (no cost benefit)
└─ Yes → Use delegation (cost savings via Haiku)
```

### Which Model Should I Use for This Phase?

```
Does this phase primarily:
- Read files?
- Run commands?
- Extract structured data?
- Parse logs?
├─ Yes → Haiku (mechanical)
└─ No → Continue

Does this phase:
- Edit multiple files?
- Apply patterns across code?
- Refactor code?
- Render templates?
├─ Yes → Sonnet (integrative)
└─ No → Continue

Does this phase:
- Diagnose root causes?
- Make design decisions?
- Resolve ambiguity?
- Plan architecture?
├─ Yes → Opus (architectural)
└─ No → Re-assess phase taxonomy (every phase should fit one category)
```

### Should This Phase Be Parallelizable?

```
Does this phase process N independent work items?
├─ No → parallelizable: false
└─ Yes → Continue

Do work items depend on each other?
├─ Yes → parallelizable: false
└─ No → Continue

Is this phase I/O-heavy (file reading, test execution)?
├─ Yes → parallelizable: true, max_parallel: 3-5
└─ No → Continue

Does this phase make architectural decisions?
├─ Yes → parallelizable: false (reasoning should not be rushed)
└─ No → parallelizable: true, max_parallel: 3-5
```

---

## Common Pitfalls

### 1. Phase Prompts Reference "Above" Content

**Problem:** Phase agent doesn't see content outside its markers.

**Fix:** Make phase prompts fully self-contained.

### 2. Over-Using Opus

**Problem:** Every phase uses Opus → no cost savings.

**Fix:** Review phase taxonomy. Reserve Opus for architectural phases only (typically <20% of phases).

### 3. Under-Parallelizing

**Problem:** Phases that could run in parallel run sequentially → no latency benefit.

**Fix:** Identify I/O-heavy phases with independent work items. Set `parallelizable: true`.

### 4. Over-Parallelizing

**Problem:** `max_parallel: 20` → API rate limits or context window overflow.

**Fix:** Set `max_parallel: 3-5` for typical workloads.

### 5. Tight Phase Coupling

**Problem:** Phase B needs detailed context from Phase A beyond structured output.

**Fix:** Either merge phases or pass richer context via JSON (e.g., include file paths, not just IDs).

### 6. Missing Input/Output Schemas

**Problem:** Unclear what a phase receives or produces → orchestrator can't route data.

**Fix:** Define explicit input/output JSON schemas in phase prompts.

---

## Related Documentation

- [Skill Delegation Metadata Schema](skill-delegation-schema.md) — Frontmatter and phase marker definitions
- [Phase Orchestrator Specification](phase-orchestrator-spec.md) — Execution engine for delegated skills
- [Delegation Performance Metrics](delegation-metrics-spec.md) — Cost, latency, and quality tracking

---

## Questions or Feedback?

See `.claude/README.md` § Skill Delegation Architecture or file an issue.

---

**Last Updated:** 2026-05-09
