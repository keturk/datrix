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

**A multi-phase run is ONE run, not a sequence of runs.** When the invocation names several phases (`PHASES: 72, 73, 74`), you own all of them to the end. Completing a phase — even a fully green one — is **not** a stopping point, not a natural pause, and not a place to hand back to the user for a "shall I continue?" A green phase boundary has exactly one successor action: **spawn the first wave of the next phase, in the same turn.** The only exits from the run are a **Fable `F` (ASK_USER)** decision at 3i Step C or 3f, and the final report **after the last phase**. See **Multi-Phase Continuation** below — it binds.

**The orchestrator's mandate is conformance, not throughput** (CLAUDE.md "Task Orchestration" states the full rationale — it binds here). Two consequences at every wave and phase boundary: **a green suite is necessary but NOT sufficient** (the explicit design-conformance gates at 3g and 3i Step A2 prove the design invariant itself), and **a task whose agent returned BLOCKED can never be quietly marked COMPLETED** (per the shared checklist `d:\datrix\.claude\skills\_shared\completion-eligibility.md`).

**Every decision you cannot make climbs the same ladder — and the user is its LAST rung, not its first.** The full mechanism is `d:\datrix\.claude\skills\_shared\decision-adjudication-protocol.md` — **read it; it binds everywhere in this skill that a decision, conflict, or blocker appears.**

> **1 INVESTIGATE** (read the code and the docs yourself — most "decisions" dissolve) → **2 DECIDE** (if the evidence settles it, decide and act; escalating a decision you can make is as much a failure as stopping) → **3 ADJUDICATE** (if you genuinely cannot decide, a **Fable** adjudicator — `model: "fable"`, `effort: "high"` — decides, and its decision is binding) → **4 ASK THE USER** (**only** when Fable returns decision **F (ASK_USER)**).

**Fable is not the blocker door. Fable is the decision door.** It is reached through **two entry doors that converge on the same ladder**:

- **Door A — a subagent reports BLOCKED.** A BLOCKED is not a verdict; it is a *claim you must adjudicate*. Never stop on it, never relay it. Investigate it yourself; if it is bogus (the common case) correct the agent and it finishes the task; if it is genuinely real, Fable decides what happens instead and you carry that out.
- **Door B — a decision or conflict YOU hit.** Two designs contradict. A design-named invariant surface has no owning task. A task's premise is false against the code. A fix failed and the correct scope is ambiguous. A phase gate is red and the recovery scope is unclear. Phase/task ordering conflicts with what the code requires. **All of these go to Fable, not to the user.**

**If you are drafting an `AskUserQuestion` and Fable has not returned `F` on that exact question, you are on the wrong rung — go back to rung 3.** The only exceptions are the closed list in the protocol's §7: a credential/account that exists nowhere in the repo · an irreversible outward-facing action needing authorization (real cloud spend, a push, a deploy) · a genuine product/business call · a user-set prohibition that must be lifted. **Which design to follow, what order to run phases in, whether a task set satisfies its design, how to close a coverage gap, what the fix scope is, and whether to continue after a failure are NOT on that list — they are rung-3 decisions.**

**Key differences from `/execute-tasks-parallel`:**
- **Readiness audit before any execution** (Step 1e) — audits the task set against the design doc AND the current implementation, then authors the missing tasks and rewires `dependencies.md` before planning waves
- Dependency-aware grouping (builds a DAG, topologically sorts into waves)
- Automatic wave advancement (no human intervention between waves)
- Handles tasks with cross-dependencies (separates into waves instead of blocking)
- **Sequential multi-phase execution, with no stop in between** — given several phases (e.g. `72, 73, 74`), finishes each phase fully and then **immediately starts the next, unprompted**. At every phase boundary a gate (Step 3i) runs the full test suite for its **sweep set** (the phase's changed packages + every consumer of a changed shared layer; in a multi-phase run the first boundary sweeps **ALL packages** and later boundaries maintain that all-green guarantee incrementally) and fixes **all** failures — including pre-existing ones unrelated to the phase's changes — with Opus-led recovery. Green gate → next phase's first wave dispatches in the same turn; the run ends only at the last phase (or a Step C halt). See **Multi-Phase Continuation**

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

##### Audit mode — full vs. light (decide first)

The audit's cost must match what could have drifted. Read `dependencies.md`'s `provenance` stamp (see `dependencies-format.md`):

- **Light mode** when ALL hold: the stamp exists; `generated_by` is `/generate-tasks` or `/operationalize-design`; `generated_at` is within **24 hours**; `validated` covers the design-conformance checks (16a design-reference/acceptance-property, 16b enforcement-ordering, 16c invariant-surface, migration-coverage, dual-path); and you know of no code change on the affected surfaces since generation. In light mode, **skip re-deriving what the generator just proved** (dimensions 1, 2, 5 — coverage gaps, enforcement ordering, under-specification) and audit only the drift dimensions: **3 stale premise, 4 already-satisfied, 6 missing dependency edge** — one sonnet agent for the whole set is usually enough. Still do 1d (the design contract itself is needed by 3g/A2 regardless).
- **Full mode** otherwise: no stamp, a stale stamp (>24h), a `validated` list missing the conformance checks, a legacy-format file, known intervening code changes, or a set that has already been partially executed. Run all seven dimensions as below.
- Dimension 7 (unresolvable premise) applies in both modes — a design/code contradiction is never skipped.

State the chosen mode and its justification in the Audit Report line.

##### Procedure

1. **Delegate the evidence gathering, keep the verdicts.** Dispatch **sonnet** audit subagents in parallel (`run_in_background: true`, one per package in the task set, plus one for the design-contract coverage sweep; in light mode, one agent covering dimensions 3/4/6 for the whole set). Each gets: the design doc path + the 1d `design_contract` (invariants and their full surface sets), the task files it owns, and the shared-context digest. Each returns **findings with evidence only** — for every claim, the file:line it read or the command + output it ran. Instruct them explicitly: *report a gap only if you verified it against the code on disk; a suspicion with no evidence is not a finding.* They do not author tasks and they do not edit code.
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
- **BLOCKING (dimension 7, or a design/code contradiction you cannot reconcile)** → **this is a rung-3 decision: it goes to FABLE, not to the user.** Do not `AskUserQuestion` here. Spawn a **Fable** adjudicator (`decision-adjudication-protocol.md` §5, **Door B**) with your evidence packet: what each design requires (quoted verbatim from the primary sources), what the code actually does (`file:line`), why no task can bridge them, the options you see and what each costs, and your leaning. Execute its decision (§6) — **A** no-conflict / **B** fix-elsewhere / **C** amend-task / **D** resequence / **E** spawn-follow-up / **F** ask-user. Only **F** reaches the user, and then you ask with Fable's exact question and recommendation. Never paper over the contradiction with a task that pretends the premise holds, and never hand the raw contradiction to the user as if the choice were theirs to make.

  **This is the exact hole that let a phase-19/phase-31 design contradiction reach the user unadjudicated.** A cross-design conflict *feels* like the user's call precisely because it is above any single task — that feeling is the trap. It is a design-level engineering judgment, and it gets the strongest model.

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

4. **Phase boundaries are wave boundaries** — even if a task in phase 35 has no dependencies, it cannot start until ALL phase 34 waves are complete. Each phase boundary is also a **Phase Boundary Gate** (Step 3i): the earlier phase must pass an explicit completion check — every package in the gate's sweep set (changed packages + shared-layer consumers; ALL packages at a multi-phase run's first boundary) must pass its **full** test suite with all failures fixed, including pre-existing ones unrelated to the phase, with Opus-led recovery on failure — before the next phase's first wave is spawned.

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

