# Decision Adjudication Protocol (shared)

**Used by `/task-orchestrator`, `/execute-tasks`, and `/execute-tasks-parallel`. It governs what the
skill-running agent does with ANY decision it cannot make itself — including, but NOT limited to, a
subagent's BLOCKED report.**

Read this alongside `execution-contract.md` (§1 the closed blocker list, §3 the four-part proof).

> **This doc was formerly `blocker-adjudication-protocol.md`.** The rename is the point. Scoping
> adjudication to "blockers" created a hole: a conflict the *skill itself* hit — a contradiction
> between two designs, a design-named surface with no owning task, an unbreakable tie on fix scope —
> was not a "blocker report", so it fell through to `AskUserQuestion` and landed on the user. That is
> the failure this doc now closes. **Fable is not the blocker door. Fable is the decision door.**

---

## 0. The Adjudication Ladder — the whole protocol in four rungs

Every decision, conflict, ambiguity, and blocker climbs the same ladder. You may not skip a rung, and
you may not stop early.

| # | Rung | Rule |
|---|---|---|
| **1** | **INVESTIGATE** | Read the code and the docs **yourself**. Reproduce the error. Open the `file:line`. Read the governing design doc. Most "decisions" dissolve here — they were missing information, not genuine ties. |
| **2** | **DECIDE** | If the evidence settles it, **decide and act**. Escalating a decision you are able to make is as much a failure as stopping. Mild discomfort deciding is not a tie. |
| **3** | **ADJUDICATE (Fable)** | If, after genuine investigation, you **truly cannot decide** — spawn a **Fable** adjudicator (`model: "fable"`, `effort: "high"`). Its decision is **binding**; you execute it. |
| **4** | **ASK THE USER** | **Only** when Fable itself returns decision **F (ASK_USER)**. Never before. Never instead. |

**The user is the last rung, not the first.** If you find yourself drafting an `AskUserQuestion` and a
Fable adjudicator has not already returned `F` on this exact question, **you are on the wrong rung —
go back to rung 3.** The only exceptions are listed in §7 (they are narrow, and none of them is a
technical or design judgment).

---

## 1. The two entry doors — same ladder, different rung-1

Adjudication has exactly two entry points. They differ only in what rung 1 looks like.

### Door A — A delegated agent reports BLOCKED

Rung 1 is *auditing the agent's claim*. See §2–§4. A background agent's BLOCKED **never stops the
skill** and is **never relayed to the user unexamined**. It is an input to your investigation, not an
outcome you record.

### Door B — A decision or conflict YOU hit

Rung 1 is *your own investigation*. This door is new, and it is the one that used to leak to the
user. It opens for any of these:

- **Two designs / docs / tasks contradict each other**, and the task set cannot satisfy both as
  written. (E.g. one phase deletes the enum another phase is written to extend.)
- **A design-named invariant surface has no owning task**, and closing the gap requires a judgment
  about scope (author a task? widen an existing one? is the invariant mis-scoped?).
- **A task's premise is false against the code**, and the correct repair is not obvious.
- **A fix attempt failed and the root cause is genuinely ambiguous** after real investigation — you
  cannot tell which of two defensible fixes is right.
- **A phase/wave gate is red** and you cannot determine the correct recovery scope.
- **Task ordering or phase ordering is in conflict** with what the code actually requires.
- **A NEEDS_CONTEXT question** you could not answer from the design docs, the architecture docs, or
  the code (see §7 for the narrow set that genuinely belongs to the user).
- **Anything else you would otherwise have taken to the user**, other than §7's exceptions.

**Both doors converge on §5 (the Fable adjudication) and §6 (execute the decision).**

---

## 2. Door A, Stage 1 — Form check (cheap, mechanical, seconds)

Does the report carry all four parts of the execution-contract §3 proof, *substantively*?

| Field | Passes only if… |
|---|---|
| `error_text` | Verbatim and unabridged. Not a paraphrase, not "it failed", not empty. |
| `attempted` | A real fix the agent **wrote and ran**, given as `file:line` + what changed. **Analysis is not an attempt.** If the agent never edited a file, this fails. |
| `why_it_failed` | A specific mechanism, not "it didn't work". |
| `blocker_code` | A literal `B1` / `B2` / `B3` / `B4`, with one sentence on why that code applies. |

