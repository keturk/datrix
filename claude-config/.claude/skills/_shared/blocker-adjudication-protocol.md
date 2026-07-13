# Blocker Adjudication Protocol (shared)

**Used by `/task-orchestrator`, `/execute-tasks`, and `/execute-tasks-parallel`. It governs what the
skill-running agent does when a background agent reports BLOCKED.**

Read this alongside `execution-contract.md` (§1 the closed blocker list, §3 the four-part proof).

---

## 0. The rule this protocol exists to enforce

**A background agent's BLOCKED report never stops the skill.** Not once, not ever. A BLOCKED report
is *an input to your investigation*, not an outcome you record and move past.

There are exactly two things that can happen to a BLOCKED report:

1. **You disprove it** → you correct the agent and it finishes the task.
2. **You confirm it** → a **Fable adjudicator** decides what happens instead, and you carry out that
   decision.

There is no third branch. "Agent said BLOCKED, so the task is BLOCKED" is a non-answer — it means the
skill did nothing but relay a message. **You are the one being paid to know whether the blocker is
real.** The agent that hit the wall is, by construction, the agent least able to see over it.

---

## 1. Stage 1 — Form check (cheap, mechanical, seconds)

Does the report carry all four parts of the execution-contract §3 proof, *substantively*?

| Field | Passes only if… |
|---|---|
| `error_text` | Verbatim and unabridged. Not a paraphrase, not "it failed", not empty. |
| `attempted` | A real fix the agent **wrote and ran**, given as `file:line` + what changed. **Analysis is not an attempt.** If the agent never edited a file, this fails. |
| `why_it_failed` | A specific mechanism, not "it didn't work". |
| `blocker_code` | A literal `B1` / `B2` / `B3` / `B4`, with one sentence on why that code applies. |

**Any field missing, vague, or empty → the report is malformed. Go straight to Stage 3 (Correct and
re-dispatch).** Do not investigate a report that hasn't even made a claim — send it back.

A report that passes Stage 1 has made a *claim*. It has not yet earned anything.

---

## 2. Stage 2 — Independent investigation (this is the work; do not skip it)

**A well-formed proof is still an assertion until you check it against the code and the docs
yourself.** Agents write confident, well-structured, four-part BLOCKED reports for problems that are
simply work. The form check cannot catch that. Only reading can.

**Investigate every one of the four claims, with your own tool calls:**

1. **Reproduce the error.** Run the failing command / test yourself, in the same context (same shell,
   same redirections — CLAUDE.md § Investigation). Does the verbatim error text actually appear?
   - Error does not reproduce → **illegitimate.** The agent's environment or invocation was wrong.
   - Different error → **illegitimate as reported.** The real error is different; that's the one to fix.
2. **Read the attempted fix.** Open the `file:line` the agent named. Is the change actually there
   (or was it undone)? Is it a genuine attempt at the root cause, or a patch at the boundary?
   - No edit at that location → **illegitimate.** The agent never attempted anything.
   - Edit is a workaround / boundary patch → **illegitimate.** It never tried the correct fix.
3. **Trace the root cause yourself.** Read the code the error points into — the module, its callers,
   the shared layer beneath it. Read the design doc and the package docs that govern it. You are
   looking for the thing the agent stopped short of.
4. **Test the blocker code against reality** (the table in §3 below). This is where most claimed
   blockers die.

Use subagents to *gather* (read files, grep the corpus, run the repro) — but **the verdict is yours.**
Never delegate the adjudication itself to another background agent; that just moves the same failure
one level down.

### Time-box, not a corner-cut

If the investigation is expensive, delegate the reading, not the deciding. But **do not shorten it by
believing the agent.** An hour spent proving a blocker false is cheaper than a phase that silently
ships unimplemented.

---

## 3. Is it legitimate? Test the blocker code against what you just read

| Claimed | It is **legitimate** only if… | It is **illegitimate** if… (all common — expect these) |
|---|---|---|
| **B1 MISSING_ACCESS** | The fix genuinely needs a credential / endpoint / license / external resource that **is not in the repo and cannot be obtained from it**. You looked. | The value exists in the repo, a config, a fixture, or an env file. A test double or a local fixture would serve. The "external service" is one the package already stubs. **A missing *file* or *symbol* is never B1 — create it.** |
| **B2 UNDECIDABLE** | Two designs are *genuinely* defensible, the choice is expensive to reverse, and **nothing in the design docs, the architecture docs, or the existing code settles it**. You read all three. | The design doc, `design-principles.md`, the architecture cheat sheet, or an existing pattern in the codebase settles it. One option is plainly better. The agent just didn't want to decide. **Mild discomfort deciding is not B2.** |
| **B3 USER_FORBADE** | The only correct fix requires an action the user **explicitly** prohibited (in CLAUDE.md or in this request). Quote the prohibition. | The agent inferred a prohibition. It read a *convention* as a *ban*. A different correct fix exists that violates nothing. |
| **B4 FENCED_SURFACE** | The root cause is on a surface the user **explicitly excluded in this request**. Quote the exclusion. | The "fence" is the task file's own file list — **that is an expected surface, not a fence** (execution-contract §4). The root cause is in another package (go fix it there). The surface is merely *unfamiliar*. |

