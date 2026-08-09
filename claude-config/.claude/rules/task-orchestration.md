# Task Orchestration

Read this when running `/task-orchestrator`, `/execute-tasks`, `/execute-tasks-parallel`,
or whenever you are about to mark a task COMPLETED, file a task, or close a phase.

## Completing a task

**Always use `complete.ps1`.** Never edit the task heading directly — Edit/Write bypass
the validation hook `complete.ps1` enforces. Read `datrix/scripts/tasks/quick-reference.md`
for the exact invocation before calling any task script.

**Timing.** In `/task-orchestrator` and `/execute-tasks-parallel` runs, mark a task
COMPLETED only after the **wave's test gate passes** (targeted per-package tests for that
wave; full suites run once at the quality gate / phase boundary, never per wave). Agent
success is necessary but not sufficient — do not mark tasks COMPLETED as individual
agents return.

**Never run `complete.ps1`** on a task whose agent returned BLOCKED, whose `## How Solved`
contains `BLOCKED` / `partial` / `out of scope` / `workaround` / `dual path` /
`not yet wired` or any unmet-criterion statement, or whose design-acceptance property is
unproven — regardless of suite color. Spawn the blocker as a tracked follow-up task; do
not bury it in a footnote. (This has happened: a task was marked COMPLETED while its own
How-Solved said `Status: BLOCKED`.)

## Phases

**Agents never create a phase.** Creating a `.tasks\phase-NN\` directory that does not
already exist is a **planning act reserved to Jon** and to the planning skills he invokes
by name (`/generate-tasks`, `/operationalize-design`). No agent — foreground, background,
subagent, orchestrator, or fix loop — may create one, and "the execution contract told me
to file a real tracked task" is **not** authorization to open a new phase. A new phase
silently seeds the next orchestration run with work nobody scheduled, and it is what
`latest-phase.ps1` reports.

**A task you must file goes in the phase you are executing.** Number it the next free
`{TT}` in that phase (`validate-dependencies.ps1 -Phase {NN} -NextTaskNumber`) and put it
in the owning package's existing `.tasks\phase-{NN}\`. Never file forward into a fresh
phase — filing forward is how work gets deferred past the gate meant to catch it.

**A phase is COMPLETE only when every task in it is COMPLETE.** Adding a task to the phase
you are running adds it to that phase's completion bar; it does not ride along unfinished.
If you file a task mid-phase, you finish it before declaring the phase done — or you carry
a valid B1–B4 blocker with the four-part proof for it. Reporting a phase green while one
of its own tasks sits NOT STARTED is a false completion.

**Enforcement before what it governs.** A task that establishes or enforces a design
invariant (a validator, a fail-loud guard, a parser-level rejection, a conformance check)
must run BEFORE — and be a `Depends on` of — every task that relies on it or migrates
content subject to it. Never order a migration ahead of the guard meant to police it: the
migration would "pass" against an absent check. This is exactly how a migration once
slipped through before its guarding validator was in place.

## Conformance over throughput

The orchestrator ensures tasks satisfy the DESIGN; it does not blindly run them. A green
test suite, "it generates", and "0 warnings" are necessary but NEVER sufficient.

Every task carries a `**Design reference:**` (the D#/G#/numbered invariant it implements)
and a `**Design acceptance property:**` (the observable end-state). A task/phase is done
only when that property is **proven by an executable check you run yourself** — negative
(the old/forbidden state is gone on the affected surface) and positive (the new path is
exercised) — pasted as command + output, not an agent's self-report.

For any "X replaces Y" scope, prove **Y is gone everywhere on the surface**, not just that
X works. When a design states an invariant over a SET of surfaces, verify EVERY surface: a
guard on the easy surface with the rest silently dropped is a phase failure even under a
green suite. That is how a validation gap once slipped through — a config-driven escape
hatch bypassed a fail-loud check that only covered the more obvious code path.

Run an explicit design-conformance gate at each phase boundary, including single-phase
runs, in addition to the test gate.

## BLOCKED must be VALID before it is terminal

- **Invalid BLOCKED** — missing any part of the execution-contract §3 four-part proof
  (verbatim error text, attempted fix at `file:line`, why it failed, B1–B4 code):
  **reject and re-dispatch the task**, quoting the agent's own report back to it. This is
  the common case. It is not a task outcome; it is a non-answer.
- **Valid BLOCKED** — four-part proof present, B1–B4 matched: terminal. It can never
  become COMPLETED. Spawn it as a tracked follow-up task.

## Pipeline skills and optional deps

In pipeline skills like `/operationalize-design`, when an optional dependency is absent but
the pipeline can still produce its core deliverable, take the graceful-degradation path,
note the degradation in the summary, and continue. Do not halt with an AskUserQuestion gate
for missing optional validators. STOP only for genuinely blocking conditions (unresolved
required decisions, missing required inputs, technical impossibility).

## Generation granularity

`generate.ps1` generates a whole project from its `system.dtrx` — there is **no**
single-service generation mode (a per-service `.dtrx` is part of the system, not
independently generable). A change affecting one service still requires regenerating that
project's full system. To verify, regenerate only the affected project; do not regenerate
unrelated projects or run group / `-All` / `-TestSet` / `-Domains` generation.

## Fixing generation issues — ONE EXAMPLE, ONE LANGUAGE

A log naming twenty failing examples is a queue, not a batch. Pick ONE example, fix it
**for the language it actually failed under**, and stop there.

- **Only the failing language.** Do not generate the example for other registered languages
  to "see if they're affected". If ecommerce failed on java, you fix java.
- **Ask permission before checking any other language.** Checking three more costs roughly
  4× the budget of the one you were asked about. That is Jon's call — ask in one line and wait.
- **Never generate another example before the current one is fixed** — not to check whether
  it's related, not to see if a fix generalises, not as a mid-fix regression check.
- **To prove a fix generalises, write a test** in the owning `datrix-codegen-*` package. A
  test proves the invariant forever; a corpus sweep proves it once and evaporates.
- **No-regression checks run centrally, ONCE**, after the work is done and only over what
  you were asked to touch — never inside each fix iteration, never pasted into every
  dispatched agent's acceptance criteria.

`-All` / `-Domains` / `-TestSet` on `generate.ps1` are hard-blocked by
`validate-script-invocation.py`; the block cannot be overridden.