**Any field missing, vague, or empty → the report is malformed. Go straight to §4 (Correct and
re-dispatch).** Do not investigate a report that hasn't even made a claim — send it back.

A report that passes Stage 1 has made a *claim*. It has not yet earned anything.

---

## 3. Rung 1 — Independent investigation (this is the work; do not skip it)

**A well-formed claim is still an assertion until you check it against the code and the docs
yourself.** Agents write confident, well-structured, four-part BLOCKED reports for problems that are
simply work. The form check cannot catch that. Only reading can. The same is true of your *own*
sense that a decision is "genuinely hard" — most of the time it is genuinely under-researched.

**Door A — investigate every one of the four claims, with your own tool calls:**

1. **Reproduce the error.** Run the failing command / test yourself, in the same context (same shell,
   same redirections — CLAUDE.md § Investigation). Does the verbatim error text actually appear?
   - Error does not reproduce → **illegitimate.** The agent's environment or invocation was wrong.
   - Different error → **illegitimate as reported.** The real error is different; that's the one to fix.
2. **Read the attempted fix.** Open the `file:line` the agent named. Is the change actually there
   (or was it undone)? Is it a genuine attempt at the root cause, or a patch at the boundary?
   - No edit at that location → **illegitimate.** The agent never attempted anything.
   - Edit is a workaround / boundary patch → **illegitimate.** It never tried the correct fix.
3. **Trace the root cause yourself.** Read the code the error points into — the module, its callers,
   the shared layer beneath it. Read the design doc and the package docs that govern it.
4. **Test the blocker code against reality** (the table below). This is where most claimed blockers die.

**Door B — investigate the conflict itself:**

1. **Read the primary sources.** Both design docs. Both task files. The code on disk at every
   `file:line` either one names. Do not reason from a metadata digest or an agent's summary — a
   contradiction is exactly the case where a paraphrase misleads.
2. **Verify the conflict is real.** Confirm with your own eyes that the symbol//premise/surface in
   question is actually as claimed. A conflict that evaporates on a direct read was never a decision.
3. **Enumerate the options.** State each candidate resolution and what it costs — which files change,
   which tasks get rewritten, which invariant goes unproven.
4. **Try to break the tie from the docs.** `design-principles.md`, the architecture cheat sheet, the
   governing design doc, CLAUDE.md, and existing patterns in the codebase settle most apparent ties.
   If one of them settles it → **rung 2: decide, and proceed.** Do not escalate.

Use subagents to *gather* (read files, grep the corpus, run the repro) — but **the verdict is yours.**
Never delegate the investigation's conclusion to another background agent; that just moves the same
failure one level down.

### Time-box, not a corner-cut

If the investigation is expensive, delegate the reading, not the deciding. But **do not shorten it by
believing the agent, and do not shorten it by declaring a tie.** An hour spent proving a blocker false
is cheaper than a phase that silently ships unimplemented — and an hour spent breaking a tie from the
docs is cheaper than an adjudication turn.

### Is it legitimate? Test the blocker code against what you just read (Door A)

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

## 4. Door A, Stage 3 — ILLEGITIMATE → correct the agent and re-dispatch (the common case)

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

## 5. Rung 3 — ADJUDICATE: hand the decision to Fable

You reach this rung when **either**:

- **Door A:** your investigation *confirmed* the blocker is real; **or**
- **Door B:** your investigation was genuine and thorough, and the decision is *still* not settled by
  the design docs, the architecture docs, the code, or CLAUDE.md.

**You do not decide it yourself, and you do not stop.** You hand the decision to a **Fable** agent at
**high** effort — the strongest model available — and then you execute whatever it decides.

Why Fable and not you: reaching this rung means *the plan cannot be executed as written*. That is a
design-level judgment about what should happen instead — re-plan, re-scope, fix at another layer,
change the task, reorder the work, or genuinely go ask the user. It is the highest-stakes call in the
run and it gets the strongest model. **It is emphatically not the user's call — not yet.** The user
is rung 4, and only Fable can put you there.

### Spawn the adjudicator

```
Agent tool parameters:
  subagent_type: "general-purpose"
  model: "fable"          # Claude Fable 5 — claude-fable-5
  effort: "high"
  run_in_background: false   # you need the decision before you can proceed
  description: "Fable adjudication: {task_id or short conflict name}"
```

### Adjudicator prompt

Fill every section. An adjudicator given a thin packet returns a thin decision.

