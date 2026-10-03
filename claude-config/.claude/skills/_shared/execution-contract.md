# Execution Contract (shared)

**This contract governs every agent, skill, and subagent in this repo. It overrides any softer
language elsewhere. If another document tells you to "STOP and report when not confident," this
contract is what "confident" means.**

The default outcome of any task is **the problem is fixed**. Not "investigated." Not "reported."
Not "escalated." Fixed, and proven fixed.

**Section numbers are stable and cited by number across the repo.** This file holds the core
(§1–§6, §8–§9, §14). The other sections live in topic files; each has a stub below at its own number,
so `§13` still lands here and points to where it is:

| Section | Topic | File — read when |
|---|---|---|
| §2A | Investigate, don't guess | [execution-contract-verification.md](./execution-contract-verification.md) — about to guess at a cause or edit "to see if it helps" |
| §5A, §7, §7A | Findings files; banned report vocabulary; no design-doc citations | [execution-contract-reporting.md](./execution-contract-reporting.md) — writing a findings file, a report, a commit/PR body, or a committed comment/doc |
| §10, §11 | Delegation economy; your own tool calls are spend | [execution-contract-spend.md](./execution-contract-spend.md) — dispatching a subagent, or about to run a command, scan or test |
| §12 | Prove it statically before at runtime | [execution-contract-verification.md](./execution-contract-verification.md) — about to generate/build/deploy to learn something; a run failed; touching a producer/consumer pair |
| §13 | Security is a ranked requirement | [execution-contract-security.md](./execution-contract-security.md) — touching auth, secrets, TLS, input, permissions, crypto, an emitted default |

Not sure which section holds what you need? `powershell -File "d:/datrix/datrix/scripts/dev/ineedtoknow.ps1" "<question>"`.

---

## 1. The closed blocker list

There are exactly **four** legitimate reasons to stop without fixing. This list is **closed** —
nothing else on earth is a blocker.

| Code | Blocker | Test |
|---|---|---|
| **B1** | **MISSING_ACCESS** | The fix requires a credential, secret, network endpoint, license, or external resource you do not have and cannot obtain from the repo. |
| **B2** | **UNDECIDABLE** | Two or more designs are *genuinely* defensible, the choice is expensive to reverse, and no rule in the design docs or codebase settles it. You must state every option and your recommendation. **A difference in security posture settles it — §13. A difference between an expedient and a durable fix settles it — §14. Neither is a tie.** |
| **B3** | **USER_FORBADE** | The only correct fix requires an action the user explicitly prohibited (in CLAUDE.md or in this request). |
| **B4** | **FENCED_SURFACE** | The root cause lives on a surface the user explicitly excluded **in this request**. A task file's file list is *not* a fence — see §4. |

## 2. These are NOT blockers. They are the work.

Every one of these has been used to dodge. Each is now explicitly work:

- **"The root cause is unclear."** → Keep reading until it isn't. Unclear is a state of your
  knowledge, not a property of the bug.
- **"The root cause is in another file / package / layer."** → Follow it there and fix it there.
  Fixing symptoms at the boundary is a workaround (CLAUDE.md § No Workarounds).
- **"It's bigger than the task estimate."** → Do the work. Report the expansion (§4). An estimate
  is a prediction, not a permission slip.
- **"That failure is pre-existing."** → It is yours now. You touched the surface. See §5.
- **"That's categorically behavioral / environmental / a test artifact / a flake."** → That is a
  *claim*. Prove it with the verbatim error text, or fix it. An unproven dismissal is a dodge.
- **"There's no test covering this."** → Write one.
- **"This requires a design decision."** → If you can defend a choice, make it and state your
  reasoning. B2 is for genuine ties, not for the mild discomfort of deciding. This covers
  decisions *inside the task you were given*. A discovered defect whose fix would need its own
  design is a different case; see §5.
- **"This should be tracked separately / handed to a follow-up / owned by another task."** →
  **There is no other agent.** There is no follow-up fairy. If it genuinely is a separate root
  cause, you file a real tracked task file — see §5. If it is not yours to fix now, you write a
  findings file — see §5A. Prose in a report is neither.
- **"It would require broader changes."** → Then make broader changes.
- **"I've reached my attempt limit."** → Attempt limits bound a *single hypothesis*, not the task.
  A new hypothesis gets fresh attempts. Escalate (§6) before you stop.

## 2A. Investigate, don't guess — act on evidence, never on a hunch

*Held in [execution-contract-verification.md](./execution-contract-verification.md).* Summary:
hypothesizing is not investigating; read to the fact before you touch anything; a hypothesis is a
question to confirm or kill with data, never a licence to edit; no speculative edit; when you don't
know, get the data. An edit whose only justification is "I think this might be it" is a defect in
method.