**Non-blockers, restated — every one of these arrives dressed as a blocker and every one is a
re-dispatch:** root cause unclear (keep reading) · missing dependency (implement it) · missing file
(create it) · pre-existing failure (it's yours now) · lives in another package (go there) · bigger
than estimated (do it) · no test coverage (write one) · "environmental" / "behavioral" (prove it with
the error text or fix it) · "would require broader changes" (make them) · "should be tracked
separately" (**there is no other agent**) · attempt limit reached (a new hypothesis gets fresh
attempts).

---

## 4. Stage 3 — ILLEGITIMATE → correct the agent and re-dispatch (the common case)

The task is **not** failed, **not** blocked, and **not** recorded as either. It goes back out with a
correction. Dispatch a **fresh** agent (same model tier as the original, or one tier up if the task
turned out to be subtler than it looked) with a prompt that carries the original task **plus** this
correction packet:

```
YOUR PREVIOUS BLOCKED REPORT WAS REJECTED. It was not a blocker — it is work.

WHAT YOU CLAIMED:
{quote the agent's own blocker_proof back to it, verbatim}

WHY THAT IS WRONG (I verified this myself against the code):
{the specific finding that kills the claim, with file:line or the command + its output —
 e.g. "You claimed B1 MISSING_ACCESS for the storage endpoint. `datrix-common/src/.../config.py:88`
 already resolves it from the local fixture; I ran the repro and it succeeds."}

WHAT YOU MISSED:
{the fact, file, doc section, or pattern the agent did not read}

THE PATH FORWARD:
{concrete next step(s) — the root cause as far as you have traced it, and where to go from there.
 If you traced it fully, give the fix; the agent implements it.}

SCOPE: If the root cause lies outside your task's file list, FOLLOW IT AND FIX IT THERE and report
the added files under `scope_expansion`. The file list is the expected surface, not a fence.

Re-read `.claude/skills/_shared/execution-contract.md` §1-§3 before you start. Your default outcome
is: THE PROBLEM IS FIXED.
```

**Re-dispatch limit:** a task may be corrected and re-dispatched this way **at most twice**. On a
third invalid BLOCKED, the agent has proven it will not converge — stop re-dispatching, do the
root-cause analysis yourself in full, and dispatch a *directed implementer* (execution-contract-style
"apply this pre-decided fix, do not re-decide") rather than an open-ended task agent.

**Never record an illegitimate BLOCKED as a failure, a skip, or a footnote.** It never happened; the
task is still in flight.

---

## 5. Stage 3′ — LEGITIMATE → delegate the decision to a Fable adjudicator

Your investigation confirmed the blocker is real. **You do not decide what to do about it, and you do
not stop.** You hand the decision to a **Fable** agent at **high** effort — the most capable model
available — and then you execute whatever it decides.

Why Fable and not you: a confirmed blocker means the *task as written cannot be completed as
written*. That is a design-level judgment about what should happen instead — re-plan, re-scope, fix
at another layer, change the task, or genuinely go ask the user. It is the highest-stakes call in the
run and it gets the strongest model.

### Spawn the adjudicator

```
Agent tool parameters:
  subagent_type: "general-purpose"
  model: "fable"          # Claude Fable 5 — claude-fable-5
  effort: "high"
  run_in_background: false   # you need the decision before you can proceed
  description: "Fable adjudication: {task_id}"
```

### Adjudicator prompt