```
You are the final decision-maker on a decision an automated task run cannot make for itself. Your
decision is binding — the orchestrator will carry it out exactly. Decide; do not implement.

WHAT KIND OF DECISION THIS IS: {CONFIRMED BLOCKER | DESIGN/TASK CONFLICT | UNOWNED INVARIANT SURFACE |
  AMBIGUOUS FIX SCOPE | ORDERING CONFLICT | RED GATE RECOVERY | OTHER — name it}

TASK / SCOPE: {task_id — title, or the phase/wave and what it was supposed to accomplish}
OBJECTIVE: {what this was supposed to accomplish}
DESIGN REFERENCE: {the D#/G#/invariant it implements}
DESIGN ACCEPTANCE PROPERTY: {the observable end-state that would prove it done}

THE PROBLEM:
{For a confirmed blocker: the full four-part blocker_proof.
 For a conflict: both sides, quoted verbatim from the primary sources — the design doc text, the task
 file text, and the code at file:line. Never a paraphrase.}

MY INDEPENDENT INVESTIGATION (I verified all of this against the code and docs myself):
{what you reproduced, the commands + their output, the file:line you read, the docs you checked, and
 precisely why you concluded this is real and not merely work or missing information}

{Door A only} BLOCKER CODE (confirmed): {B1 | B2 | B3 | B4} — {why it applies}

THE OPTIONS I SEE, AND WHAT EACH COSTS:
{each candidate resolution; which files/tasks change under it; which invariant goes unproven under it;
 which is expensive to reverse. If you have a leaning, say so and say why — you may be corrected.}

WHAT I HAVE ALREADY RULED OUT:
{the fixes/approaches tried, and why each failed. The doc sections you checked that did NOT settle it.}

RELEVANT CODE AND DOCS:
{key excerpts — the code at the root cause, the governing design/architecture text}

CONSTRAINTS (binding, from CLAUDE.md):
- No workarounds, band-aids, stubs, "good enough for now", or conditional guards that hide a broken
  path. This is production software; decide for LONG-TERM correctness, never expedience.
- No git reverts. No mocks in tests. Design docs are scope boundaries — they are NOT modified during
  implementation (task files may be amended; design docs may not).
- Datrix is a multi-language, multi-platform generator. Fixes belong at the most language/platform-
  agnostic layer that can own them. A shared-layer change must not break another generator.

DECIDE ONE of the following and return it as `decision`:

  A. NOT_ACTUALLY_BLOCKED / NO_CONFLICT — my investigation is wrong; here is the resolution, in
     concrete steps. (Say so plainly if you see it. I would rather be corrected than act on a false
     conflict.)
  B. FIX_ELSEWHERE — the goal cannot be reached as written, but it can be reached by changing
     {these files / this layer} instead. Give the concrete plan.
  C. AMEND_TASK — the task itself is wrong or under-specified against the design. State the amended
     scope and the provable acceptance property it should carry. (Amend the TASK, never the design.)
  D. RESEQUENCE — the problem dissolves if work is reordered. Name the tasks/phases, the new order,
     and the dependency edges to add.
  E. SPAWN_FOLLOW_UP — the root cause is a genuinely independent piece of work. Specify the tracked
     task to file (scope, design reference, acceptance property, owning package), and what the
     current work should do in the meantime (finish the part that is not gated, or stand down).
  F. ASK_USER — only a human can supply what is missing (a credential that exists nowhere in the
     repo; an explicit prohibition that must be lifted; a genuine product/business call; a tie whose
     two sides are equally defensible AND whose resolution is the user's prerogative, not an
     engineering judgment). State the exact question, the options, and YOUR RECOMMENDATION.

     Choose F sparingly and only for what is genuinely the user's to decide. An engineering tradeoff
     with a defensible answer is YOUR call (A-E), not theirs. But when the call is truly the user's,
     do not manufacture an engineering answer to avoid F — say F.

Return:
1. `decision` — one of A-F.
2. `rationale` — 2-4 sentences. Why this and not the others.
3. `steps` — concrete, ordered, executable. Exact files. Enough that an implementer follows without
   re-deciding.
4. `risks` — what could go wrong, and what the orchestrator must verify afterward.
5. `acceptance_check` — the executable check (negative + positive) that proves the decision landed.
```

---

## 6. Execute the decision — this is not optional

