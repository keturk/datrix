# Task Completion Eligibility (shared) — used by /execute-tasks, /execute-tasks-parallel, /task-orchestrator

A task is eligible for COMPLETED only when **ALL FOUR** hold. A green suite satisfies only #1 — necessary, never sufficient.

1. **Tests green for the task's package** — the gate that governs the current run (targeted per-task, full suite at the quality gate / wave gate). GREEN means `result == "PASSED"` AND `counts.failed == 0` AND `counts.error == 0` in the canonical `index.json` — errors count as red, never read `failed` alone.
2. **Not BLOCKED (terminal rule).** Agent status is IMPLEMENTED — never BLOCKED / FAILED / NEEDS_CONTEXT. A BLOCKED task can NEVER become COMPLETED, regardless of suite color.
3. **How-Solved is clean.** If the task's `## How Solved` contains any of `BLOCKED` / `Status: BLOCKED` / `partial` / `out of scope` / `workaround` / `dual path` / `not yet wired` / `future migration` / `legacy ... preserved`, or any unmet-criterion statement → NOT complete. The self-report overrides an IMPLEMENTED status (phase-01's 01-20 was marked COMPLETED with `Status: BLOCKED` in its body — this check makes that impossible).
4. **Design-acceptance property proven.** Run the task's `**Design acceptance property:**` check yourself (negative: old/forbidden state gone on the affected surface; positive: new path exercised). Paste command + output into How-Solved. Never trust the agent's claim. For "X replaces Y": prove Y is gone everywhere on the surface. Unprovable (or missing on a non-trivial impl/migration task) → NOT complete.

**If all 4 hold:** mark complete via the script (never edit the heading directly):
```bash
powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "{task_path}"
```
Then add `## How Solved` with mandatory proof-of-work: files created/modified (with line counts), raw test output, the design-acceptance check command + output, and key design decisions. A task without this evidence is NOT properly completed.

**If any of 2–4 fail:** do NOT run `complete.ps1`. Record the unmet condition, mark BLOCKED/FAILED honestly, and spawn the blocker as a tracked follow-up task — never a footnote. NEVER mark complete because "the suite is green."
