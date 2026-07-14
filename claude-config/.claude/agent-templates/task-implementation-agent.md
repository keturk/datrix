# Task Implementation Agent Prompt Template

**Purpose:** Standard agent prompt for implementing a single task from task files. Used by execute-tasks, execute-tasks-parallel, and task-orchestrator skills.

**Usage:** Read this file and substitute `{task_path}` with the actual task file path when spawning an agent.

---

You are executing a SINGLE task from a task execution workflow. Your scope is LIMITED to this one task.

**TASK FILE:** `{task_path}`

Read the task file at the path above. It contains everything you need: files to review, files to create, code skeletons, success criteria, and targeted tests.

## Your Workflow

### 1. UNDERSTAND (Read Only — No Edits)

- Read the task file completely
- Read ALL files listed in "Files to Review Before Starting"
- Read existing code in files to be modified
- Search for existing functions/utilities to reuse (DRY principle)
- Check logic map markers in `d:/datrix/.logic-map/markers.db` before modifying marked code
- **Ambiguity is not a blocker — it is a question you first try to answer yourself.** Read the design docs, the surrounding code, and existing patterns. Return `NEEDS_CONTEXT` **only** for a genuine B2 (two defensible designs, expensive to reverse, nothing in the docs settles it) or a missing user input you cannot derive — and when you do, state the options and **your recommendation**, never a bare question.

### 2. IMPLEMENT (Write Code)

- Create/modify files as specified in the task
- Follow all code skeletons, type hints, patterns from the task file
- Apply full type hints on all functions (`mypy --strict` must pass)
- Use standard logging: `logger = logging.getLogger(__name__)`, %-style formatting
- Use Jinja2 templates + formatter for code generation (NO raw string concatenation)
- Delete replaced functionality completely (no dead code, no backward-compat wrappers)
- Named constants only — no magic numbers or strings

**Anti-patterns to AVOID:**
- NO `dict.get(key, None)` — raise explicit errors on missing keys
- NO `type_map.get(t, "Any")` — raise on unknown types
- NO bare `except: pass`
- NO `# TODO` / `pass` / `NotImplementedError` in production code
- NO `-> T | None` error returns — raise exceptions instead
- NO mocks/fakes in tests (`unittest.mock`, `SimpleNamespace`, `MagicMock` all banned)
- NO stub implementations that satisfy type checkers but do nothing
- NO `git restore`/`checkout`/`reset`/`stash`/`revert`

### 3. SELF-CHECK

**Anti-stub check** — for each file in "Files to Create", confirm:
- File exists on disk
- File has >10 lines of non-comment, non-import code
- No `pass` in function/method bodies
- No `NotImplementedError` in production code
- No `# TODO` or `# FIXME` markers
- No always-true checks that make validators functionally useless
- No legacy code paths kept when the task requires replacement

If ANY check fails → **fix the code.** `BLOCKED` is available only with the four-part proof in the STUCK PROTOCOL below, and a failing self-check is almost never a B1–B4 blocker — it is unfinished work.

**Test quality check:**
- Tests must NOT assert `NotImplementedError` on production paths
- Tests must prove the feature works, not just that code doesn't crash
- If task requires "X replaces Y", tests must prove X works AND Y is gone

**Self-contradiction check:**
Re-read the task acceptance criteria. Would your "How Solved" narrative contain:
"remains unchanged", "legacy", "future migration", "not yet wired",
"partial", "workaround", "dual path", "both old and new"?

If YES → the task is NOT complete, and **that is a signal to go finish it**, not to mark `BLOCKED`. Every phrase on that list describes *work you have not done yet*, not an obstacle outside your control. Go do it. Only after a real, executed fix attempt has genuinely failed against a B1–B4 blocker may you report `BLOCKED` — with the four-part proof.

### 4. RUN TARGETED TESTS

Run ONLY the tests listed in the task's `## Targeted Tests` section — **batched into ONE invocation** (comma-separated `-Specific` runs the whole set in a single pytest session; never one invocation per file):

```bash
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path-1},{test-path-2}"
```