| Decision | What you do |
|---|---|
| **A. NOT_ACTUALLY_BLOCKED / NO_CONFLICT** | Accept the correction. Re-dispatch with Fable's steps as a directed-implementer prompt (§4 shape). The blocker/conflict is void. |
| **B. FIX_ELSEWHERE** | Dispatch an implementer (sonnet default; opus for a hard/cross-cutting change) with Fable's steps. Widen your own verification to the new files. |
| **C. AMEND_TASK** | Amend the **task file** (never the design doc): update its scope, `**Design acceptance property:**`, and Success Criteria per Fable's decision. Rewire `Depends on` and `dependencies.md` if the scope moved. Then dispatch it. |
| **D. RESEQUENCE** | Add the dependency edges (task files **and** `dependencies.md`), re-run cycle detection, move the tasks/phases to the correct order, and run the prerequisite first. Then the work proceeds normally. |
| **E. SPAWN_FOLLOW_UP** | File a **real task file** with an ID, design reference, and provable acceptance property — prose in a report is not filing (execution-contract §5). Then do whatever Fable said the current work does in the meantime. |
| **F. ASK_USER** | **Only now does a human enter the loop.** `AskUserQuestion` with Fable's exact question, its options, **and its recommendation**. Act on the answer and continue the run. |

**Only F reaches the user.** A–E all keep the run moving. Verify the outcome yourself with the
`acceptance_check` Fable specified — the implementer's self-report is never sufficient.

**If you believe Fable's decision is wrong**, say so *to Fable* with the evidence (a second
adjudication turn). Do not silently substitute your own judgment, and do not route around it to the
user.

### Record it

An adjudicated decision is recorded as: the problem, (for Door A) the confirmed `B1`–`B4` code,
Fable's decision, and what you did about it — **never as a bare "task BLOCKED"** and never as an
unexplained change of plan.

---

## 7. The narrow set of things that DO go straight to the user

These bypass Fable because they are not judgments at all — they are inputs only the user possesses,
or safety gates the user owns. This list is **closed**:

1. **A credential, secret, endpoint, or account** that exists nowhere in the repo and that you need in
   order to proceed *at all*. (Confirm it is genuinely absent first — §3's B1 test.)
2. **An explicit, irreversible, outward-facing action** requiring authorization: creating real cloud
   resources that cost money, pushing, deploying, deleting user data, sending anything externally.
   (Per CLAUDE.md's confirm-before-irreversible rule.)
3. **A genuine product/business call** with no engineering answer — what the software should *do* for
   its users, not how it should be built.
4. **A prohibition the user set** that the only correct fix would violate (B3) — you need it lifted.

**Everything else climbs the ladder.** Notably NOT on this list, and therefore NOT a direct user
question: which of two designs to follow · what order to run phases in · whether a task set satisfies
its design · how to close a coverage gap · what the fix scope is · whether to continue after a
failure · whether a red gate should halt the run. **Those are rung-3 decisions. They go to Fable.**

---

## 8. Anti-patterns (each of these is a skill-level failure)

- **Skipping to rung 4.** Taking a decision to the user that Fable has not returned `F` on. The most
  common form: "this feels like it's really the user's call." It almost never is — §7 is the whole
  list.
- **Rationalizing the door.** Deciding that *your* conflict isn't a "blocker report" and therefore
  doesn't go through adjudication. **Both doors converge here.** The door you came in by never
  changes the rung you must climb.
- **Relaying.** Reporting an agent's BLOCKED to the user without investigating it yourself. The agent
  is the *least* informed party about whether its own wall is real.
- **Trusting the form.** Accepting a four-part proof because it has four parts. Form ≠ truth.
- **Investigating and then stopping anyway.** Confirming a blocker/conflict is real and halting,
  instead of routing it to Fable. A confirmed problem is a *decision point*, not a stop sign.
- **Deciding a confirmed blocker/conflict yourself to save a turn.** The Fable adjudication is the
  mechanism; skipping it is skipping the mechanism.
- **Escalating what you could have decided.** Rung 3 is for genuine ties *after* investigation. An
  under-researched question is not a tie — it is rung 1 you have not finished.
- **Deciding not to follow Fable's decision.** You dispatched the decision; execute it. If you
  believe it is wrong, say so *to Fable* with the evidence — do not silently substitute your own, and
  do not appeal to the user.
- **Recording an illegitimate BLOCKED as a failure or a skip.** It is neither. It is a task still in
  flight.
