# Decision Escalation Protocol (shared) — used by /execute-tasks and /execute-tasks-parallel

When execution reaches a genuine design or architectural decision — multiple valid approaches, root cause unclear after investigation, or ambiguous fix scope — escalate to an Opus 4.8 (extra-high effort) agent **before** asking the user or marking a task failed.

**Escalation is not an exit — it is how you KEEP GOING.** Under the execution contract (`execution-contract.md`), returning BLOCKED on a *technical* ambiguity **without having escalated first** is an invalid report. Escalate, get the decision, implement it. The work continues.

(Note: `/task-orchestrator` does NOT use this doc — it already runs on Opus and analyzes in-context per its own reframed protocol.)

**This doc is not the blocker door.** It handles a problem **you** hit — a failing fix, an unclear root
cause, an ambiguous fix scope. When a **background agent reports BLOCKED**, that goes through
`blocker-adjudication-protocol.md` instead: you investigate the claim yourself against the code and
the docs, correct-and-re-dispatch the agent if it is bogus (the common case), and — only if the
blocker survives your investigation — hand the decision to a **Fable** adjudicator (`model: "fable"`,
`effort: "high"`), whose ruling you then execute. Never stop on an agent's BLOCKED, and never relay
one to the user unexamined.

## When to Escalate

**DO escalate for:**
- An agent returns BLOCKED or NEEDS_CONTEXT with a **technical ambiguity** (design choice, conflicting patterns, unclear root cause)
- The first fix attempt fails and root cause is unclear
- A fix introduces additional failures, suggesting a systemic root cause
- Cascading failures across unrelated code — correct fix scope is unclear
- The task conflicts with existing architecture in a way requiring architectural judgment

**Do NOT escalate for:**
- Simple errors with obvious fixes (typo, wrong import) → fix directly
- Genuine B1/B3 blockers (no credential/access; user explicitly forbade the only correct action) → these are the only things that stop work, and they need the four-part proof

**These are NOT "hard blockers" — they are WORK. Never stop for them, and never escalate them either; just do them:**
- **Missing file** → create it.
- **Missing dependency / unimplemented function you need** → implement it. (Routing *around* it is the workaround CLAUDE.md bans.)
- **Incomplete prereq task** → if it's genuinely required and unstarted, that is a *dependency-ordering* fact for the orchestrator, not a blocker for you — say so precisely, and do everything the prereq does not gate.
- **Unclear root cause** → keep reading. Escalate only *after* real investigation has genuinely deadlocked.

**Spec gaps / missing user-supplied input:** first try to derive the answer from the design docs and codebase. Ask the user only for a true B2 (two defensible designs, expensive to reverse) or a value you genuinely cannot derive — and always bring **your recommendation**, never a bare question.

## How to Escalate

Spawn a subagent via the Agent tool:

```
subagent_type: "general-purpose"
model: "opus"
effort: "xhigh"
description: "Opus decision: {brief problem description}"
```

**Opus agent prompt:**
```
You are a senior architect making a high-stakes implementation decision. Do NOT implement — analyze and recommend only.

CONTEXT:
Task: {task_id} — {title}
Objective: {what the task was supposed to accomplish}

PROBLEM:
{exact error, conflict, or ambiguity — be specific}

WHAT WAS TRIED:
{each fix attempt or approach considered, with outcome}

RELEVANT CODE (key excerpts):
{file paths and actual code snippets}

YOUR TASK:
Analyze for long-term correctness. Decide what is genuinely best for the LONG-TERM health of this production system. This is NOT a hackathon and you are NOT trying to save the day — never pick the simple or expedient option and defer the correct one to a "future" that never arrives. Do NOT suggest workarounds, band-aids, or "good enough for now" solutions. Consider:
- Root cause (not symptom)
- Impact on other components
- Consistency with existing patterns
- Long-term maintainability

Return:
1. Root cause analysis (2-3 sentences)
2. Recommended approach — concrete, step-by-step instructions
3. Exact files to modify and what changes to make
4. Why this is the right long-term choice (not the quick fix)
5. Any risks or prerequisites

Be specific. The implementing agent will follow your recommendation directly.
```

## After Opus Returns

- Implement exactly what Opus recommended with the current model — do NOT improvise beyond the recommendation
- If Opus recommends stopping and asking the user, surface Opus's full analysis as context when asking