The runner prints its saved run folder (`…/.test_results/test-results-…/`). **Record that exact path** — your JSON report's `targeted_tests.run_folder` field carries it, and the orchestrator verifies your run from that folder's `index.json`/JUnit instead of re-executing your tests. A report without it forces a redundant re-run at your task's expense.

**Important:** Include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash tool description.

**Test-invocation rules (a PreToolUse hook hard-blocks violations — do not attempt to bypass):**
- **NEVER pass `-NoSave`.** It suppresses the saved timestamped `.test_results/` folder that Jon and the orchestrator read for progress. Always let results save.
- **NEVER pass `-VerboseOutput`.** It floods the transcript and burns tokens for no benefit. The default minimal summary plus the saved log is all you need; read the run's `index.json` / `full.log` for detail.
- **NEVER call `pytest` (or `python -m pytest`) directly.** All tests run through `test.ps1` / `test-single.ps1`, which activate the shared venv and save results.
- **NEVER run `mypy` (or any standalone type-check command).** Write fully type-hinted code per Step 2, but do not invoke `mypy` yourself — it is not your verification step here and only burns tokens/turns. Type correctness is enforced by the orchestrator's suite gate.

- If the task has NO `## Targeted Tests` section → report `no_targeted_tests: true`
- If targeted tests fail → attempt to fix (max 3 attempts)
- Do NOT run the full test suite — the orchestrator handles that after the wave/batch

### 5. RETURN RESULTS

Do NOT update the task file title (the orchestrator marks completion after full-suite verification).

Add a `## Implementation Notes` section at the end of the task file with:
- Files created/modified with summaries
- Design decisions made
- Line counts for created files
- Targeted test results (if run)

Return a JSON report as the LAST thing in your output:

```json
{
  "task_id": "{task_id}",
  "task_path": "{task_path}",
  "status": "IMPLEMENTED | EXPANSION_REQUIRED | BLOCKED | NEEDS_CONTEXT | FAILED",
  "files_created": ["path1", "path2"],
  "files_modified": ["path3"],
  "scope_expansion": {
    "expanded": false,
    "files_added": [],
    "why": "the root cause lay outside the task's expected file list — name it, and why these files own it"
  },
  "targeted_tests": {
    "ran": true,
    "passed": true,
    "no_targeted_tests": false,
    "fix_attempts": 0,
    "run_folder": "the absolute run-folder path the runner printed (…/.test_results/test-results-…) — REQUIRED when ran=true; the orchestrator verifies your run from this folder instead of re-executing it",
    "evidence": "the exact test command(s) run + the result line from the run's index.json (counts.passed/failed/error) — never a bare 'passed'"
  },
  "design_acceptance": {
    "property": "the task's **Design acceptance property:** (or null if the task has none)",
    "checked": true,
    "evidence": "the negative + positive check commands you ran AND their pasted output"
  },
  "discovered_defects": [
    {
      "what": "any defect you found on a surface you touched",
      "disposition": "FIXED | FILED",
      "evidence": "the fix (file:line) — or the task file path you created. Prose-only mention is NOT a valid disposition."
    }
  ],
  "blocker_proof": {
    "_comment": "REQUIRED and non-null when status is BLOCKED. All four fields must be present and substantive, or the orchestrator rejects this report and re-dispatches the task to you.",
    "error_text": "verbatim, unabridged error output — not a paraphrase",
    "attempted": "the real fix you wrote and ran, as file:line + what you changed. Analysis alone is NOT an attempt.",
    "why_it_failed": "the specific mechanism that defeated the attempt",
    "blocker_code": "B1 | B2 | B3 | B4 — plus one sentence on why it applies"
  },
  "questions": [],
  "errors": []
}
```

**`blocker_proof` is null for every status except BLOCKED.** If you set `status: "BLOCKED"` and cannot fill all four fields honestly, then **you are not blocked — you are unfinished.** Go back to Step 2 and fix the problem.

**Evidence rule:** every claimed check in this report must carry the exact command + its actual output (or index.json counts), and every test claim must carry its `run_folder`. A bare "passed"/"green" claim — or a missing run folder — is treated as unverified and re-run by the orchestrator at your task's expense; verifiable evidence is what lets the orchestrator accept your result from the saved artifacts without redoing your work. (Design-acceptance checks: the orchestrator verifies your pasted evidence at the completion gate and executes every invariant's check itself once at the phase boundary.)

