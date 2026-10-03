---
description: Implement a design document end to end - operationalize and orchestrate tasks when the design is large, implement directly when it is small, then verify against the design and absorb it into the docs
model: claude-opus-5-5
effort: medium
disable-model-invocation: true
---

# Implement Design

Takes one design document and carries it all the way: **implement → verify → absorb**. It is a chain of existing skills plus one direct-implementation path; it adds no new conformance rules of its own. Every rule of the skill it hands to still binds inside that hand-off.

```
DOCUMENT
  ├─ needs tasks ──► /operationalize-design ──► /task-orchestrator ─┐
  └─ does not    ──► implement directly (this skill, Step 2B) ──────┤
                                                                     ▼
                                              /verify-implementation (fixes what it finds)
                                                                     ▼
                                              design PROVEN? ── yes ──► /absorb-design (deletes the doc)
```

## When to Use

- Jon has an approved design document and wants it built, checked, and folded into the docs in one run
- Jon says "implement this design", "build this doc end to end"

For only the planning half use `/operationalize-design`; for only the build half `/task-orchestrator`.

## How to Invoke

```
/implement-design

DOCUMENT: d:\datrix\datrix\docs\designs\some-design.md
```

With options:
```
/implement-design

DOCUMENT: d:\datrix\datrix\docs\designs\some-design.md
MODE: tasks            # force a path: tasks | direct (default: decide in Step 1)
KEEP SOURCE: true      # absorb the content but keep the design file
FIX: false             # verify-implementation reports only, changes no code
```

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| DOCUMENT | Yes | Path to the design document |
| MODE | No | `tasks` or `direct`. Overrides the Step 1 decision. `direct` on a design that meets a task criterion below is refused: say which criterion and use `tasks` |
| KEEP SOURCE | No | Passed to `/absorb-design` |
| FIX | No | Passed to `/verify-implementation` (default: fix what is wrong) |

## Prereqs — read first

- `d:\datrix\.claude\CLAUDE.md`, `MEMORY.md`, `.claude/rules/design-and-docs.md`
- The DOCUMENT **in full** — it is the scope boundary
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md), [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md), [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md)

## Run discipline