```
You are the final decision-maker on a CONFIRMED blocker in an automated task run. Your decision is
binding — the orchestrator will carry it out exactly. Decide; do not implement.

TASK: {task_id} — {title}
OBJECTIVE: {what the task was supposed to accomplish}
DESIGN REFERENCE: {the D#/G#/invariant it implements}
DESIGN ACCEPTANCE PROPERTY: {the observable end-state that would prove it done}

THE BLOCKER (reported by the implementing agent):
{the full four-part blocker_proof}

MY INDEPENDENT INVESTIGATION (I verified this against the code and docs myself):
{what you reproduced, the commands + their output, the file:line you read, the docs you checked,
 and precisely why you concluded the blocker is REAL and not work}

BLOCKER CODE (confirmed): {B1 | B2 | B3 | B4} — {why it applies}

WHAT I HAVE ALREADY RULED OUT:
{the fixes/approaches you and the agent tried, and why each failed}

RELEVANT CODE AND DOCS:
{key excerpts — the code at the root cause, the governing design/architecture text}

CONSTRAINTS (binding, from CLAUDE.md):
- No workarounds, band-aids, stubs, "good enough for now", or conditional guards that hide a broken
  path. This is production software; decide for LONG-TERM correctness, never expedience.
- No git reverts. No mocks in tests. Design docs are scope boundaries — they are not modified during
  implementation.
- Datrix is a multi-language, multi-platform generator. Fixes belong at the most language/platform-
  agnostic layer that can own them. A shared-layer change must not break another generator.

DECIDE ONE of the following and return it as `decision`:

  A. NOT_ACTUALLY_BLOCKED — my investigation is wrong; here is the fix, in concrete steps.
     (Say so plainly if you see it. I would rather be corrected than ship a false blocker.)
  B. FIX_ELSEWHERE — the task cannot be done as written, but the goal can be reached by changing
     {these files / this layer} instead. Give the concrete plan.
  C. AMEND_TASK — the task itself is wrong or under-specified against the design. State the amended
     scope and the provable acceptance property it should carry.
  D. RESEQUENCE — the blocker dissolves if another task runs first. Name it and the dependency edge.
  E. SPAWN_FOLLOW_UP — the root cause is a genuinely independent piece of work. Specify the tracked
     task to file (scope, design reference, acceptance property, owning package), and what the
     current task should do in the meantime (finish the part that is not gated, or stand down).
  F. ASK_USER — only a human can supply what is missing (a credential that exists nowhere in the
     repo; an explicit prohibition that must be lifted; a B2 tie you genuinely cannot break). State
     the exact question, the options, and YOUR RECOMMENDATION.

Return:
1. `decision` — one of A-F.
2. `rationale` — 2-4 sentences. Why this and not the others.
3. `steps` — concrete, ordered, executable. Exact files. Enough that an implementer follows without
   re-deciding.
4. `risks` — what could go wrong, and what the orchestrator must verify afterward.
5. `acceptance_check` — the executable check (negative + positive) that proves the decision landed.
```

### Execute the decision — this is not optional

| Decision | What you do |
|---|---|
| **A. NOT_ACTUALLY_BLOCKED** | Accept the correction. Re-dispatch the task with Fable's steps as a directed-implementer prompt (§4 shape). The blocker is void. |
| **B. FIX_ELSEWHERE** | Dispatch an implementer (sonnet default; opus for a hard/cross-cutting change) with Fable's steps. Widen your own verification to the new files. |
| **C. AMEND_TASK** | Amend the **task file** (never the design doc): update its scope, `**Design acceptance property:**`, and Success Criteria per Fable's decision. Rewire `Depends on` and `dependencies.md` if the scope moved. Then dispatch it. |
| **D. RESEQUENCE** | Add the dependency edge (task file **and** `dependencies.md`), re-run cycle detection, move the task to the correct wave, and run the prerequisite first. Then the task runs normally. |
| **E. SPAWN_FOLLOW_UP** | File a **real task file** with an ID, design reference, and provable acceptance property — prose in a report is not filing (execution-contract §5). Then do whatever Fable said the current task does in the meantime. |
| **F. ASK_USER** | Only now does a human enter the loop. `AskUserQuestion` with Fable's exact question, its options, **and its recommendation**. Act on the answer and continue the run. |

**Only F pauses for the user.** A–E all keep the run moving. Verify the outcome yourself with the
`acceptance_check` Fable specified — the implementer's self-report is never sufficient.

### Record it

A legitimate blocker that went through Fable adjudication is recorded as: the blocker, the confirmed
`B1`–`B4` code, Fable's decision, and what you did about it. **Never as a bare "task BLOCKED".**

---

## 6. Anti-patterns (each of these is a skill-level failure)

- **Relaying.** Reporting an agent's BLOCKED to the user without investigating it yourself. The agent
  is the *least* informed party about whether its own wall is real.
- **Trusting the form.** Accepting a four-part proof because it has four parts. Form ≠ truth.
- **Investigating and then stopping anyway.** Confirming a blocker is real and halting, instead of
  routing it to Fable. A confirmed blocker is a *decision point*, not a stop sign.
- **Deciding a confirmed blocker yourself to save a turn.** The Fable adjudication is the mechanism;
  skipping it is skipping the mechanism.
- **Deciding not to follow Fable's decision.** You dispatched the decision; execute it. If you
  believe it is wrong, say so *to Fable* with the evidence (a second adjudication turn) — do not
  silently substitute your own.
- **Recording an illegitimate BLOCKED as a failure or a skip.** It is neither. It is a task still in
  flight.
