---
description: Execute implementation tasks from task files — read, implement, verify, mark complete
model: claude-sonnet-4-6
disable-model-invocation: true
delegation-strategy:
  phases:
    - name: "pre_check"
      model: "haiku"
      parallelizable: false
      description: "Read task files, validate dependencies, identify quality gates"
    - name: "implement"
      model: "claude-sonnet-4-6"
      parallelizable: false
      description: "Apply code changes per task specification"
    - name: "verify"
      model: "claude-sonnet-4-6"
      parallelizable: true
      max_parallel: 5
      description: "Run targeted tests, fix all failures"
    - name: "quality_gate"
      model: "claude-sonnet-4-6"
      parallelizable: false
      description: "Run full suite directly (one per affected package) for final validation"
---

# Execute Tasks

Systematic workflow for implementing tasks from `.tasks/` phase files. Reads each task file, implements it following project standards, verifies the result, fixes all test failures, updates the task file with how it was solved, and marks it complete.

**Assumes all tests are passing before starting.** Does not capture baselines.

**Task model.** Current task sets (from `/generate-tasks` and `/operationalize-design`) are lean: each **implementation task carries its own tests** (its `## Tests` / `## Targeted Tests`), so the verify phase's targeted run already exercises the new tests — there are no separate `-tests` tasks. Independent verification lives in the **one per-package quality gate** (run as the `quality_gate` phase here). Standalone `-verify` tasks are legacy; the verification-task handling below remains so older phases that still contain them execute correctly. This skill already runs targeted tests per task and the full suite **once** in the quality gate phase — keep that split; do not add per-task full-suite runs.

## When to Use

- User provides one or more task file paths and asks to implement them
- User says "execute tasks", "implement these tasks", or "work on phase N"
- User points to a `.tasks/phase-{NN}/` directory and wants tasks completed
- After `/generate-tasks` or `/operationalize-design` has produced task files

## How to Invoke

```
/execute-tasks

TASKS:
d:\datrix\datrix-common\.tasks\phase-05\task-05-01-generator-base.md
d:\datrix\datrix-common\.tasks\phase-05\task-05-02-template-loader.md
```

Execute all tasks in a phase:
```
/execute-tasks

PHASE: d:\datrix\datrix-common\.tasks\phase-05\
```

Single task:
```
/execute-tasks

TASK: d:\datrix\datrix-common\.tasks\phase-05\task-05-01-generator-base.md
```

## Documentation Quick Reference

For complete documentation index with "When to use" guidance, see [doc_index.md](../../../../../datrix/docs/doc_index.md).

**Essential reads (MANDATORY before starting):**
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) → Core rules, STOP AND THINK principle
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md) → System architecture (operative summary)
- [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md) → Design philosophy (operative summary)

