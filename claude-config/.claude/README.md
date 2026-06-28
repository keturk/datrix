# Claude Code Skills

This directory configures Claude Code for the Datrix project. `CLAUDE.md` defines project rules; `skills/` contains on-demand slash commands.

## Skills Reference

| Skill | Purpose | Mode |
|---|---|---|
| `/imports` | Look up canonical module import paths | Reference |
| `/logic-map` | Query and maintain implementation markers in `markers.db` | Reference |
| `/fix` | Phased fix workflow with confidence gates | Reference |
| `/fix-issue` | Fix issues from structured issue reports with Root Cause Analysis | Interactive |
| `/fix-bug-report` | Analyze project bug reports, classify, fix root causes, and update reports | Interactive |
| `/codegen-review` | Submission checklist, repo rules, code examples | Reference |
| `/complexity-reducer` | Refactor functions exceeding cognitive complexity 15 | Interactive |
| `/delegate` | Dispatch work to background agents with two-stage review | Interactive |
| `/evaluate-generated` | Compare `.dtrx` source against generated output | Interactive |
| `/evaluate-generated-service` | Service-level evaluation of generated code | Interactive |
| `/generate-tasks` | Break design documents into implementable task files | Interactive |
| `/troubleshoot-generated` | Diagnose generated code test failures | Interactive |
| `/fix-tests` | Fix test failures one at a time with verification | Interactive |
| `/apply-reviews` | Apply review artifacts from Tier 1 (local) and Tier 2 (Codex) | Interactive |
| `/scope` | Anchor session with language/file/directory constraints | Reference |
| `/checkpoint-debug` | Structured multi-bug debugging with checkpoints | Interactive |
| `/troubleshoot-and-fix` | Autonomous diagnose → fix → verify pipeline | Interactive |
| `/codegen-fix-loop` | Self-correcting iterative fix loop with hard limits | Interactive |
| `/operationalize-design` | Design doc → decisions → docs → tasks → cleanup | Interactive |
| `/execute-tasks` | Execute tasks one at a time with verification | Interactive |
| `/execute-tasks-parallel` | Execute independent tasks in parallel (no dependency analysis) | Interactive |
| `/task-orchestrator` | Fully automated multi-wave task execution with dependency analysis | Interactive |
| `/absorb-design` | Absorb completed design documents into memory | Interactive |
| `/commit-and-push` | Git commit and push workflow | Interactive |
| `/premortem` | Premortem analysis for plans, launches, products, hires, strategies | Interactive |

**Mode** — *Reference* skills are read-only prompts injected into context. *Interactive* skills run multi-phase workflows that read and (in some cases) write files.

