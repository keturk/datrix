---
description: Fully automated multi-wave task orchestrator with dependency analysis and test gating
model: opus
effort: xhigh
---

# Task Orchestrator

Fully automated multi-wave task orchestrator. Accepts a set of tasks (individual files, multiple files, or an entire phase directory), analyzes dependencies, topologically sorts tasks into execution waves, and executes each wave with parallel agents. Runs test suites automatically between waves. No human intervention except on task failure after exhausting fix attempts.

## Your Role — Opus Orchestrator: Judgment, Not Typing

You run on Opus 4.8 at extra-high effort because this skill performs the **highest-stakes judgment in the repo** — the design-conformance gate, the BLOCKED-is-terminal calls, the wave/enforcement ordering, and the completion decisions that a lower-scrutiny orchestrator has gotten wrong before. That capability is for deciding, not for doing. You are the orchestrator and decision-maker; **execution goes to subagents on cheaper models.**

- **You (Opus) own — never delegated:** the dependency DAG and wave plan, the design-conformance contract (Step 1d), the **readiness-audit adjudication** (Step 1e — which findings are real, what task closes each gap, how dependencies rewire) and the conformance gates (3g, 3i Step A2), BLOCKED/completion decisions, failure attribution and fix-scope decisions, escalation judgment, integration across tasks, and the pass/fail verdict on every gate.
- **You delegate DOWN — always:** implementing tasks (already delegated, 3b), gathering the readiness audit's evidence and writing the task files it adds (1e), building the shared-context digest, running test suites and conformance checks, **and implementing fixes in the fix loops (3e / 3i Step A) — do NOT edit code inline on Opus.** You decide the fix (root cause, scope, exact change); a subagent types it.

Two resources are scarce and both are yours to protect: **Opus tokens** (never spend them on typing a fix a Sonnet agent can apply from your spec) and **your context window** (it must survive a whole multi-phase run — delegate the token-heavy reading/editing so your context holds the conformance state, not file contents).

**But "delegate DOWN — always" is not "delegate everything, at any size."** A subagent is a purchase drawn from a shared, exhaustible budget — see execution-contract §10, which binds here. A dispatch costs 100k–800k tokens; a small edit you have already diagnosed costs a few tool calls. So:

- **A fix you have already root-caused to `file:line`, and that is small and contained, you make yourself.** The "do NOT edit code inline on Opus" rule exists to protect your *context* from token-heavy reading, not to forbid a three-line edit whose diagnosis you already hold. Dispatching a 400k agent to type a change you can make in two calls is the rule defeating its own purpose.
- **Size every dispatch to what is actually unknown.** Each extra acceptance criterion you write is budget the agent spends.
- **Verify the shared set centrally, once, after the wave** — never by putting a "also regenerate/re-run these others" list into every agent's acceptance criteria. That duplicates one check by the number of agents.
- **Read the token usage on every completion and react.** An agent returning no usable report after a large spend means you mis-sized it: shrink the next dispatch, never re-issue the same shape at the same size. Two such returns means your sizing model is wrong.
- **Cap wave width to genuinely independent work.** Parallel agents buy wall-clock, which is rarely the binding constraint; seven where two would do costs 3.5× for a marginally earlier result.

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
- **Optimization pass before any execution** (Step 1f) — having established the set is *sufficient*, makes it *efficient*: retires already-satisfied tasks, merges duplicated scope, drops dependency edges that serialize nothing, splits over-broad tasks, and repairs defective targeted-test lists — then executes the result with co-dispatch batching (3b). Never at the cost of a design invariant
- Dependency-aware grouping (builds a DAG, topologically sorts into waves)
- Automatic wave advancement (no human intervention between waves)
- Handles tasks with cross-dependencies (separates into waves instead of blocking)
- **Sequential multi-phase execution, with no stop in between** — given several phases (e.g. `72, 73, 74`), finishes each phase fully and then **immediately starts the next, unprompted**. At every phase boundary a gate (Step 3i) runs the full test suite for its **sweep set** (the phase's changed packages + their reverse-dependency closure per `d:\datrix\.claude\skills\_shared\verification-strategy.md`; boundaries maintain the run's affected-green guarantee incrementally — the sweep is ALL packages only when the closure is everything, e.g. a `datrix-common` change, or the change log is tainted) and fixes **all** failures — including pre-existing ones unrelated to the phase's changes — with Opus-led recovery. Green gate → next phase's first wave dispatches in the same turn; the run ends only at the last phase (or a Step C halt). See **Multi-Phase Continuation**

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
2. Run the phase-status script (see 1b) — it handles dependencies.md (JSON and legacy) and the task-file glob fallback itself

### 1b. Read Task Metadata (scripted)

**IMPORTANT:** The orchestrator automatically discovers tasks when a PHASE is provided. The user does NOT need to provide a list of task files.

**One script call replaces all manual discovery and metadata extraction** (read `datrix/scripts/tasks/quick-reference.md` before invoking; a pre-tool hook enforces this):

```bash
powershell -File "d:/datrix/datrix/scripts/tasks/phase-status.ps1" {NN}
```