Once waves are assigned, the 3d test gate runs **targeted tests only** for every wave of the phase — no full suite runs inside a phase, for any package, for any reason. The phase-boundary gate (3i) is the authoritative and only full sweep.

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

## Multi-Phase Continuation (binding — read before Step 3)

When the run covers more than one phase, the wave loop of Step 3 runs over **every wave of every phase**, in the phase-sequential order computed in 2c. It terminates on exactly one condition: **there is no next wave in any remaining phase.** Nothing else ends it.

**Multi-phase runs carry an ALL-PACKAGES-GREEN guarantee.** At every phase boundary of a multi-phase run, the orchestrator must be able to assert "all tests for all packages are passing" — established by the first boundary's all-packages sweep and maintained incrementally at later boundaries (3i Step A's sweep-set rules). This guarantee is what lets phase `P+1` build on `P` without inheriting hidden rot. It never creates a stopping point: a red package found by the sweep is **fixed at the gate** (Step A's attribution-agnostic fix loop), and a green gate flows directly into the next phase's first wave in the same turn.

**At a green phase boundary you do not stop, do not summarize-and-yield, and do not ask.** Passing 3i's gates (Step A full-suite green on every touched package + Step A2 design-conformance) is the *permission* to continue, not a milestone to report and rest on. The Phase Checkpoint is a one-line progress marker emitted **on the way into** the next phase's first wave — in the same turn, with no intervening question to the user. If you catch yourself writing a summary of what phase `P` accomplished while phase `P+1` still has unexecuted waves, you have stopped early: dispatch the next wave instead.

**Illegitimate reasons to stop at a phase boundary — all of them:** the phase went green and it "feels like a good checkpoint"; the run is long / many tokens spent; the user "might want to review before continuing"; the next phase looks large; the context is filling up (delegate harder — see the Opus-orchestrator contract); you already emitted a checkpoint that reads like a conclusion. None of these appear in the exit list below, and none are B1–B4.

**The complete list of exits from a multi-phase run:**

| Exit | Trigger | Where |
|---|---|---|
| Halt-and-ask | Phase `P` still red after Opus-led recovery **AND** a **Fable** adjudication returned **F (ASK_USER)**. A red phase alone is NOT an exit — it is a rung-3 decision; Fable's A–E all keep the run moving. | 3i Step C |
| Task-failure prompt | A task failed after the directed-fix attempt, **Fable** adjudicated and returned **F**, and the user chose to stop | 3f |
| Blocking readiness finding | Design/code contradiction no task can reconcile, **which Fable adjudicated to F**. A contradiction alone is NOT an exit — Fable's A–E (amend, resequence, fix-elsewhere, follow-up) resolve it and the run continues | 1e, dimension 7 |
| Test-infrastructure failure | `test.ps1` itself errors twice | Error Recovery |
| **Run complete** | **The last wave of the LAST phase has passed its gates** | Step 4 |

**Note what is NOT on this list:** a red phase, a failed task, a design contradiction, a coverage gap, an ordering conflict, or an unclear fix scope. **None of those is an exit** — every one is a rung-3 decision that goes to Fable, and only a Fable **F** can turn one into a stop. The run ends when the work is done or when Fable says a human must decide. Nothing else.

**Step 4's Final Report is emitted once, at the end of the LAST phase — never at an intermediate phase boundary.** An intermediate boundary emits the Phase Checkpoint only.

If the user chose *Proceed anyway* at a Step C halt, the run continues into phase `P+1` and the same rule applies to every later boundary: keep going to the last phase.

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
- `package_change_log{}` — map of `package → every file changed in that package this run and by whom` (task agents' `files_created`/`files_modified` + `scope_expansion`, fix subagents' reported changes, audit-authored task files). Fed by 3c/3e/3i; consumed by the 3i sweep-set rules and the carry-forward optimization. If any change cannot be attributed to a recorded report, mark the log **tainted** — a tainted log disables carry-forward (3i sweeps everything)
- `package_green_state{}` — map of `package → the run-ID/timestamp of its last GREEN full-suite run in this orchestration run` (set only by 3i Step A results read from `index.json`). Used with `package_change_log{}` to decide which packages a later phase boundary must re-sweep

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
3. **Drive the pool with the Agent Progress Polling Protocol — never wait passively on completion notifications.** Read `d:\datrix\datrix\claude-config\.claude\agent-templates\agent-progress-polling-protocol.md` and run its poll loop over `in_flight`: every ~5 minutes (paced by a bounded `TaskOutput(block=true, timeout=300000)` on one in-flight agent), perform a **genuine** check of every in-flight agent — its status **and** its on-disk artifacts — and classify it (completed / progressing / stalled / errored). Never assume an agent is working because no notification arrived. A completion notification that DOES arrive is a valid trigger to run a poll cycle **immediately** (harvest that agent, refill the slot) rather than letting a finished agent hold a slot until the next 5-minute boundary — the genuine check remains the trust anchor; the notification only advances its timing. When the genuine check shows an agent has **completed**, immediately run 3c **for that one agent** (parse its result, handle BLOCKED/NEEDS_CONTEXT/re-spawn) and remove it from `in_flight`. A stalled agent (no assigned-artifact change across two consecutive polls, ~10 min) is investigated and, if hung, `TaskStop`-ped and re-dispatched or marked BLOCKED — never left counted as in-flight.
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

**Quality-gate tasks — suppress the agent's full-suite run AND its design-conformance scan.** A `**Category:** Quality Gate` task file lists "Run full test suite (`test.ps1 {package-name}`)" as a verification step (its `## Targeted Tests` scope is the full suite) and carries a design-conformance scan (checklist item 2b). In an orchestrated run BOTH are owned by the orchestrator — the full suite by the phase-boundary sweep (3i Step A) and the design-conformance sweep by the phase-boundary conformance gate (3i Step A2) — so the agent running either is a pure duplicate. When spawning a quality-gate agent, append this directive to its prompt:

> Do NOT run the full test suite (`test.ps1 {package-name}`) — skip Verification Step 1 / the `## Targeted Tests` full-suite command; the orchestrator's phase-boundary sweep owns that verdict. Do NOT execute the design-conformance scan (checklist item 2b — per-invariant surface sweeps and acceptance checks); the orchestrator's phase-boundary conformance gate owns those executions. Run no tests at all. Perform the remaining static verification in full: the non-trivial-implementation scan (stubs / `TODO` / `pass` / `NotImplementedError`, always-true validators, legacy/dual paths), the coverage & test-quality sanity checks (read the tests; do not run them), and the "How Solved" self-contradiction scan. Report every finding in your JSON result; the orchestrator owns the pass/fail verdict.

This keeps the gate's independent static-analysis value (a different agent than the implementers reads everything) while each expensive execution — suite and conformance — happens exactly once, at the phase boundary. The QG agent's findings feed 3i Step A2 as input (A2 must read them and act on each one); they are not a substitute for A2's own executions.

The rolling pool (above) governs when the next task is dispatched — a freed slot is refilled immediately, not after the whole wave drains.

#### 3c. Collect Agent Results (per completion)

Run this **each time a poll detects that one agent has completed** (the genuine check in 3b step 3 — never triggered by passively awaiting a notification) — not once per sub-group:

1. Parse the JSON report from the agent's output
2. Record status: IMPLEMENTED / EXPANSION_REQUIRED / BLOCKED / NEEDS_CONTEXT / FAILED

3. **If BLOCKED — run the DECISION ADJUDICATION PROTOCOL, Door A (`d:\datrix\.claude\skills\_shared\decision-adjudication-protocol.md`) FIRST, before any other handling.** Read it; it is binding. In brief:

   - **An agent's BLOCKED never stops this run.** It is an input to *your* investigation, not an outcome you record. Recording "agent said BLOCKED → task BLOCKED" is a non-answer: it means the orchestrator relayed a message instead of doing its job.
   - **Stage 1 — form check.** Does `blocker_proof` carry all four parts substantively (verbatim `error_text`; an `attempted` fix the agent actually **wrote and ran**, as `file:line` — analysis is not an attempt; a specific `why_it_failed`; a literal `B1`/`B2`/`B3`/`B4`)? Any field missing or vague → malformed; go straight to Stage 3.
   - **Stage 2 — INVESTIGATE IT YOURSELF, through the code and the docs.** A well-formed proof is still an assertion. Reproduce the error in the same context; open the `file:line` and check the attempted fix is real and aimed at the root cause; trace the root cause yourself; read the design/architecture docs that govern the surface; then test the claimed B-code against what you actually found (the legitimacy table in §3 of the protocol). Delegate the *reading and the repro* to subagents; **the verdict is yours** — never delegate adjudication to another background agent.
   - **Stage 3 — ILLEGITIMATE (the common case) → correct and re-dispatch.** Send a fresh agent the original task **plus** the correction packet from protocol §4: its own claim quoted back, the specific finding that kills it (with your `file:line` or command + output), what it missed, and the path forward. The task is **not** failed and **not** blocked — it is still in flight. Never add it to `failed_tasks`. Max **two** such re-dispatches; on a third invalid BLOCKED, do the full root-cause analysis yourself and dispatch a *directed implementer*.
   - **Stage 3′ — LEGITIMATE → Fable adjudication.** You confirmed it is real. **You do not decide what to do about it and you do not stop.** Spawn a **Fable** adjudicator (`model: "fable"`, `effort: "high"`, `run_in_background: false`, `subagent_type: "general-purpose"`) with the exact prompt in protocol §5 — the task + objective + design acceptance property, the four-part proof, **your** independent findings, the confirmed B-code, what you ruled out, and the CLAUDE.md constraints. It returns one binding `decision`: **A** not-actually-blocked / **B** fix-elsewhere / **C** amend-task / **D** resequence / **E** spawn-follow-up / **F** ask-user — with steps, risks, and an `acceptance_check`.
   - **Then execute that decision** (protocol §5 table). **Only F pauses for the user**; A–E all keep the run moving — dispatch the implementer, amend the task file (never the design doc), rewire `dependencies.md` and re-run cycle detection, file a real tracked task, or re-dispatch. Verify the outcome yourself with Fable's `acceptance_check`; the implementer's self-report is never sufficient.
   - **Fake blocker classes to expect and reject:** "missing dependency" (implement it), "missing file" (create it), "incomplete prereq", "unclear root cause" (keep reading), "pre-existing failure" (it's yours now), "environmental"/"behavioral" (prove it with the error text or fix it), "needs broader changes" (make them), "should be tracked separately" (**there is no other agent**). None of these are B1–B4.

4. **Recording a blocker.** A task that went through Fable adjudication is recorded as: the blocker, the confirmed B-code, Fable's decision, and what you did about it — **never as a bare "task BLOCKED"**. A task only enters `failed_tasks` when Fable's decision leaves it genuinely uncompletable (typically an **F** whose answer the user could not supply, or an **E** where the current task is fully gated by the follow-up).

5. If **EXPANSION_REQUIRED**: the agent knows the fix and needs the file lock. **Re-dispatch it serially the moment the conflicting files are free** (it may run alone after the wave join). This is *not* a failure and never goes to `failed_tasks`. Never shelve it, footnote it, or count the task as done.

6. If **NEEDS_CONTEXT** with a **spec gap or missing input**: first try to derive the answer from the design docs, the architecture docs, and the code (rung 1). If you derive it, re-queue the agent with the answer (rung 2). If you genuinely cannot, it is a **rung-3 decision → Fable** (Door B) — **not** an automatic user question. Only the protocol's §7 closed list goes straight to the user (a credential/account absent from the repo · an irreversible outward-facing action needing authorization · a genuine product call · a prohibition to be lifted); relay those via `AskUserQuestion` **with your recommendation**, then re-queue the agent with the answer.
7. If **NEEDS_CONTEXT** with a **technical ambiguity**: invoke the **Decision Escalation Protocol** — analyze and decide in-context yourself, then re-queue the implementation agent with your concrete recommendation. Do **not** pass a technical ambiguity to the user; that is your job. If your own analysis genuinely cannot settle it, go to **Fable** (rung 3) — never to the user.
8. If **FAILED**: record targeted test failures, add to `failed_tasks`

9. **DISCOVERED-DEFECT GATE.** For every entry in the agent's `discovered_defects`, the `disposition` must be `FIXED` (with a `file:line`) or `FILED` (with a real task file path that exists on disk). A prose-only mention is **not** a disposition — file the task yourself before the wave gate, or re-dispatch the agent to fix it. Nothing an agent discovered may evaporate into a report footnote.

Then free the agent's slot and refill the pool (3b step 4). Emit a brief progress report at the **wave join** (when the pool has fully drained), not after each completion — keep per-completion output to a one-line status.

#### 3d. Run the Wave Test Gate Per Package (targeted ONLY — never a full suite inside a phase)

**HARD RULE — never run any test mid-wave.** Do NOT invoke `test.ps1` until the **wave join** — EVERY task in the wave has finished implementing and the rolling pool has fully drained. No per-task, per-completion, or partial-wave test runs. The wave's test gate runs exactly once here, after the whole wave is complete.

**HARD RULE — NO FULL SUITE INSIDE A PHASE. THE LIST OF EXCEPTIONS IS EMPTY.** Inside a phase you run **only targeted tests for what the wave actually affected**. The full suite runs at the **phase boundary** (3i) and nowhere else. There is no last-touch-wave exception, no "the package is done so gate it now" exception, and — read this twice — **no shared-layer exception.**

At the wave join, the gate covers — for each `package` with completed tasks in this wave — **only** the union of the `## Targeted Tests` files from that package's completed tasks in this wave, plus the specific test files covering any code the wave moved, changed, or deleted. Coverage does NOT mean re-executing all of it: the gate below verifies each agent's already-saved run artifacts first and re-executes only what artifacts cannot prove.

**The shared-layer trap (this has been walked into repeatedly — do not repeat it).** CLAUDE.md's cross-surface impact rule says a change to a shared layer (`datrix-common`, `datrix-codegen-common`, any shared contract) must not break any consuming package. That rule tells you **WHICH packages must not be broken**. It does **NOT** authorize running their full suites mid-phase, and it is not a licence to re-run the world every time a shared file is touched. Inside the phase, cover a shared-layer change with **targeted tests over the changed surface and its consumers' call sites** — the specific test files exercising the moved/changed symbol in each consuming package. The phase-boundary sweep (3i) is what proves the consumers are whole. Buying that certainty 30 minutes early, at the cost of many minutes of redundant suite time, is not a trade you get to make.

Rationale: a package that appears in many waves would otherwise have its full suite executed many times for no added signal. The phase-boundary gate (3i) is the authoritative full sweep and it is not optional — nothing ships without it, including a single-phase run.

After the **wave join** — the rolling pool has fully drained (`in_flight` and `wave_queue` both empty):

1. Group completed tasks in this wave by `package`, and assemble each package's **wave targeted set**: the union of its tasks' `## Targeted Tests` files + the specific test files covering code the wave moved, changed, or deleted.

2. **Verify each agent's targeted run from its saved artifacts FIRST — do not re-execute what a machine-written artifact already proves.** Every `test.ps1` run persists a timestamped run folder with `index.json` + JUnit XML, and the agent's JSON report must carry the run-folder path the runner itself printed (`targeted_tests.run_folder`). For each task, **accept the agent's run without re-executing** only when ALL hold:
   - the reported run folder exists under `{package}/.test_results/` and its `index.json` is parseable (never substitute the newest directory on disk — only the path the runner printed);
   - the folder's timestamps fall within that agent's dispatch window;
   - the JUnit XML names tests from **exactly** the task's targeted files — nothing else, none missing (the same selection-integrity contract `test-specific-selection-gate.ps1` enforces);
   - `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0`.

3. **Re-run — batched — only what artifacts cannot prove.** For each affected package, ONE `test.ps1` invocation with a comma-separated `-Specific` list (multi-path batching runs the whole set in a single pytest session — never one invocation per file), covering only:
   - **(a) cross-task interference:** test files covering code touched by MORE THAN ONE task in this wave — the one thing no single agent's run can have seen;
   - **(b) unproven runs:** any task whose report lacks `run_folder`, or whose artifacts are missing, stale, mismatched, or red under step 2's acceptance rules;
   - **(c) uncovered changes:** test files over code the wave changed that no accepted agent run exercised;
   - **(d) spot check:** one randomly-chosen task's targeted files per wave, even if its artifacts were accepted — trust-but-verify.

   ```bash
   # ALWAYS targeted inside a phase. A bare `test.ps1 {package-name}` (no -Specific)
   # is a FULL SUITE and is FORBIDDEN here — it belongs only to the 3i phase gate.
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path-1},{test-path-2},{test-path-3}"
   ```

   Fire all affected packages' re-runs concurrently — a single message with multiple Bash calls — so a multi-package wave gates in parallel instead of back-to-back. Include `VERIFIED_AGAINST_QUICK_REFERENCE` in each Bash tool description. Each package writes its own `.test_results/` folder, so parallel runs do not collide. If nothing in a package falls under (a)–(d), that package's gate rests entirely on its accepted artifacts — that is the intended outcome, not a skipped gate.

4. **Read the canonical result from `index.json`, not the console.** `test.ps1` saves a timestamped folder under `{package}/.test_results/test-results-*/` and prints its path on the final console lines. Read that folder's `index.json` — it is the machine-readable source of truth (for both the step-2 accepted runs and the step-3 re-runs). Do NOT eyeball-parse stdout. Extract:
   - `result` — `"PASSED"` or `"FAILED"`
   - `counts.passed`, `counts.failed`, **`counts.error`**, `counts.skipped`, `counts.xfailed`, `counts.xpassed`
   - From `full.log` in the same folder: the failing test node IDs **and** the erroring module/collection paths (errors have no per-test node ID — they are reported at module level)

5. **Decide the gate over the union of accepted artifact results (step 2) and re-run results (step 3). The gate is GREEN only when every one of them has `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0`.** Treat **errors exactly like failures** — a pytest *error* (collection / import / fixture / setup failure) means tests never ran, which is a worse outcome than an assertion failure, not a passable one. Never read `failed` alone: a run with `failed == 0` but `error > 0` is RED, not green.
   - Gate GREEN → proceed to 3g (mark complete)
   - Gate RED (any `failed` or `error`) → proceed to 3e (attribute & fix)
   - If a re-run's `index.json` is missing or unparseable → the run did not complete cleanly; treat as a **test infrastructure failure** (see Error Recovery), do not infer a pass from stdout. (An *agent* run with a bad `index.json` is not an infrastructure failure — it simply fails step 2 acceptance and lands in the step-3 re-run batch.)

#### 3e. Attribute Failures and Fix Loop

Process **both** red outcomes from `counts`: assertion **failures** (`counts.failed`) and **errors** (`counts.error`). They are attributed and fixed the same way, with one difference in how you locate them:
- A **failure** has a per-test node ID (`tests/...::test_x`) — fix the code under test.
- An **error** is reported at module/collection level with no per-test node ID (e.g. an `ImportError`, a fixture error, a syntax error that breaks collection). Read `full.log` for the ERRORS section, attribute by the **erroring module/file path**, and fix the import/fixture/syntax root cause. An error often hides many tests that never ran — resolving it can change the pass count substantially, so always re-run after fixing one.

**Delegation split for the fix loop.** Attribution (step 1) and the fix-scope decision are YOUR judgment — do them inline. Reading the failing test/code and applying the edit (steps 2–3) are delegated to a **fix subagent** — do NOT edit code inline on Opus. You verify (step 4) by running the targeted test yourself, or by delegating the run and reading its `index.json`.

For each failing test **and each erroring module** from the wave gate (always targeted inside a phase — there is no full-suite wave):

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

After the fix loop, re-run the gate once to verify no regressions: the package's **wave targeted set**, batched into one `test.ps1 {package} -Specific "…,…"` invocation. If a fix modified code **outside** the wave tasks' own files, do NOT escalate to a full suite (the phase boundary owns that) — instead **widen the targeted re-run** to include the specific test files covering the fix's added files (and, for a shared-layer file, the consumers' call-site tests), and record those files in `package_change_log{}` so the 3i sweep set picks up the package and its consumers at the boundary.

#### 3f. Handle Failures (Escalate → Adjudicate → only then Ask)

If the first fix attempt fails:

1. **Rung 1–2: invoke the Decision Escalation Protocol** — analyze the root cause in-context yourself (task spec, all fix attempts, exact failures), then dispatch a fix subagent with your concrete remediation plan. Attempt your directed fix once. If it succeeds, proceed normally.
2. **If your directed fix also fails → rung 3: FABLE adjudicates. Do NOT ask the user.** "Should the run continue or stop after this failure?" is an **engineering judgment about the plan**, not a user preference — it depends on what the task gated, whether its dependents are genuinely blocked, and whether the root cause poisons later phases. That is precisely a rung-3 call.

   Spawn a **Fable** adjudicator (`decision-adjudication-protocol.md` §5, **Door B**, kind: `AMBIGUOUS FIX SCOPE`) with: the task and its design acceptance property, every fix attempt and its verbatim failure, your root-cause analysis, the tasks that depend on this one, and the options you see (continue-and-skip-dependents / re-scope the task / fix at another layer / file a follow-up / halt). Execute its decision (§6):
   - **A/B** → dispatch an implementer with Fable's steps; the task is still in flight.
   - **C** → amend the task file and re-dispatch.
   - **D** → resequence and run the prerequisite first.
   - **E** → file a real tracked follow-up task; add this task to `failed_tasks`, compute transitive dependents into `skipped_tasks`, and continue the run.
   - **F** → **only now** `AskUserQuestion`, with Fable's exact question, options, and recommendation.

**Never present a bare "Continue or Stop?" menu.** That menu asks the user to make an engineering call on evidence they have not seen — and it was a standing invitation to launder a hard decision into a user prompt. If the honest answer is "this failure means the run must stop," Fable will say so (`F`, or `E` with the run halted), and you will bring the user a *decision with its reasoning*, not a fork in the road.

#### 3g. Mark Tasks Complete — only after the design-acceptance + BLOCKED-terminal checks pass

Apply the shared 5-condition checklist `d:\datrix\.claude\skills\_shared\completion-eligibility.md` — tests green / not-BLOCKED-terminal / How-Solved clean / design-acceptance proven / discovered defects dispositioned. Orchestrator bindings:
- Condition 1's governing gate is the **wave test gate (3d)** for the task's package.
- Condition 4 uses the `design_acceptance_property` recorded in Step 1d, applied **evidence-first**: verify the agent's pasted check (commands are real, outputs consistent with the tree/artifacts you can read) and re-execute it yourself only when the evidence is missing, unparseable, or contradicted. The authoritative execution of every acceptance check happens exactly once per phase, at 3i Step A2 — do not run it a third time here when the agent's evidence verifies. An unprovable property routes to 3e/escalation as a conformance failure, not a pass.
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

Stricter than 3d: **every package in the sweep set must pass its FULL suite with zero failures and zero errors — pre-existing failures included** (3d's pre-existing allowance does NOT hold here; they are blocking and must be driven to zero before phase `P+1`). Runs every time a phase completes, even a fully green one — cross-wave integration and pre-existing rot only surface against the complete phase.

1. **Determine the sweep set.** Build it from `package_change_log{}` (which includes task agents' `files_created`/`files_modified`, every `scope_expansion`, and every fix-subagent edit from 3e/3f — not just the task files' declared lists):
   - **Changed packages:** every package with any recorded change in phase `P`.
   - **Shared-layer consumers (ALWAYS):** if any changed file lies in a shared layer (`datrix-common`, `datrix-codegen-common`, `datrix-language`, or any shared contract), add **every package that depends on it** per the dependency graph in `datrix/docs/architecture/architecture-overview.md`. This is the sweep 3d's shared-layer rule defers to — the boundary is where consumers are proven whole, so a consumer of a changed shared layer is in the sweep set *even though no task modified it*.
   - **Multi-phase runs — the all-packages guarantee:** at the **first** phase boundary of a multi-phase run, the sweep set is **ALL testable framework packages**, regardless of what phase 1 touched — this establishes the run's all-green baseline (pre-existing rot anywhere surfaces now, not under a later phase). At each **later** boundary, the guarantee is maintained incrementally: sweep = changed + consumers since each package's last GREEN full run (`package_green_state{}`); a package with **zero recorded changes** since its last green sweep carries its green status forward and is listed as `carried` in the checkpoint — green-at-last-sweep plus provably-unchanged-since IS "all tests passing" for that package. **Safety valve:** if `package_change_log{}` is tainted (any change that cannot be attributed to a recorded agent report), carry-forward is disabled — sweep ALL packages at this boundary.
   - **Single-phase runs:** changed + shared-layer consumers (no all-packages baseline requirement).
2. **Run the full suite for every package in the sweep set concurrently** — fire all `test.ps1 {package}` calls in a **single message** (one Bash call per package). Include `VERIFIED_AGAINST_QUICK_REFERENCE` in each Bash tool description.
3. **Read each package's `index.json`** (the canonical result, never stdout). A package is GREEN only when `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` — errors count as red, exactly as the 3d gate rules. Record each GREEN package into `package_green_state{}`.
4. **Fix every red package to GREEN — regardless of attribution.** For each failing test and each erroring module across ALL packages in the sweep set, **including failures in code that no task in this phase modified**:
   - **Delegate the fix, own the verdict.** Dispatch a **sonnet** (or **opus** for a subtle/cross-cutting root cause) fix subagent to read the failing test and the code under test, trace to the **root cause**, and fix it there. Unlike 3e this is NOT scope-restricted to a task's files — instruct the agent to fix whatever is red at its root. Bind it with NO workarounds, NO `xfail`/skip-to-pass, NO band-aids, NO conditional guards that hide the broken path, NO git reverts (CLAUDE.md). You do NOT read/edit the code inline on Opus — you decide what's in scope and verify the result.
   - Verify authoritatively: re-run the specific test (`test.ps1 {package} -Specific "{path}"`), then re-run the full package suite — reading `index.json`, not the agent's self-report.
   - If the first fix attempt fails or the root cause is unclear → **Decision Escalation Protocol** — analyze the root cause in-context yourself, then re-dispatch the fix subagent with your directed remediation plan. If your directed fix still fails, that test/module becomes a blocking item carried into Step C's halt-and-ask.
   - If a red test traces to a root cause **genuinely outside this repo's control** (e.g. a known-flaky external integration) → do NOT silently skip it; record it as a blocking item and surface it in Step C, letting the user decide. Do not invent this exception to dodge a real fix.
5. **Re-run until clean** — after fixes, repeat the full suite for the packages that were RED (their green peers' recorded results stand; nothing changed them). `test.ps1 -Rerun` selects exactly the projects whose latest run reported failures, or fire the red packages' `test.ps1 {package}` calls concurrently. Repeat until every sweep-set package is GREEN, or escalation/halt is reached. An error fixed in one module often unhides many tests that never ran, so always re-run the failing package's full suite after a fix rather than trusting `-Specific` alone. If a fix touched a package OUTSIDE the current red set (scope expansion into a green or unswept package), add that package to the sweep set and run its full suite too.

##### Step A2 — Phase-end DESIGN-CONFORMANCE gate (runs at EVERY phase end, including single-phase runs)

A green suite proves the code runs; it does NOT prove the design holds. This gate verifies phase `P` actually satisfied the `design_contract` built in Step 1d. **It runs at the end of every phase — including a single-phase run — and a phase cannot be declared complete without it, even when Step A is fully green.** This is the gate phase-01 lacked.

**A2 is the phase's single authoritative EXECUTION of the acceptance checks.** Implementation agents run them and paste evidence; 3g verifies that evidence; A2 is where the orchestrator itself executes each invariant's check, once, across the full surface set. Do not treat the earlier evidence as a reason to skip A2, and do not add executions elsewhere. Where a quality-gate agent ran this phase (3b), **read its static-checklist findings first** (stub scan, coverage sanity, How-Solved contradictions) and disposition every one — they are input to this gate, not a substitute for its executions.

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

**Green phase** — every sweep-set package passed Step A's full-suite gate (all red driven to zero; carried-forward packages count as green by the carry-forward rule) **AND Step A2's design-conformance gate passed (every design-named surface enforced, every task's acceptance property proven, no open conformance gap)** AND `failed` and `skipped` are both empty:
- Emit the Phase Checkpoint (below) — a one-line progress marker, **not** a report and **not** a conclusion.
- **Immediately spawn the first wave of phase `P+1` (3a/3b), in this same turn.** No pause, no `AskUserQuestion`, no "phase {P} is complete — shall I continue?", no summary of the phase's accomplishments. A green gate is the *authorization* to continue, and continuing is the only thing you may do with it (Multi-Phase Continuation, above).
- Only when phase `P` is the **last** phase in the run does a green gate lead to Step 4's final report instead of a next wave.

##### Step C — Red phase

Any `failed` or `skipped` task in phase `P`, **OR** any package still red after Step A's fix loop, **OR any unresolved design-conformance failure from Step A2** (an unenforced design-named surface, an unproven task acceptance property, or an open conformance gap):
   - **Do NOT start phase `P+1` yet.**
   - **First, produce the phase-recovery plan yourself (in-context, as the Opus orchestrator)** — invoke the **Decision Escalation Protocol** (phase-recovery variant) scoped to the whole phase. You already hold: every failed/skipped task in phase `P`, **every still-red test/module from Step A** (including pre-existing failures that resisted the fix loop), the exact test failures/errors, all prior fix attempts (wave-level 3e/3f **and** Step A), and the relevant code excerpts. Analyze them and produce a **phase-recovery plan** — root cause(s) across the failed items (name shared causes explicitly) and concrete, per-item remediation steps, in a sensible order. This is exactly the judgment you are on Opus for; do it inline rather than spawning another Opus agent to decide.
   - **Dispatch subagents to implement your recovery plan** (**sonnet**, or **opus** for the hardest items), partitioned so no two agents write the same files: give each the per-item remediation steps, exact files to modify, and the CLAUDE.md constraints. Then re-run the **full test suite for every affected package** yourself (3d gate rules — GREEN only when `result == "PASSED"` AND `failed == 0` AND `error == 0`). Re-attribute and mark any now-passing tasks complete via `complete.ps1`.
   - **Re-evaluate the phase:**
     - If phase `P` is now green → emit the Phase Checkpoint, proceed to phase `P+1`.
     - If phase `P` is **still red** after implementing your own recovery plan → **rung 3: FABLE adjudicates the phase.** Do NOT `AskUserQuestion` here. "Halt the run, or advance a phase carrying known failures?" is an engineering judgment about whether the red state poisons phase `P+1` — exactly a rung-3 call, and one the user cannot make without the evidence you hold.

   **Fable adjudication on unresolved phase failure** (`decision-adjudication-protocol.md` §5, **Door B**, kind: `RED GATE RECOVERY`). Hand it:
   - Every failed/skipped task in phase `P`, with its design acceptance property.
   - Every still-red test/module (including pre-existing, unattributed), with **verbatim** error text.
   - Every fix attempt — wave-level (3e/3f) and Step A — and why each failed.
   - Your own root-cause analysis, and whether the red state is load-bearing for phase `P+1` (does anything in `P+1` depend on the broken surface?).
   - The options and their costs: halt · advance-carrying-failures · fix at another layer · re-scope the phase · file follow-ups.

   Execute its decision (§6):
   - **A/B/C/D** → apply the fix/amendment/resequencing, re-run the phase gate, and continue the run.
   - **E** → file the real tracked follow-up task(s), carry phase `P`'s `failed`/`skipped` forward into run-wide state, and start phase `P+1` (3a's skip logic prunes downstream dependents).
   - **F** → **only now** `AskUserQuestion`, with Fable's exact question, options, and recommendation, plus the evidence above.

   **Never present a bare "Stop or Proceed anyway?" menu.** It hands the user a fork without the evidence to choose, and it is how a hard call gets laundered into a user prompt. Bring them a *decision with its reasoning*, and only when Fable says the call is genuinely theirs.

**Phase Checkpoint format** (emit at every phase boundary, green or after recovery):
```
Phase {P} COMPLETE — {completed}/{phase_total} tasks | tests: {package}: {passed}/{total} | {package}: {passed}/{total} | carried green: {package, package | none}
→ Starting phase {P+1}
```

(`carried green` names the packages whose all-green status was carried forward without a re-sweep — green at their last full run with zero recorded changes since. Multi-phase runs only; omit for single-phase runs.)

The `→ Starting phase {P+1}` line is a **commitment, not a plan announcement**: the very next thing you do after emitting it is dispatch phase `P+1`'s first wave. Emitting it and then ending the turn is the failure this gate exists to prevent. Omit that line only when `P` is the last phase in the run (then Step 4 follows).

Track phases as their own TodoWrite group so the user can see phase-level progress distinct from wave-level progress. Keep the next phase's todos visibly pending at every boundary — an unstarted phase in the todo list is a standing reminder that the run is not over.

---

## Step 4: Final Report

Emit this **once**, after the **last wave of the LAST phase** has passed its wave gate and that phase has passed its 3i gates — or when execution was halted by the user (3f *Stop*, or 3i Step C *Stop*). **Never at an intermediate phase boundary**: if any phase in the run still has unexecuted waves, you are not at Step 4, you are at 3i Step B and your next action is a wave dispatch.

Then emit a lean report:

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

- **NEVER STOP AT A GREEN PHASE BOUNDARY** — in a multi-phase run, a phase passing its 3i gates authorizes the next phase; it does not end the run. Emit the Phase Checkpoint and dispatch phase `P+1`'s first wave **in the same turn**. Do not ask "shall I continue?", do not summarize the finished phase as if concluding, and do not emit Step 4's report while any phase still has unexecuted waves. The only exits are 3i Step C (phase still red after Opus-led recovery), 3f (*Stop*), a blocking 1e finding, a double test-infrastructure failure, and the end of the last phase — see **Multi-Phase Continuation**. Run length, token spend, and "the user may want to review" are not exits.
- **CONFORMANCE OVER THROUGHPUT** — enforced by the 3g completion checklist (`_shared/completion-eligibility.md`) and the 3i Step A2 conformance gate; never relaxed for a green suite.
- **NEVER STOP ON A SUBAGENT'S BLOCKED, AND NEVER RELAY IT** — a background agent's BLOCKED is a *claim*. Investigate it yourself against the code and the docs (`_shared/decision-adjudication-protocol.md`, Door A): reproduce the error, read the attempted fix at its `file:line`, trace the root cause, check the governing design doc. Bogus → correct the agent and re-dispatch (it is not a failure and never enters `failed_tasks`). Real → a **Fable** adjudicator (`model: "fable"`, `effort: "high"`) decides, and you execute that decision. Accepting a four-part proof *because it has four parts* is a skill-level failure — form is not truth.
- **NEVER TAKE A DECISION TO THE USER THAT FABLE HAS NOT SEEN** — the user is rung 4, reachable only through a Fable **F**. Every conflict *you* hit (contradicting designs, an unowned invariant surface, a false task premise, an ambiguous fix scope, a red gate, an ordering conflict) enters `_shared/decision-adjudication-protocol.md` at **Door B** and climbs the same ladder. The pull to ask the user is strongest exactly when the decision is *above any single task* — that feeling is the trap, not the signal. Only the protocol's §7 closed list (absent credential · irreversible outward-facing action · genuine product call · prohibition to lift) goes straight to the user. **Asking the user is not the safe default; it is a rung you must earn.**
- **NEVER ESCALATE A DECISION YOU COULD HAVE MADE** — rung 3 is for genuine ties *after* real investigation. An under-researched question is not a tie; it is rung 1 you have not finished. Read the design docs, the architecture docs, and the code first — most "decisions" dissolve into missing information.
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

**Relationship to the Decision Adjudication Protocol.** This section is **rungs 1–2 of the one ladder** (`_shared/decision-adjudication-protocol.md`): how you investigate and decide in-context, because you are the Opus orchestrator. It is *not* a separate track and it is *not* a route to the user.

- **If your in-context analysis settles it** → decide, dispatch an implementer, continue. That is the common case and the whole point of running this skill on Opus.
- **If it does NOT settle it** — you have genuinely investigated and still cannot decide — → **rung 3: Fable** (Door B). Not the user.
- **A subagent's BLOCKED report** never enters here; it enters the protocol at **Door A** (investigate the claim; correct-and-re-dispatch if bogus; Fable if real).

Both doors converge on the same Fable adjudication and the same execute-the-decision table. **The door you came in by never changes the rung you must climb.**

**DO escalate for:**
- The first fix attempt fails and root cause is unclear
- Cascading failures suggest a systemic problem where the correct fix scope is uncertain
- A task's implementation conflicts with existing architecture in a way that requires architectural judgment

**Do NOT escalate for:**
- Incomplete prerequisite dependencies → **not a stop.** Implement the dependency, or resequence the wave so the prerequisite runs first. (An agent that calls this a blocker gets corrected and re-dispatched.)
- Simple syntax/import errors with obvious fixes → fix directly
- Clear spec violations → fix directly
- Missing user-supplied information → derive it from the design docs and the code first. If you cannot, it is a **rung-3 decision → Fable**, *not* an automatic user question. Only the protocol's §7 closed list reaches the user directly (a credential/account absent from the repo · an irreversible outward-facing action needing authorization · a genuine product/business call · a prohibition to be lifted) — and then always with your recommendation.

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
- If your analysis concludes the run should stop and ask the user, **that conclusion is not self-executing** — it goes to **Fable** (rung 3) with your full root-cause analysis in the packet. You do not have the authority to route yourself to the user; only a Fable **F** does that. If Fable returns A–E, execute it and the run continues.

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
  - Handle each failure per 3f (escalate → adjudicate; only a Fable **F** reaches the user)
  - Next wave processes only tasks whose dependencies are all in `completed_tasks`