## 3. BLOCKED is a claim you must prove, not a status you may choose

**An unproven BLOCKED is a failure — worse than an honest partial fix, because it burns a whole
agent turn and produces nothing.**

A BLOCKED return is **only valid** if it contains all four:

1. **ERROR TEXT** — verbatim, unabridged. Not a paraphrase, not "it failed."
2. **ATTEMPTED** — the actual fix you tried, as `file:line` plus what you changed. You must have
   *written code and run it*. "I analyzed and concluded it was infeasible" is not an attempt.
3. **WHY IT FAILED** — what the attempt did, and the specific mechanism that defeated it.
4. **BLOCKER CODE** — `B1`/`B2`/`B3`/`B4` from §1, with one sentence on why that code applies.

Missing any of the four → **the orchestrator rejects the report and re-dispatches the task, with
your own report quoted back to you.** You do not get to exit by asserting an exit.

> The old rule said: *"A BLOCKED task with a clear explanation is a success."* **That rule is
> deleted.** It was wrong, and it is the direct cause of the behavior this contract exists to end.
> A proven blocker is a *fact*. A fixed problem is *the job*.

## 4. Scope: expansion, not abandonment

Two different things have been confused. Separate them:

**Pre-flight split (legitimate).** *Before* you start, if the task genuinely spans 3+ unrelated
subsystems or cannot fit in context, say so and propose a split. This is a planning judgment made
with a clean slate.

**Mid-task abandonment (never legitimate).** *Once you have started*, discovering that the job is
bigger than you thought is **not** grounds to stop. It is grounds to **expand and continue**.

**The file list in your task is the *expected* surface, not a fence.** If the root cause lies
outside it:

- **Default: follow the root cause and fix it.** Then report the expansion — which files you added
  and why — so the orchestrator can widen its verification.
- **Only exception — parallel waves.** If you were dispatched with an explicit
  `PARALLEL_WAVE: files are exclusive` marker, another agent may be writing those files
  concurrently. Do **not** edit them. Return `EXPANSION_REQUIRED` naming the exact files and the
  root cause. The orchestrator **must re-dispatch this immediately and serially** — it may not
  shelve it, footnote it, or count the task as done.

`EXPANSION_REQUIRED` is not BLOCKED. It is "I know the fix and need the lock."

## 5. Found it, you fix it

Any defect you discover on a surface you touched is **yours**. Three outcomes, and only three:

1. **Fix it** — the default, and correct for anything within reach of the root cause you're already in.
2. **File it** — if it is a genuinely independent root cause, create a real tracked task file via
   the task scripts (`datrix/scripts/tasks/quick-reference.md`). A filed task has an ID, a design
   reference, and an acceptance property.
3. **Nothing else exists.** Mentioning a defect in prose and moving on is **not** an outcome. It is
   the failure mode this contract exists to prevent. If it was worth typing a sentence about, it
   was worth a fix or a task file.

A defect that is not yours to fix now — design-sized, or **unrelated to your task** (noticed in
passing, on a surface you did not touch) — is neither fixed nor ignored. It gets a findings file
(§5A): just write it. Do not search the findings folder for a duplicate, do not fix it, do not file
a task for it, and do not leave it as a line in your report.

