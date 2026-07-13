---
description: Fully automated multi-wave task orchestrator with dependency analysis and test gating
model: opus
effort: xhigh
---

# Task Orchestrator

Fully automated multi-wave task orchestrator. Accepts a set of tasks (individual files, multiple files, or an entire phase directory), analyzes dependencies, topologically sorts tasks into execution waves, and executes each wave with parallel agents. Runs test suites automatically between waves. No human intervention except on task failure after exhausting fix attempts.

## Your Role — Opus Orchestrator: Judgment, Not Typing

You run on Opus 4.8 at extra-high effort because this skill performs the **highest-stakes judgment in the repo** — the design-conformance gate, the BLOCKED-is-terminal calls, the wave/enforcement ordering, and the completion decisions that phase-01 got wrong. That capability is for deciding, not for doing. You are the orchestrator and decision-maker; **execution goes to subagents on cheaper models.**

- **You (Opus) own — never delegated:** the dependency DAG and wave plan, the design-conformance contract (Step 1d), the **readiness-audit adjudication** (Step 1e — which findings are real, what task closes each gap, how dependencies rewire) and the conformance gates (3g, 3i Step A2), BLOCKED/completion decisions, failure attribution and fix-scope decisions, escalation judgment, integration across tasks, and the pass/fail verdict on every gate.
- **You delegate DOWN — always:** implementing tasks (already delegated, 3b), gathering the readiness audit's evidence and writing the task files it adds (1e), building the shared-context digest, running test suites and conformance checks, **and implementing fixes in the fix loops (3e / 3i Step A) — do NOT edit code inline on Opus.** You decide the fix (root cause, scope, exact change); a subagent types it.

Two resources are scarce and both are yours to protect: **Opus tokens** (never spend them on typing a fix a Sonnet agent can apply from your spec) and **your context window** (it must survive a whole multi-phase run — delegate the token-heavy reading/editing so your context holds the conformance state, not file contents).

Because you ARE Opus at extra-high effort, the old "escalate up to a more-capable agent" step collapses: you do the architectural analysis **in-context** (you already hold the failure context), then dispatch a subagent to implement your decision. See the reframed **Decision Escalation Protocol** below. Delegation is never abdication — you verify every returned result with a command you run (or delegate the run and read the result), and a subagent's self-report never substitutes for the design-acceptance evidence you paste into the gate.

**The orchestrator's mandate is conformance, not throughput** (CLAUDE.md "Task Orchestration" states the full rationale — it binds here). Two consequences at every wave and phase boundary: **a green suite is necessary but NOT sufficient** (the explicit design-conformance gates at 3g and 3i Step A2 prove the design invariant itself), and **BLOCKED is terminal — it can never become COMPLETED** (per the shared checklist `d:\datrix\.claude\skills\_shared\completion-eligibility.md`; the blocker is spawned as a tracked task).

**Key differences from `/execute-tasks-parallel`:**
- **Readiness audit before any execution** (Step 1e) — audits the task set against the design doc AND the current implementation, then authors the missing tasks and rewires `dependencies.md` before planning waves
- Dependency-aware grouping (builds a DAG, topologically sorts into waves)
- Automated test execution (runs full suite via Bash, does not ask user)
- Automatic wave advancement (no human intervention between waves)
- Handles tasks with cross-dependencies (separates into waves instead of blocking)
- **Sequential multi-phase execution** — given several phases (e.g. `72, 73, 74`), finishes each phase fully before starting the next. At every phase boundary a gate (Step 3i) runs the **full test suite for every package the phase touched** and fixes **all** failures — including pre-existing ones unrelated to the phase's changes — with Opus-led recovery, before the next phase starts

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

```
/task-orchestrator
PHASE: 36                                  # most common — number or full path d:\datrix\datrix\.tasks\phase-36\
PHASES: 34, 35, 36                         # multiple phases (numbers or paths, one per line)
TASKS: {newline-separated task file paths} # individual tasks (less common)
```

