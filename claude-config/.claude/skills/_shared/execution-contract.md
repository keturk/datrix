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
  Fixing symptoms at the boundary is a workaround (CLAUDE.md § No Workarounds). If following it
  makes the job broader or bigger than was asked, that is §4: ask for approval.
- **"That's categorically behavioral / environmental / a test artifact / a flake."** → That is a
  *claim*. Prove it with the verbatim error text, or fix it. An unproven dismissal is a dodge.
- **"There's no test covering this."** → Write one.
- **"This requires a design decision."** → If you can defend a choice, make it and state your
  reasoning. B2 is for genuine ties, not for the mild discomfort of deciding. This covers
  decisions *inside the task you were given*. A discovered defect whose fix would need its own
  design is a different case; see §5.
- **"This should be tracked separately / handed to a follow-up / owned by another task."** →
  If the task needs it, it is the task: do it. If the task does not need it, write a findings
  file — see §5A. Prose in a report is neither.
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

## 4. Scope: what was asked; growth needs Jon's approval

The scope of a task is what Jon asked for, or the design doc or task file you were given. You do
all of it, completely. You do not grow it on your own judgment.

**Pre-flight split.** *Before* you start, if the task spans 3+ unrelated subsystems or cannot fit
in one session, say so and propose a split.

**Growth mid-task needs approval.** When the job turns out bigger than estimated, or the correct
fix needs broader changes than the request states, stop that part and ask:

- "Broader" means changes the request does not name: new model fields, phases, diagnostics,
  modules or abstractions; packages it does not name; or a multiple of the expected size.
- Ask in one line starting `APPROVAL_REQUIRED:` — what the expansion is, why the task needs it
  (evidence, `file:line`), and its measured size (below). A subagent returns status
  `APPROVAL_REQUIRED` with the same content; the orchestrator puts it to Jon and does not
  re-dispatch it until he answers.
- Keep working everything that does not depend on the answer. If nothing does, end the turn on
  the question. That is a legitimate exit.
- **Never answer it yourself by shipping a smaller fix (§14).** Unapproved expansion and a
  cut-down fix are both wrong; the question is the only right move.

**Sizing an expansion: measured, in agent terms.** The size in an `APPROVAL_REQUIRED` request
is what the agent doing the work would spend, computed from counts. It is never a guess and
never a person's effort. Sizing agent work in engineer-hours is like using walking time to plan
a road trip: the distance is right, but the speed belongs to someone else.

- **Census.** The files, call sites and packages the change touches, each one counted (code-index
  `find_references`, or a census command whose output you saw). Name each count's source.
- **Cost.** Tokens and agent wall-clock minutes, worked out as census × a rate this run measured
  on comparable work: the minutes between ledger timestamps, and the tokens one unit used. Show
  the arithmetic, e.g. `U01: 2 files, 7 min, ~0.4M tokens → 100 files at 2–4 per unit ≈ 30 units ≈
  3.5 h, ~12M tokens`. If the run has done no comparable work yet, state the census and what each
  site needs (an argument added, or a fixture built per test). Say there is no measured rate
  yet; do not invent one.
- **Never human effort.** No engineer-hours, -days, sprints or "a day's work". No "roughly",
  "about" or "a lot" in place of a count.
- **A document's effort figure is not a baseline.** An effort estimate in a design doc or task
  file ("about half a day") was written for a person, so never scale it, convert it or compare
  against it. Compare your census against what the document *names* (its files, packages and
  units).

**The task's file list is the expected surface.** Following your own defect's root cause into a
neighbouring file or package to fix it there is the task, not an expansion, as long as it stays
within the size and kind of change the task describes. Patching at the boundary to avoid crossing
it is a workaround.

**Parallel waves.** If you were dispatched with an explicit `PARALLEL_WAVE: files are exclusive`
marker, another agent may be writing files outside your list. Do **not** edit them. Return
`EXPANSION_REQUIRED` naming the exact files and the root cause. That is a lock request inside
approved scope, not BLOCKED: the orchestrator re-dispatches it serially as soon as the files are free.

## 5. What you find that the task does not need

A defect, gap or oddity you discover while working is **not fixed** unless the task needs it fixed
to be correct. That covers a defect on a file you touched, a failure your change did not cause,
other instances of the defect class you are fixing, and anything unrelated to your task. Each one
gets a findings file (§5A): just write it. Do not search the findings folder for a duplicate, do not
fix it, do not file a task for it, and do not leave it only as a line in your report. Jon decides
what becomes work.

If the task *does* need it — your change cannot be correct or pass its checks without it — it is
part of the task: fix it, and if that makes the task broader or bigger, §4 applies.

**A discovery never becomes a task file or a phase.** Filing it as a task would make it mandatory
work nobody approved. **No agent may create a `.tasks\phase-NN\` directory that does not already
exist** — foreground, background, subagent, orchestrator, or fix loop alike. Creating a phase is a
planning act reserved to Jon and to the planning skills he invokes by name (`/generate-tasks`,
`/operationalize-design`); a phase that appears on its own silently seeds the next orchestration
run with work nobody scheduled, and it moves what `latest-phase.ps1` reports.

## 5A. Findings files — nothing you notice is dropped

*Held in [execution-contract-reporting.md](./execution-contract-reporting.md).* Summary: anything
you find that the task does not need (§5) — a defect, a design flaw, an issue on any surface — gets
a findings file at `d:\datrix\reports\finding\YYYYMMDD-HHMMSS-<slug>.md` (brief; no search first;
duplicates are fine), and you cite its path in your reply. A findings file is never a reason to stop.

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

Exactly three things end a turn: **the task is finished** (§8 holds for every item, or a valid §3
blocker is proven), **the user tells you to stop**, or **everything left waits on an
`APPROVAL_REQUIRED` question (§4)**. There is no fourth exit. In particular,
*writing a report does not end the work* — the report is what you send *because* the work is done,
never the thing you do *instead of* finishing it.

- **A "what remains" list is a work queue, not a deliverable.** If your draft report contains a
  "remaining", "still to fix", "next up", or "not yet done" section, you are not finished. Delete
  the section and go fix those items. An item that is not part of the task is a findings file
  (§5); an item that would grow the task is an `APPROVAL_REQUIRED` question (§4). Neither is a
  "remaining" list.
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

- Lead with the result (fixed / APPROVAL_REQUIRED / EXPANSION_REQUIRED / valid BLOCKED), then the proof.
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
structure, never eyeball it with a regex; use the checks that already exist; characterize the
class, fix the instances the task needs and put the rest in a findings file; an insertion is an
integration.

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

There is no follow-up fairy. A fix labelled temporary is a permanent fix with a note attached —
and the note is the part that evaporates. What survives a compaction, a session end, and a handover
is the code you landed; the sentence explaining that it was only provisional does not.

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

Then it is genuinely large, and §4 already answers: if it is larger or broader than what was
approved, **ask** (`APPROVAL_REQUIRED:`) and keep working what does not depend on the answer. A task
that has not started and truly spans 3+ unrelated subsystems can be proposed for a pre-flight
split. Neither is ever a licence to ship the small version of a job you already began.

### 14.5 The test to run before you write the change

> *If this were the only change ever made here, would it be right?*

If the answer needs a "for now", a "until", or a "then later", it is not the fix. Go find the one
that does not.