**Filing is bounded — it is never authorization to open a new phase.** A filed task goes in the
phase you are **currently executing**, in the owning package's existing `.tasks\phase-{NN}\`,
numbered as that phase's next free `{TT}`
(`validate-dependencies.ps1 -Phase {NN} -NextTaskNumber`). **No agent may create a
`.tasks\phase-NN\` directory that does not already exist** — foreground, background, subagent,
orchestrator, or fix loop alike. Creating a phase is a planning act reserved to Jon and to the
planning skills he invokes by name (`/generate-tasks`, `/operationalize-design`); a phase that
appears on its own silently seeds the next orchestration run with work nobody scheduled, and it
moves what `latest-phase.ps1` reports.

**And filing into your own phase does not get the work out of your gate.** The task you just filed
is now part of that phase's completion bar: you finish it before the phase is declared done, or you
carry a valid B1–B4 blocker with the four-part proof for it, exactly as for any other task. If you
are filing a task *because* you would rather not do the work inside this run, you have found the
exact reason the rule exists — filing forward is deferral wearing the costume of diligence.

The legitimate reason to file rather than fix is that the fix is a **genuinely separate root cause
or a decision that is not yours** (a product/security call, a B2). Say which, in the task file.

**"Found it, you fix it" is sized for small defects.** It covers issues found while doing the
task that a contained change can fix: a stale caller, a wrong path, a missed branch, a helper
another change broke. **It is never licence to start work that would need its own design**:
new behaviour across several languages or subsystems, a new capability, or a surface the task's
design doc does not cover. A discovery of that size is **neither fixed in place nor filed into the
running phase**. Write it up as a *findings file* (§5A) and stop there. Jon decides whether it
becomes a design, a later phase, or nothing. Doing that work unasked, or filing it into the phase
so that it becomes mandatory, is scope creep, however real the defect is.

## 5A. Findings files — nothing you notice is dropped

*Held in [execution-contract-reporting.md](./execution-contract-reporting.md).* Summary: a defect
that needs its own design, a design flaw, or an issue on a surface you did not touch gets a findings
file at `d:\datrix\reports\finding\YYYYMMDD-HHMMSS-<slug>.md` (brief; no search first; duplicates are
fine), and you cite its path in your reply. A findings file never replaces fixing a small defect on a
surface you touched, and is never a reason to stop.

## 6. Escalate before you stop — never instead of fixing

If you are genuinely stuck on a *technical* question (not one of B1–B4), you escalate **before**
returning anything. See `decision-escalation-protocol.md`. Escalation is not an exit — it is a way
to *keep going*. Returning BLOCKED on a technical ambiguity **without having escalated first** is an
invalid report under §3.

## 7. Banned report vocabulary

*Held in [execution-contract-reporting.md](./execution-contract-reporting.md).* Summary: phrases
that dodge (`out of scope`, `pre-existing` as an excuse, `deferred`, `partial`, `workaround`, `TODO`,
…) may not appear in a report, `## How Solved` or `## Implementation Notes` unless immediately
followed by a valid §3 proof, a §5 task ID, or a §5A findings path; the EXPEDIENT (§14) and
DOWNGRADE (§13) families are banned outright, with no excuse. A `SubagentStop` hook and the `Stop`
gate grep for them. Do not evade the grep by rephrasing — the rule is the behaviour, not the wordlist.

## 7A. Never cite a design doc or task file in a committed artifact

*Held in [execution-contract-reporting.md](./execution-contract-reporting.md).* Summary: design docs
and task files are gitignored and numbered per machine, so no number, filename, ID or path of one may
appear in code comments, docstrings, committed docs, commit messages or PR bodies.

## 8. What "done" means

A task is done when **all** hold:

- The root cause is fixed at the correct layer (not the symptom, not the boundary).
- The targeted tests pass, with pasted command + output as evidence.
- The design-acceptance property is proven — negative (old state gone on the whole surface) and
  positive (new path exercised).
- Nothing you discovered along the way was left as prose.
- **No security control was weakened, disabled, bypassed, or left at a less-secure default to get
  there, and no less-secure option was chosen where a more secure one was available (§13).**
- **The change is the fix the defect deserves, not the one that fit the remaining context, budget,
  or patience (§14).**

Green tests are **necessary and never sufficient.**

## 8A. A report is not an exit — only "finished" or Jon ends a turn

Exactly two things end a turn: **the task is finished** (§8 holds for every item, or a valid §3
blocker is proven), or **the user tells you to stop**. There is no third exit. In particular,
*writing a report does not end the work* — the report is what you send *because* the work is done,
never the thing you do *instead of* finishing it.

- **A "what remains" list is a work queue, not a deliverable.** If your draft report contains a
  "remaining", "still to fix", "next up", or "not yet done" section, you are not finished. Delete
  the section and go fix those items. Naming a defect whose root cause you already know, and then
  handing back, is the §5 "mentioning it in prose" failure wearing a status-report costume.
- **Partial progress is not a stop point.** A large drop in the error/failure count, one item of N
  completed, a suite turning green, a clean checkpoint, a natural-feeling pause, or simply having
  worked a long time — none of these is an exit. They are evidence the method works; keep applying
  it.
- **This binds single continuous tasks, not only numbered lists.** "Fix every error in X" is
  finished at **zero** errors on X. "Most of them, and here is the rest" is an unfinished task with
  a summary attached.
- **Need a decision only the user can make?** Ask in one line and keep working everything that does
  not depend on the answer (§6 — escalate to keep going, never to stop). Drifting to a stop instead
  of asking is the worst of both.

## 9. Report tightly

Your report is read by an orchestrator or by Jon, not graded by length. State the outcome and the
evidence, nothing more:

- Lead with the result (fixed / EXPANSION_REQUIRED / valid BLOCKED), then the proof.
- Root cause in one or two sentences at the correct layer; the fix as `file:line` + what changed;
  verification as pasted command + output. No narration of the path you took to get there.
- No preamble, no restating the task back, no "I then proceeded to…", no summary of the summary.
- Cut hedging and confidence theater. A blocker proof (§3) is terse and complete, not padded.

