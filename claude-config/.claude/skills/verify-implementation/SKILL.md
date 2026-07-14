---
description: Code-review completed tasks against the design document they implement, then fix anything wrong or missing so the implementation conforms to the design
model: sonnet
effort: high
disable-model-invocation: true
---

# Verify Implementation

Given a design document and the tasks implemented from it, code-review the **actual code on disk** to confirm it satisfies the design — every invariant, every acceptance property, every affected surface. Where the implementation is wrong, incomplete, or missing, trace to root cause and fix it. This is a conformance gate, not a status check: a green test suite and a task's own "How Solved" note are inputs to your judgment, never proof.

**This skill does not run test suites.** The tasks reached COMPLETED through their own test gate — the suites already ran and passed, and re-running them proves nothing about design conformance. Your evidence is the code on disk plus targeted, read-only checks (grep sweeps over a surface set, a generation run, a validator invocation). The ONLY test execution in scope is running the **specific tests covering a fix you made** in Phase 3, to confirm that fix works and broke nothing near it.

## When to Use

- A design document has been operationalized and its tasks marked COMPLETED — you want to confirm they actually implement the design before absorbing it
- User says "verify the implementation", "check these tasks match the design", "did we build this right"
- After a `/task-orchestrator` or `/execute-tasks-parallel` run, as an independent conformance pass over the whole design
- Before `/absorb-design`, to catch a task that passed its suite but drifted from the design

## How to Invoke

```
/verify-implementation

DESIGN: d:\datrix\datrix\docs\designs\some-design.md
```

With explicit tasks (otherwise auto-detected — see Inputs):
```
/verify-implementation

DESIGN: d:\datrix\datrix\docs\designs\some-design.md
TASKS: d:\datrix\datrix-common\.tasks\phase-42
FIX: false          # review only — report findings, do not modify code
```

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| DESIGN | Yes | Path to the design document the tasks implement |
| TASKS | No | A phase folder, a list of task files, or a phase number. If omitted, auto-detect: grep all `D:\datrix\*/.tasks/` files whose `**Design reference:**` line points at DESIGN |
| FIX | No | If `false`, produce the conformance report but make NO code changes (default: fix what is wrong or missing) |

## Prereqs — read first

- `d:\datrix\.claude\CLAUDE.md` and `MEMORY.md`
- The DESIGN document **in full** — it is the scope boundary and the source of truth
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md), [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md)
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) (index → prohibited-patterns, code-quality-standards, repo-specific-rules, canonical-imports)
- For any package you will touch, its [test-guidelines/](../../../../../datrix-common/docs/contributing/test-guidelines/)

## Governing rules (from CLAUDE.md — these bite in every phase)

- **Conformance over throughput.** "It generates", "0 warnings", "suite green", and a task's `## How Solved` self-report are NECESSARY but NEVER sufficient. Done = the design acceptance property is **proven by a check you run yourself** — a NEGATIVE check (the old/forbidden state is gone everywhere on the affected surface) AND a POSITIVE check (the new path exists and is exercised) — pasted as command + output. These checks are code reads, grep sweeps over the surface set, generation runs, and validator invocations — never suite runs.
- **The suites are not your evidence.** They already passed before this skill was invoked; that is its precondition, not its output. Do not re-run a package suite to "confirm" conformance, and never report a green suite as proof the design was met.
- **Invariant-surface coverage.** When the design states an invariant over a SET of surfaces, verify EVERY surface. A guard on the easy surface with the rest silently dropped is a conformance failure even under a green suite.
- **Never assume/fabricate — look it up.** Read the actual code. Do not trust a `## How Solved` claim, an agent's prior self-report, or a passing test as evidence that the design was met — verify against the code and by execution.
- **BLOCKED is terminal.** A task whose `## How Solved` contains `BLOCKED`/`partial`/`out of scope`/`workaround`/`dual path`/`not yet wired` — or any unmet-criterion statement — did NOT satisfy the design, regardless of suite color. Treat it as a finding.
- **Cross-surface impact.** Shared layers (`datrix-common`, `datrix-codegen-common`, any shared contract) are consumed by EVERY generator. If you fix one, identify every consuming package and run the **targeted tests covering the changed behavior** in each — not each package's full suite, and not only the package where the finding surfaced.
- **Generality-preserving.** Place fixes at the most language/platform-agnostic layer that can own them; provider/language specifics live only in the owning codegen package. Never hardcode "the currently-shipped languages/providers are the only targets".
- **No workarounds.** Fix the root cause or STOP and report. No band-aids, no conditional guards that hide a broken path.
- **No git reverts** (`checkout`/`restore`/`reset`/`stash`/`revert`). Undo your own edits manually.
- **Temp files** only under `D:\datrix\.scripts\`, `.test-output\`, `.tmp\`. Never scatter scratch files in the repo tree.
- **Domain isolation.** No customer/domain language in framework packages.

## Scope back-off

If verification reveals the implementation is wrong across 3+ unrelated subsystems, or the fixes would require chain-debugging that fills context, STOP after the report phase and propose splitting. Don't silently attempt a massive fix sweep. A single clearly-scoped root-cause fix is in bounds; a rewrite is not.

---

## Pipeline

### Phase 1: Ingest — build the conformance checklist

**Goal:** Turn the design + tasks into a concrete, checkable list of what MUST be true in the code.

1. Read the DESIGN in full. Extract every **design invariant / decision / requirement** as a numbered checklist item, keyed by its `D#`/`G#`/numbered-decision id where the design uses one. For each, note the **set of surfaces** it applies to (which languages, providers, packages, files) — this is what invariant-surface coverage checks against.
2. Resolve the task set (from TASKS, or auto-detect via the `**Design reference:**` line pointing at DESIGN). Read each task file: its `**Design acceptance property:**`, its Success Criteria, and its `## How Solved` section.
3. For each design requirement, map which task(s) claim to implement it. Flag:
   - **Design requirements with no owning task** — potential missing implementation
   - **Tasks whose `## How Solved`** contains a BLOCKED/partial/workaround/dual-path marker — presumptive findings
   - **Acceptance properties stated as "tests pass"/"generates clean"** rather than a provable negative+positive check — the task under-specified its own conformance; you must derive the real check from the design

