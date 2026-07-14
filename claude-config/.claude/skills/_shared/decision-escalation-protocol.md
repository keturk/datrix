# Decision Escalation Protocol (shared) — used by /execute-tasks and /execute-tasks-parallel

When execution reaches a genuine design or architectural decision — multiple valid approaches, root cause unclear after investigation, or ambiguous fix scope — escalate to an Opus 4.8 (extra-high effort) agent **before** marking a task failed.

**Escalation is not an exit — it is how you KEEP GOING.** Under the execution contract (`execution-contract.md`), returning BLOCKED on a *technical* ambiguity **without having escalated first** is an invalid report. Escalate, get the decision, implement it. The work continues.

(Note: `/task-orchestrator` does NOT use this doc — it already runs on Opus and analyzes in-context per its own reframed protocol.)

## Where this doc sits on the Adjudication Ladder

`decision-adjudication-protocol.md` defines the one ladder every decision climbs:
**1 INVESTIGATE → 2 DECIDE → 3 ADJUDICATE (Fable) → 4 ASK THE USER.**

**This doc is rungs 1–2**: how you investigate and reach a decision yourself, using an Opus analyst
when the analysis is heavy. It is *not* an exit and it is *not* a route to the user.

**If the Opus analysis does NOT settle it — you still cannot decide — you go to rung 3, not to the
user.** Spawn a **Fable** adjudicator (`model: "fable"`, `effort: "high"`) per
`decision-adjudication-protocol.md` §5 and execute its decision. The user is rung 4, reachable **only**
when Fable returns decision **F (ASK_USER)**, or for the narrow closed list in that doc's §7
(credential you don't have · irreversible outward-facing action needing authorization · genuine
product call · a prohibition that must be lifted).

**A delegated agent's BLOCKED report** does not enter here at all — it enters
`decision-adjudication-protocol.md` at Door A: investigate the claim yourself against the code and the
docs, correct-and-re-dispatch the agent if it is bogus (the common case), and — only if the blocker
survives your investigation — hand the decision to Fable, whose ruling you then execute. Never stop on
an agent's BLOCKED, and never relay one to the user unexamined.

## When to Escalate

**DO escalate for:**
- An agent returns BLOCKED or NEEDS_CONTEXT with a **technical ambiguity** (design choice, conflicting patterns, unclear root cause)
- **Two fix attempts on DISTINCT hypotheses have failed** — or the first failure already exposes a genuine design-level ambiguity. (Do not escalate a single mechanical miss: a second hypothesis grounded in the error text costs less than an Opus dispatch. Do not grind past two failed hypotheses without escalating either — that is the loop this protocol exists to break.)
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

**Spec gaps / missing user-supplied input:** first try to derive the answer from the design docs and codebase. If you cannot derive it, that is **not** an automatic user question — a spec gap with two defensible readings is a rung-3 decision and goes to **Fable** (`decision-adjudication-protocol.md` §5). Only the closed §7 list reaches the user directly: a credential/account that exists nowhere in the repo · an irreversible outward-facing action needing authorization · a genuine product/business call · a user-set prohibition that must be lifted. Whenever you do reach the user, bring **your recommendation** — never a bare question.

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
You are a senior architect making a high-stakes implementation decision. Analyze and recommend. Exception — TRIVIAL FIX: if the correct fix turns out to be trivial (a few lines in a single file, no design trade-off), APPLY it yourself, run the specific failing test via test.ps1 -Specific, and return the diff + the run's index.json result alongside your analysis — do not round-trip a one-line edit through another dispatch. Anything larger: recommend only, do NOT implement.

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

- **Opus reached a decision** → implement exactly what it recommended with the current model. Do NOT improvise beyond the recommendation. The work continues.
- **Opus applied a trivial fix itself** (per the trivial-fix exception) → verify its returned diff against the no-workaround rules and confirm the test result from the run's `index.json`; then continue. Its self-report alone is not sufficient.
- **Opus did NOT settle it** (it reports a genuine tie, or its recommendation fails when implemented, or it concludes the plan cannot be executed as written) → **go to rung 3: adjudicate.** Spawn a **Fable** adjudicator (`model: "fable"`, `effort: "high"`) per `decision-adjudication-protocol.md` §5, handing it Opus's full analysis as part of the packet, and **execute Fable's decision** (§6).
- **Opus recommends "stop and ask the user"** → that is a recommendation, not a routing instruction. **Opus does not have the authority to send you to the user; only Fable does.** Take it to Fable with Opus's analysis attached. If Fable returns **F (ASK_USER)**, you ask — with Fable's exact question, options, and recommendation. If Fable returns A–E, you execute that instead.
