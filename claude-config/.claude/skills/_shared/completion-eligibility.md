# Task Completion Eligibility (shared) — used by /execute-tasks, /execute-tasks-parallel, /task-orchestrator

> **Governed by `.claude/skills/_shared/execution-contract.md`.**

A task is eligible for COMPLETED only when **ALL FIVE** hold. A green suite satisfies only #1 — necessary, never sufficient.

1. **Tests green for the task's package** — the gate that governs the current run (targeted per-task and at wave gates; the full suite runs at the quality-gate phase / phase boundary, never per-task). GREEN means `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` in the canonical `index.json` — errors count as red, never read `failed` alone. Verified agent run artifacts (the reported run folder's `index.json`/JUnit, per the executor's acceptance rules) count as the run's result — re-execute only what artifacts cannot prove.
2. **Not BLOCKED (terminal rule).** Agent status is IMPLEMENTED — never BLOCKED / FAILED / NEEDS_CONTEXT / EXPANSION_REQUIRED. A *validly* BLOCKED task can NEVER become COMPLETED, regardless of suite color. (An **invalidly** BLOCKED task — one missing the execution-contract §3 four-part proof — is not a completed task *or* a failed one: **reject it and re-dispatch**. See the orchestrator's BLOCKED-validity gate.)
3. **How-Solved EXISTS, and is clean.**

   **PRESENCE FIRST — an absent `## How Solved` section FAILS this condition.** It is not "clean by default." This is not hypothetical: in phase 31 the orchestrator gated all 12 tasks with `awk '/^## How Solved/,0' file | grep -E "<dodge words>"` and every one printed **clean** — because the section did not exist, so `awk` emitted nothing and `grep` matched nothing. A check that cannot fail manufactures confidence; it is worse than no check. **Prove the section is present BEFORE you grep it, and treat "no section" as a hard fail:**
   ```bash
   grep -q "^## How Solved" "$task_file" || echo "FAIL: no ## How Solved — task is NOT complete"
   ```
   The same trap applies to every "grep for bad things" gate in this repo: **an empty haystack always passes.** Whenever you scan for forbidden content, first assert the thing you are scanning actually exists and is non-empty.

   **Then, cleanliness.** If the task's `## How Solved` contains any of `BLOCKED` / `Status: BLOCKED` / `partial` / `out of scope` / `not part of this task` / `beyond the scope` / `workaround` / `dual path` / `not yet wired` / `future migration` / `future work` / `legacy ... preserved` / `remains unchanged` / `pre-existing` / `categorically behavioral` / `environmental issue` / `should be tracked separately` / `left as-is` / `would require broader changes` / `deferred` / `not my file`, or any unmet-criterion statement → NOT complete. The self-report overrides an IMPLEMENTED status (phase-01's 01-20 was marked COMPLETED with `Status: BLOCKED` in its body — this check makes that impossible). **Rephrasing to evade this list is a worse offense than the dodge — the rule is the behavior, not the wordlist.**
4. **Design-acceptance property proven — evidence-first, executed once at the governing conformance gate.** The task's `**Design acceptance property:**` check (negative: old/forbidden state gone on the affected surface; positive: new path exercised) must be executed and its command + output present in How-Solved. At task-completion time, **verify the agent's pasted evidence** (the commands are real, the outputs consistent with the tree and artifacts you read) and **re-execute the check yourself only when the evidence is missing, unparseable, or contradicted** — never accept a bare claim. The **authoritative execution** happens exactly once per phase at the governing conformance gate (the orchestrator's phase-boundary Step A2; the package quality gate's design-conformance scan in non-orchestrated runs), across the invariant's FULL surface set — that execution is never skipped on the strength of earlier evidence. For "X replaces Y": prove Y is gone everywhere on the surface. Unprovable (or missing on a non-trivial impl/migration task) → NOT complete.
5. **Every discovered defect is dispositioned.** Each entry in the agent's `discovered_defects` is either `FIXED` (with a `file:line`) or `FILED` (with a task file path that **exists on disk** — verify it). A defect mentioned only in prose is **not** dispositioned → NOT complete. Nothing an agent found may evaporate into a footnote.

**If all 5 hold:** mark complete via the script (never edit the heading directly):
```bash
powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "{task_path}"
```
Then add `## How Solved` with mandatory proof-of-work: files created/modified (with line counts), the test run-folder path + its `index.json` counts + failing node IDs if any (NOT a raw console dump — the saved run folder is the verifiable evidence), the design-acceptance check command + output, and key design decisions. A task without this evidence is NOT properly completed.

**If any of 2–5 fail:** do NOT run `complete.ps1`. NEVER mark complete because "the suite is green."

But note what "not complete" means: **it is a signal to go finish the work, not a status to file.** Conditions 3, 4, and 5 all describe *unfinished work*, not obstacles — a dodge phrase in How-Solved, an unproven acceptance property, or an undispositioned defect are things you resolve by **doing them**. Re-dispatch the task (or fix it yourself) and close the gap.

Mark BLOCKED/FAILED **only** when a real, executed fix attempt has genuinely failed against a proven B1–B4 blocker carrying the four-part proof (execution-contract §3) — then spawn it as a tracked follow-up task, never a footnote. An unproven BLOCKED is not an honest outcome; it is a non-answer, and it gets re-dispatched.