**Delegation** — Some interactive skills support smart delegation: they decompose into phases, select the optimal model per phase (Haiku/Sonnet/Opus), and execute parallelizable phases concurrently. See [Skill Delegation Architecture](#skill-delegation-architecture).

---

### `/imports`

Looks up canonical Datrix module import paths for common classes and utilities. Contains ~64 mappings covering Entity, Service, generators, type system, migrations, configs, and more. Use when you need the correct import path for a Datrix internal class.

### `/logic-map`

Queries, adds, and maintains canonical implementation markers in source code. Markers live in a SQLite database at `d:/datrix/.logic-map/markers.db`.

**Marker types:**
- `@canonical` — source-of-truth implementation
- `@pattern` — approved approach
- `@boundary` — data transformation point
- `@invariant` — system-wide rule

**Related scripts:** `logic-map.ps1`, `logic-map-report.ps1`

### `/fix`

Structured three-phase fix workflow with confidence gates:

1. **Understand** — read-only diagnosis, trace root cause
2. **Fix** — write code, check for logic map markers
3. **Verify** — run tests, stop on new failures

Includes runaway detection: stops if modified files exceed 2x the estimate or work continues for 3+ rounds without convergence.

### `/codegen-review`

Pre-submission quality checklist with 14 items covering: no placeholders, no mocks, mypy strict compliance, test coverage, cognitive complexity, type annotations, logging format, and marker usage. Also includes per-package repository rules for `datrix-common`, `datrix-language`, and `codegen-*`.

### `/complexity-reducer`

Refactors Python functions with cognitive complexity above 15. Uses Radon and `cognitive_complexity` for analysis.

**Strategies:** early returns, extract helpers, replace flags with state objects, comprehensions, guard clauses, strategy pattern.

**Validation:** AST parsing, `mypy --strict`, `pytest`, behavior preservation.

### `/delegate`

Dispatches tasks to background agents with a two-stage code review process.

**Model selection:**
- Haiku — mechanical / boilerplate tasks
- Sonnet — integration work
- Opus — architecture decisions and review

**Review stages:** Stage 1 (spec compliance), Stage 2 (code quality). Output is persisted to `d:/datrix/.agent_output/<date>-<task>/`.

### `/evaluate-generated`

Compares `.dtrx` source definitions against generated output to assess deployment readiness. Read-only — does not fix anything.

**Phases:**
1. Analyze DSL source (extract feature inventory)
2. Scan generated output (manifest + filesystem)
3. Cross-reference (gaps, dead code, unused modules)
4. Semantic verification (transpilation correctness)
5. Deployment readiness assessment
6. Generate report to `d:\datrix\eval\`

### `/generate-tasks`

Breaks design documents into implementable task files with globally unique numbering.

**Task numbering:** `{phase}-{task_number}`, unique across all repos within a phase.
**Task file path:** `d:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md`
**Categories:** Implementation, Tests, Documentation.

Validates dependencies and reports a dependency graph with parallelizable groups.

### `/troubleshoot-generated`

Investigates and documents generated code test failures. Read-only — produces diagnostic reports, does not apply fixes.

**Phases:**
1. Read logs, summarize failures
2. Analyze broken generated code
3. Trace back to codegen source (template/generator origin)
4. Assess impact, group issues
5. Write reports to `d:\datrix\issues\YYYYMMDD-HHMMSS-{issue-slug}.md`

### `/fix-tests`

Systematically fixes test failures one at a time with verification between each fix. Prevents cascading regressions from batch-fixing.

**Workflow:**
1. Triage — group failures by root cause, prioritize (import errors first)
2. Fix loop — for each root cause: read code → identify fix → apply → verify → regression check
3. Final report — summary of all fixes applied and test results

**Key constraints:** One root cause at a time. No debug scatter. Max 3 attempts per root cause. STOP on new regressions.

### `/scope`

Anchors a session with explicit scope constraints to prevent wrong-direction exploration. Injected as a reference at session start.

**Constraints:**
- `LANGUAGE` — restrict to Python or TypeScript generator only
- `FILES TO READ FIRST` — mandatory reading before any hypothesis
- `STAY OUT OF` — directories Claude must not enter

Scope violations trigger a STOP-and-report instead of silent expansion.

### `/checkpoint-debug`

Structured debugging for sessions with multiple bugs. Each fix follows a strict checkpoint cycle with user-visible progress markers.

**Checkpoint cycle:** Understand (A) → Fix (B) → Verify (C) → Regression Check (D, every 3 fixes).

**Key constraints:** One issue at a time. User approves execution order. STOP on new failures. No skipping checkpoints.

### `/troubleshoot-and-fix`

Autonomous end-to-end pipeline: diagnose generated code test failures → trace to codegen root cause → implement fixes → regenerate → verify. Collapses the two-session troubleshoot+fix pattern into one.

**Pipeline:** Diagnose (read-only) → Plan Fixes → Implement (one at a time) → Regenerate → Final Report.

**Key constraints:** Confidence gates between phases. Abort on scope creep. Never fix generated code directly — always fix the generator. One root cause at a time with verification.

### `/codegen-fix-loop`

Self-correcting iterative loop: attempt fix → run tests → analyze failure → adjust → repeat until green, with a hard iteration limit (default: 5). Prevents unbounded debugging spirals.

**Loop:** Understand (once) → [Propose → Apply → Test → Analyze → Adjust] × N → Final Verification.

**Key constraints:** Hard iteration limit. STOP if error gets worse. STOP if same error repeats. No debug scatter. Each iteration's rationale must reference specific code or error output.

### `/operationalize-design`

End-to-end design document pipeline: audit → resolve decisions → update docs → generate tasks → delete original. Collapses multi-day design operationalization into a single session.

**Pipeline:** Analysis → Decisions (with evidence) → Documentation Transfer → Task Generation → Cleanup.

**Key constraints:** No tasks without resolved ambiguities. No deleting before transfer verified. Every decision needs codebase evidence. Every task needs acceptance criteria.

### `/task-orchestrator`

Fully automated multi-wave task orchestrator. Accepts a set of tasks (individual files, multiple files, or entire phase directories), analyzes dependencies, groups tasks into execution waves via topological sort, and executes each wave with parallel agents. Runs test suites automatically between waves — no human intervention except on task failure.

**Workflow:**
1. Read all tasks, build dependency DAG, detect cycles
2. Topological sort into waves (phase-sequential: all tasks in phase N complete before phase N+1)
3. For each wave: implement (max 3 parallel agents) → targeted tests → full suite → fix loop → mark complete
4. Checkpoint after each wave, advance automatically
5. Pause and ask user on task failure (after 3 fix attempts)

**Key difference from `/execute-tasks-parallel`:** Dependency-aware grouping, automated test execution, automatic wave advancement, and multi-phase sequential ordering. No human intervention between waves.

### `/fix-issue`

Fix issues from structured issue reports with Root Cause Analysis and Recommended Fix. Reads issue report, implements the recommended fix, verifies with tests, and updates the report with resolution.

**Workflow:** Understand → Implement Fix → Verify → Update Report

### `/fix-bug-report`

Analyze structured bug reports from project repositories, classify each bug as an app-definition fix or generator-level fix, implement the appropriate changes, and update each bug report with the resolution.

**Phases:** Triage → Fix → Update → Report

**Workflow reference:** `D:\<project-repo>\claude\fix-bug-report.md`

### `/evaluate-generated-service`

Service-level evaluation of generated code against `.dtrx` source definitions. Focused on service-level concerns rather than full project evaluation.

### `/apply-reviews`

Apply review artifacts from Tier 1 (local) and Tier 2 (Codex) to task files. Reads review findings, groups by task and severity, applies fixes automatically, and marks applied findings to prevent double-application.

**Workflow:**
1. Discover review artifacts (`*.review.local.json`, `phase-{NN}.review.codex.json`)
2. Group findings by task and severity (blocking → major → minor → nit)
3. Apply fixes per task (highest severity first)
4. Handle phase-level findings (dependency cycles, etc.)
5. Write `.review.applied.json` markers

**Key features:** Never double-applies findings, skips unfixable findings requiring design decisions, preserves task file structure.

### `/execute-tasks`

Execute implementation tasks one at a time with verification. Simpler than `/execute-tasks-parallel` and `/task-orchestrator`, suitable for small task sets (1-3 tasks) where you want to see progress one task at a time.

### `/execute-tasks-parallel`

Execute independent tasks in parallel without dependency analysis. Suitable for 2-4 independent tasks with no cross-dependencies. Simpler and lower cost than `/task-orchestrator`.

**When to use:** Small sets of independent tasks where you don't need dependency analysis or automated wave advancement.

**When NOT to use:** Tasks with dependencies (use `/task-orchestrator`), single tasks (use `/execute-tasks`).

### `/absorb-design`

Absorb completed design documents into project memory. After implementing a design doc, this skill extracts key decisions, patterns, and constraints and adds them to the project's memory system.

### `/commit-and-push`

Git commit and push workflow. Creates commits following project conventions and pushes to remote repository.

### `/premortem`

Runs a premortem on plans, launches, products, hires, strategies, or decisions. Uses "prospective hindsight" to identify failure modes before they happen by assuming the plan already failed and working backward to explain why.

**Method:** Based on Gary Klein's premortem technique (published in Harvard Business Review). The brain shifts into narrative mode and generates far more specific, creative, honest reasons when you say "this already failed, tell me why" instead of "what could go wrong?"

**Phases (delegated to specialized agents):**
1. Context gathering — what, who, success criteria
2. Raw premortem — generate exhaustive list of failure reasons
3. Deep analysis (parallel) — one agent per failure reason analyzes: failure story, underlying assumption, early warning signs
4. Synthesis — most likely failure, most dangerous failure, hidden assumption, revised plan, pre-launch checklist
5. Report generation — visual HTML report + markdown transcript

**Output:** `premortem-report-[timestamp].html` (visual, scannable) + `premortem-transcript-[timestamp].md` (complete analysis)

**Delegation strategy:** Uses multi-phase delegation with parallel deep analysis agents (up to 9 concurrent) for efficiency.

---

## Skill Delegation Architecture

Complex skills can opt into **smart delegation** to improve cost efficiency, latency, and quality through:

1. **Model specialization** — Each phase runs on the model best suited for its cognitive demand
2. **Parallel execution** — Independent work items run concurrently via Claude Code's Task tool
3. **Focused context** — Agents receive phase-specific prompts, not entire skill workflows

### Phase Taxonomy

| Complexity | Model | Task Examples |
|---|---|---|
| **Mechanical** | Haiku | Log parsing, file globbing, structured data extraction, test execution, file format validation |
| **Integrative** | Sonnet | Multi-file code edits, pattern application across modules, template rendering, dependency resolution |
| **Architectural** | Opus | Root cause diagnosis, design decisions, cross-cutting refactors, ambiguity resolution |

### How It Works

Skills with a `delegation-strategy` frontmatter field decompose their workflow into phases:

```yaml
---
description: Execute implementation tasks from task files
delegation-strategy:
  phases:
    - name: "Pre-Execution Check"
      model: "haiku"
      parallelizable: false
    - name: "Baseline Test Capture"
      model: "haiku"
      parallelizable: true
      max_parallel: 5
    - name: "Implementation"
      model: "sonnet"
      parallelizable: false
    - name: "Verification"
      model: "haiku"
      parallelizable: true
      max_parallel: 5
---
```

The orchestrator:
1. Parses the delegation strategy
2. For each phase, spawns agent(s) with the specified model
3. For parallelizable phases, launches multiple agents concurrently
4. Collects results and synthesizes a final report

**Phase content** is delimited by HTML comment markers in the skill body:

```markdown
<!-- PHASE: baseline -->
## Baseline Test Capture

For each task:
1. Read task file
2. Extract "Targeted Tests" section
3. Run test commands

**Output**: Baseline test results JSON
<!-- END_PHASE: baseline -->
```

### Benefits

**Cost reduction:** Right-sizing models to cognitive demand can reduce token usage by 50-90% for multi-phase skills.

**Latency reduction:** Parallel execution of independent work items reduces wall-clock time by 20%+ for skills with 3+ parallelizable tasks.

**Quality improvement:** Phase-specific prompts reduce ambiguity and hallucination; model specialization improves accuracy.

### Delegation-Enabled Skills

Skills that support delegation:

- `/execute-tasks` — Parallel baseline capture and verification
- `/execute-tasks-parallel` — Parallel task implementation without dependency analysis
- `/troubleshoot-and-fix` — Parallel log parsing and regeneration
- `/premortem` — Parallel deep analysis agents (up to 9 concurrent) for failure scenario analysis

### Implementation Details

**Agent output persistence:** Phase outputs are stored in `d:/datrix/.agent_output/{session_id}/{phase_name}/` for debugging and resumability.

**Failure handling:** Phases fail fast — if a phase fails, execution stops and the user is presented with the failure report.

**Progress visibility:** Phase checkpoints are streamed to the user as each phase completes (consistent with existing `/fix-tests` and `/troubleshoot-and-fix` checkpoint patterns).

**Backward compatibility:** Skills without `delegation-strategy` continue to work as monolithic prompts. Delegation is opt-in.

---

## Directory Layout

```
.claude/
  CLAUDE.md                             # Project rules and standards
  README.md                             # This file
  MEMORY.md                             # Project memory and context
  settings.json                         # Shared settings
  settings.local.json                   # Local sandbox permissions
  hooks/
    validate-script-invocation.py       # Hook to validate PowerShell script usage
  docs/
    delegation-metrics-spec.md          # Metrics for delegation performance
    phase-orchestrator-spec.md          # Phase orchestrator specification
    skill-authoring-guide-delegation.md # Guide for authoring delegated skills
    skill-delegation-schema.md          # Schema for delegation metadata
  agent-templates/
    dependencies-format.md              # Task dependencies file format
    task-implementation-agent.md        # Template for task implementation agents
  skills/
    imports/SKILL.md
    logic-map/SKILL.md
    fix/SKILL.md
    fix-issue/SKILL.md
    fix-bug-report/SKILL.md
    fix-tests/SKILL.md
    fix-cli/SKILL.md
    fix-common/SKILL.md
    fix-extensions/SKILL.md
    fix-language/SKILL.md
    fix-codegen-aws/SKILL.md
    fix-codegen-azure/SKILL.md
    fix-codegen-common/SKILL.md
    fix-codegen-component/SKILL.md
    fix-codegen-docker/SKILL.md
    fix-codegen-python/SKILL.md
    fix-codegen-sql/SKILL.md
    fix-codegen-typescript/SKILL.md
    codegen-review/SKILL.md
    codegen-fix-loop/SKILL.md
    complexity-reducer/SKILL.md
    delegate/SKILL.md
    evaluate-generated/SKILL.md
    evaluate-generated-service/skill.md
    generate-tasks/SKILL.md
    troubleshoot-generated/skill.md
    troubleshoot-and-fix/skill.md
    apply-reviews/SKILL.md
    scope/SKILL.md
    checkpoint-debug/SKILL.md
    operationalize-design/SKILL.md
    execute-tasks/skill.md
    execute-tasks-parallel/skill.md
    task-orchestrator/SKILL.md
    absorb-design/SKILL.md
    commit-and-push/SKILL.md
    premortem/SKILL.md
```
