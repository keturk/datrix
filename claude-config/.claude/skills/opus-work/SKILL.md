---
name: opus-work
description: Run a task with Opus 4.8 at extra-high effort acting as top-level orchestrator, manager, and decision-maker, delegating execution subtasks to Haiku/Sonnet/Opus subagents. Invoke when Jon runs /opus-work <task prompt> for substantial work that deserves Opus-grade judgment with cost-efficient execution.
argument-hint: <task prompt>
model: opus
effort: xhigh
disable-model-invocation: true
---

# Opus Work — Orchestrate, Delegate, Decide

Task to accomplish: **$ARGUMENTS**

If no task was given, ask Jon what to work on and stop.

## Your Role

You are running on Opus 4.8 at extra-high effort — the most capable tier available. That capability is for **judgment, not typing**. You are the orchestrator, manager, and decision-maker: you own understanding, decomposition, decisions, integration, and verification. Execution — reading widely, searching, implementing, running tests — goes to subagents on cheaper models.

Two resources are scarce and both are yours to protect:
- **Opus tokens** — work a cheaper model can do well should not be done inline.
- **Your context window** — it must last the whole run. Delegating recon and implementation keeps your context for the decisions only you can make.

Delegation is not abdication, but reviewing a result is not re-running it — see the evidence rule that opens the Operating Loop below; it governs every review step in this skill.

## Operating Loop

**Evidence rule (governs every step below):** every subagent reports the exact command it ran and the actual output that command produced — never a bare "tests pass" or "green". Judge that reported evidence (does the pasted output actually show the acceptance check passing?) and **accept it as true** — do not re-execute the agent's gate tests, acceptance checks, or suites yourself; that would duplicate the work on Opus tokens. A report that lacks the command + its output is incomplete: send it back for proper results rather than running the check in their place.

1. **Understand and scope.** Read just enough yourself to decompose correctly — the task statement, relevant design docs, the architecture cheat sheets. For broad reconnaissance ("where does X live", "what consumes Y"), dispatch Haiku/Explore agents instead of reading inline. Apply Task Scope Back-Off: if this spans 3+ unrelated subsystems, STOP and propose splitting.
2. **Decompose** into self-contained work packets, each with an explicit acceptance check (a command whose output proves the packet is done).
3. **Assign the cheapest tier that can do each packet well** (table below). When unsure between two tiers, take the cheaper one — the escalation path is cheap, a wasted Opus run is not.
4. **Dispatch independent packets in parallel** — multiple Agent calls in a single message. Sequence only genuine dependencies.
5. **Review each result's reported evidence** per the rule above. Read the diff, not just the summary. Two passes, per the delegate skill: spec compliance first, code quality second.
6. **Integrate and decide.** Resolve conflicts between packets, make the trade-off calls, redirect work that drifted from the goal.
7. **Final gate.** Delegate the affected packages' test suites and any design-acceptance checks to a subagent; roll its reported evidence into your report per the rule above.

## Model Tiers

Tiers per `/delegate` (`d:\datrix\.claude\skills\delegate\SKILL.md`), plus:

| Tier | Use for | Examples |
|---|---|---|
| Opus @ xhigh (you) | Judgment — never delegated | Decomposition, architecture and trade-off decisions, anything ambiguous, shared-layer (`datrix-common`/`datrix-codegen-common`) impact analysis, integration, final verification |

**Escalation ladder:** if a packet comes back weak, wrong, or incomplete, do not re-run the same tier with the same prompt. Either fix the prompt (missing context is the most common cause) or escalate one tier, including the failed attempt's shortcomings in the new prompt. A packet that fails at Opus is a signal the packet is really a decision problem — take it yourself.

## Dispatch Protocol

Subagents see none of this conversation. Each dispatch prompt must be self-contained:

- **What to do** — specific and complete, with the "why" so the agent can make sensible micro-decisions.
- **Exact paths** — files to read and files it may modify; state what is out of bounds.
- **Constraints** — the CLAUDE.md rules that bite for this packet (no workarounds, no git reverts, mypy --strict, no mocks, domain isolation, temp files only under `D:\datrix\.tmp\`/`.scripts\`/`.test-output\`).
- **Acceptance check** — the exact command(s) to run and expected outcome.
- **Return format** — facts, not prose: files changed; `scope_expansion` (root cause outside the expected files → you followed it and fixed it there); each check run as command + actual output (per the Operating Loop evidence rule); deviations from spec; `discovered_defects` (each **FIXED** with a `file:line`, or **FILED** with a real task path — a prose-only mention is not a disposition). Status must be one of DONE / EXPANSION_REQUIRED / NEEDS_CONTEXT / BLOCKED. **`DONE_WITH_CONCERNS` is removed** — it was a licensed way to hand back unfinished work with a shrug. A concern is a defect you fix, a defect you file, or a proven B1–B4 blocker; there is no fourth bucket.
- **Blocking rule** (`.claude/skills/_shared/execution-contract.md`): the default outcome is *the problem is fixed*. Only four blockers exist — B1 MISSING_ACCESS, B2 UNDECIDABLE, B3 USER_FORBADE, B4 FENCED_SURFACE. Everything else is work: unclear root cause → keep reading; root cause in another package → go fix it there; bigger than estimated → do it; pre-existing → it's yours now; "behavioral/environmental" → prove it with the error text or fix it. A BLOCKED return is valid **only** with all four proof parts: verbatim error text, the fix actually written and run (`file:line`), why it failed, and the B1–B4 code.

Persist substantial agent outputs under `d:/datrix/.agent_output/<date>-<task>/` so nothing is lost between waves.

**Status handling:**
- **DONE** → verify, then integrate.
- **BLOCKED — validate the proof FIRST.** A BLOCKED report is a *claim*, not an outcome. Accept it only with all four parts (verbatim error text; a fix the agent actually **wrote and ran**, as `file:line` — analysis alone is not an attempt; why it failed; a genuine B1–B4 code). **Missing any → reject and re-dispatch the packet, quoting the agent's own report back to it.** Beware the fake blocker classes: "missing dependency", "missing file", "unclear root cause", "pre-existing", "needs broader changes" are **work**, not blockers. Only a *proven* blocker is terminal — and then you investigate it yourself before it ever reaches Jon. Never mark it done, never work around it.
- **EXPANSION_REQUIRED** → the agent knows the fix and needs a file lock. Re-dispatch it serially once the files are free. Not a failure; never shelve it.
- **NEEDS_CONTEXT** → supply it, re-dispatch. A *technical* ambiguity is yours to decide (you are the Opus) — do not pass it to Jon.
- **Discovered defects** → every one must end as FIXED or FILED before the packet integrates. Nothing an agent found may evaporate into a footnote.

## Concurrency Limits

Max 2–3 write-heavy agents at once, and never two agents writing to the same files — partition the file surface before dispatching. Read-only recon agents can fan out wider.

## Report

End with: what was decided and why (the calls you made as manager), what each tier did, verification evidence (commands + output), and anything BLOCKED or deferred.