**End-of-phase output (lean — data only):**
```
INGEST: {design title}
Requirements: {N} (surface-set sizes noted)
Tasks in scope: {N} ({auto-detected|explicit})
Unowned requirements: {N}; BLOCKED/partial markers: {N}
```

---

### Phase 2: Review — code-review each requirement against the code on disk

**Goal:** For every checklist item, decide CONFORMS / VIOLATES / MISSING on **evidence from the actual code** — never on a self-report, and never on the suite that already passed.

This phase is a **read-only review**. Do not run any package test suite here: the tasks' suites passed before this skill was invoked, so a green run tells you nothing you did not already know, and it cannot distinguish a design that was implemented from one that was quietly dropped.

**Evidence-baseline rule (avoid triple-running acceptance checks).** When the tasks came out of an orchestrated run whose phase-boundary conformance gate already EXECUTED an invariant's acceptance check (the command + output is pasted in the tasks' How-Solved / the phase record, and the tree has not changed since), treat that evidence as the baseline: verify it (the command is real, the output is consistent with the code you read), spot re-execute a sample, and re-execute in full **only** where evidence is missing, stale, contradicted by the code, or under-scoped (a surface the design names that the pasted check never swept — the most common gap, and always re-checked). Where no such evidence exists — or the user asked for a fully independent pass — execute every check yourself as written below. Independence is preserved by the verification-of-evidence + the sweep of surfaces the earlier gate missed, not by mechanically re-running commands whose output is already on file.

For each design requirement:

1. **Read the implementing code** the task points at (and search for it independently — the task may have implemented it elsewhere, or not at all). Confirm the code actually does what the design requires, not merely that a function by the expected name exists.
2. **Run the acceptance check** — this is the core of the skill. Both halves are code reads, grep sweeps, generation runs, or validator invocations; neither is a suite run:
   - **NEGATIVE:** prove the old / forbidden construct is gone **everywhere on the requirement's surface set** (grep/search the whole set, not one file). Paste the command + output.
   - **POSITIVE:** prove the new path exists and is reachable — read the call chain that reaches it, point at the test that covers it (its existence and content, not a fresh run of it), show generation emitting it, or show the validator rejecting the bad input. Paste the command + output.
   - Put any scratch runners under `D:\datrix\.scripts\`, output under `D:\datrix\.test-output\`.
3. **Invariant-surface sweep:** for a set-invariant, check EVERY surface in the set. Record each surface's verdict individually — "the easy surface passes" is not "the invariant holds".
4. **Code-quality review** of the changed code against `ai-agent-rules` / prohibited-patterns: placeholders/TODOs, silent fallbacks, `except: pass`, `T | None` error returns, mocks/fakes in tests, magic constants, `Any`, cognitive complexity, missing type hints. A conformant-but-shoddy implementation is still a finding.
5. **Contradiction check:** if a task's `## How Solved` claims something the code does not support (names a file/function/flag that doesn't exist, claims a surface was migrated that still has the old construct), that is a finding — surface it, don't paper over it.

Classify each finding: **MISSING** (design requirement unimplemented), **WRONG** (implemented but violates the design), **INCOMPLETE** (some surfaces done, others dropped), **QUALITY** (conforms but breaks a code standard).

**End-of-phase output:**
```
REVIEW: {N} requirements checked
CONFORMS: {n}  VIOLATES: {n}  MISSING: {n}  INCOMPLETE: {n}  QUALITY: {n}

Findings (each with: requirement id, surface(s) affected, evidence command+output snippet, root cause):
1. [MISSING] {requirement} — {what's absent} — {evidence}
2. [INCOMPLETE] {requirement} — done on {surfaces}, dropped on {surfaces} — {evidence}
...
```

**If FIX is false** → output the report and STOP here.