Read the resulting `D:\datrix\.tmp\tasks\phase-{NN}-status.json`. Per task it carries everything 1b used to extract by hand — `task_id`, `task_path`, `title`, `status`/`is_completed`, `package`, `category`, `depends_on` (normalized task IDs), `design_reference`, `design_acceptance_property` (full text), `files_to_review`, `files_to_create_modify`, `targeted_tests`, `languages`, `has_how_solved`, `how_solved_redflags` — plus phase-level `dependencies_md` (json/legacy/absent), `provenance` (drives 1e's light/full mode), `dep_mismatches`, and `missing_dependency_files`. It discovers tasks across ALL repos' `.tasks\phase-{NN}\` folders and merges `dependencies.md` when present (schema reference: `d:\datrix\datrix\claude-config\.claude\agent-templates\dependencies-format.md`).

1. **Skip completed tasks** — `is_completed == true` tasks are excluded from execution but stay in the graph (dependencies of other tasks may reference them)
2. **Task bodies are still read where the work happens** — an implementation agent reads its own full task file at dispatch; the orchestrator itself works from the JSON and reads a task file directly only when adjudicating something the metadata cannot settle
3. **Re-run the script after ANY task-file amendment** (1e authored/amended tasks, completion marks) — the JSON is a snapshot of disk truth, not a cache

### 1c. Validate (scripted)

Run the wave planner — its `blocking_issues` list is the validation verdict:

```bash
powershell -File "d:/datrix/datrix/scripts/tasks/plan-waves.ps1" {NN}
```

- `MISSING_DEP_FILE` in blocking_issues (a referenced dependency task file does not exist on disk) → STOP, report missing file
- `MIXED_LANGUAGE_TASK` (a task's files span more than one implementation language) → STOP, report scope error
- Any reported `cycle` → STOP (see 2b)
- If zero non-completed tasks remain (`phase-{NN}-status.json` shows 0 pending) → report "All tasks already completed" and exit

### 1d. Build the Design-Conformance Contract (the orchestrator's source of truth for "done")

The orchestrator gates on the design, so it must hold the design in hand — not just the task list. Before execution:

1. **Collect the design reference(s).** Read the `**Design reference:**` of every task. Resolve the distinct design-doc path(s) the phase implements.
2. **Read the design doc(s)** and extract, per phase, the **design contract**: the list of invariants / numbered decisions (D#/G#) the phase must satisfy, and for each invariant **the full SET of surfaces it ranges over** (e.g. "fail-loud applies to integration AND CDN AND auth AND datasource positions"). This surface set is what catches a half-implemented invariant — a phase that guards one surface and silently drops the rest.
3. **Per task, record its `design_acceptance_property`** — the observable end-state + the executable check (negative + positive) that proves it. If a non-trivial implementation/migration task has NO design acceptance property (blank or "tests pass"), flag it: it is under-specified and its completion cannot be verified. Note it for the gate; do not silently let it pass on suite-green alone.
4. **Map invariant → tasks.** For every invariant surface in the contract, identify which task covers it. If a surface in the design's set has NO task covering it → record a **conformance gap** now (a design-named surface with no implementer). Feed it into the Readiness Audit (Step 1e), which closes it by authoring the missing task **before** execution. (3i Step A2 remains the backstop for gaps that only surface later — but a gap visible up front must never be deferred to the phase boundary.)

`design_contract` (invariants + surface sets) and per-task `design_acceptance_property` are checked by 1e (readiness), 3g (completion) and 3i Step B (phase conformance). Without this contract, the orchestrator can only check "did it run" — which is exactly how a half-enforced invariant has shipped clean before.

### 1e. Readiness Audit — is this task set sufficient to satisfy the design against the CURRENT code?

**Run this before ANY execution.** The task set was authored against the design and the codebase **as they were when `/generate-tasks` ran**; both may have moved since, and the generator may have missed a surface. Executing an insufficient task set produces the same failure mode every time — every task COMPLETED, the suite green, and the design still unenforced. The audit answers one question: *if every task in this set succeeds exactly as written, will the `design_contract` from 1d hold over the code that is actually on disk today?* If the answer is anything but yes, the audit **adds the missing tasks and rewires dependencies** before Step 2 builds the DAG.

The audit is **read-only with respect to source code** — it authors task files and updates `dependencies.md`, and touches nothing else. It **never modifies the design doc** (CLAUDE.md: design docs are scope boundaries). The run's single permitted design-doc write is Step 4's `Status:`-line update, at the very end, after every task implementing that doc is COMPLETE — never here, and never mid-run.

##### Audit dimensions (each finding needs evidence — a file:line you read or a command + its output)

1. **Coverage gap** — a design invariant/surface from the 1d contract with no task implementing it. Includes the case where a task covers *part* of an invariant's surface set (the guard on the easy surface, the rest silently dropped).
2. **Enforcement ordering gap** — a validator / fail-loud guard / parser rejection exists as a task but is NOT a `Depends on` of every task that migrates or relies on content it governs (CLAUDE.md "Enforcement before what it governs"). Also the case where the *guard itself is missing* while its migration task exists.
3. **Stale premise** — the task assumes code state that is no longer true: a file/class/function/constant it says to modify does not exist, has been renamed, or already carries the change. Verify each task's `## Files to Review Before Starting`, `## Files to Create` and the specific symbols it names against the code on disk.
4. **Already-satisfied** — the current implementation already provides the task's design acceptance property. Prove it with the acceptance check (negative + positive); a task that merely *looks* done is not.
5. **Under-specified task** — a non-trivial task with a blank / vacuous `**Design acceptance property:**` ("tests pass", "it generates"). Its completion cannot be verified, so 3g can never pass it honestly.
6. **Missing dependency edge** — task B modifies or imports a file/symbol task A creates, but B does not `Depends on` A; or two tasks in the same prospective wave write the same file with no ordering.
7. **Unresolvable premise (BLOCKING)** — the design contradicts the code in a way no task can reconcile (the design names an API/symbol/behavior that does not and cannot exist as described). This is not an audit fix; it is a STOP.

##### Audit scope — the phase you are about to execute, and no further (binding)

**Audit exactly one phase: the one whose first wave you are about to dispatch.** In a multi-phase run, phase `P+1`'s audit — and the optimization pass (1f) that follows it — run at the phase boundary (3i), immediately before its first wave, never up front alongside phase `P`'s.

This is not a cost concession, it is the more accurate ordering: the audit's whole question is *does this task set hold against the code on disk today*, and phase `P` is about to change that code. An audit of phase `P+1` performed before phase `P` runs is answering the question against a codebase that will not exist by the time those tasks execute.

**The audit is the run's largest pre-execution cost and it sits on the critical path — bound it.** An unattended run that spends its whole window auditing and dispatches zero implementation agents has failed completely, and no amount of audit quality redeems that. Hard limits:

- **One dispatch round.** Fan out the audit agents once, in parallel, and adjudicate what comes back. A second round is licensed only by a finding that *changes which surfaces need auditing* — never by "let me be thorough."
- **Cap the fan-out at 6 agents** (light mode: 1–2). More packages than that → give one agent several packages, not one agent each.
- **Sonnet, never Opus, for evidence gathering.** The verdicts are yours; the reading is not.
- **If the audit is still running when its round returns nothing actionable, it is over.** Emit the report and plan waves.

The audit is a gate on *correctness of the task set*, not a research project. Its output is a short list of gaps and edges — if you have spent more tokens auditing than you expect the phase's implementation to cost, you have already overrun.

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
   - Location: the **owning package's** `.tasks\phase-{NN}\` directory (the package whose surface the invariant lives on — apply the generality-preserving rule: the most language/platform-agnostic layer that can own it). **`{NN}` is the phase you are running — never a new one.** You may not create a `.tasks\phase-NN\` directory that does not already exist; creating a phase is a planning act reserved to Jon and the planning skills he invokes by name (`/generate-tasks`, `/operationalize-design`). A task you add here joins this phase's completion bar and must be finished before the phase is declared done.
   - ID: the next free `{TT}` for that phase — get it from `powershell -File "d:/datrix/datrix/scripts/tasks/validate-dependencies.ps1" -Phase {NN} -NextTaskNumber` (prints only the number, scanning every repo's `.tasks\phase-{NN}\`). Never reuse or renumber an existing ID.
   - Content: the full task template from `/generate-tasks` (`d:\datrix\.claude\skills\generate-tasks\SKILL.md`, "File Structure") — including a real `**Design reference:**` (the D#/G# it closes), a **provable** `**Design acceptance property:**` with its negative + positive check, `## Files to Review Before Starting`, `## Files to Create`, `## Targeted Tests`, and its own `## Tests` section. A task the audit adds must be as complete as one `/generate-tasks` emits; a stub task is a workaround.
   - Delegate the *writing* to a **sonnet** agent from your spec (you decide the scope, acceptance property, package, and dependencies; the agent types the file), then read the result and verify it carries a provable acceptance property.
   - For an **under-specified** existing task, do not add a new task — amend that task file's `**Design acceptance property:**` and its Success Criteria to carry the provable check. (Amending a *task* is allowed; amending the *design* is not.)
4. **Rewire dependencies — task files AND `dependencies.md` must stay in lockstep.**
   - Edit the `**Depends on:**` field of every affected task file: new tasks' own prerequisites, plus edges **into** the new tasks from every task they must precede (a newly-added guard becomes a `Depends on` of every migration it governs).
   - Update `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` to match — per the JSON schema in `d:\datrix\datrix\claude-config\.claude\agent-templates\dependencies-format.md`: append a `tasks[]` entry for each new task (`task_id`, `task_path`, `title`, `is_completed: false`, `package`, `dependencies`, `category`) and update the `dependencies` array of every existing task that gained an edge. If the file is in the legacy "Group N" text format, **rewrite it as JSON** (the preferred format) rather than patching groups. If it does not exist, create it — the amended set is now the phase's source of truth and the next run must see it.
   - Re-validate the amended graph with the scripts: `phase-status.ps1 {NN}` (fresh snapshot; `dep_mismatches` must be empty), `validate-dependencies.ps1 -Phase {NN}` (must PASS — it checks dependencies.md completeness, dep resolution, acyclicity, file-vs-JSON agreement, and cross-repo numbering), and `plan-waves.ps1 {NN}` (no `cycle`, no `blocking_issues`). A cycle introduced by the audit's own edges is a bug in your rewiring — fix it, do not ship it.
5. **Re-verify the contract.** With the amended set, re-run 1d step 4: every invariant surface in the `design_contract` must now map to at least one task. If a surface still has no owner, you have not finished the audit.

##### Outcomes

- **Ready (no gaps)** → say so in one line and proceed to Step 2.
- **Ready after amendment** → emit the Audit Report (below) and proceed to Step 2 with the amended task set. **Do not ask the user for permission to proceed** — closing a gap the design already mandates is in scope; the audit is reported, not negotiated.
- **BLOCKING (dimension 7, or a design/code contradiction you cannot reconcile)** → **this is a rung-3 decision: it goes to FABLE, not to the user.** Do not `AskUserQuestion` here. Spawn a **Fable** adjudicator (`decision-adjudication-protocol.md` §5, **Door B**) with your evidence packet: what each design requires (quoted verbatim from the primary sources), what the code actually does (`file:line`), why no task can bridge them, the options you see and what each costs, and your leaning. Execute its decision (§6) — **A** no-conflict / **B** fix-elsewhere / **C** amend-task / **D** resequence / **E** spawn-follow-up / **F** ask-user. Only **F** reaches the user, and then you ask with Fable's exact question and recommendation. Never paper over the contradiction with a task that pretends the premise holds, and never hand the raw contradiction to the user as if the choice were theirs to make.

  **This is the exact hole that has let a contradiction between two design docs reach the user unadjudicated before.** A cross-design conflict *feels* like the user's call precisely because it is above any single task — that feeling is the trap. It is a design-level engineering judgment, and it gets the strongest model.

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

### 1f. Optimization Pass — same design, reached for less

**1e asks "is this task set sufficient?" 1f asks "is this task set efficient?"** They are different questions and both run before any agent is dispatched. A task set is a *plan*, and `/generate-tasks` authored it without knowing what the graph would look like once it was scheduled — so it routinely carries work that is duplicated across two tasks, edges that serialize tasks nothing actually orders, and tasks whose `## Targeted Tests` name a suite the harness will refuse to run. Executing that as-written costs agents, waves, and wall-clock for no added conformance.

**Run 1f immediately after 1e, over the amended set, before Step 2 plans waves.** In a multi-phase run it runs per phase, paired with that phase's audit — up front for the first phase, at the phase boundary (3i) for each later one, for the same reason 1e is scoped that way: phase `P` is about to change the code phase `P+1`'s plan is optimized against.

##### Cost bound (binding — this pass must not become the thing it optimizes)

**1f spends no new subagents and reads no new source code.** Everything it needs is already in hand: `phase-{NN}-status.json` (1b), the baseline `phase-{NN}-waves.json` (1c), the design contract (1d), and 1e's adjudicated findings. It is a judgment pass over metadata you already hold, and its edits are field-level — per the delegation economy you make them yourself rather than buying a 400k dispatch to type a `**Depends on:**` line. The one exception is authoring a *new* task file for a split (O4), which follows 1e's authoring mechanism (you spec it, a sonnet agent types it).

**Bias to no-op.** A set from a recent `/generate-tasks` is usually already close to optimal; 1f's normal output is a single line. Hunting marginal merges on Opus tokens is the same overrun that once burned an entire overnight window on a readiness audit — five tasks run as authored are cheaper than an hour spent proving four would do. If a transform's saving is not obvious from the JSON in front of you, it is not there.

##### The six transforms — the list is closed

Anything not on this list is not an optimization you may apply.

1. **O1 Retire an already-satisfied task.** 1e dimension 4 *finds* these; 1f is where one leaves the graph. Requires its acceptance check (negative + positive) run and its output pasted. Never on "it looks done."
2. **O2 Drop a spurious dependency edge.** `B depends on A` where B neither reads, imports, nor modifies anything A creates, and the two write no common file. Dropping it widens the wave and shortens the critical path — usually the single largest saving available. **Never drop:** an enforcement edge (a guard, validator, or fail-loud check before what it governs — CLAUDE.md, and 1e dimension 2 exists to *add* these); a shared-file write-ordering edge; or any edge you cannot positively prove is spurious. **The costs are asymmetric and that decides ties:** a wrongly-kept edge costs one wave of wall-clock, a wrongly-dropped one costs a race, a clobbered file, or a migration running ahead of its guard. **Default is keep.**
3. **O3 Merge duplicate scope.** Two tasks whose `files_to_create_modify` and acceptance properties describe the same work. Fold into a survivor. **Never merge across packages, across implementation languages, or across a guard/migration boundary** — a merged guard+migration is a task that polices itself.
4. **O4 Split an over-broad task.** Only when the halves are genuinely independent (disjoint files, no shared symbol) **and** the split actually shortens the critical path — a split that just widens an already-wide wave buys nothing and costs a dispatch. A `MIXED_LANGUAGE_TASK` from 1c is a **mandatory** split, not an optional one.
5. **O5 Repair a defective `## Targeted Tests`.** A task naming a bare full suite (`test.ps1 <pkg>`, `-All`, a tier sweep) is a defective task file per CLAUDE.md, and `guard-full-suite-runs.py` blocks its agent unconditionally — so leaving it is not just wasteful, it is a dispatch that will fail. Replace it with the specific test files covering the code that task changes.
6. **O6 Fix the model tier now, while you hold the whole set.** Record the intended 3b tier (haiku / sonnet / opus) per task here. One judgment pass across the set is both cheaper and more consistent than N ad-hoc calls made under dispatch pressure.

##### Merge and retire bookkeeping — the completion bar does not move

**Never delete a task file.** `validate-dependencies.ps1` requires task numbers unique and sequential across repos and `dependencies.md` to cover every discovered file; a deleted file breaks both. An absorbed (O3) or retired (O1) task stays on disk and stays on the phase's completion bar:

- Add `**Superseded by:** task-{NN}-{TT}` to its body, and move every inbound edge to the survivor.
- **An absorbed task is marked COMPLETED at the same 3g gate as its survivor — never at 1f** — with a `## How Solved` carrying the survivor's acceptance evidence verbatim. Completing it at optimization time is a false completion (the work does not exist yet); leaving it unresolved wedges the Stop gate, which counts any task that is neither COMPLETED nor carrying a B1–B4 proof.
- A retired already-satisfied task (O1) *may* be completed here, and only here, because its `## How Solved` is the acceptance check output you just pasted — that is real proof of work, not a status you picked.

##### Four invariants 1f may never break (verify all four before Step 2)

1. **Every invariant surface in the 1d `design_contract` still maps to at least one task** — re-run 1d step 4 over the optimized set. An optimization that orphans a surface has traded away the thing the run exists to prove.
2. **`validate-dependencies.ps1 -Phase {NN}` PASSES** — task files' `**Depends on:**` and `dependencies.md` stay in lockstep exactly as in 1e step 4. Every merge, retire, split, and dropped edge is written to BOTH.
3. **`plan-waves.ps1 {NN}` returns no `cycle` and no `blocking_issues`** — a graph broken by your own rewiring is a bug to fix, not to ship.
4. **No task's `design_acceptance_property` was weakened.** 1f changes *how* the design is reached; it never changes *what* is proven. If a transform would trade conformance for speed it is not an optimization — drop it. **Conformance over throughput binds here exactly as it does at the gates.**

##### Optimization Report (emit after the Audit Report, before the execution plan)

```
OPTIMIZATION — phase {NN}: {N} → {M} tasks, {W_before} → {W_after} waves
Merged:   task-{NN}-{TT} ← task-{NN}-{TT}  ({the scope they shared})
Split:    task-{NN}-{TT} → task-{NN}-{TT} + task-{NN}-{TT}  ({why, and what it shortens})
Retired:  task-{NN}-{TT} — already satisfied ({acceptance check + its output})
Unedged:  task-{NN}-{TT} ⊥ task-{NN}-{TT}  ({why the edge was not real})
Tests:    task-{NN}-{TT} — bare full suite → {specific files}
```

Omit any line with nothing to report. If nothing cleared the bar: `OPTIMIZATION — phase {NN}: {N} tasks, {W} waves; no changes.` — and that is a good outcome, not a failure to find something.

---

## Step 2: Build Dependency DAG and Plan Waves (scripted)

### 2a–2e. Compute the plan with the wave planner

The entire DAG/cycle/wave/conflict/ordering computation is one script call over the **amended and optimized** task set (the tasks added and edges rewired by 1e, and merged/split/re-edged by 1f, are ordinary members of the graph — re-run the script after any amendment; the plan you execute is computed from the post-1f set, never the baseline):

```bash
powershell -File "d:/datrix/datrix/scripts/tasks/plan-waves.ps1" {NN}
```

Read `D:\datrix\.tmp\tasks\phase-{NN}-waves.json`. What it computes (and you therefore do NOT re-derive by hand):

- **DAG semantics (2a):** completed dependencies count as satisfied (no edge); a dependency that is not completed and not in the set is a `blocking_issues` entry → STOP, report "Task {id} depends on {dep_id} which is not completed and not in the provided task set".
- **Cycle detection (2b):** a non-null `cycle` names the actual cycle path → STOP immediately, report `"Dependency cycle detected: {task_a} → {task_b} → ... → {task_a}"`, exit.
- **Kahn topological waves (2c):** `waves[]` lists task IDs per wave; `wave_details[]` adds packages per wave.
- **File-conflict splitting (2d):** waves whose tasks share a file in files-to-create/modify are already split into sequential conflict-free sub-waves; `file_conflicts[]` records what was split and why.
- **Quality Gate & Verification ordering (2e):** `Quality Gate` tasks are held to the last wave(s) before anything that depends on them (e.g. an Acceptance task); `Verification`/`Acceptance` tasks follow their dependencies.

**Multi-phase runs (phase ordering is a hard constraint):** run `plan-waves.ps1` once per phase, in numeric order, and concatenate the wave lists — ALL of an earlier phase's waves complete before ANY later phase's first wave. Each phase boundary is also a **Phase Boundary Gate** (Step 3i): the earlier phase must pass an explicit completion check — every package in the gate's sweep set (changed packages + their reverse-dependency closure per `_shared/verification-strategy.md`) must pass its **full** test suite with all failures fixed, including pre-existing ones unrelated to the phase, with Opus-led recovery on failure — before the next phase's first wave is spawned.

**Exit codes:** 0 = plan computed, no blockers; 1 = blockers or cycle present (read the JSON and apply the STOP rules above); 2 = usage error.

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

**Do not OFFER to wait, either.** The plan block ends at `Executing...` and the very next thing you do is spawn wave 1's agents — in the same turn, with no sentence in between that invites a reply. Every one of these is banned here and at every later boundary, however politely phrased: *"if you'd rather I stop at a specific wave, say so"* · *"shall I continue?"* · *"this will be expensive — confirm before I proceed"* · *"let me know if you want to review first"*. An offer to hold is functionally identical to holding: it ends the turn, and an unattended run then sits idle until morning with zero tasks executed. **This has happened — a 185-task run spent its entire overnight window on the readiness audit and ended on exactly such an offer.** The Stop gate (`.claude/hooks/gate-orchestration-stop.py`) now refuses that ending, but do not make it do your job.

Cost is not a reason to check in. The run's size was known when Jon invoked it with the phase list; reporting the bill back to him mid-run buys nothing and risks the whole window. If the run is genuinely larger than the task set implied, note it in **one clause** inside the plan block and keep dispatching.

---

## Multi-Phase Continuation (binding — read before Step 3)

When the run covers more than one phase, the wave loop of Step 3 runs over **every wave of every phase**, in the phase-sequential order computed in 2c. It terminates on exactly one condition: **there is no next wave in any remaining phase.** Nothing else ends it.

**Multi-phase runs carry an AFFECTED-PACKAGES-GREEN guarantee.** At every phase boundary of a multi-phase run, the orchestrator must be able to assert "every package in the run's cumulative affected set (changed packages + reverse-dependency closure, per `_shared/verification-strategy.md`) passes its full suite" — established at the first boundary and maintained incrementally at later boundaries (3i Step A's sweep-set rules). Packages outside the affected set are provably untouched by this run (nothing they depend on changed), so their health is owned by the scheduled full sweep, not bought again here. This guarantee is what lets phase `P+1` build on `P` without inheriting rot the run itself created. It never creates a stopping point: a red package found by the sweep is **fixed at the gate** (Step A's attribution-agnostic fix loop), and a green gate flows directly into the next phase's first wave in the same turn.

**At a green phase boundary you do not stop, do not summarize-and-yield, and do not ask.** Passing 3i's gates (Step A full-suite green on every touched package + Step A2 design-conformance) is the *permission* to continue, not a milestone to report and rest on. The Phase Checkpoint is a one-line progress marker emitted **on the way into** the next phase's first wave — in the same turn, with no intervening question to the user. If you catch yourself writing a summary of what phase `P` accomplished while phase `P+1` still has unexecuted waves, you have stopped early: dispatch the next wave instead.

**Illegitimate reasons to stop at a phase boundary — all of them:** the phase went green and it "feels like a good checkpoint"; the run is long / many tokens spent; the user "might want to review before continuing"; the next phase looks large; the context is filling up (delegate harder — see the Opus-orchestrator contract); you already emitted a checkpoint that reads like a conclusion. None of these appear in the exit list below, and none are B1–B4.

**The complete list of exits from a multi-phase run:**

| Exit | Trigger | Where |
|---|---|---|
| Halt-and-ask | Phase `P` still red after Opus-led recovery **AND** a **Fable** adjudication returned **F (ASK_USER)**. A red phase alone is NOT an exit — it is a rung-3 decision; Fable's A–E all keep the run moving. | 3i Step C |
| Task-failure prompt | A task failed after the directed-fix attempt, **Fable** adjudicated and returned **F**, and the user chose to stop | 3f |
| Blocking readiness finding | Design/code contradiction no task can reconcile, **which Fable adjudicated to F**. A contradiction alone is NOT an exit — Fable's A–E (amend, resequence, fix-elsewhere, follow-up) resolve it and the run continues | 1e, dimension 7 |
| Test-infrastructure failure | `test.ps1` itself errors twice | Error Recovery |
| **Run complete** | **The last wave of the LAST phase has passed its gates** | Steps 4–5 |

**Note what is NOT on this list:** a red phase, a failed task, a design contradiction, a coverage gap, an ordering conflict, or an unclear fix scope. **None of those is an exit** — every one is a rung-3 decision that goes to Fable, and only a Fable **F** can turn one into a stop. The run ends when the work is done or when Fable says a human must decide. Nothing else.

**Step 4's design-status update and Step 5's Final Report happen once, at the end of the LAST phase — never at an intermediate phase boundary.** An intermediate boundary emits the Phase Checkpoint only, and never touches a design doc.

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
- `audit_added_tasks[]` — tasks authored by the Readiness Audit (1e) to close a design gap; they execute like any other task and are reported separately in Step 5
- `optimizations[]` — the transforms 1f applied (merge / retire / split / dropped edge / repaired targeted tests), with the before→after wave counts; reported in Step 5
- `superseded_tasks{}` — map of `absorbed task_id → surviving task_id` from 1f O3. Each absorbed task is completed at its survivor's 3g gate, carrying the survivor's acceptance evidence — never before
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

**Co-dispatch — one agent, several small tasks (the execution half of 1f).** A dispatch costs 100k–800k tokens, most of it spent *before the first edit*: reading the shared context, the task file, and the surrounding code. Two small tasks on the same surface pay that startup twice for one body of reading. Batch several tasks into **one** agent when ALL hold:

- same package, and all in the **same wave**;
- each is individually small (the tier you fixed at 1f O6 is haiku or low-end sonnet);
- they share files or the same surface, so the second task is nearly free once the first is understood;
- combined, they still fit comfortably in one agent's context and 40 turns.

**One narrow extension:** you may pull in a task from the immediately-following conflict sub-wave when that sub-wave exists *only* because 2d split a file conflict with a task in this batch. One agent works them sequentially, so the conflict cannot race — this collapses a split the planner had to make conservatively.

Rules for a batched dispatch:
- Give the agent every task file path and require a **separate JSON result entry per task**. Each task keeps its own 3c handling, its own acceptance evidence, and its own 3g completion decision — batching changes who types, never what is proven.
- It occupies **one** pool slot; record the union of its assigned files for the polling snapshot.
- **Never batch** across packages, across implementation languages, or a Quality Gate task with implementation tasks (the QG agent's value is being a *different* reader from the implementers).
- A batch that returns BLOCKED or FAILED on one task does not condemn the others — adjudicate each entry on its own.

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

**Every dispatch cites the invariant it serves. Every dispatch forbids nesting.** Two rules on the brief itself — they cost one line each and they are the cheapest scope control available, because both are visible in the dispatch you are typing.

1. **Name the invariant, or don't dispatch.** The design contract you built in 1d — the numbered `G#`/`D#` invariants and their surface sets — is not just gate material; it is the **work authorization for the whole run**. Every agent brief you write must name the invariant (or the task's `design_acceptance_property`) it serves. If you cannot name one while writing the brief, you are not dispatching phase work — you are dispatching something you decided was worth doing, and it belongs in the final report as a finding for the user to schedule, not in this run. This is the check that catches self-authorized expansion at the only moment it is cheap to catch: before N agents exist. **A rule violation with no invariant behind it is a finding, not a task.**

2. **Subagents do not spawn subagents.** Put `Do NOT spawn subagents. Do this work yourself, sequentially.` in every brief. A subagent that fans out again multiplies token cost with no added coverage (one such child has burned >140k tokens almost entirely on dispatch overhead), and it fragments reporting so badly that the orchestrator ends up re-verifying everything from disk anyway. Depth-1 fan-out only: you dispatch, they work.

**"Found it, you fix it" covers surfaces you *touched*, not surfaces you *scanned*.** The ownership rule in CLAUDE.md is about collateral you created or disturbed. A defect you merely *observed* while grepping — in a package this phase never modified — is a **report line**, not a work item. Turning a scan across N files into ownership of N files is scope invention wearing the costume of diligence. The distinction to hold: *root cause of a failure you are fixing lies outside your files* → follow it and fix it there; *pre-existing violation you noticed while reading* → write it down and move on.

**Producing a count is not a commitment to clear it.** If you promise the user a repo-wide figure, the deliverable is **the figure**. Scanning to produce a number does not convert that number into a work queue — deciding to clear it is the user's call, and it needs rule 1's invariant test like anything else.

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
   - **When the run is RED**, get the failing/erroring detail from the collector instead of reading `full.log` — pass it the **printed** run folder (never `-Project`, which picks the newest folder on disk and can race a concurrent session):
     ```bash
     powershell -File "d:/datrix/datrix/scripts/test/collect-failure-data.ps1" "{printed-run-folder}"
     ```
     Its `failure-data.json` carries every error/failure cluster (errors first — module-level collection errors have no per-test node ID), each with a representative traceback tail and a ready `test_command`.

5. **Decide the gate over the union of accepted artifact results (step 2) and re-run results (step 3). The gate is GREEN only when every one of them has `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0`.** Treat **errors exactly like failures** — a pytest *error* (collection / import / fixture / setup failure) means tests never ran, which is a worse outcome than an assertion failure, not a passable one. Never read `failed` alone: a run with `failed == 0` but `error > 0` is RED, not green.
   - Gate GREEN → proceed to 3g (mark complete)
   - Gate RED (any `failed` or `error`) → proceed to 3e (attribute & fix)
   - If a re-run's `index.json` is missing or unparseable → the run did not complete cleanly; treat as a **test infrastructure failure** (see Error Recovery), do not infer a pass from stdout. (An *agent* run with a bad `index.json` is not an infrastructure failure — it simply fails step 2 acceptance and lands in the step-3 re-run batch.)

#### 3e. Attribute Failures and Fix Loop

Process **both** red outcomes from `counts`: assertion **failures** (`counts.failed`) and **errors** (`counts.error`). Work from the RED run's `failure-data.json` (produced in 3d step 4) — its clusters are the attribution units, one root cause each. They are attributed and fixed the same way, with one difference in how you locate them:
- A **failure** cluster has per-test node IDs (`tests/...::test_x`) — fix the code under test.
- An **error** cluster is reported at module/collection level with no per-test node ID (e.g. an `ImportError`, a fixture error, a syntax error that breaks collection). Attribute by the **erroring module/file path** from the cluster's representative, and fix the import/fixture/syntax root cause. An error often hides many tests that never ran — resolving it can change the pass count substantially, so always re-run after fixing one.

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
- **Superseded tasks (1f O3) settle here, with their survivor.** For every `absorbed → survivor` pair in `superseded_tasks{}`, when the survivor passes all 4 conditions, complete the absorbed task in the same step: `complete.ps1` on its path with a `## How Solved` carrying the survivor's acceptance evidence verbatim plus the `**Superseded by:**` pointer. If the survivor fails, the absorbed task fails with it — the merge did not make it disappear, and leaving it neither COMPLETED nor blocker-proofed wedges the Stop gate.

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
   - **Reverse-dependency closure (ALWAYS):** add every package in each changed package's reverse-dependency closure per `d:\datrix\.claude\skills\_shared\verification-strategy.md` (its table + derivation commands; a shared-layer change — `datrix-common`, `datrix-codegen-common`, `datrix-language`, any shared contract — pulls in every consumer). This is the sweep 3d's shared-layer rule defers to — the boundary is where consumers are proven whole, so a consumer of a changed shared layer is in the sweep set *even though no task modified it*. When an edge is uncertain, include the package.
   - **Multi-phase runs — the affected-green guarantee:** at the **first** phase boundary, the sweep set is the affected set (changed + closure) of everything the run has touched so far — NOT unconditionally all packages; a package outside the closure cannot have been broken by this run, and pre-existing rot in untouched packages is the scheduled full sweep's job, not this gate's. At each **later** boundary, the guarantee is maintained incrementally: sweep = changed + closure since each package's last GREEN full run (`package_green_state{}`); a package with **zero recorded changes** (in itself and its dependency cone) since its last green sweep carries its green status forward and is listed as `carried` in the checkpoint — green-at-last-sweep plus provably-unchanged-since IS "all tests passing" for that package. **Safety valve:** if `package_change_log{}` is tainted (any change that cannot be attributed to a recorded agent report), closure-based selection is disabled — sweep ALL packages at this boundary.
   - **Repo gates:** when the phase touched a codegen package, codegen-common, language, common, or `datrix/examples`, add `reference-example-parity-gate.ps1` to the sweep; add other repo gates only when their surface was touched (per `_shared/verification-strategy.md` "Repo gates").
   - **Single-phase runs:** same rule — changed + reverse-dependency closure.
2. **Run the sweep set concurrently and read the verdict in one call:**
   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/affected-gate.ps1" -Projects {pkg1},{pkg2},...
   ```
   Include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash tool description. `affected-gate.ps1` schedules `test.ps1 <pkg>` for every package you pass (plus its own re-derived closure, so it never runs a narrower set than step 1 computed) concurrently under a worker budget, then aggregates one GREEN/RED verdict by reusing `gate-verdict.ps1`'s own per-project evaluation — this replaces firing `test.ps1` per package and separately calling `gate-verdict.ps1`. It prints one GREEN/RED line per package + `OVERALL`, and writes per-package counts and capped failing-test lists to its `Details:` JSON. Sanity-check each package's `run_dir`/`age_minutes` in the JSON against the run you just fired (a concurrent session's newer run would show up here). A package is GREEN only when `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` — errors count as red, exactly as the 3d gate rules; the script already applies this (UNKNOWN/in-progress/missing results are RED). Record each GREEN package into `package_green_state{}`. For each RED package, run `collect-failure-data.ps1` on its run dir for the cluster detail that drives step 3.
3. **Fix every red package to GREEN — regardless of attribution.** For each failing test and each erroring module across ALL packages in the sweep set, **including failures in code that no task in this phase modified**:
   - **Delegate the fix, own the verdict.** Dispatch a **sonnet** (or **opus** for a subtle/cross-cutting root cause) fix subagent to read the failing test and the code under test, trace to the **root cause**, and fix it there. Unlike 3e this is NOT scope-restricted to a task's files — instruct the agent to fix whatever is red at its root. Bind it with NO workarounds, NO `xfail`/skip-to-pass, NO band-aids, NO conditional guards that hide the broken path, NO git reverts (CLAUDE.md). You do NOT read/edit the code inline on Opus — you decide what's in scope and verify the result.
   - Verify authoritatively: re-run the specific test (`test.ps1 {package} -Specific "{path}"`), then re-run the full package suite — reading `index.json`, not the agent's self-report.
   - If the first fix attempt fails or the root cause is unclear → **Decision Escalation Protocol** — analyze the root cause in-context yourself, then re-dispatch the fix subagent with your directed remediation plan. If your directed fix still fails, that test/module becomes a blocking item carried into Step C's halt-and-ask.
   - If a red test traces to a root cause **genuinely outside this repo's control** (e.g. a known-flaky external integration) → do NOT silently skip it; record it as a blocking item and surface it in Step C, letting the user decide. Do not invent this exception to dodge a real fix.
4. **Re-run until clean** — after fixes, re-run `affected-gate.ps1 -Projects {red packages}` for the fresh verdict (their green peers' recorded results stand; nothing changed them). Repeat until every sweep-set package is GREEN, or escalation/halt is reached. An error fixed in one module often unhides many tests that never ran, so always re-run the failing package's full suite after a fix rather than trusting `-Specific` alone. If a fix touched a package OUTSIDE the current red set (scope expansion into a green or unswept package), add that package to the sweep set and run its full suite too.

##### Step A2 — Phase-end DESIGN-CONFORMANCE gate (runs at EVERY phase end, including single-phase runs)

A green suite proves the code runs; it does NOT prove the design holds. This gate verifies phase `P` actually satisfied the `design_contract` built in Step 1d. **It runs at the end of every phase — including a single-phase run — and a phase cannot be declared complete without it, even when Step A is fully green.** Skipping it is exactly how a half-enforced invariant has shipped undetected before.

**A2 is the phase's single authoritative EXECUTION of the acceptance checks.** Implementation agents run them and paste evidence; 3g verifies that evidence; A2 is where the orchestrator itself executes each invariant's check, once, across the full surface set. Do not treat the earlier evidence as a reason to skip A2, and do not add executions elsewhere. Where a quality-gate agent ran this phase (3b), **read its static-checklist findings first** (stub scan, coverage sanity, How-Solved contradictions) and disposition every one — they are input to this gate, not a substitute for its executions.

For each invariant / numbered decision (D#/G#) in phase `P`'s `design_contract`:

1. **Enumerate the invariant's full surface set** (from Step 1d). For each surface the design names, run the invariant's **acceptance check** (negative + positive) against REAL generated output / migrated source — not against an agent's self-report. Paste the command + output. **Express the checks as a conformance-gate spec where they are grep/existence assertions** — one spec per invariant, re-runnable, with a `negative_control` tree so a vacuous "forbidden token absent" grep fails loud (see `datrix/scripts/dev/quick-reference.md`):
   ```bash
   powershell -File "d:/datrix/datrix/scripts/dev/conformance-gate.ps1" -Spec "D:\datrix\.tmp\phase-{NN}-{invariant}.spec.json"
   ```
   For an invariant claiming **output-neutrality** ("X replaces Y with byte-identical output"), prove it with `dev\byte-identity-generate.ps1` rather than a hand-rolled hash comparison.
   - *Negative:* the forbidden construct/state is gone on that surface (e.g. `grep` finds zero raw `env(...)` on secret positions in the migrated tree).
   - *Positive:* the new path is actually exercised (e.g. the generated service resolves each secret via `get_secret(<handle>)`; no `${VAR}`/literal secret remains).
2. **Any surface in the design's set that is unguarded / unconverted is a CONFORMANCE FAILURE** — even if every task is COMPLETED and every suite is GREEN. A half-implemented invariant (guarded on the easy surface, silently dropped on the rest) is exactly the escape mode this step is built to catch.
3. **Verify every task's `design_acceptance_property` was actually proven** (its check + output is in its How-Solved). A COMPLETED task whose property is unproven is a conformance failure — reopen it.
4. **Check the conformance gaps recorded in Step 1d** (design-named surfaces with no covering task). Any unresolved gap is a phase-level failure.

A conformance failure is handled like a red package: fix it to conformance within the phase (spawn a follow-up task for an out-of-scope root cause), or carry it to Step C's halt-and-ask. **NO declaring the phase done with a known unenforced design surface.** Report each conformance failure explicitly — never let it pass silently under a green suite.

##### Step B — Partition and evaluate

Partition phase `P`'s tasks into `completed`, `failed`, and `skipped` (using the run-wide state variables, filtered to tasks whose `phase == P`).

**Green phase** — every sweep-set package passed Step A's full-suite gate (all red driven to zero; carried-forward packages count as green by the carry-forward rule) **AND Step A2's design-conformance gate passed (every design-named surface enforced, every task's acceptance property proven, no open conformance gap)** AND `failed` and `skipped` are both empty **AND every task in the phase is COMPLETE — including any task you or an agent filed mid-run**:

> **A task filed during the phase joins that phase's completion bar.** Re-run `phase-status.ps1 {NN}` before declaring a phase green and confirm zero pending tasks; a task you added at a gate (a discovered defect, a readiness-audit gap) is finished here, not deferred. You may not create a new phase to park it in — see 1e and CLAUDE.md "Task Orchestration". Declaring a phase COMPLETE while one of its own tasks sits NOT STARTED is a false completion, and filing forward to dodge this gate is precisely the move this rule forbids.
- Emit the Phase Checkpoint (below) — a one-line progress marker, **not** a report and **not** a conclusion.
- **Run phase `P+1`'s 1d → 1e → 1f now** (its design contract, readiness audit, and optimization pass), against the code phase `P` just changed — then plan its waves (Step 2). This is the boundary work, not a stopping point.
- **Immediately spawn the first wave of phase `P+1` (3a/3b), in this same turn.** No pause, no `AskUserQuestion`, no "phase {P} is complete — shall I continue?", no summary of the phase's accomplishments. A green gate is the *authorization* to continue, and continuing is the only thing you may do with it (Multi-Phase Continuation, above).
- Only when phase `P` is the **last** phase in the run does a green gate lead to Step 4's design-status update and Step 5's final report instead of a next wave.

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

The `→ Starting phase {P+1}` line is a **commitment, not a plan announcement**: the very next thing you do after emitting it is dispatch phase `P+1`'s first wave. Emitting it and then ending the turn is the failure this gate exists to prevent. Omit that line only when `P` is the last phase in the run (then Steps 4–5 follow).

Track phases as their own TodoWrite group so the user can see phase-level progress distinct from wave-level progress. Keep the next phase's todos visibly pending at every boundary — an unstarted phase in the todo list is a standing reminder that the run is not over.

---

## Step 4: Design Status Update (end of run only)

Runs **once**, after the LAST phase has passed its 3i gates and **before** the final report. It updates the `Status:` line of every design doc this run finished — and nothing else in the doc, ever.

**The carve-out, stated precisely.** CLAUDE.md's "never modify design docs during implementation" and 1e's read-only rule both still bind: no section, requirement, scope boundary, decision, or wording in the body may change, at any point in the run. This step rewrites exactly one line — `Status:` — and only after every task implementing that doc is COMPLETE and its conformance gate has passed. A doc whose status still reads "ready for operationalization" after its last task landed is a stale pointer that aims the next reader, and the next planning run, at work that is already done.

1. **Collect the docs.** From every task's `design_reference` (in each phase's `phase-{NN}-status.json`), take the absolute `d:\datrix\design\*.md` path the field begins with. Deduplicate. Skip references that name no `design/` doc (`none — …`, or a pointer to an already-absorbed `docs/` file) — they have no status line to own.

2. **Enumerate every task implementing each doc, across ALL phases — not just this run's.** A design doc is routinely split over several phases; finishing the phases you ran does not make the doc done.
   ```bash
   grep -rl "{design-doc-filename}" d:/datrix/*/.tasks/ --include="task-*.md"
   ```
   For each hit, read its first heading from disk: complete iff it starts `# COMPLETED:`. Read disk — do not infer completeness from this run's state variables.

3. **Decide, per doc:**
   - **Every referencing task COMPLETED**, and every phase this run executed for that doc passed 3i Step A (full-suite) **and** Step A2 (design-conformance) → update the status, per item 4 below.
   - **Any referencing task not COMPLETED** — a pending task in a phase outside this run, or one of this run's `failed_tasks` / `skipped_tasks` → **leave the doc untouched** and report it in Step 5's `Design:` line as `{doc} — {N} task(s) outstanding`. Never write a partial or in-progress status: a half-updated status line is worse than a stale one, and the outstanding tasks are what the report is for.

4. **Rewrite the `Status:` line and only that line.** Use `Edit` with the doc's existing status line as the exact `old_string`, so the change cannot spill past it:
   ```
   Status: **Implemented — phase(s) {NN}[, {NN}] complete; verified by the phase-boundary test and design-conformance gates.**
   ```
   - No `^Status:` line in the doc → do **not** add one and do **not** edit the doc; report `{doc} — no Status line, not updated`.
   - Already reading `Implemented` → leave it. This step is idempotent.
   - A `Status:` line whose text you cannot fit the template to (an unusual state you did not author) is a rung-3 call, not a rewrite-and-hope: leave the doc alone and report it.

5. **Touch nothing else.** Not the body, not a "remaining work" section that the run happened to close out, not a date elsewhere in the doc. The doc stays on disk; folding its content into the official docs is `/absorb-design`, a separate act Jon invokes — Step 5 names each updated doc so he can decide.

---

## Step 5: Final Report

Emit this **once**, after the **last wave of the LAST phase** has passed its wave gate, that phase has passed its 3i gates, and Step 4 has run — or when execution was halted by the user (3f *Stop*, or 3i Step C *Stop*; a halted run still runs Step 4, which will simply find outstanding tasks and leave the docs alone). **Never at an intermediate phase boundary**: if any phase in the run still has unexecuted waves, you are not at Step 5, you are at 3i Step B and your next action is a wave dispatch.

Then emit a lean report:

```
DONE: {COMPLETED|PARTIAL|HALTED} — {completed}/{total} tasks, {waves_executed}/{total_waves} waves
Phases: {P}: COMPLETE | {P+1}: PARTIAL | {P+2}: NOT STARTED   (only for multi-phase runs)
Audit: {N} tasks added to close design gaps: {task-id} ({gap})  (only if the readiness audit amended the set)
Optimized: {N} merged, {N} retired, {N} split, {N} edges dropped, {W_before}→{W_after} waves  (only if 1f changed the set)
Design: {design-doc} → Implemented | {design-doc} — {N} task(s) outstanding   (only if the run resolved any design reference)
Tests: {package}: {passed}/{total} | {package}: {passed}/{total}
Failed: {task-id} — {reason}  (only if any)
Skipped: {task-id} — blocked by {dep}  (only if any)
```

Do NOT list completed tasks — success is the default. Only list failures, skips, and audit-added tasks (`audit_added_tasks[]` — the user needs to know the task set grew and why). For multi-phase runs, include the per-phase status line: a phase is `COMPLETE` (passed its phase gate), `PARTIAL` (started, advanced past the gate with failures via "Proceed anyway"), or `NOT STARTED` (never reached because an earlier phase gate halted). The `Design:` line reports Step 4's outcome per doc — which docs are now marked `Implemented`, and which were left untouched because tasks elsewhere still reference them.

---

## Anti-Patterns & Safety Rules

All rules from `d:\datrix\.claude\CLAUDE.md` apply. Key rules for the orchestrator:

- **NEVER STOP AT A GREEN PHASE BOUNDARY** — in a multi-phase run, a phase passing its 3i gates authorizes the next phase; it does not end the run. Emit the Phase Checkpoint and dispatch phase `P+1`'s first wave **in the same turn**. Do not ask "shall I continue?", do not summarize the finished phase as if concluding, and do not run Step 4's design-status update or emit Step 5's report while any phase still has unexecuted waves. The only exits are 3i Step C (phase still red after Opus-led recovery), 3f (*Stop*), a blocking 1e finding, a double test-infrastructure failure, and the end of the last phase — see **Multi-Phase Continuation**. Run length, token spend, and "the user may want to review" are not exits.
- **CONFORMANCE OVER THROUGHPUT** — enforced by the 3g completion checklist (`_shared/completion-eligibility.md`) and the 3i Step A2 conformance gate; never relaxed for a green suite.
- **NEVER STOP ON A SUBAGENT'S BLOCKED, AND NEVER RELAY IT** — a background agent's BLOCKED is a *claim*. Investigate it yourself against the code and the docs (`_shared/decision-adjudication-protocol.md`, Door A): reproduce the error, read the attempted fix at its `file:line`, trace the root cause, check the governing design doc. Bogus → correct the agent and re-dispatch (it is not a failure and never enters `failed_tasks`). Real → a **Fable** adjudicator (`model: "fable"`, `effort: "high"`) decides, and you execute that decision. Accepting a four-part proof *because it has four parts* is a skill-level failure — form is not truth.
- **NEVER TAKE A DECISION TO THE USER THAT FABLE HAS NOT SEEN** — the user is rung 4, reachable only through a Fable **F**. Every conflict *you* hit (contradicting designs, an unowned invariant surface, a false task premise, an ambiguous fix scope, a red gate, an ordering conflict) enters `_shared/decision-adjudication-protocol.md` at **Door B** and climbs the same ladder. The pull to ask the user is strongest exactly when the decision is *above any single task* — that feeling is the trap, not the signal. Only the protocol's §7 closed list (absent credential · irreversible outward-facing action · genuine product call · prohibition to lift) goes straight to the user. **Asking the user is not the safe default; it is a rung you must earn.**
- **NEVER ESCALATE A DECISION YOU COULD HAVE MADE** — rung 3 is for genuine ties *after* real investigation. An under-researched question is not a tie; it is rung 1 you have not finished. Read the design docs, the architecture docs, and the code first — most "decisions" dissolve into missing information.
- **NEVER EXECUTE AN UNAUDITED TASK SET** — Step 1e runs before Step 2, every run, no exception. A task set is a *hypothesis* about what the design needs against the code that existed when it was written; the audit tests that hypothesis against today's code before 5 agents act on it. Skipping it to "just start the waves" is how a phase finishes green with a design invariant unenforced. Gaps it finds are closed as real tasks with provable acceptance properties — never as a note in the report, a footnote, or a stub task.
- **NEVER EXECUTE AN UNOPTIMIZED TASK SET, AND NEVER OPTIMIZE AWAY CONFORMANCE** — Step 1f runs after 1e, every phase, before waves are planned: retire what is already satisfied, merge duplicated scope, drop edges that order nothing, repair bare-full-suite targeted tests, and batch co-located small tasks at dispatch (3b). It spends **no new agents and reads no new source** — it is a pass over metadata you already hold, and its normal output is one line. But an optimization that orphans a design surface, weakens an acceptance property, drops an enforcement edge, or merges a guard with the migration it polices is not an optimization — it is the conformance failure the gates exist to catch, bought a few minutes earlier. **Default is keep the edge; default is no-op.**
- **NO ASSUMING — ENUMERATE AND VERIFY STATE** — characterize a corpus by enumerating ALL of it (counted), not a sample; reason about git/working-tree from the CURRENT on-disk state you just read, never a remembered snapshot. Paste real command output for every conformance claim.
- **GENUINE agent monitoring, never assumption** — when agents run in the background pool, drive them with the Agent Progress Polling Protocol: check every ~5 minutes what each agent is *actually* doing (status **and** on-disk artifacts). Never report an agent as "working" without that evidence, and never rely on a completion notification to know an agent finished.
- **JUDGMENT INLINE, TYPING DELEGATED** — you are the Opus orchestrator: decompose, attribute, decide fix-scope, gate conformance, and analyze escalations in YOUR context; dispatch subagents (haiku/sonnet/opus) to read widely, run suites, and apply fixes. Do NOT edit code inline on Opus in the fix loops (3e/3i) — decide the fix, then hand the edit to a subagent. Reading the minimum code needed to decide is fine; doing the whole implementation inline is not.
- **NEVER DELEGATE THE DECISION** — the old "escalate up to a more-capable agent" is gone; you ARE the Opus brain. Analyze in-context at extra-high effort, then dispatch a cheaper implementer (an `opus` subagent only for a genuinely hard/cross-cutting fix). Verify every returned result with a check you run (or delegate the run and read `index.json`) — a subagent's self-report never substitutes for the design-acceptance evidence you paste into the gate.
- **NEVER EDIT A DESIGN DOC BEYOND ITS `Status:` LINE, AND NEVER BEFORE THE RUN IS OVER** — design docs are scope boundaries (CLAUDE.md). The one permitted write is Step 4's status-line rewrite, at the end of the last phase, only for a doc whose every referencing task — across ALL phases, not just this run's — is COMPLETED. A doc with outstanding tasks anywhere is left untouched and reported. Never write a partial status, never edit the body, and never mark a doc implemented off this run's state variables instead of what the task files on disk say.
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