**On demand (read only when a task's package or surface needs the depth — not a blanket pre-read):**
- [architecture-overview.md](../../../../../datrix/docs/architecture/architecture-overview.md) → full architecture index + sub-docs
- [design-principles.md](../../../../../datrix/docs/architecture/design-principles.md) → full design principles

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

## Delegation Constraints

When phases are delegated to sub-agents (per the delegation-strategy metadata):

- **Shared context digest (build once, inject everywhere):** before the first delegated dispatch, build a compact digest (≤ ~400 lines) of the architecture cheat sheet, design-principles cheat sheet, ai-agent-rules core rules, and the `.project-structure.md` of each package in the task set — delegate the build to a **haiku** agent. Prepend the package-relevant slice to every delegated agent's prompt under `## Shared Architecture Context (pre-read — do not re-fetch)` so N agents do not each re-read the same docs. The digest is reference context, not a substitute for the task file or the code the agent touches.
- **max_turns:** Set `max_turns: 40` on each delegated agent. Do NOT leave agents uncapped — unbounded agents become unmonitorable.
- **Background delegation + genuine polling (NOT completion notifications):** Spawn each delegated agent with `run_in_background: true` and drive it with the **Agent Progress Polling Protocol** (read `d:\datrix\datrix\claude-config\.claude\agent-templates\agent-progress-polling-protocol.md`). Do NOT wait passively for a completion notification and do NOT assume the agent is working. Every ~5 minutes, perform a **genuine** check of each in-flight agent — its status **and** the on-disk artifacts it is supposed to be producing — and classify it (completed / progressing / stalled / errored). Record each agent's `task_id` and assigned `files_to_create`/`files_to_modify`, and snapshot those files' line counts at dispatch.
- **BLOCKED from a delegated agent → adjudicate it; never relay it, never stop on it.** Run the **Decision Adjudication Protocol, Door A** (`d:\datrix\.claude\skills\_shared\decision-adjudication-protocol.md`) — read it; it is binding:
  1. **Form check** — all four parts of the execution-contract §3 proof, substantively (verbatim error text; a fix the agent actually **wrote and ran**, as `file:line` — analysis is not an attempt; why it failed; a literal `B1`/`B2`/`B3`/`B4`). Missing any → malformed; skip to step 3.
  2. **Investigate it yourself, through the code and the docs.** A well-formed proof is still an assertion. Reproduce the error in the same context; open the `file:line` and verify the attempted fix is real and aimed at the root cause; trace the root cause yourself; read the design/architecture docs governing that surface; test the claimed B-code against what you found (legitimacy table, protocol §3). Delegate the reading and the repro if you like — **never the verdict.**
  3. **ILLEGITIMATE (the common case) → correct and re-dispatch.** Fresh agent, original task **plus** the correction packet (protocol §4): its claim quoted back, the finding that kills it (your `file:line` or command + output), what it missed, the path forward. The task is **not** failed and **not** blocked — it is still in flight. Max two such re-dispatches; on a third, do the root-cause analysis yourself and dispatch a directed implementer.
  4. **LEGITIMATE → Fable adjudication.** Spawn a **Fable** decision agent (`subagent_type: "general-purpose"`, `model: "fable"`, `effort: "high"`, `run_in_background: false`) with the protocol §5 prompt. It returns one binding decision — **A** not-actually-blocked / **B** fix-elsewhere / **C** amend-task / **D** resequence / **E** spawn-follow-up / **F** ask-user — and you **execute it** (protocol §6 table). **Only F reaches the user**; A–E keep the run moving. Verify with the `acceptance_check` it specifies.
- **A decision or conflict YOU hit → the SAME ladder, via Door B.** Contradicting designs/tasks, a design-named surface with no owning task, a task premise that is false against the code, an ambiguous fix scope after a failed fix, an ordering conflict — **all of these go to Fable, not to the user.** Investigate first (rung 1); decide if the evidence settles it (rung 2); if you genuinely cannot decide, adjudicate (rung 3). **The user is rung 4, reachable only through a Fable `F`.**
- **Question relay (surfaced at poll time):** If a poll's genuine check finds a delegated agent with **NEEDS_CONTEXT**, first try to answer it yourself from the design docs, the architecture docs, and the code — most such questions are missing information, not genuine ties. Relay via `AskUserQuestion` **with your recommendation** ONLY for the protocol's §7 closed list (a credential/account absent from the repo · an irreversible outward-facing action needing authorization · a genuine product/business call · a prohibition to be lifted), then re-dispatch the agent (background) with the answer. A **technical or design** ambiguity is never a user question — resolve it yourself, or send it to Fable. Do NOT guess answers or silently skip the agent.
- **Stalled agents:** A delegated agent whose assigned files have not changed across two consecutive polls (~10 min), or that the poll shows is hung, is investigated — `TaskStop` it and **re-dispatch** with corrective context. A hung or turn-exhausted agent is an *agent* failure, not a *task* blocker; never record it as BLOCKED. Never leave a stalled agent counted as in-flight.
- **Progress reporting:** Emit the one-line poll heartbeat each cycle, and a brief status update after each phase (or each task within a phase). Do NOT run through all phases silently and dump a wall of text at the end.
- **Test execution split:** Delegated agents run ONLY targeted tests (from each task's `## Targeted Tests` section). The orchestrator runs the full test suite once in the quality gate phase. This prevents redundant full-suite runs when multiple tasks are being processed. If a task has no targeted tests section, the agent skips test execution and reports `no_targeted_tests: true`.

<!-- PHASE: pre_check -->
## Phase 1: Pre-Execution Check

Read all task files, validate dependencies, and plan execution order.

### Steps

For each task file provided in the skill invocation:

1. **Read the task file completely**
2. **Extract metadata:**
   - Title (from `# Task {NN}-{TT}: {Title}`)
   - Dependencies (from `**Depends on:**` field in header)
   - Package (from `**Package:**` field)
   - Category (from `**Category:**` field)
3. **Check dependencies:**
   - For each dependency (e.g., `task-40-01-foo`), verify the dependency task file exists
   - Read the dependency task file and check if title starts with `# COMPLETED:`
   - If NOT completed → mark this task as BLOCKED
4. **Verify referenced files exist:**
   - Read the "Files to Review Before Starting" section
   - Check each file path exists on disk
   - If any file does not exist → mark this as a red flag (will ask user for clarification)
5. **Determine language/generator scope:**
   - From the `**Package:**` field, determine if this is Python or TypeScript
   - Check "Files to Create/Modify" — if they mix .py and .ts files, mark as scope error
6. **Identify quality gate tasks:**
   - If `**Category:** Quality Gate` → mark this task as quality_gate type
   - Quality gate tasks MUST execute LAST among all tasks for the package
7. **Identify verification tasks (legacy category — current task sets no longer emit them):**
   - If `**Category:** Verification` → mark this task as verification type
   - Verification tasks are verification-only — they check that implementation was done correctly
   - Verification tasks MUST execute AFTER their dependency implementation/test tasks (same session is fine)

### Input

Task file paths from skill invocation (provided by user as TASKS:, PHASE:, or TASK:).

### Output

JSON array of tasks in execution order — one entry per task with fields: `task_path`, `task_id`, `title`, `package`, `category`, `dependencies[]`, `language_scope`, `is_quality_gate`, `is_blocked`, `files_to_review[]`, `files_to_create[]`, `files_to_modify[]`, `red_flags[]`.

### Error Conditions

- **Dependency not completed:** Task is BLOCKED. Mark `is_blocked: true`, record which dependency is incomplete.
- **Task file does not exist:** Mark as red flag: `"Task file not found at specified path"`
- **Referenced file does not exist:** Mark as red flag: `"File to review does not exist: {path}"`
- **Mixed language scope:** Mark as red flag: `"Task mixes Python and TypeScript files"`

If ANY task has `is_blocked: true` or non-empty `red_flags[]`, STOP and report to user. Do NOT proceed to the implement phase.

### Use the TodoWrite Tool

If more than 5 tasks are provided, create a todo list before completing this phase.
<!-- END_PHASE: pre_check -->

<!-- PHASE: implement -->
## Phase 2: Implementation

For each task (sequentially, in dependency order), read the task specification and apply the required code changes.

### Input

Task metadata from pre_check phase.

### Steps

Process tasks one at a time in dependency order. For each task:

#### Step 1: Understand (Read Only — No Edits)

1. **Read the task file completely**
2. **Read ALL files listed in "Files to Review Before Starting"**
3. **Read existing code** in any files that will be modified (use Read tool)
4. **Study existing Datrix implementation patterns** — do NOT reinvent anything
5. **Search for existing functions/utilities** before writing new code (DRY principle)
6. **Check for ambiguities:**
   - If the task requirements are unclear, STOP and ask for clarification
   - Never guess or assume

**End-of-step assessment:**
- Root understanding (one sentence: what this task accomplishes)
- Files to create/modify (exact paths from task file)
- Dependencies satisfied: YES (already validated in pre_check)
- Ambiguities: NONE / {list of questions}

**If ambiguities exist — climb the ladder (`_shared/decision-adjudication-protocol.md`); the user is its LAST rung, not its first:**
- **Technical or design ambiguity** (conflicting patterns, multiple valid architectural approaches, a task premise that is false against the code) → **rung 1–2:** read the design docs, the architecture docs, and the code; most ambiguities dissolve. If the analysis is heavy, invoke the **Decision Escalation Protocol** (Opus 4.8 extra-high-effort agent) and proceed to Step 2 using its recommendation. **If that still does not settle it → rung 3: Fable** (`model: "fable"`, `effort: "high"`, Door B). Execute its decision. Never take a design ambiguity to the user.
- **Spec gap / missing input** → first try to derive it from the design docs and the code. If you cannot, that is a **rung-3 decision → Fable**, not an automatic user question.
- **Only the protocol's §7 closed list goes straight to the user** — a credential/account that exists nowhere in the repo · an irreversible outward-facing action needing authorization · a genuine product/business call · a user-set prohibition to be lifted. For those: STOP, ask **with your recommendation**, and WAIT for answers before proceeding to Step 2.

#### Step 2: Implement (Write Code)

Apply the implementation described in the task file:

1. **Create/modify files** as specified in "Files to Create/Modify"
2. **Follow all code skeletons, type hints, and patterns** from the task file
3. **Check for logic map markers:**
   - Before modifying any function or class, search for `@canonical`, `@pattern`, `@boundary`, `@invariant` markers
   - If a marker exists on code you're modifying, update the marker summary/rules
   - If deleting marked code, remove the marker entirely
4. **Apply full type hints** on all functions
5. **Use standard logging:**
   - `logger = logging.getLogger(__name__)`
   - %-style formatting: `logger.info("event key=%s", value)`
6. **Use Jinja2 templates + formatter for code generation:**
   - Never use raw string concatenation (`code += f"class {name}:"`)
   - Use Jinja2 templates + ruff format (Python) / Prettier (TypeScript)
7. **Delete replaced functionality completely:**
   - No dead code
   - No backward-compatibility wrappers
   - One way to do each thing

**Scope discipline — expand, don't abandon** (execution-contract §4):
- The task's file list is the **expected surface, not a fence**. If the root cause lies outside it, **follow it and fix it there**, then report the expansion under `scope_expansion`.
- Growing beyond the task's estimate is **not** a stopping condition — an estimate is a prediction, not a permission slip.
- Do NOT make unrelated "improvements" to surrounding code. (Following a root cause is not an improvement — it is the job.)

**STUCK protocol — fix it; BLOCKED is a claim you must prove** (execution-contract §1–§3):
- **Your default outcome is: the problem is fixed.** Not investigated, not reported.
- **These are NOT blockers — they are the work:** missing dependency (**implement it**), missing file (**create it**), patterns unclear (**read more**), root cause unclear (**keep reading**), scope grew (**do the work**), failure is pre-existing (**it's yours now**), lives in another package (**go fix it there**), no test covers it (**write one**).
- **Design ambiguity → escalate, don't stop.** Escalation (`_shared/decision-escalation-protocol.md`) is how you *keep going*. Returning BLOCKED on a technical ambiguity without escalating first is an invalid report.
- **A valid BLOCKED needs all four:** verbatim error text; the fix you actually wrote and ran (`file:line` — analysis alone is **not** an attempt); why it failed; and the `B1`/`B2`/`B3`/`B4` code. **Missing any → the report is rejected and the task is re-dispatched to you.**
- Writing `pass`, `NotImplementedError`, empty method bodies, or trivial stubs that satisfy type checkers but do nothing is the **worst** outcome — invisible debt that wastes future sessions.
- **An unproven BLOCKED is the second-worst** — it burns a whole turn and produces nothing. A *proven* blocker is a fact; a *fixed* problem is the job.

**Partial completion is NOT completion:**
- If the task says "delete old path, use new path" and you keep both paths → task is NOT complete
- If a dependency (e.g., executor) has `NotImplementedError` and you work around it with legacy code → mark BLOCKED, not COMPLETED
- If you implement a checker/validator but its checks always return true or are placeholder logic → task is NOT complete
- The test for "is this complete?" is: does the code do what the task's acceptance criteria specify, without workarounds, fallbacks, or dual paths?

**Anti-patterns to avoid:**
- NO `dict.get(key, None)` — raise explicit errors
- NO `type_map.get(t, "Any")` — raise on unknown types
- NO bare `except: pass` — always log and re-raise
- NO `# TODO` / `pass` — implement completely
- NO `-> T | None` error returns — raise descriptive errors
- NO mocks/fakes in tests (`MagicMock`, `Mock`, `patch`, `SimpleNamespace`)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

**Best practices:**
- Fail fast and loud: `raise ExplicitError(f"message with context")`
- Provide helpful messages: `"Not found. Available: [...]"`
- Apply full type hints: `def foo(x: str) -> int:`
- Use immutable models: `ConfigDict(frozen=True)`
- Write comprehensive tests (include error and success cases)

#### Step 3: Mark Implementation Complete

For each task, record:
- Files created (list of paths)
- Files modified (list of paths)
- Key design decisions made

**Quality gate tasks:**
Quality gate tasks (identified by `**Category:** Quality Gate`) are verification-only — they have NO implementation step. Skip Step 2 for quality gate tasks.

**Verification tasks:**
Verification tasks (identified by `**Category:** Verification`) are verification-only — they have NO implementation step. Skip Step 2 for verification tasks. They run their own checklist in the verify phase.

### Input Format

For each task:
```json
{
  "task_path": "...",
  "task_id": "...",
  "is_quality_gate": false
}
```

### Output Format

For each task:
```json
{
  "task_path": "d:\\datrix\\.tasks\\phase-40\\task-40-01.md",
  "task_id": "task-40-01",
  "status": "implemented",
  "files_created": ["d:\\datrix\\.claude\\docs\\skill-delegation-schema.md"],
  "files_modified": [],
  "design_decisions": [
    "Schema enforces self-containment requirement for phase prompts",
    "Phase taxonomy table provides clear Haiku/Sonnet/Opus mapping"
  ],
  "ambiguities_encountered": []
}
```

OR (for quality gate):
```json
{
  "task_path": "...",
  "task_id": "...",
  "status": "skipped_implementation",
  "reason": "Quality gate task (verification-only)"
}
```

### Abort Conditions

STOP immediately if:
- Modified more than **double** the files estimated by the task AND the expansion is not a root-cause follow (execution-contract §4: following the root cause outside the expected file list is the default, not an abort — report it under `scope_expansion`; unrelated "improvements" are what this bound catches)
- Ambiguities survive the adjudication ladder (a Fable **F**, or a §7 closed-list item the user must answer)

On abort, report what was completed, what failed, and what cannot proceed.

### Handling Ambiguity

- Never guess or assume when requirements are unclear
- Never make design decisions on behalf of the user — ask first
- If a file referenced in the task does not exist at the given path, STOP and ask
- If the task contradicts existing code patterns, STOP and ask which approach to follow
<!-- END_PHASE: implement -->

<!-- PHASE: verify -->
## Phase 3: Verification

For each task (in parallel, up to 5 tasks concurrently), run targeted tests and fix all failures. If the first fix attempt fails, escalate immediately to Opus 4.8 at extra-high effort (Decision Escalation Protocol).

**Assumes all tests were passing before implementation started.**

### Input

Task metadata + implementation results.

For each task:
```json
{
  "task_path": "...",
  "task_id": "...",
  "implementation": {"files_created": [...], "files_modified": [...]},
  "is_quality_gate": false
}
```

### Steps

#### Step 1: Identify Required Tests

**Documentation-only tasks — skip verification.**

For tasks that modified code:

1. **Determine test scope:**
   - Read task file's `## Targeted Tests` section
   - Targeted tests exist AND task is NOT quality gate → run the targeted tests (below)
   - NO targeted tests → run NO per-task tests; record `no_targeted_tests: true`. Do NOT substitute a per-task full suite — the Phase-4 quality gate's single full-suite run per package is the covering gate.
   - Task IS quality gate (`**Category:** Quality Gate`) → run NO tests for it. The full suite it lists is owned by Phase 4 (one run per package — running it here too is the double-suite defect); perform only the task's **static** checklist (non-trivial-implementation scan, coverage/test-quality sanity by reading the tests, How-Solved self-contradiction scan) and carry the findings into Phase 4.

2. **Execute the targeted tests yourself:**

   Batch the task's targeted files into ONE invocation — comma-separated `-Specific` runs the whole set in a single pytest session; never one invocation per file:
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path-1},{test-path-2}"
   ```
   Read the run's saved `index.json` (the runner prints its path) for the canonical result — do NOT eyeball-parse stdout. Do NOT stop to ask the user to run any test — this skill runs every test itself, targeted and full-suite alike.

   **Test-invocation rules (a PreToolUse hook hard-blocks violations):**
   - **Never pass `-NoSave`** — it hides the saved progress Jon reads. Always let results save.
   - **Never pass `-VerboseOutput`** — it burns tokens for no benefit; read the run's `index.json` / `full.log` for detail.
   - **Never call `pytest` (or `python -m pytest`) directly** — always go through `test.ps1` / `test-single.ps1`.
   - **Never run `mypy`** (or any standalone type-checker) — write fully type-hinted code, but do not invoke a type-check command; it only burns tokens/turns.

#### Step 2: Evaluate Test Results

1. **Read the canonical results from the run's `index.json`** (never a console transcript):
   - `result`, `counts.passed`, `counts.failed`, `counts.error`, `counts.skipped`
   - GREEN means `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` — a pytest error counts as red exactly like a failure
   - **When RED**, get the failing/erroring detail scripted — pass the collector the **printed** run folder (never `-Project`, which grabs the newest folder on disk):
     ```
     powershell -File "d:/datrix/datrix/scripts/test/collect-failure-data.ps1" "{printed-run-folder}"
     ```
     Its `failure-data.json` gives per-cluster representatives with traceback tails and ready `test_command`s — do not read `full.log`

2. **Evaluate results:**
   ```
   if all tests pass:
       → verification PASSED
   else:
       → verification FAILED, proceed to Step 3 (Fix Failures)
   ```

#### Step 3: Fix All Failures

If any test failures exist:

1. **Invoke fix workflow:**
   - Read failing test file
   - Understand what the test expects
   - Identify root cause of failure
   - Fix the issue (modify code, update test, or both)

2. **After each fix attempt, re-run the relevant tests yourself** — the specific failing tests (batched `-Specific`), and read the run's `index.json`. Never stop to ask the user to run a test, targeted or full-suite.

3. **Track each attempt:**

   | Attempt | What was tried | Result |
   |---------|---------------|--------|
   | 1       | {description} | {pass/fail + error} |
   | 2       | {description} | {pass/fail + error} |
   | 3       | {description} | {pass/fail + error} |

4. **Outcomes:**
   - **A fix attempt passes** → verification PASSED
   - **Two fix attempts on DISTINCT hypotheses have failed** (or the first failure already exposes a genuine design ambiguity) → invoke the **Decision Escalation Protocol** (Opus 4.8 extra-high-effort analyst with full context: task spec, both attempts, exact failures); implement its recommendation; if still failing → verification FAILED (proceed to Step 4). Do not escalate after a single mechanical miss — a second hypothesis grounded in the error text costs less than an Opus dispatch; do not grind past two failed hypotheses without escalating either.
   - **If a fix introduces additional failures** → undo your own edit manually (NO git reverts), then invoke the **Decision Escalation Protocol** before any further attempt

#### Step 4: Verification Failed (if Opus-assisted attempt also fails)

If tests still fail after the Opus-assisted attempt:

1. **Do NOT mark the task COMPLETED**
2. **Update the task file:**
   - Change title to `# FAILED: Task {NN}-{TT}: {Title}`
   - Add `## Why Failed` section immediately after title:

```markdown
## Why Failed

**Test failures after implementation (not fixed after Opus-assisted attempt):**

| Attempt | What was tried | Result |
|---------|---------------|--------|
| 1       | {description} | {error} |
| 2       | {description} | {error} |
| 3       | {description} | {error} |

**Failing tests:**
- {test_name} — {error message}

**Recommendation:** {next steps for human review}
```

3. **Do NOT proceed to mark_complete phase for this task**

#### Step 5: Mark Complete (ONLY if verification passed)

If verification PASSED:

1. **Verify files are non-trivial (anti-stub check):**
   For each file in "Files to Create", confirm:
   - File exists on disk
   - File has >10 lines of non-comment, non-import code
   - No `pass` in function/method bodies (search with grep)
   - No `NotImplementedError` in production code
   - No `# TODO` or `# FIXME` markers
   - No always-true/always-false checks that make validators or checkers functionally useless
   - No legacy/old code paths kept alongside new code when the task requires replacement
   If ANY file fails this check → do NOT mark complete. Either fix the implementation or mark BLOCKED.

2. **Verify tests prove the feature, not the gap:**
   - Tests must NOT assert `NotImplementedError` or `NotImplemented` on production code paths — that codifies the gap as "expected behavior"
   - Tests must NOT only test shallow/happy paths while leaving the core behavior untested
   - If the task requires "X replaces Y", tests must prove X works AND Y is gone — not just that the code doesn't crash

3. **Design-acceptance verification + self-contradiction check (MANDATORY — suite-green is not enough):**
   Apply conditions 3 and 4 of the shared checklist `d:\datrix\.claude\skills\_shared\completion-eligibility.md`: prove the task's `**Design acceptance property:**` with an executable negative + positive check (command + output pasted into "How Solved"; for "X replaces Y", Y is gone everywhere on the surface), and scan your "How Solved" narrative for the BLOCKED/partial/workaround/dual-path red-flag phrases. Any unproven property or red-flag phrase → the task is **not complete** and must not be marked COMPLETED. It is also **not automatically BLOCKED**: run the **Decision Adjudication Protocol** (`_shared/decision-adjudication-protocol.md`) on the underlying obstacle — investigate it, and if it survives, let the **Fable** adjudicator decide what happens instead. A task is only recorded as blocked after that adjudication, with the confirmed B-code and Fable's decision attached.

2. **Mark task as completed using the script:**
   ```bash
   powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "{task_path}"
   ```
   This changes the title from `# Task {NN}-{TT}: {Title}` to `# COMPLETED: Task {NN}-{TT}: {Title}`.

3. **Add `## How Solved` section immediately after title with **mandatory proof-of-work**:

```markdown
## How Solved

- **`{file_path}`** — {implementation summary}
- **Design decisions:** {key decisions made}
- **Test coverage:** {test summary}

### Proof of Work

**Test evidence (canonical, not raw console dumps):**
```
{run-folder path the runner printed (…/.test_results/test-results-…/)}
{index.json result + counts (passed/failed/error/skipped)}
{failing test node IDs, if any — from full.log}
```
Do NOT paste raw full pytest output — it duplicates the saved run folder and burns tokens (the same reason `-VerboseOutput` is banned). The run folder + `index.json` counts ARE the verifiable evidence; anyone can open the folder.

**Design-acceptance proof** (the invariant from `**Design acceptance property:**`, proven — not asserted):
```
{paste the negative + positive check commands AND their output —
 e.g. the grep showing the old pattern is gone, and the check showing the new path is exercised}
```

**Files created (with line counts):**
- `{file_path}` — {N} lines (non-comment, non-blank)
```

The proof-of-work section is **mandatory**. A task without its run-folder path + `index.json` counts in its "How Solved" section is NOT considered properly completed. This evidence allows independent verification without re-running the tools.

**Quality gate tasks:** mark complete via `complete.ps1` as above, then add a "How Solved" whose Proof of Work is the Phase-4 full-suite run folder + `index.json` counts per package, plus the static-checklist findings (no files created/modified).

**Verification tasks:**

Verification tasks (identified by `**Category:** Verification`) follow their own checklist defined in the task file. They do NOT implement code — they verify that implementation tasks were completed correctly. The "How Solved" section must include:
- Result of each verification checklist item (pass/fail)
- Raw pytest output
- For each file checked: line count and stub-check result
- If ANY check fails: mark the task FAILED and identify which implementation task needs rework

### Output Format

For each task:

**If verification PASSED:**
```json
{
  "task_path": "...",
  "task_id": "...",
  "status": "COMPLETED",
  "tests_run": 12,
  "tests_passing": 12,
  "tests_failing": 0,
  "failures": [],
  "fix_attempts": 0,
  "files_created": [...],
  "files_modified": [...]
}
```

**If verification FAILED:**
```json
{
  "task_path": "...",
  "task_id": "...",
  "status": "FAILED",
  "tests_run": 15,
  "tests_passing": 13,
  "tests_failing": 2,
  "failures": ["test_entity_relationships", "test_field_inheritance"],
  "fix_attempts": 3,
  "fix_attempt_log": [
    {"attempt": 1, "tried": "...", "result": "..."},
    {"attempt": 2, "tried": "...", "result": "..."},
    {"attempt": 3, "tried": "...", "result": "..."}
  ],
  "recommendation": "Review entity relationship logic. Tests expect bidirectional refs but implementation only creates forward refs."
}
```

### Checkpoint Report

After verifying each task, emit:

**If COMPLETED:**
```
CHECKPOINT — Task {NN}-{TT}: {Title}
Status: COMPLETED
Files created: {list}
Files modified: {list}
Tests: {pass}/{total} passing
```

**If FAILED:**
```
CHECKPOINT — Task {NN}-{TT}: {Title}
Status: FAILED (verification failed after Opus-assisted attempt)
Files created: {list}
Files modified: {list}
Tests: {pass}/{total} passing

Fix attempts:
1. {what was tried} — {result}
2. {what was tried} — {result}
3. {what was tried} — {result}

Failing tests:
- {test_name} — {error}

Recommendation: {next steps}
```

### Abort Conditions

STOP immediately if:
- First fix attempt failed and Opus-assisted attempt also failed
- A fix attempt introduces additional failures
- Fix reveals cascading issues in unrelated subsystems
- Test failures appear in a different package than the one being modified

On abort, report what was completed, what failed, and what remains.
<!-- END_PHASE: verify -->

<!-- PHASE: quality_gate -->
## Phase 4: Quality Gate

Run the full test suite for the affected package(s) to catch cross-task integration issues.

### Input

Verification results from all tasks:

```json
{
  "tasks": [
    {"task_id": "task-40-01", "status": "COMPLETED", "package": ".claude/"},
    {"task_id": "task-40-02", "status": "COMPLETED", "package": ".claude/"},
    {"task_id": "task-40-03", "status": "FAILED", "package": ".claude/"}
  ]
}
```

### Steps

1. **Determine affected packages:**
   - Group tasks by `package` field
   - For each unique package, prepare to run full suite

2. **For each package, identify test command:**

   **Full test suite:**
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

3. **Run the full suite yourself — one run per affected package, fired concurrently** (a single message with one Bash call per package; each package writes its own `.test_results/` folder so parallel runs do not collide). Do NOT stop and ask the user to run anything. This is the ONE full-suite run per package for the whole skill invocation — the quality-gate task's own listed suite command was already suppressed in Phase 3.

4. **Read the multi-package verdict with the gate script** (canonical `index.json` results, never stdout):
   ```
   powershell -File "d:/datrix/datrix/scripts/test/gate-verdict.ps1" -Projects {pkg1},{pkg2}
   ```
   One GREEN/RED console line per package + `OVERALL`; per-package counts and failing-test lists in its `Details:` JSON. Sanity-check each package's `run_dir` in the JSON against the runs you just fired. GREEN only when `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` — errors are red, exactly like failures (the script applies this; UNKNOWN/missing results are RED).

5. **Attribute failures (if any):**
   - For each RED package, run `collect-failure-data.ps1` on its run dir (from the gate JSON) — the clusters give the failing test files and erroring modules
   - Cross-reference each cluster's files against each task's `## Targeted Tests` section
   - Report which task likely introduced the failure

### Output Format

**If quality gate PASSED:**

```json
{
  "status": "COMPLETED",
  "packages_tested": [".claude/"],
  "total_tests": 185,
  "tests_passing": 185,
  "tests_failing": 0
}
```

Emit:
```
CHECKPOINT — Quality Gate — {package-name}
Status: COMPLETED
Tests: 185/185 passing
```

**If quality gate FAILED:**

```json
{
  "status": "FAILED",
  "packages_tested": [".claude/"],
  "total_tests": 185,
  "tests_passing": 183,
  "tests_failing": 2,
  "failures": [
    {
      "test_name": "test_phase_marker_extraction",
      "error": "AssertionError: Expected 5 phases, got 4",
      "likely_source_task": "task-40-03-refactor-execute-tasks-skill"
    }
  ]
}
```

Emit:
```
CHECKPOINT — Quality Gate — {package-name}
Status: FAILED
Tests: 183/185 passing

Failures:
- test_phase_marker_extraction — AssertionError: Expected 5 phases, got 4
  Likely source: Task 40-03 (Refactor /execute-tasks Skill for Delegation)

Recommendation: Re-run task-40-03 with /fix-tests, then re-run quality gate.
```

### Notes

- Quality gate runs AFTER all individual task verifications
- It catches integration issues that might not appear in targeted tests
- If quality gate fails, report which tasks likely introduced the failures
<!-- END_PHASE: quality_gate -->

## Final Report

After all phases complete, report only essential status:

```
Tasks completed: {N}/{total}
Tasks failed: {N}

Completed:
- Task {NN}-{TT}: {Title}
- Task {NN}-{TT}: {Title}

Failed (if any):
- Task {NN}-{TT}: {Title} — {why}
```

## Decision Adjudication Protocol (the one ladder)

Read and follow `d:\datrix\.claude\skills\_shared\decision-adjudication-protocol.md`. **Every** decision you cannot make climbs it:

> **1 INVESTIGATE** (read the code and the docs yourself) → **2 DECIDE** (if the evidence settles it, decide and act) → **3 ADJUDICATE** (a **Fable** adjudicator — `model: "fable"`, `effort: "high"` — decides; binding) → **4 ASK THE USER** (**only** on a Fable **F**).

Two entry doors converge on it:
- **Door A — a delegated agent reports BLOCKED.** Never stop on it, never relay it. Investigate the claim yourself; bogus (the common case) → correct and re-dispatch; confirmed → Fable. A four-part proof is not true just because it has four parts.
- **Door B — a decision or conflict YOU hit.** Contradicting designs, an unowned invariant surface, a false task premise, an ambiguous fix scope, an ordering conflict. **These go to Fable too** — they are not user questions.

**Fable is not the blocker door; it is the decision door.** Only the protocol's §7 closed list reaches the user directly: absent credential · irreversible outward-facing action · genuine product call · prohibition to lift.

## Decision Escalation Protocol (rungs 1–2)

Read and follow `d:\datrix\.claude\skills\_shared\decision-escalation-protocol.md` — it defines how you investigate and decide (technical design ambiguity in Step 1, failed first fix with unclear root cause, systemic/cascading failures, architectural conflicts) vs. not (obvious fixes → fix directly), the exact Opus 4.8 xhigh agent parameters + prompt, and the implement-exactly-what-Opus-recommended rule. **Escalation is not an exit — it is how you keep going.** Missing dependencies/files/prereqs and unclear root causes are **work**, not blockers: implement, create, keep reading.

**If the Opus analysis does not settle it, you go to rung 3 (Fable) — not to the user.** Opus can recommend "ask the user"; it cannot route you there. Only Fable's **F** can.

---

## Anti-Patterns

- **NO relaying a BLOCKED report** — a delegated agent's BLOCKED is a claim, not a verdict, and the agent that hit the wall is the party least able to see over it. Investigate it yourself through the code and the docs; correct the agent if it is bogus; route it to a **Fable** adjudicator if it is real (`_shared/decision-adjudication-protocol.md`, Door A). Passing an unexamined blocker up to the user is the skill doing nothing.
- **NO taking a decision to the user that Fable has not seen** — the user is rung 4, reachable only through a Fable **F**. Every conflict *you* hit goes to Fable via Door B. The pull to ask the user is strongest exactly when the decision is *above any single task* — that feeling is the trap, not the signal. Asking the user is not the safe default; it is a rung you must earn.
- **NO assuming a delegated agent is working** — when a phase is delegated to a background sub-agent, drive it with the Agent Progress Polling Protocol: a genuine status + on-disk artifact check every ~5 minutes. Never report an agent as "in progress" without that evidence, and never rely on a completion notification to learn it finished.
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

