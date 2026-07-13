# Task Completion Eligibility (shared) — used by /execute-tasks, /execute-tasks-parallel, /task-orchestrator

> **Governed by `.claude/skills/_shared/execution-contract.md`.**

A task is eligible for COMPLETED only when **ALL FIVE** hold. A green suite satisfies only #1 — necessary, never sufficient.

1. **Tests green for the task's package** — the gate that governs the current run (targeted per-task, full suite at the quality gate / wave gate). GREEN means `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` in the canonical `index.json` — errors count as red, never read `failed` alone.
2. **Not BLOCKED (terminal rule).** Agent status is IMPLEMENTED — never BLOCKED / FAILED / NEEDS_CONTEXT / EXPANSION_REQUIRED. A *validly* BLOCKED task can NEVER become COMPLETED, regardless of suite color. (An **invalidly** BLOCKED task — one missing the execution-contract §3 four-part proof — is not a completed task *or* a failed one: **reject it and re-dispatch**. See the orchestrator's BLOCKED-validity gate.)
3. **How-Solved is clean.** If the task's `## How Solved` contains any of `BLOCKED` / `Status: BLOCKED` / `partial` / `out of scope` / `not part of this task` / `beyond the scope` / `workaround` / `dual path` / `not yet wired` / `future migration` / `future work` / `legacy ... preserved` / `remains unchanged` / `pre-existing` / `categorically behavioral` / `environmental issue` / `should be tracked separately` / `left as-is` / `would require broader changes` / `deferred` / `not my file`, or any unmet-criterion statement → NOT complete. The self-report overrides an IMPLEMENTED status (phase-01's 01-20 was marked COMPLETED with `Status: BLOCKED` in its body — this check makes that impossible). **Rephrasing to evade this list is a worse offense than the dodge — the rule is the behavior, not the wordlist.**
4. **Design-acceptance property proven.** Run the task's `**Design acceptance property:**` check yourself (negative: old/forbidden state gone on the affected surface; positive: new path exercised). Paste command + output into How-Solved. Never trust the agent's claim. For "X replaces Y": prove Y is gone everywhere on the surface. Unprovable (or missing on a non-trivial impl/migration task) → NOT complete.
5. **Every discovered defect is dispositioned.** Each entry in the agent's `discovered_defects` is either `FIXED` (with a `file:line`) or `FILED` (with a task file path that **exists on disk** — verify it). A defect mentioned only in prose is **not** dispositioned → NOT complete. Nothing an agent found may evaporate into a footnote.

**If all 4 hold:** mark complete via the script (never edit the heading directly):
```bash
powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "{task_path}"
```
Then add `## How Solved` with mandatory proof-of-work: files created/modified (with line counts), raw test output, the design-acceptance check command + output, and key design decisions. A task without this evidence is NOT properly completed.

**If any of 2–5 fail:** do NOT run `complete.ps1`. NEVER mark complete because "the suite is green."

But note what "not complete" means: **it is a signal to go finish the work, not a status to file.** Conditions 3, 4, and 5 all describe *unfinished work*, not obstacles — a dodge phrase in How-Solved, an unproven acceptance property, or an undispositioned defect are things you resolve by **doing them**. Re-dispatch the task (or fix it yourself) and close the gap.

Mark BLOCKED/FAILED **only** when a real, executed fix attempt has genuinely failed against a proven B1–B4 blocker carrying the four-part proof (execution-contract §3) — then spawn it as a tracked follow-up task, never a footnote. An unproven BLOCKED is not an honest outcome; it is a non-answer, and it gets re-dispatched.