**If all findings are CONFORMS** → skip to Final Summary (nothing to fix).

---

### Phase 3: Fix — repair each finding at its root cause

**Goal:** Make the implementation conform. One correct fix at the right layer, not five patches.

For each finding, in dependency order (fix an enforcement/guard gap before the content it governs):

1. **Trace to root cause** before touching code. Understand why the design requirement is unmet — a missing branch, a wrong layer, a dropped surface, a guard that was never wired.
2. **Design the fix at the most agnostic layer that can own it** (generality-preserving rule). If the requirement is a shared invariant, fix it in the shared layer once — not per-consumer.
3. **Implement** it. Follow all code standards (type hints, `mypy --strict`, no `Any`, no mocks in tests, named constants, complexity ≤15). If the requirement needed a test that was never written, write it (real objects, per the test guidelines) — but never a cross-package or language/provider matrix test.
4. **If the root cause is outside the task/design scope** (a pre-existing bug in an unrelated subsystem) → STOP and report it as a blocker; do NOT paper over it with a workaround to make this design "pass".

**Cross-surface discipline:** if you touch a shared layer, list every consuming package and note, for each, the **specific tests that cover the behavior you changed** — those are what you run in Phase 4. The finding's own package is not the whole blast radius, and no package's full suite is the answer either.

---

### Phase 4: Re-verify — prove each fix conforms and broke nothing near it

**Goal:** Every finding closed by the same standard used to open it. Reached ONLY if you changed code in Phase 3 — if nothing was fixed, there is nothing to re-verify.

1. **Re-run each fixed requirement's acceptance check** (negative + positive) and paste command + output. The forbidden state is gone on the FULL surface set; the new path is exercised.
2. **Run the targeted tests for what you changed** — the specific tests covering the fixed behavior (the test you wrote for it, plus the existing tests over the code path you touched), in the fixed package and in each consuming package for a shared-layer fix. Run these because YOUR edit could have broken them — not to re-confirm a suite that already passed. Select them narrowly (see `datrix/scripts/test/quick-reference.md` for the authoritative parameter list):
   - `test\test.ps1 <package> -Specific "tests/unit/test_foo.py"` — the test file covering the fix
   - `test\test.ps1 <package> -Keyword "<name>"` — pytest `-k` match when the fix spans a few named tests
   - `test\test-single.ps1 "tests/unit/test_foo.py" -Project <package>` — one file, full output
   Paste command + output. Do NOT run a whole package suite, and never `-All`.
3. **Re-sweep set-invariants** across all surfaces — confirm no surface was left behind.
4. If any check still fails → return to Phase 3 (root cause, not another patch). If it cannot be closed without out-of-scope work → STOP and report the blocker.

**End-of-phase output:**
```
RE-VERIFY:
Findings fixed: {n}/{N}  (each: requirement id → negative+positive check now passing)
Targeted tests run for fixes: {test selector: pass/fail, ...}
Set-invariant surfaces re-swept: {all pass | list stragglers}
Blockers (out of scope): {none | list}
```

---

## Final Summary (lean — no "next steps" padding)

```
VERIFY-IMPLEMENTATION: {design title}
Requirements: {N} checked
Conformed as-built: {n}   Fixed: {n}   Blocked (out of scope): {n}
Files changed: {list}
Targeted tests run for fixes: {selector: pass, ... | none — no code changed}
Design conformance: {PROVEN — all acceptance checks pass | INCOMPLETE — see blockers}
```

If any requirement remains unproven, say so plainly — do NOT report success on a green suite alone.

## Anti-Patterns

- **NO running package test suites to verify conformance** — they already passed; that is this skill's precondition. The only tests you run are the specific ones covering a fix YOU made in Phase 3.
- **NO trusting `## How Solved`, a prior agent's report, or a passing suite as proof** — verify against the code on disk and by running the acceptance check yourself.
- **NO "it generates" / "suite green" as done** — a requirement is met only when its negative+positive acceptance check passes with pasted output.
- **NO checking one surface of a set-invariant** — sweep every surface; a straggler is a finding.
- **NO workarounds** — fix the root cause at the right layer, or STOP and report the blocker. A conditional guard that hides a broken design path is a false pass.
- **NO fix in a language/provider-specific layer for a shared requirement** — place it at the most agnostic layer that can own it (generality-preserving).
- **NO shared-layer fix verified only where it surfaced** — run the targeted tests for the changed behavior in every consuming package (cross-surface impact rule).
- **NO cross-package or language/provider matrix tests** — each `datrix-*` package tests only its own surface; the public `datrix` repo hosts no test suite.
- **NO marking a BLOCKED/partial task as conformant** — BLOCKED is terminal; report it.
- **NO scope creep** — if fixes span 3+ unrelated subsystems, STOP after the report and propose splitting.
- **NO temp files outside `.scripts\`/`.test-output\`/`.tmp\`**.
- **NO modifying the design document** — it is the source of truth being verified against, not an editable artifact.
- **NO git restore/checkout/reset/stash/revert** — undo your own edits manually.