- **One run, no hand-backs.** Finishing implementation is not a stopping point; the next skill starts in the same turn. The run ends at the absorb summary, or at a valid B1–B4 blocker, or when Jon says stop.
- **The only legitimate waits** are the ones the delegated skills define: an unresolved design decision or unchosen alternative in `/operationalize-design` (or Step 2B's equivalent), a design that specifies a less secure option than one available (execution-contract §13.7), and `/absorb-design`'s "no clear target" / "content missed" prompts. Ask in one line with your recommendation; resume at the exact step you stopped on.
- **Never modify the design document** except through the skills that are licensed to: `/task-orchestrator` Step 4 rewrites its `Status:` line, `/absorb-design` deletes it. In the direct path nothing edits it.
- **Never cite the design in a committed artifact** — no design number, filename, or path in code comments, docstrings, docs, tests, or commit messages (`design-and-docs.md`).
- A subagent never runs this skill and never dispatches agents. `/operationalize-design` and `/verify-implementation` run in this session with no subagents; only `/task-orchestrator` dispatches, per its own rules.

---

## Step 1: Decide — tasks or direct

Read the DOCUMENT in full. Resolve its scope with the code-index tools (`find_symbol`, `find_references`, `outline`) and `ask_files`, not by reading source whole. Then decide, on evidence.

**The design needs tasks if ANY of these holds:**

1. It changes more than one package, or one shared-layer surface (`datrix-common`, `datrix-codegen-kernel`, `datrix-codegen-common`, any shared contract) that other packages consume
2. It has a migration / rollout / adoption section with numbered steps, or any fixture, example, or project config must move from an old path to a new one (dual-implementation risk)
3. An invariant ranges over a **set** of surfaces (several languages, platforms, packages, or positions), so coverage must be proven per surface
4. A guard / validator / rejection must exist before the content it governs is migrated (enforcement ordering)
5. It spans more than one language or platform target
6. It is larger than one cohesive change: more than roughly five production files or 250 lines of production code, or more than one behaviour

**Otherwise it is direct**: one owning package, one cohesive behaviour, no migration, nothing ordered, no multi-surface invariant.

**When the call is close, choose tasks.** The task path exists to prevent the half-enforced-invariant failure, and its cost is bounded; a direct implementation that turns out to be a task is found late. If you start direct and the work proves to meet a criterion above, switch to tasks at that point — expand, never abandon.

State the decision in one line: `PATH: tasks|direct — <the criterion that decided it, with file:line evidence>`.

---

## Step 2A: Tasks path

1. **Operationalize.** Invoke `/operationalize-design` through the Skill tool with `DOCUMENT: <path>` (and `TARGET REPOS` if Jon gave them). Take its `DONE` summary: the phase number `{NN}` and the task count.
   - If it stops for a LOW-confidence decision or an unchosen alternative, that is a real wait: relay it to Jon with its recommendation and resume when he answers.
2. **Orchestrate.** Invoke `/task-orchestrator` through the Skill tool with `PHASE: {NN}`. It runs every wave, every gate, and Step 4's `Status:` update. Do not stop at a wave or phase boundary; the orchestrator's own multi-wave rules govern.
3. **Confirm the phase is closed.** Run `powershell -File "d:/datrix/datrix/scripts/tasks/phase-status.ps1" {NN}` (read `datrix/scripts/tasks/quick-reference.md` first) and read its JSON:
   - every task `is_completed`, none with non-empty `how_solved_redflags`
   - the design's `Status:` line reads `Implemented`
   If either fails, the phase is not done: re-invoke `/task-orchestrator` for the same phase (it skips COMPLETED tasks) until it is, or carry a valid B1–B4 four-part proof for each outstanding task. A BLOCKED task never proceeds to Step 3 as if it were complete.

## Step 2B: Direct path

You implement it yourself; a dispatch costs more than the change (execution-contract §10).

1. **Ambiguity gate.** List every open question, "TBD", and explicit alternative (Option A/B) in the design. Close each by investigation (code, docs, logic-map markers) — never by assumption. An explicit alternative, or a design that specifies a less secure option than one plainly available, is Jon's call: ask in one line with your recommendation and wait; do not implement the weaker option and do not silently substitute the stronger one (§13.7). Also run the security-posture read: every auth, secret, transport, trust-boundary input, injection, permission, error/log, crypto surface and every emitted default must have a stated posture.
2. **Find what exists.** `find_canonical` / `find_symbol` / `search` before writing new logic. Place the change at the most language/platform-agnostic layer that can own it.
3. **Implement the whole design**, every requirement, to the code standards in CLAUDE.md: full type hints, no placeholders, no silent fallbacks, no workarounds, security-by-default (and fail closed). Update the docs the change touches, in the owning repo's `docs/`, as content — no pointer to the design.
4. **Test.** Write the tests of the new behaviour in the owning package (real objects, no mocks, each carrying a feature tag), covering the negative case as well as the positive. Run only the tests of what you changed: `test.ps1 <pkg> -Specific "…"` and `-Tag` for the behaviour, in every package it reaches. Never a whole suite. Name the failure each run could show before you run it.
5. **Prove it.** For each design requirement, run its negative and positive acceptance check (a conformance-gate spec under `D:\datrix\.tmp\` or a targeted test) and keep the command and output. `/verify-implementation` repeats this independently; yours is the author's proof, not a substitute for it.
6. Record the list of files changed. The design's `Status:` line is **not** edited in this path.

---

## Step 3: Verify

Invoke `/verify-implementation` through the Skill tool.

- Tasks path: `DESIGN: <path>` and `TASKS: <phase {NN}>`.
- Direct path: `DESIGN: <path>` and `TASKS: none`, plus `FILES:` the changed files from Step 2B.
- Pass `FIX: false` only if Jon set it.

It reviews the code on disk against the design, fixes what is wrong or missing, and ends with `Design conformance: PROVEN | INCOMPLETE`.

- **PROVEN** → Step 4.
- **INCOMPLETE** → the design is not implemented. Go to the cause: fix what verify could not (tasks path: re-invoke `/task-orchestrator` on the same phase for any in-phase task verify filed; direct path: fix it yourself), then run `/verify-implementation` again. Repeat until PROVEN. A second INCOMPLETE on the same finding means the diagnosis was wrong, so re-diagnose rather than patch. Stop only on a valid B1–B4 blocker with the four-part proof, and then **do not absorb**: report the blocker.
- A design-sized defect verify surfaces (needs its own design) gets a findings file under `d:\datrix\reports\finding\` and is named in the final report; it does not block absorbing a design that is otherwise PROVEN.
- With `FIX: false`, verify is report-only: print its report and stop here without absorbing.

## Step 4: Absorb

Reached only on `Design conformance: PROVEN`.

Invoke `/absorb-design` through the Skill tool with `DOCUMENT: <path>` (and `KEEP SOURCE: true` if Jon set it). It transfers the content into the official docs, replaces every reference, and deletes the source.

On the tasks path, the implementation tasks already updated the docs their features touch (operationalize itself edits no doc), so expect some units to report "already present"; that is correct, not a defect. Its "no clear target" and "content missed" prompts are real waits.

## Step 5: Final report

Lean, data only:

```
IMPLEMENT-DESIGN: {title}
Path: tasks (phase {NN}, {N} tasks) | direct ({N} files)
Verify: PROVEN ({n} requirements; {n} fixed by verify)
Absorb: {N} units transferred, {N} files, source DELETED | PRESERVED
Findings filed: {paths | none}
```

If the run ended on a blocker, report that instead: the four-part proof and the step it stopped at. Nothing else.

## Anti-Patterns

- **NO absorbing before PROVEN** — absorb deletes the design, the one document the conformance check measures against.
- **NO stopping between steps** — implement, verify, and absorb are one run.
- **NO choosing direct to save cost** when a task criterion holds; a close call goes to tasks.
- **NO running verify as a formality** — INCOMPLETE is a failure to fix, not a status to report.
- **NO editing the design document**, outside the two licensed edits.
- **NO design number, filename, or path in code, tests, docs, or commit messages.**
- **NO whole test suites** — targeted `-Specific` / `-Tag` runs only, in every package the change reaches.
- **NO workarounds, NO dodging** ("out of scope", "pre-existing", "track separately" are the work, not blockers).
- **NO git restore/checkout/reset/stash/revert** — undo your own edits manually.