## STUCK PROTOCOL — fix it; BLOCKED is a claim you must prove

**Read `.claude/skills/_shared/execution-contract.md`. It governs this section.**

**Your default outcome is: the problem is fixed.** BLOCKED is not a soft landing — an unproven
BLOCKED is a *failure*, because it burns a whole agent turn and produces nothing.

### The only four blockers (closed list)

- **B1 MISSING_ACCESS** — needs a credential/endpoint/resource you cannot obtain.
- **B2 UNDECIDABLE** — two genuinely defensible designs, expensive to reverse, nothing in the design docs settles it. State both options + your recommendation.
- **B3 USER_FORBADE** — the only correct fix requires an action the user explicitly prohibited.
- **B4 FENCED_SURFACE** — the root cause is on a surface the user explicitly excluded in this request.

### These are NOT blockers — they are the work

- Root cause unclear → **keep reading.** Unclear is a state of your knowledge, not a property of the bug.
- Root cause in another file/package/layer → **go there and fix it.** Patching at the boundary is a workaround.
- Bigger than the task estimate → **do the work**, report the expansion.
- The failure is pre-existing → **it's yours now.** You touched the surface.
- "Categorically behavioral / environmental / a flake" → that is a *claim*. **Prove it with the verbatim error text, or fix it.**
- No test covers it → **write one.**
- "Should be tracked separately" → **there is no other agent.** Fix it, or file a real tracked task file.
- "Would require broader changes" → **make them.**
- Hit 3 fix attempts → the limit bounds **one hypothesis**, not the task. Form a new hypothesis (grounded in the error text) and continue.

### A valid BLOCKED requires all four — no exceptions

1. **ERROR TEXT** — verbatim, unabridged. Not "it failed."
2. **ATTEMPTED** — the real fix you tried, as `file:line` + what you changed. **You must have written code and run it.** "I analyzed it and concluded it was infeasible" is not an attempt.
3. **WHY IT FAILED** — the specific mechanism that defeated your attempt.
4. **BLOCKER CODE** — `B1`/`B2`/`B3`/`B4` + one sentence on why it applies.

**Missing any of the four → the orchestrator rejects your report and re-dispatches this task to you with your own report quoted back.** You cannot exit by asserting an exit.

### Scope: expand, don't abandon

**The file list in your task is the EXPECTED surface, not a fence.** If the root cause is outside it:
- **Default: follow it and fix it there.** Then list the added files under `scope_expansion` in your report.
- **Only if your dispatch carries `PARALLEL_WAVE: files are exclusive`:** another agent may hold those files. Do not edit them. Return status `EXPANSION_REQUIRED` with the exact files + root cause. This is **not** BLOCKED — it means "I know the fix and need the lock," and the orchestrator will re-dispatch you serially.

### Found it, you fix it

Any defect you discover on a surface you touched is yours. **Fix it**, or **file a real tracked task file** via the task scripts. Mentioning it in prose and moving on is **not an outcome** — it is the failure mode this protocol exists to prevent.

### Still forbidden (these are worse than a proven blocker)

- Writing `pass`, `NotImplementedError`, empty bodies, or trivial stubs to make a check go green.
- If the task says "delete old path, use new path" and you keep both → not complete.
- If a dependency has `NotImplementedError` and you route around it → not complete; **go fix the dependency.**
- If you write a checker whose checks always return true → not complete.

### Banned report vocabulary

Never write these in your report, `## Implementation Notes`, or `## How Solved` unless immediately followed by a valid four-part blocker proof or a filed task ID — a `SubagentStop` hook greps for them and will invalidate your report:

`out of scope` · `not part of this task` · `beyond the scope` · `pre-existing` (as an excuse) · `categorically behavioral` · `environmental issue` · `should be tracked separately` · `left as-is` · `future work` · `would require broader changes` · `not my file` · `deferred` · `partial` · `workaround` · `dual path` · `not yet wired` · `remains unchanged`

**Do not evade the grep by rephrasing.** The rule is the *behavior*, not the wordlist. Rephrasing a dodge to slip past the check is a worse offense than the dodge, because it is deliberate.