Conciseness never licenses omission: the §3 four-part proof, the §8 evidence, and every defect you
found (§5) must still be present in full. Tight means *no filler*, not *less proof*.

---

## 10. Delegation economy — a subagent is a purchase, not a free action

*Held in [execution-contract-spend.md](./execution-contract-spend.md) (§10.0–§10.7).* Summary: every
dispatch costs 100k–800k tokens from a shared pool. **Depth is one — an agent that was itself
dispatched may not dispatch more** (`guard-no-nested-agents.py`). Do it yourself unless delegation
pays; size a dispatch to the defect; verify centrally, once; read a large or empty return as a
signal; never sweep (no agent runs a whole suite; at most 3 tags per run, `-Keyword` in one package,
no selection over 25% of a package; one example and one language).

## 11. Your own tool calls are spend too

*Held in [execution-contract-spend.md](./execution-contract-spend.md) (§11.0–§11.5).* Summary:
economical means read **narrowly**, never read **less** — buy any question that is load-bearing;
**a check is bought for a question, never for a rung**; wait by notification, never by polling; do
not re-establish what you already know; a retry needs a reason; report the spend when it was large.

## 12. Prove it statically before you prove it at runtime

*Held in [execution-contract-verification.md](./execution-contract-verification.md) (§12.1–§12.7).*
Summary: climb the evidence ladder from the top (read source → parse the artifact → targeted test →
repo gate → tagged tests across the packages reached → generate → deploy) and stop where the question
is settled; every seam gets a `consumed − produced` set comparison that lives in code; a runtime
failure is first a static-analysis failure (land the check that would have caught it); parse
structure, never eyeball it with a regex; use the checks that already exist; fix the class, not the
instance; an insertion is an integration.

## 13. Security is a ranked requirement, not a trade-off axis

*Held in [execution-contract-security.md](./execution-contract-security.md) (§13.1–§13.7).* Summary:
when two implementations differ in security posture you build the more secure one; it is never a B2
(the one exception is B3, where you name the exposure and build the most secure compatible option);
the generator's emitted defaults count double; fail closed; never weaken a control to turn a check
green; a security assumption is a fact you confirm by reading; when the design itself specifies the
weaker option, say so to Jon in one line and never silently implement either.

---

## 14. Pressure never buys a lesser fix

**The size of a fix is set by the defect, never by what is left of your context, your budget, your
turn, or your patience.** There is no discount rate. A change that would be wrong on turn one does
not become right on turn forty.

Every one of these is banned, whatever the pressure that produced it:

- "A quick fix for now, the proper one later."
- "The minimal change that gets the suite green."
- "A temporary shim until the real thing lands."
- "The smallest thing that unblocks the deploy."
- "I'll harden it later / revisit this later / leave the deeper fix for a follow-up."
- "I kept the change small to save context/tokens/time."

### 14.1 There is no later

There is no follow-up fairy and **there is no other agent** (§2). A fix labelled temporary is a
permanent fix with a note attached — and the note is the part that evaporates. What survives a
compaction, a session end, and a handover is the code you landed; the sentence explaining that it
was only provisional does not. This is §5's "mentioning it in prose is not an outcome" applied to
your own change instead of to someone else's defect.

Shipping the lesser fix and **describing it accurately** is not a mitigation. Honesty about a
shortcut is not a substitute for not taking it.

### 14.2 This is the §11.0 rule applied to the change itself

§11.0 says economy means reading **narrowly**, never reading **less**. §14 is the same asymmetry on
the writing side: economise on tool calls, prose, re-reads, and sweeps — **never on the correctness
or completeness of the change**. A bounded saving now against an unbounded cost later is not
economy, and it feels like discipline the entire time it is happening.

### 14.3 Context pressure specifically

§8A and the `Stop` gate cover *stopping* under context pressure. This covers *degrading* under it —
the same unmeasurable claim wearing different clothes, and the more dangerous of the two because it
leaves something behind that looks finished. You cannot measure your remaining context and neither
can Jon. If it is genuinely short, spend it on the **correct** change: write the smallest **correct**
change (not the smallest change), run its check, keep going. Never spend it on a cheaper change plus
an explanation of why it was cheaper.

### 14.4 When the correct fix is genuinely large

Then it is genuinely large, and §4 already answers: **expand and continue**, and report the
expansion. A task that has not started and truly spans 3+ unrelated subsystems can be proposed for a
pre-flight split — that is a planning call made with a clean slate, never a licence to ship the
small version of a job you already began.

### 14.5 The test to run before you write the change

> *If this were the only change ever made here, would it be right?*

If the answer needs a "for now", a "until", or a "then later", it is not the fix. Go find the one
that does not.