For a PHASE/PHASES input the orchestrator discovers tasks automatically — first via `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` if present, otherwise by globbing `task-*.md` across all package `.tasks\phase-{NN}\` directories. The user never needs to list tasks.

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

1. **First, check for the consolidated dependencies file** at `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` (phase-level, NOT in package directories). If it exists: try JSON (new format — extract task_id, task_path, title, is_completed, package, dependencies, category; skip per-file reads for graph construction); if not JSON, parse as "Group N"-headed line-separated task paths (groups = dependency waves; still read task files for full metadata).

2. **If dependencies.md doesn't exist**, glob for `task-*.md` in every package's `.tasks\phase-{NN}\` directory (`d:\datrix\*\.tasks\phase-{NN}\`) and read each task file to extract metadata (see below).

**Dependencies.md schema:**

See `d:\datrix\datrix\claude-config\.claude\agent-templates\dependencies-format.md` for the JSON schema.

2. **Metadata extraction (when reading task files manually):**
   - `task_id` — from filename (e.g., `task-07-01` from `task-07-01-base-class.md`)
   - `title` — from `# Task {NN}-{TT}: {Title}` heading
   - `is_completed` — title starts with `# COMPLETED:`
   - `package` — from `**Package:**` field
   - `dependencies` — from `**Depends on:**` field (list of task ID slugs, or "None")
   - `category` — from header (Implementation / Tests / Documentation / Quality Gate / Verification)
   - `design_reference` — from `**Design reference:**` field (design-doc path + section(s) + the D#/G#/numbered invariant the task implements)
   - `design_acceptance_property` — from `**Design acceptance property:**` field (the observable end-state that proves the task satisfies the design, and the check that proves it)

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

### 1d. Build the Design-Conformance Contract (the orchestrator's source of truth for "done")

The orchestrator gates on the design, so it must hold the design in hand — not just the task list. Before execution:

1. **Collect the design reference(s).** Read the `**Design reference:**` of every task. Resolve the distinct design-doc path(s) the phase implements.
2. **Read the design doc(s)** and extract, per phase, the **design contract**: the list of invariants / numbered decisions (D#/G#) the phase must satisfy, and for each invariant **the full SET of surfaces it ranges over** (e.g. "fail-loud applies to integration AND CDN AND auth AND datasource positions"). This surface set is what catches a half-implemented invariant — a phase that guards one surface and silently drops the rest.
3. **Per task, record its `design_acceptance_property`** — the observable end-state + the executable check (negative + positive) that proves it. If a non-trivial implementation/migration task has NO design acceptance property (blank or "tests pass"), flag it: it is under-specified and its completion cannot be verified. Note it for the gate; do not silently let it pass on suite-green alone.
4. **Map invariant → tasks.** For every invariant surface in the contract, identify which task covers it. If a surface in the design's set has NO task covering it → record a **conformance gap** now (a design-named surface with no implementer). Feed it into the Readiness Audit (Step 1e), which closes it by authoring the missing task **before** execution. (3i Step A2 remains the backstop for gaps that only surface later — but a gap visible up front must never be deferred to the phase boundary.)

`design_contract` (invariants + surface sets) and per-task `design_acceptance_property` are checked by 1e (readiness), 3g (completion) and 3i Step B (phase conformance). Without this contract, the orchestrator can only check "did it run", which is exactly the phase-01 failure.

### 1e. Readiness Audit — is this task set sufficient to satisfy the design against the CURRENT code?

**Run this before ANY execution.** The task set was authored against the design and the codebase **as they were when `/generate-tasks` ran**; both may have moved since, and the generator may have missed a surface. Executing an insufficient task set produces the phase-01 outcome — every task COMPLETED, the suite green, and the design still unenforced. The audit answers one question: *if every task in this set succeeds exactly as written, will the `design_contract` from 1d hold over the code that is actually on disk today?* If the answer is anything but yes, the audit **adds the missing tasks and rewires dependencies** before Step 2 builds the DAG.

The audit is **read-only with respect to source code** — it authors task files and updates `dependencies.md`, and touches nothing else. It **never modifies the design doc** (CLAUDE.md: design docs are scope boundaries).

##### Audit dimensions (each finding needs evidence — a file:line you read or a command + its output)

1. **Coverage gap** — a design invariant/surface from the 1d contract with no task implementing it. Includes the case where a task covers *part* of an invariant's surface set (the guard on the easy surface, the rest silently dropped).
2. **Enforcement ordering gap** — a validator / fail-loud guard / parser rejection exists as a task but is NOT a `Depends on` of every task that migrates or relies on content it governs (CLAUDE.md "Enforcement before what it governs"). Also the case where the *guard itself is missing* while its migration task exists.
3. **Stale premise** — the task assumes code state that is no longer true: a file/class/function/constant it says to modify does not exist, has been renamed, or already carries the change. Verify each task's `## Files to Review Before Starting`, `## Files to Create` and the specific symbols it names against the code on disk.
4. **Already-satisfied** — the current implementation already provides the task's design acceptance property. Prove it with the acceptance check (negative + positive); a task that merely *looks* done is not.
5. **Under-specified task** — a non-trivial task with a blank / vacuous `**Design acceptance property:**` ("tests pass", "it generates"). Its completion cannot be verified, so 3g can never pass it honestly.
6. **Missing dependency edge** — task B modifies or imports a file/symbol task A creates, but B does not `Depends on` A; or two tasks in the same prospective wave write the same file with no ordering.
7. **Unresolvable premise (BLOCKING)** — the design contradicts the code in a way no task can reconcile (the design names an API/symbol/behavior that does not and cannot exist as described). This is not an audit fix; it is a STOP.

##### Procedure

1. **Delegate the evidence gathering, keep the verdicts.** Dispatch **sonnet** audit subagents in parallel (`run_in_background: true`, one per package in the task set, plus one for the design-contract coverage sweep). Each gets: the design doc path + the 1d `design_contract` (invariants and their full surface sets), the task files it owns, and the shared-context digest. Each returns **findings with evidence only** — for every claim, the file:line it read or the command + output it ran. Instruct them explicitly: *report a gap only if you verified it against the code on disk; a suspicion with no evidence is not a finding.* They do not author tasks and they do not edit code.
2. **Adjudicate each finding yourself (Opus).** Discard evidence-free claims. For each surviving finding, decide its class (1–7 above) and its remedy. A finding that would *reduce* scope (already-satisfied) needs the same standard of proof as one that adds scope — run its acceptance check yourself before acting on it.
3. **Author the missing tasks.** For each real coverage / enforcement / under-specification gap, write a new task file:
   - Location: the **owning package's** `.tasks\phase-{NN}\` directory (the package whose surface the invariant lives on — apply the generality-preserving rule: the most language/platform-agnostic layer that can own it).
   - ID: the next free `{TT}` for that phase — scan every package's `.tasks\phase-{NN}\` for the highest existing `task-{NN}-{TT}` and continue from there. Never reuse or renumber an existing ID.
   - Content: the full task template from `/generate-tasks` (`d:\datrix\.claude\skills\generate-tasks\SKILL.md`, "File Structure") — including a real `**Design reference:**` (the D#/G# it closes), a **provable** `**Design acceptance property:**` with its negative + positive check, `## Files to Review Before Starting`, `## Files to Create`, `## Targeted Tests`, and its own `## Tests` section. A task the audit adds must be as complete as one `/generate-tasks` emits; a stub task is a workaround.
   - Delegate the *writing* to a **sonnet** agent from your spec (you decide the scope, acceptance property, package, and dependencies; the agent types the file), then read the result and verify it carries a provable acceptance property.
   - For an **under-specified** existing task, do not add a new task — amend that task file's `**Design acceptance property:**` and its Success Criteria to carry the provable check. (Amending a *task* is allowed; amending the *design* is not.)
4. **Rewire dependencies — task files AND `dependencies.md` must stay in lockstep.**
   - Edit the `**Depends on:**` field of every affected task file: new tasks' own prerequisites, plus edges **into** the new tasks from every task they must precede (a newly-added guard becomes a `Depends on` of every migration it governs).
   - Update `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` to match — per the JSON schema in `d:\datrix\datrix\claude-config\.claude\agent-templates\dependencies-format.md`: append a `tasks[]` entry for each new task (`task_id`, `task_path`, `title`, `is_completed: false`, `package`, `dependencies`, `category`) and update the `dependencies` array of every existing task that gained an edge. If the file is in the legacy "Group N" text format, **rewrite it as JSON** (the preferred format) rather than patching groups. If it does not exist, create it — the amended set is now the phase's source of truth and the next run must see it.
   - Re-run 1c's validation and 2b's cycle detection over the amended graph. A cycle introduced by the audit's own edges is a bug in your rewiring — fix it, do not ship it.
5. **Re-verify the contract.** With the amended set, re-run 1d step 4: every invariant surface in the `design_contract` must now map to at least one task. If a surface still has no owner, you have not finished the audit.

##### Outcomes

- **Ready (no gaps)** → say so in one line and proceed to Step 2.
- **Ready after amendment** → emit the Audit Report (below) and proceed to Step 2 with the amended task set. **Do not ask the user for permission to proceed** — closing a gap the design already mandates is in scope; the audit is reported, not negotiated.
- **BLOCKING (dimension 7, or a design/code contradiction you cannot reconcile)** → STOP before Step 2 and `AskUserQuestion` with your evidence: what the design requires, what the code actually does, and why no task can bridge them. Never paper over it with a task that pretends the premise holds.

##### Audit Report (emit before the execution plan)

```
READINESS AUDIT — phase {NN}: {N} tasks audited, {G} gaps found

Added:    task-{NN}-{TT} ({package}) — {invariant/surface it closes}
Rewired:  task-{NN}-{TT} now depends on task-{NN}-{TT}  ({why — e.g. guard before migration})
Amended:  task-{NN}-{TT} — acceptance property was unprovable, now: {property}
Stale:    task-{NN}-{TT} — {premise that no longer holds} → {what you did about it}
dependencies.md: updated ({N} entries, {E} edges)
```

Omit any line with nothing to report. If no gaps: `READINESS AUDIT — phase {NN}: {N} tasks, no gaps; task set satisfies the design contract.`

---

## Step 2: Build Dependency DAG and Plan Waves

### 2a. Build the Directed Acyclic Graph

Build it from the **amended** task set — the tasks added and the edges rewired by the Readiness Audit (1e) are ordinary members of the graph, not an appendix to it. For each non-completed task:
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

4. **Phase boundaries are wave boundaries** — even if a task in phase 35 has no dependencies, it cannot start until ALL phase 34 waves are complete. Each phase boundary is also a **Phase Boundary Gate** (Step 3i): the earlier phase must pass an explicit completion check — every package it touched must pass its **full** test suite with all failures fixed, including pre-existing ones unrelated to the phase, with Opus-led recovery on failure — before the next phase's first wave is spawned.

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

Once waves are assigned, compute `package_last_touch_wave{}` per phase: for each package, the highest wave number **within that phase** that has a task touching the package. The 3d test gate uses this to run targeted-only tests on a package's earlier waves and the full suite only on its last-touch wave (the phase-boundary gate 3i remains the authoritative full sweep).

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

Execute each wave sequentially. Within each wave, tasks run concurrently against a **rolling pool of up to 5 in-flight agents** (Step 3b) — a freed slot is refilled as soon as the genuine 5-minute poll (Agent Progress Polling Protocol) detects an agent has finished, rather than waiting for a fixed batch to drain or for a completion notification.

### Shared Context Pre-Read (once per run, before the wave loop)

Agents otherwise each re-read the same architecture docs on startup, burning duplicate tokens and latency across a wide wave. Build a compact **shared context digest** (≤ ~400 lines) **once** at the start of Step 3, to inject verbatim into every implementation-agent prompt. **Delegate the build** — dispatch a single **haiku** agent to read the sources below and return the digest; this is mechanical reading, not judgment, so it does not belong on Opus's context. You keep the returned digest as `shared_context` and pass the package-relevant slice to each implementation agent. Sources:

- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md)
- [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md)
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) — the core rules + prohibited patterns
- The `.project-structure.md` for each package that has a task in this run (read per-package, key into the digest by package name)

The digest is **reference context, not a substitute for the task file** — agents still read their own task file and the specific code they touch. Store it as `shared_context` and pass the package-relevant slice in each agent prompt (see 3b). Build it once; reuse for every wave and every phase in the run.

### State Tracking

Maintain these state variables throughout the loop:

- `completed_tasks[]` — tasks that passed all checks and were marked complete
- `audit_added_tasks[]` — tasks authored by the Readiness Audit (1e) to close a design gap; they execute like any other task and are reported separately in Step 4
- `failed_tasks[]` — tasks that failed after 3 fix attempts
- `skipped_tasks[]` — tasks skipped because a dependency failed
- `current_wave` — wave number being executed
- `in_flight[]` — agents currently running in this wave's rolling pool (rolling dispatch, 3b)
- `wave_queue[]` — tasks in this wave not yet dispatched (FIFO, respecting 2d file-conflict ordering)
- `shared_context` — the pre-read digest injected into every agent prompt
- `package_last_touch_wave{}` — map of `package → the highest wave number within the current phase that touches that package` (computed once from the Step 2 wave plan when a phase's waves are known). Used by 3d to decide targeted-only vs. full-suite gating

### For Each Wave:

#### 3a. Check for Skipped Tasks

Before executing a wave, check if any task in this wave depends on a `failed_task`:
- If yes, add it to `skipped_tasks` with reason: `"Dependency {dep_id} failed"`
- Transitively skip all downstream tasks that depend on skipped tasks
- Remove skipped tasks from the wave
- If the entire wave is skipped → emit checkpoint and move to next wave

#### 3b. Spawn Implementation Agents (rolling pool)

Run the wave through a **rolling pool of up to 5 concurrent agents** (`CAP = 5`). This replaces the old fixed "sub-groups of 5 with a barrier between each sub-group" — that scheme idled up to 4 slots whenever one agent in a batch ran long. The pool keeps all 5 slots busy until the wave's work runs out.

**Dispatch loop:**

1. Seed `wave_queue` with all non-skipped tasks in the wave, ordered so that any **2d file-conflict** pair is sequenced (the second task of a conflicting pair must not be dispatchable until the first leaves `in_flight`). Treat such a pair as an intra-wave dependency edge inside the pool.
2. Fill the pool: dispatch tasks from the head of `wave_queue` until `len(in_flight) == CAP` or the queue is empty. Each dispatch spawns **one** background agent (`run_in_background: true`). Record each agent's `task_id` and assigned `files_to_create`/`files_to_modify`, and snapshot those files' line counts (per the polling protocol's dispatch step).
3. **Drive the pool with the Agent Progress Polling Protocol — do NOT wait for completion notifications.** Read `d:\datrix\datrix\claude-config\.claude\agent-templates\agent-progress-polling-protocol.md` and run its poll loop over `in_flight`: every ~5 minutes (paced by a bounded `TaskOutput(block=true, timeout=300000)` on one in-flight agent), perform a **genuine** check of every in-flight agent — its status **and** its on-disk artifacts — and classify it (completed / progressing / stalled / errored). Never assume an agent is working because no notification arrived. When the genuine check shows an agent has **completed**, immediately run 3c **for that one agent** (parse its result, handle BLOCKED/NEEDS_CONTEXT/re-spawn) and remove it from `in_flight`. A stalled agent (no assigned-artifact change across two consecutive polls, ~10 min) is investigated and, if hung, `TaskStop`-ped and re-dispatched or marked BLOCKED — never left counted as in-flight.
4. Refill: dispatch the next eligible task from `wave_queue` (skip any task whose 2d-conflict predecessor is still in flight; take the next eligible one). Repeat 3–4 until `wave_queue` is empty **and** `in_flight` is empty.
5. **Wave join:** the pool being fully drained (`in_flight` empty, `wave_queue` empty) is the barrier before the test gate. Do NOT start 3d until the join — this preserves the "never test mid-wave" hard rule.

A re-spawn (NEEDS_CONTEXT answered, or escalation recommendation ready) goes back through the pool like any other dispatch — it re-enters `wave_queue` and takes the next free slot.

**Task tool parameters:**
- `subagent_type: "general-purpose"`
- `model:` — tier per task (see **Model tiering** below)
- `max_turns: 40`
- `run_in_background: true` — required so each agent can be **polled** while running (see the Agent Progress Polling Protocol). A freed slot is detected by the genuine 5-minute poll, not by a passively-awaited completion notification.
- `description: "Implement task: {task_id}"`

**Model tiering (per task):**
- `"haiku"` — **documentation-only** tasks, **and** trivial mechanical code tasks where the change is unambiguous and self-contained: pure renames, moving/extracting a named constant, a single-import or single-symbol edit, mechanical signature propagation. Only when you are confident the task carries no design judgment.
- `"claude-sonnet-4-6"` — all substantive code tasks (default for anything touching logic, new files, multi-file edits, or anything you are not certain is trivial). When in doubt, use Sonnet, not Haiku.
- `"opus"` — the top **implementer** tier, spawned only for **hard/cross-cutting execution** (a subtle root cause, an implementation needing strong reasoning). Orchestration judgment (attribution, fix-scope, conformance, escalation analysis) is **never** delegated — it stays in YOUR context; you are the Opus orchestrator at extra-high effort, and only implementers are ever spawned to type.

**Fallback when background agents are genuinely unavailable** (the harness cannot spawn background tasks at all, or a deterministic run is required): fall back to foreground batches, but size them to **balance**, not rigid 5s — e.g. dispatch 6 tasks as 3+3, not 5+1, so a lone trailer never wastes a whole barrier. Aim for `ceil(N / ceil(N / CAP))` per batch. The polled rolling pool is preferred; this is only the degraded path. Note: a flaky or absent **completion-notification** channel is NOT a reason to fall back — the polling protocol does not depend on notifications, so the background rolling pool still works.

**Agent prompt template:**

Read `d:\datrix\datrix\claude-config\.claude\agent-templates\task-implementation-agent.md` and substitute `{task_path}` with the actual task file path. Prepend the package-relevant slice of `shared_context` (the pre-read digest from Step 3) to the prompt under a `## Shared Architecture Context (pre-read — do not re-fetch)` heading, so the agent skips redundant doc reads. The template contains:
- Standard workflow (UNDERSTAND → IMPLEMENT → SELF-CHECK → RUN TARGETED TESTS → RETURN RESULTS)
- Anti-patterns to avoid
- Self-check protocol (anti-stub check, test quality check, self-contradiction check)
- STUCK protocol (report BLOCKED instead of faking completion)
- JSON result format

**Template substitutions:**
- `{task_path}` → actual task file path
- `{task_id}` → task identifier (e.g., "task-34-01")
- `{package-name}` → package name from task metadata

**Quality-gate tasks — suppress the agent's full-suite run.** A `**Category:** Quality Gate` task file lists "Run full test suite (`test.ps1 {package-name}`)" as a verification step, and its `## Targeted Tests` scope is the full suite. That run is redundant here: step 3d runs the full suite for this package as the authoritative wave gate after the agent returns. So when spawning a quality-gate agent, append this directive to its prompt:

> The orchestrator runs the full test suite (`test.ps1 {package-name}`) as the authoritative wave gate immediately after you return. Do NOT run `test.ps1` yourself — skip Verification Step 1 / the `## Targeted Tests` full-suite command. Perform ONLY the non-test verification: the static red-flag scans (stubs / `TODO` / `pass` / `NotImplementedError`, over-broad IAM, legacy/dual paths, gating/byte-equivalence) and the "How Solved" self-contradiction checks. Report those findings in your JSON result; the orchestrator owns the pass/fail test verdict.

This removes the duplicate suite run while preserving both the gate's static-analysis value (agent) and an independent test verdict (orchestrator).

The rolling pool (above) governs when the next task is dispatched — a freed slot is refilled immediately, not after the whole wave drains.

#### 3c. Collect Agent Results (per completion)

Run this **each time a poll detects that one agent has completed** (the genuine check in 3b step 3 — never triggered by passively awaiting a notification) — not once per sub-group:

1. Parse the JSON report from the agent's output
2. Record status: IMPLEMENTED / EXPANSION_REQUIRED / BLOCKED / NEEDS_CONTEXT / FAILED

3. **BLOCKED-VALIDITY GATE (run this FIRST, before any other handling).** A BLOCKED report is a *claim*, not an outcome. Accept it only if `blocker_proof` carries **all four** fields, substantively:
   - `error_text` — verbatim, not a paraphrase, not empty
   - `attempted` — a real fix, written and run, as `file:line`. **Analysis alone is not an attempt.** If the agent never edited a file, this fails.
   - `why_it_failed` — a specific mechanism
   - `blocker_code` — a genuine `B1`/`B2`/`B3`/`B4` (execution-contract §1)

   **If any field is missing, vague, or the blocker_code does not actually match B1–B4 → REJECT and re-dispatch the same task to a fresh agent**, with its own report quoted back and this line prepended:
   > *Your BLOCKED report was rejected: {the failing field}. This is not one of the four blockers — it is work. Read `.claude/skills/_shared/execution-contract.md` §2, then fix the problem.*

   **Beware the fake blocker classes.** "Missing dependency", "missing file", "incomplete prereq", "unclear root cause", "pre-existing failure", "environmental", "needs broader changes" are **NOT blockers** — they are work (create the file, implement the dep, keep reading, fix it). Only B1–B4 count. Do **not** add such a task to `failed_tasks`; re-dispatch it.

   A task may be re-dispatched this way **at most twice**. On a third invalid BLOCKED, escalate to the Decision Escalation Protocol yourself, decide the fix in-context, and dispatch a directed implementer — the agent has proven it will not converge on its own.

4. If **BLOCKED** and the proof is **valid**: invoke the **Decision Escalation Protocol** — *you* (Opus) analyze the four-part proof and decide whether the blocker is genuinely outside your reach too. Only a B1/B3 (no access / user-forbidden) or a genuinely user-facing B2 goes to `failed_tasks`; a B2 you can defensibly decide, you decide, then re-dispatch a directed implementer.

5. If **EXPANSION_REQUIRED**: the agent knows the fix and needs the file lock. **Re-dispatch it serially the moment the conflicting files are free** (it may run alone after the wave join). This is *not* a failure and never goes to `failed_tasks`. Never shelve it, footnote it, or count the task as done.

6. If **NEEDS_CONTEXT** with a **spec gap or missing user input** (credentials, unresolvable requirement): relay to user via `AskUserQuestion`, then re-queue the agent with the answer
7. If **NEEDS_CONTEXT** with a **technical ambiguity**: invoke the **Decision Escalation Protocol** — analyze and decide in-context yourself, then re-queue the implementation agent with your concrete recommendation. Do **not** pass a technical ambiguity to the user; that is your job.
8. If **FAILED**: record targeted test failures, add to `failed_tasks`

9. **DISCOVERED-DEFECT GATE.** For every entry in the agent's `discovered_defects`, the `disposition` must be `FIXED` (with a `file:line`) or `FILED` (with a real task file path that exists on disk). A prose-only mention is **not** a disposition — file the task yourself before the wave gate, or re-dispatch the agent to fix it. Nothing an agent discovered may evaporate into a report footnote.

Then free the agent's slot and refill the pool (3b step 4). Emit a brief progress report at the **wave join** (when the pool has fully drained), not after each completion — keep per-completion output to a one-line status.

#### 3d. Run the Wave Test Gate Per Package (targeted intra-phase, full suite at last-touch)

**HARD RULE — never run any test mid-wave.** Do NOT invoke `test.ps1` until the **wave join** — EVERY task in the wave has finished implementing and the rolling pool has fully drained. No per-task, per-completion, or partial-wave test runs. The wave's test gate runs exactly once here, after the whole wave is complete.

**Test-scope decision (lever to avoid redundant full-suite reruns).** The phase-boundary gate (3i) already runs each touched package's **full** suite authoritatively at the end of every phase. So re-running the full suite after *every* wave is largely redundant — a package that appears in many waves had its full suite executed many times for no added signal. Instead, at the wave join, for each `package` with completed tasks in this wave:

- **If this wave is the package's last-touch wave** (`current_wave == package_last_touch_wave[package]`) → run the package's **full** suite (the authoritative in-loop gate for that package's last change this phase).
- **Otherwise (an earlier intra-phase wave)** → run only this wave's **targeted tests** — the union of the `## Targeted Tests` commands from the wave's completed tasks for that package. This catches the wave's own breakage cheaply without a full sweep.

This still gives every package exactly one in-loop full-suite gate (at its last-touch wave) plus the authoritative phase-boundary sweep (3i) — while removing the N−1 redundant early-wave full runs. A single-phase run still hits 3i's full-suite gate at phase end, so nothing ships without a full sweep.

After the **wave join** — the rolling pool has fully drained (`in_flight` and `wave_queue` both empty):

1. Group completed tasks in this wave by `package`
2. For each affected package, pick its scope per the decision above, then fire the runs for **all affected packages concurrently** — a single message with multiple Bash calls (one per package), so a multi-package wave gates in parallel instead of back-to-back:

   ```bash
   # last-touch wave for this package → full suite:
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   # earlier intra-phase wave → targeted only (one -Specific per wave task in this package):
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{wave-task-test-path}"
   ```

   Include `VERIFIED_AGAINST_QUICK_REFERENCE` in each Bash tool description.

   These runs are the orchestrator's **authoritative, independent** gate — run regardless of any result an agent self-reported, including in a quality-gate wave. (The redundant *agent-side* suite run is suppressed at spawn time — see 3b.) Do not skip them or substitute an agent's self-reported numbers. Each package writes its own `.test_results/` folder, so parallel runs do not collide; read each package's `index.json` separately in step 3. A quality-gate wave is by construction a package's last-touch wave, so it always runs the full suite.

3. **Read the canonical result from `index.json`, not the console.** `test.ps1` saves a timestamped folder under `{package}/.test_results/test-results-*/` and prints its path on the final console lines. Read that folder's `index.json` — it is the machine-readable source of truth. Do NOT eyeball-parse stdout. Extract:
   - `result` — `"PASSED"` or `"FAILED"`
   - `counts.passed`, `counts.failed`, **`counts.error`**, `counts.skipped`, `counts.xfailed`, `counts.xpassed`
   - From `full.log` in the same folder: the failing test node IDs **and** the erroring module/collection paths (errors have no per-test node ID — they are reported at module level)

4. **Decide the gate. The gate is GREEN only when `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0`.** Treat **errors exactly like failures** — a pytest *error* (collection / import / fixture / setup failure) means tests never ran, which is a worse outcome than an assertion failure, not a passable one. Never read `failed` alone: a run with `failed == 0` but `error > 0` is RED, not green.
   - Gate GREEN → proceed to 3f (mark complete)
   - Gate RED (any `failed` or `error`) → proceed to 3e (attribute & fix)
   - If `index.json` is missing or unparseable → the run did not complete cleanly; treat as a **test infrastructure failure** (see Error Recovery), do not infer a pass from stdout.

#### 3e. Attribute Failures and Fix Loop

Process **both** red outcomes from `counts`: assertion **failures** (`counts.failed`) and **errors** (`counts.error`). They are attributed and fixed the same way, with one difference in how you locate them:
- A **failure** has a per-test node ID (`tests/...::test_x`) — fix the code under test.
- An **error** is reported at module/collection level with no per-test node ID (e.g. an `ImportError`, a fixture error, a syntax error that breaks collection). Read `full.log` for the ERRORS section, attribute by the **erroring module/file path**, and fix the import/fixture/syntax root cause. An error often hides many tests that never ran — resolving it can change the pass count substantially, so always re-run after fixing one.

**Delegation split for the fix loop.** Attribution (step 1) and the fix-scope decision are YOUR judgment — do them inline. Reading the failing test/code and applying the edit (steps 2–3) are delegated to a **fix subagent** — do NOT edit code inline on Opus. You verify (step 4) by running the targeted test yourself, or by delegating the run and reading its `index.json`.

For each failing test **and each erroring module** from the wave gate run (targeted-only on earlier intra-phase waves, full suite on a package's last-touch wave):

1. **Attribute (YOUR judgment, inline):** Cross-reference the failing test file / erroring module against `files_created` and `files_modified` from tasks in this wave.
   - **Quality-gate / integration waves:** when the failing wave is a quality-gate wave (the gate task itself creates no files), the failure is almost always a *cross-task integration* failure introduced by an earlier wave's task in the **same package and phase**. Widen attribution to the `files_created`/`files_modified` of ALL completed tasks for that package across this run, not just the current wave. Attribute to the task whose changed files best match the failing test/code, and apply the fix within that task's scope.
   - If no task's files match the failing test (failure is in pre-existing, untouched code) → classify as **pre-existing**, do not fix at the wave gate, note it in the checkpoint, and treat it as a non-blocking failure for the wave per the gate's "or only pre-existing failures remain" success criterion. **This wave-level reprieve is temporary in a multi-phase run:** the Phase Boundary Gate (3i) fixes ALL of these pre-existing failures, attribution-agnostic, before the next phase starts — so a pre-existing failure left here must still be driven to zero at the phase boundary.
2. **Dispatch the fix (delegated):** spawn a **sonnet** fix subagent (`subagent_type: "general-purpose"`, `run_in_background: true`) — escalate to **opus** when the root cause is subtle or cross-cutting. Its prompt is self-contained: the failing test node ID / erroring module, the attributed task's file scope (the ONLY files it may modify), the relevant `shared_context` slice, the CLAUDE.md constraints (no workarounds, no git reverts, no mocks, no debug scatter, `test.ps1` only), and the acceptance check (the specific test must pass). It reads the test + code under test, fixes the **root cause within the attributed scope**, and returns files-changed + its targeted-test result. You supply the root-cause hypothesis when you have one; you do NOT read/edit the code yourself.
3. **Review the returned fix:** inspect the diff against the attributed scope and the no-workaround rules before trusting it — an agent's green self-report is necessary, not sufficient.
4. **Verify (YOUR gate):** re-run the specific failing test authoritatively — run it yourself or delegate the run and read the canonical `index.json`, never the agent's number:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{failing-test-path}"
   ```
   Include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash tool description.
5. **If the fix fails:** invoke the **Decision Escalation Protocol** — analyze the root cause in-context yourself (you are the Opus orchestrator), then re-dispatch the fix subagent with your concrete remediation plan (failing test, root cause, exact change). If your directed fix still fails → mark the task FAILED.

**Stop conditions:**
- **first attempt** with no progress and root cause is unclear → invoke the **Decision Escalation Protocol** (analyze in-context, dispatch a directed fix); if your directed fix also fails → mark that task FAILED
- A fix introduces new failures → have the fix subagent undo its own edit manually (a directed re-dispatch — NO git reverts), then invoke the **Decision Escalation Protocol** before trying again
- Cascading issues in unrelated subsystems → invoke the **Decision Escalation Protocol** to determine correct fix scope; if your analysis concludes the run should stop → STOP, report

After the fix loop, re-run the gate once to verify no regressions. Re-run the **same scope** that gated this wave for the package — targeted on an earlier intra-phase wave, full on a last-touch wave. Escalate to the **full** package suite if a fix modified code outside the wave tasks' own files (a shared-code fix can break tests the targeted set didn't cover):
```bash
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
```

#### 3f. Handle Failures (Escalate then Pause & Ask)

If the first fix attempt fails:

1. **First: invoke the Decision Escalation Protocol** — analyze the root cause in-context yourself (task spec, all fix attempts, exact failures), then dispatch a fix subagent with your concrete remediation plan. Attempt your directed fix once. If it succeeds, proceed normally.
2. **If your directed fix also fails**: surface to the user with your root-cause analysis included as context.

Use `AskUserQuestion` to ask the user:
```
Task {task_id} ({title}) — first fix attempt failed.

Failing tests:
- {test_name}: {error_message}

Options:
1. Continue — skip this task and all tasks that depend on it, proceed with next wave
2. Stop — halt orchestration, emit final report with current progress
```

- If **Continue**: add task to `failed_tasks`, compute transitive dependents and add to `skipped_tasks`
- If **Stop**: emit final report (Step 4) and halt execution

#### 3g. Mark Tasks Complete — only after the design-acceptance + BLOCKED-terminal checks pass

Apply the shared 4-condition checklist `d:\datrix\.claude\skills\_shared\completion-eligibility.md` — tests green / not-BLOCKED-terminal / How-Solved clean / design-acceptance property proven by a check YOU run (command + output pasted into How-Solved; never the agent's self-report). Orchestrator bindings:
- Condition 1's governing gate is the **wave test gate (3d)** for the task's package.
- Condition 4 uses the `design_acceptance_property` recorded in Step 1d; an unprovable property routes to 3e/escalation as a conformance failure, not a pass.
- **On failure of any of 2–4:** no `complete.ps1`; record in `failed_tasks` with the unmet condition, spawn the blocker as a tracked follow-up task (a real task file, not a footnote), compute transitive dependents into `skipped_tasks`, continue.
- **On pass of all 4:** run `complete.ps1 "{task_path}"` (include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash description), add the proof-of-work `## How Solved`, and append to `completed_tasks`.

#### 3h. Wave Checkpoint

Emit a lean checkpoint and update TodoWrite:

```
Wave {N}/{total}: {completed} done, {failed} failed, {skipped} skipped | {package}: {passed}/{total} passing
```

If failed or skipped tasks exist, list only those (one ID per line). Do NOT list completed tasks — success is the default.

Mark the wave's todo as completed in TodoWrite.

#### 3i. Phase Boundary Gate (runs at the end of EVERY phase, single- or multi-phase)

This gate runs at the end of **every** phase, not only multi-phase runs. In a multi-phase run (e.g. `PHASES: 72, 73, 74`) phases execute **strictly sequentially** and the gate guards each boundary; in a single-phase run it runs once at the end of the run. Either way, the phase is not declared complete until it passes BOTH the full-suite gate (Step A) AND the design-conformance gate (Step A2). The gate exists so a later phase never starts on top of an incompletely-built earlier phase, and so no phase is ever reported "done" while a design invariant it owns is unenforced.

Trigger this gate **after the last wave of a phase completes** (i.e. the next wave in the sequence belongs to a higher phase number, or there are no more waves) and **before spawning the first wave of the next phase**.

**Gate procedure for completed phase `P`:**

##### Step A — Phase-end full-suite gate (fix ALL failures, attribution-agnostic)

Stricter than 3d: **every package this phase touched must pass its FULL suite with zero failures and zero errors — pre-existing failures included** (3d's pre-existing allowance does NOT hold here; they are blocking and must be driven to zero before phase `P+1`). Runs every time a phase completes, even a fully green one — cross-wave integration and pre-existing rot only surface against the complete phase.

1. **Determine touched packages** — the set of packages appearing in `files_created` / `files_modified` of any task in phase `P` (across all of the phase's waves).
2. **Run the full suite for every touched package concurrently** — fire all `test.ps1 {package}` calls in a **single message** (one Bash call per package), exactly as 3d. Include `VERIFIED_AGAINST_QUICK_REFERENCE` in each Bash tool description.
3. **Read each package's `index.json`** (the canonical result, never stdout). A package is GREEN only when `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` — errors count as red, exactly as the 3d gate rules.
4. **Fix every red package to GREEN — regardless of attribution.** For each failing test and each erroring module across ALL touched packages, **including failures in code that no task in this phase modified**:
   - **Delegate the fix, own the verdict.** Dispatch a **sonnet** (or **opus** for a subtle/cross-cutting root cause) fix subagent to read the failing test and the code under test, trace to the **root cause**, and fix it there. Unlike 3e this is NOT scope-restricted to a task's files — instruct the agent to fix whatever is red at its root. Bind it with NO workarounds, NO `xfail`/skip-to-pass, NO band-aids, NO conditional guards that hide the broken path, NO git reverts (CLAUDE.md). You do NOT read/edit the code inline on Opus — you decide what's in scope and verify the result.
   - Verify authoritatively: re-run the specific test (`test.ps1 {package} -Specific "{path}"`), then re-run the full package suite — reading `index.json`, not the agent's self-report.
   - If the first fix attempt fails or the root cause is unclear → **Decision Escalation Protocol** — analyze the root cause in-context yourself, then re-dispatch the fix subagent with your directed remediation plan. If your directed fix still fails, that test/module becomes a blocking item carried into Step C's halt-and-ask.
   - If a red test traces to a root cause **genuinely outside this repo's control** (e.g. a known-flaky external integration) → do NOT silently skip it; record it as a blocking item and surface it in Step C, letting the user decide. Do not invent this exception to dodge a real fix.
5. **Re-run until clean** — repeat the full per-package suite after fixes until every touched package is GREEN, or escalation/halt is reached. An error fixed in one module often unhides many tests that never ran, so always re-run the full suite after a fix rather than trusting `-Specific` alone.

##### Step A2 — Phase-end DESIGN-CONFORMANCE gate (runs at EVERY phase end, including single-phase runs)

A green suite proves the code runs; it does NOT prove the design holds. This gate verifies phase `P` actually satisfied the `design_contract` built in Step 1d. **It runs at the end of every phase — including a single-phase run — and a phase cannot be declared complete without it, even when Step A is fully green.** This is the gate phase-01 lacked.

For each invariant / numbered decision (D#/G#) in phase `P`'s `design_contract`:

1. **Enumerate the invariant's full surface set** (from Step 1d). For each surface the design names, run the invariant's **acceptance check** (negative + positive) against REAL generated output / migrated source — not against an agent's self-report. Paste the command + output.
   - *Negative:* the forbidden construct/state is gone on that surface (e.g. `grep` finds zero raw `env(...)` on secret positions in the migrated tree).
   - *Positive:* the new path is actually exercised (e.g. the generated service resolves each secret via `get_secret(<handle>)`; no `${VAR}`/literal secret remains).
2. **Any surface in the design's set that is unguarded / unconverted is a CONFORMANCE FAILURE** — even if every task is COMPLETED and every suite is GREEN. A half-implemented invariant (guarded on the easy surface, silently dropped on the rest) is exactly the phase-01 escape; this step is built to catch it.
3. **Verify every task's `design_acceptance_property` was actually proven** (its check + output is in its How-Solved). A COMPLETED task whose property is unproven is a conformance failure — reopen it.
4. **Check the conformance gaps recorded in Step 1d** (design-named surfaces with no covering task). Any unresolved gap is a phase-level failure.

A conformance failure is handled like a red package: fix it to conformance within the phase (spawn a follow-up task for an out-of-scope root cause), or carry it to Step C's halt-and-ask. **NO declaring the phase done with a known unenforced design surface.** Report each conformance failure explicitly — never let it pass silently under a green suite.

##### Step B — Partition and evaluate

Partition phase `P`'s tasks into `completed`, `failed`, and `skipped` (using the run-wide state variables, filtered to tasks whose `phase == P`).

**Green phase** — every touched package passed Step A's full-suite gate (all red driven to zero) **AND Step A2's design-conformance gate passed (every design-named surface enforced, every task's acceptance property proven, no open conformance gap)** AND `failed` and `skipped` are both empty:
- Emit the Phase Checkpoint (below).
- Proceed to the first wave of phase `P+1`.

##### Step C — Red phase

Any `failed` or `skipped` task in phase `P`, **OR** any package still red after Step A's fix loop, **OR any unresolved design-conformance failure from Step A2** (an unenforced design-named surface, an unproven task acceptance property, or an open conformance gap):
   - **Do NOT start phase `P+1` yet.**
   - **First, produce the phase-recovery plan yourself (in-context, as the Opus orchestrator)** — invoke the **Decision Escalation Protocol** (phase-recovery variant) scoped to the whole phase. You already hold: every failed/skipped task in phase `P`, **every still-red test/module from Step A** (including pre-existing failures that resisted the fix loop), the exact test failures/errors, all prior fix attempts (wave-level 3e/3f **and** Step A), and the relevant code excerpts. Analyze them and produce a **phase-recovery plan** — root cause(s) across the failed items (name shared causes explicitly) and concrete, per-item remediation steps, in a sensible order. This is exactly the judgment you are on Opus for; do it inline rather than spawning another Opus agent to decide.
   - **Dispatch subagents to implement your recovery plan** (**sonnet**, or **opus** for the hardest items), partitioned so no two agents write the same files: give each the per-item remediation steps, exact files to modify, and the CLAUDE.md constraints. Then re-run the **full test suite for every affected package** yourself (3d gate rules — GREEN only when `result == "PASSED"` AND `failed == 0` AND `error == 0`). Re-attribute and mark any now-passing tasks complete via `complete.ps1`.
   - **Re-evaluate the phase:**
     - If phase `P` is now green → emit the Phase Checkpoint, proceed to phase `P+1`.
     - If phase `P` is **still red** after implementing Opus's plan → **HALT at the phase boundary** and `AskUserQuestion` (below). Do not auto-advance.

   `AskUserQuestion` on unresolved phase failure:
   ```
   Phase {P} did not complete cleanly — Opus-led recovery still leaves failures.

   Failed / skipped tasks in phase {P}:
   - {task_id}: {reason}

   Unresolved test failures (incl. pre-existing, unattributed):
   - {package} :: {test_or_module}: {error summary}

   Opus's analysis:
   {1-2 line summary of Opus's root-cause finding}

   Options:
   1. Stop — halt orchestration here; phase {P+1}+ not started. Emit final report.
   2. Proceed anyway — start phase {P+1}; tasks transitively depending on phase {P}'s failed tasks stay skipped, the rest run. Unresolved package failures are carried forward and reported.
   ```
   - **Stop** → emit final report (Step 4) and halt; later phases are reported as `NOT STARTED`.
   - **Proceed anyway** → carry phase `P`'s `failed`/`skipped` forward into run-wide state and start phase `P+1` (3a's skip logic already prunes downstream dependents).

**Phase Checkpoint format** (emit at every phase boundary, green or after recovery):
```
Phase {P} COMPLETE — {completed}/{phase_total} tasks | tests: {package}: {passed}/{total} | {package}: {passed}/{total}
→ Starting phase {P+1}
```

Track phases as their own TodoWrite group so the user can see phase-level progress distinct from wave-level progress.

---

## Step 4: Final Report

After all waves are executed (or execution is halted by user), emit a lean report:

```
DONE: {COMPLETED|PARTIAL|HALTED} — {completed}/{total} tasks, {waves_executed}/{total_waves} waves
Phases: {P}: COMPLETE | {P+1}: PARTIAL | {P+2}: NOT STARTED   (only for multi-phase runs)
Audit: {N} tasks added to close design gaps: {task-id} ({gap})  (only if the readiness audit amended the set)
Tests: {package}: {passed}/{total} | {package}: {passed}/{total}
Failed: {task-id} — {reason}  (only if any)
Skipped: {task-id} — blocked by {dep}  (only if any)
```

Do NOT list completed tasks — success is the default. Only list failures, skips, and audit-added tasks (`audit_added_tasks[]` — the user needs to know the task set grew and why). For multi-phase runs, include the per-phase status line: a phase is `COMPLETE` (passed its phase gate), `PARTIAL` (started, advanced past the gate with failures via "Proceed anyway"), or `NOT STARTED` (never reached because an earlier phase gate halted).

---

## Anti-Patterns & Safety Rules

All rules from `d:\datrix\.claude\CLAUDE.md` apply. Key rules for the orchestrator:

- **CONFORMANCE OVER THROUGHPUT / BLOCKED IS TERMINAL** — enforced by the 3g completion checklist (`_shared/completion-eligibility.md`) and the 3i Step A2 conformance gate; never relaxed for a green suite.
- **NEVER EXECUTE AN UNAUDITED TASK SET** — Step 1e runs before Step 2, every run, no exception. A task set is a *hypothesis* about what the design needs against the code that existed when it was written; the audit tests that hypothesis against today's code before 5 agents act on it. Skipping it to "just start the waves" is how a phase finishes green with a design invariant unenforced. Gaps it finds are closed as real tasks with provable acceptance properties — never as a note in the report, a footnote, or a stub task.
- **NO ASSUMING — ENUMERATE AND VERIFY STATE** — characterize a corpus by enumerating ALL of it (counted), not a sample; reason about git/working-tree from the CURRENT on-disk state you just read, never a remembered snapshot. Paste real command output for every conformance claim.
- **GENUINE agent monitoring, never assumption** — when agents run in the background pool, drive them with the Agent Progress Polling Protocol: check every ~5 minutes what each agent is *actually* doing (status **and** on-disk artifacts). Never report an agent as "working" without that evidence, and never rely on a completion notification to know an agent finished.
- **JUDGMENT INLINE, TYPING DELEGATED** — you are the Opus orchestrator: decompose, attribute, decide fix-scope, gate conformance, and analyze escalations in YOUR context; dispatch subagents (haiku/sonnet/opus) to read widely, run suites, and apply fixes. Do NOT edit code inline on Opus in the fix loops (3e/3i) — decide the fix, then hand the edit to a subagent. Reading the minimum code needed to decide is fine; doing the whole implementation inline is not.
- **NEVER DELEGATE THE DECISION** — the old "escalate up to a more-capable agent" is gone; you ARE the Opus brain. Analyze in-context at extra-high effort, then dispatch a cheaper implementer (an `opus` subagent only for a genuinely hard/cross-cutting fix). Verify every returned result with a check you run (or delegate the run and read `index.json`) — a subagent's self-report never substitutes for the design-acceptance evidence you paste into the gate.
- **NO workarounds** — fix root causes, not symptoms. If something is broken, trace to root cause
- **NO git reverts** — never use `git checkout`, `git restore`, `git reset`, `git stash`, `git revert`
- **NO debug scatter** — zero temporary logging statements left behind
- **NO mocks in tests** — `unittest.mock`, `MagicMock`, `SimpleNamespace` all banned
- **NO temporary files outside designated folders** — use `D:\datrix\.scripts\`, `D:\datrix\.test-output\`, `D:\datrix\.tmp\`
- **Test execution via PowerShell scripts only** — always use `test.ps1` / `test-single.ps1`, **never call `pytest` (or `python -m pytest`) directly**. A PreToolUse hook hard-blocks direct pytest.
- **Never pass `-NoSave` or `-VerboseOutput` to `test.ps1`** — `-NoSave` hides the saved progress Jon reads; `-VerboseOutput` burns tokens for no benefit. Run with neither flag and read `index.json` for results. The hook hard-blocks both flags. This applies to the orchestrator's own gate/specific runs **and** every spawned agent.
- **Never run `mypy`** (or any standalone type-checker) in this workflow — neither the orchestrator nor its agents. Code must be fully type-hinted, but type correctness is covered by the suite gate; a separate mypy run only burns tokens/turns.
- **VERIFIED_AGAINST_QUICK_REFERENCE** — include in all Bash descriptions for script invocations
- **Logic map** — check `d:/datrix/.logic-map/markers.db` before modifying code with markers
- **Project domain isolation** — no customer/project domain language in framework packages

## Decision Escalation Protocol

You are the Opus orchestrator — the escalation target is **you**: shift out of dispatch-and-supervise mode into deliberate, in-context architectural analysis, then dispatch a subagent to implement your decision. When execution reaches a genuine design/architectural decision (multiple valid approaches, unclear root cause after investigation, ambiguous fix scope), do this analysis yourself **before** pausing for the user or marking a task failed — it is the highest-value use of your Opus budget; typing the resulting edit is not.

### When to Escalate

**DO escalate for:**
- An agent returns BLOCKED with a technical ambiguity (unclear design choice, conflicting patterns, unknown root cause) — not a hard blocker like a missing file
- The first fix attempt fails and root cause is unclear
- Cascading failures suggest a systemic problem where the correct fix scope is uncertain
- A task's implementation conflicts with existing architecture in a way that requires architectural judgment

**Do NOT escalate for:**
- Incomplete prerequisite dependencies → STOP immediately, report
- Simple syntax/import errors with obvious fixes → fix directly
- Clear spec violations → fix directly
- Missing user-supplied information (credentials, paths, spec gaps) → ask user directly

### How to Escalate — analyze in-context, then dispatch the implementer

**Step 1 — Analyze yourself (this is the Opus judgment).** Read the failing test and the relevant code excerpts (read them now if you delegated earlier and don't hold them), and reason to a decision. Decide what is genuinely best for the LONG-TERM health of this production system — this is NOT a hackathon and you are NOT trying to save the day; never pick the simple or expedient option and defer the correct one to a "future" that never arrives. No workarounds, band-aids, or "good enough for now". Produce, in your own reasoning:
1. Root cause analysis (not symptom) — 2-3 sentences
2. The chosen approach — concrete, step-by-step
3. Exact files to modify and what changes to make
4. Why this is the right long-term choice (not the quick fix), considering impact on other components, consistency with existing patterns, and maintainability
5. Any risks or prerequisites the implementer must know

Reading the minimum code needed to decide correctly is a legitimate use of your context — but do not drift into doing the whole implementation inline. Once the decision is made, hand the typing off.

**Step 2 — Dispatch a subagent to implement your decision.** Spawn a **sonnet** implementer (**opus** only for a genuinely hard/cross-cutting change) to apply your decision — the implementer executes, it does not re-decide:

```
Agent tool parameters:
  subagent_type: "general-purpose"
  model: "claude-sonnet-4-6"   # or "opus" for a hard change
  run_in_background: true
  description: "Directed fix: {task_id}"
```

**Implementer prompt template** (fill from your Step-1 analysis — the agent follows it exactly, it does NOT re-decide):
```
Apply a specific, pre-decided fix. Do NOT redesign — the root cause and approach are already determined; implement them exactly.

TASK CONTEXT: {task_id} — {title}; objective: {what the task was supposed to accomplish}
ROOT CAUSE (decided): {your root-cause finding}
FIX TO APPLY (step by step): {your concrete steps}
EXPECTED FILES (the surface I predict — NOT a fence): {exact paths}
SCOPE RULE: If the root cause lies outside the expected files, FOLLOW IT AND FIX IT THERE, then report the added files under `scope_expansion`. Do not patch at the boundary — that is a workaround. {If dispatched inside a parallel wave, add instead: `PARALLEL_WAVE: files are exclusive` — another agent may hold files outside your list; do NOT edit them; return status EXPANSION_REQUIRED naming the exact files + root cause, and I will re-dispatch you serially. EXPANSION_REQUIRED is not BLOCKED.}
CONSTRAINTS: NO workarounds / band-aids / xfail-to-pass / conditional guards that hide the broken path; NO git reverts; NO mocks; NO debug scatter; test via test.ps1 only (never pytest directly); no -NoSave/-VerboseOutput.
ACCEPTANCE CHECK: {the exact test that must pass}

BLOCKING RULE (execution-contract §1-§3 — read `.claude/skills/_shared/execution-contract.md`):
Your default outcome is THE PROBLEM IS FIXED. There are exactly four blockers: B1 MISSING_ACCESS, B2 UNDECIDABLE (two defensible designs), B3 USER_FORBADE, B4 FENCED_SURFACE. Everything else is work — unclear root cause (keep reading), root cause in another package (go fix it), bigger than estimated (do it), pre-existing (it's yours now), "behavioral/environmental" (prove it with the error text or fix it), no test (write one), "should be tracked separately" (there is no other agent).
A BLOCKED return is ONLY valid with all four: (1) verbatim error text, (2) the fix you actually wrote and ran, as file:line, (3) why it failed, (4) the B1-B4 code. Missing any → I reject the report and re-dispatch this task to you with your own report quoted back.
FOUND IT, YOU FIX IT: any defect you discover on a surface you touched is yours — fix it, or file a real tracked task. Prose-only mention is not an outcome.

RETURN: files changed (with line counts), `scope_expansion`, the targeted-test result (command + pasted output), `discovered_defects` (each FIXED or FILED), and — only if BLOCKED — the four-part `blocker_proof`. Status: DONE / EXPANSION_REQUIRED / BLOCKED.
```

Note the removed status: **`DONE_WITH_CONCERNS` no longer exists.** It was a licensed way to hand back unfinished work with a shrug. A concern is either a defect you fix, a defect you file as a tracked task, or a proven B1–B4 blocker — there is no fourth bucket.

**Step 3 — Verify yourself.** Run the acceptance check authoritatively (or delegate the run and read `index.json`), review the diff against your intended change and the no-workaround rules. The implementer's self-report is necessary, never sufficient.

### Phase-Recovery Variant (Phase Boundary Gate, 3i)

When escalation is triggered by a **red phase gate** rather than a single task, the problem spans every failed/skipped task in the phase. Same protocol — **you** produce the recovery plan in-context (do not delegate the planning to another agent), then dispatch implementers per item. Reason through the phase-wide framing below to produce your plan, then hand each item's concrete steps to a **sonnet**/**opus** implementer (partitioned by files) exactly as in "How to Escalate" Step 2.

Analysis framing for a failed phase (produce a recovery plan in-context, do not implement inline). Assemble: every failed/skipped task (with exact failing tests/erroring modules + error text), every still-red unattributed test/module from Step A, all prior fix attempts (3e/3f and Step A), and the relevant code excerpts. Reason to: (1) root cause(s) — name shared causes behind multiple failures explicitly; (2) a per-item remediation plan with concrete steps; (3) exact files to modify; (4) remediation order (some fixes unblock others); (5) any item that genuinely cannot be recovered here (so the halt-and-ask covers just that item). Long-term-correct fixes only — no workarounds, no expedient fixes deferred "to the future". The goal: every touched package fully green (zero failures AND zero errors, pre-existing included — at a phase boundary they are blocking, not excused).

### After Your Analysis

- Dispatch subagent implementers (Sonnet default, Opus for the hardest items) to apply your plan; they implement exactly what you decided — no improvising beyond it. Partition so no two agents write the same files.
- For a phase-recovery plan: after the implementers return, re-run the full suite for **every affected package** yourself (3d gate rules) before re-evaluating the phase gate.
- If your analysis concludes the run should stop and ask the user, surface your full root-cause analysis as context when asking.

---

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

