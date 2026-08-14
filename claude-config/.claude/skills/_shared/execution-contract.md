# Execution Contract (shared)

**This contract governs every agent, skill, and subagent in this repo. It overrides any softer
language elsewhere. If another document tells you to "STOP and report when not confident," this
contract is what "confident" means.**

The default outcome of any task is **the problem is fixed**. Not "investigated." Not "reported."
Not "escalated." Fixed, and proven fixed.

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
  reasoning. B2 is for genuine ties, not for the mild discomfort of deciding.
- **"This should be tracked separately / handed to a follow-up / owned by another task."** →
  **There is no other agent.** There is no follow-up fairy. If it genuinely is a separate root
  cause, you file a real tracked task file — see §5. Prose in a report is not filing.
- **"It would require broader changes."** → Then make broader changes.
- **"I've reached my attempt limit."** → Attempt limits bound a *single hypothesis*, not the task.
  A new hypothesis gets fresh attempts. Escalate (§6) before you stop.

## 2A. Investigate, don't guess — act on evidence, never on a hunch

**Hypothesizing is not investigating.** Guessing at a cause, changing something, and seeing if the
symptom moves is banned. "Throwing mud at the wall to see what sticks" wastes the turn and usually
fixes nothing. Every action you take must be justified by evidence you have *already gathered* —
read code, captured error text, an observed value — not by a theory you have not yet confirmed.

The rule:

- **Read to the fact before you touch anything.** The cause of a failure is discoverable by reading
  the relevant code, the error output, and the data. Find it. Do not assume what a function
  returns, what a config holds, what a symbol means, or where control flows — open the file and
  confirm it. "Never assume/fabricate — look it up" (CLAUDE.md § Core Principles) is not advice; it
  is the method.
- **A hypothesis is a question, not a license to edit.** If you have a theory, the next step is to
  *confirm or kill it with data* (read the code path, add a targeted observation, capture the real
  value) — not to apply a speculative fix and hope. Confirm first, then act once.
- **No speculative edit.** Do not change code "to see if it helps," do not fix a thing you have not
  first proven is the cause, do not try several changes at once hoping one lands. One confirmed
  root cause → one deliberate fix.
- **When you don't know, get the data — you are never stuck for lack of a guess.** The answer to
  "what's causing this?" is always another read, another captured error, another observed value —
  never a fresh guess layered on an unconfirmed one. This binds with § "No second hypothesis
  without the error text": if the evidence is invisible, your first action is to *make it visible*,
  not to theorize around it.

An edit whose only justification is "I think this might be it" is a defect in method, whether or not
it happens to work. State the evidence that drove each change; if you cannot, you have not
investigated yet.

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

## 6. Escalate before you stop — never instead of fixing

If you are genuinely stuck on a *technical* question (not one of B1–B4), you escalate **before**
returning anything. See `decision-escalation-protocol.md`. Escalation is not an exit — it is a way
to *keep going*. Returning BLOCKED on a technical ambiguity **without having escalated first** is an
invalid report under §3.

## 7. Banned report vocabulary

These phrases must **never** appear in an agent report, a `## How Solved`, or an
`## Implementation Notes` section unless immediately followed by a valid §3 blocker proof or a §5
filed task ID:

```
out of scope · outside the scope · not part of this task · beyond the scope
pre-existing (as an excuse) · categorically behavioral · environmental issue
should be tracked separately · left as-is · left for a follow-up · future work
would require broader changes · someone else's · not my file · deferred
partial · workaround · dual path · not yet wired · remains unchanged · TODO
```

Two further families are banned outright — they do not describe *whose* work it is, they describe
shipping the wrong work. A proof or a task ID does **not** excuse either one:

```
EXPEDIENT (§14):  quick fix · temporary fix · interim fix · stopgap · band-aid
                  minimal change to get it green · for now · good enough for now
                  harden it later · revisit this later · proper fix can come later
                  to save context/tokens/budget · smallest thing that unblocks

DOWNGRADE (§13):  disabled the auth check · relaxed the validation · loosened CORS
                  turned off TLS verification · bypassed authorization
                  hardcoded the credential · less secure but simpler · insecure default
```

A `SubagentStop` hook greps for these, and the always-on `Stop` gate greps the main loop for the
same two families. A hit without an accompanying proof or task ID marks the report **invalid** and
the task **not complete** — regardless of test-suite color.

This is not a vocabulary game: **do not evade the grep by rephrasing.** Rephrasing a dodge to slip
past the check is a worse offense than the dodge, because it is deliberate. The rule is the
*behavior*, not the wordlist.

## 7A. Never cite a design doc or task file in a committed artifact

Design docs (`design/`) and task files are `.gitignored` and authored on two machines, so their
numbering collides (two different `044-…` docs, same-numbered tasks) and none of them exists after
a clone. **A reference to one from anything committed is a dangling pointer** — it points at the
wrong artifact, or nothing, on another machine.

So a design-doc or task-file number, filename, ID, or path must **never** appear in: code comments,
docstrings, committed documentation (`docs/`, READMEs), commit messages, or PR bodies. State *what*
the code does and *why* — never "implements design 044-x" or "per task 03-12". This is exempt only
for design/task files referencing *each other* (`Design reference:`, `Depends on:`): that is
internal, gitignored orchestration machinery, not a committed artifact.

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

Every dispatched agent costs real budget drawn from a shared, exhaustible pool. A run that reaches
the right answer by spending a week of budget in a day is **not** a good run. Cost is part of the
engineering judgment, exactly like correctness and scope — not a separate concern owned by someone
else. You cannot see the meter; that does not excuse you, because you can see every agent's reported
token count and you can see how many you dispatched.

### 10.1 Do it yourself unless delegation actually pays

Before dispatching, ask: *do I already know the fix?* If you have the root cause at `file:line` and
the change is small and contained, **make the edit**. A dispatch costs 100k–800k tokens; the same
edit made directly costs a handful of tool calls. Delegation earns its price when the work is large,
genuinely parallel, or needs a context you do not want to load — never as a default reflex, and never
as a way to avoid doing a small thing yourself.

Reach for an agent when: the task needs broad exploration you have not done; several genuinely
independent workstreams can proceed at once; or the reading required would blow the orchestrator's
context. Do not reach for one to: apply a fix you have already diagnosed, edit a config or fixture,
correct documentation, or run a command and read its output.

### 10.2 Size the dispatch to the defect

Scale the ask to what is actually unknown. A three-error fix with a known root cause is a small,
tightly-scoped dispatch, not a request for exhaustive investigation, full-suite runs, and
multi-example verification. Every extra acceptance criterion you write is budget the agent will
spend. Ask for the smallest evidence that actually proves the fix.

### 10.3 Verify centrally, once — never N times in parallel

**Do not put a "regenerate these other examples / re-run these other suites" list in every dispatch.**
If the orchestrator verifies the shared set after the wave lands — and it should — then every
per-agent copy of that verification is pure duplication, multiplied by the number of agents. One
central verification catches the same regressions as N scattered ones, at 1/N the cost.

The narrow exception: when an agent is changing a surface so shared that it must know immediately
whether it broke a sibling, give it exactly one no-regression target, not four.

### 10.4 A large or empty return is a signal — act on it

Every completion reports its token usage. Read it. Then react:

- An agent that returns **without a usable report** after a large spend means the task was mis-sized.
  **Shrink the next dispatch. Never re-dispatch the same shape at the same size.**
- Two such returns in a run means your sizing model is wrong, not that the agents are unlucky.
- Track the running total across a session. If you cannot state roughly what the run has spent so
  far, you are not managing it.

### 10.5 Cap concurrency to the real constraint

Parallel agents buy wall-clock, and wall-clock is rarely the binding constraint. Dispatching seven
agents where two would do multiplies cost by three and a half for a result that arrives slightly
sooner. Parallelise when the workstreams are genuinely independent and the total is bounded — not to
feel busy.

### 10.6 Never sweep — not across examples, not across languages

Regenerating unrelated examples, running `-All` suites reflexively, or re-verifying already-green
work "to be safe" is the single easiest way to burn budget for no information. Generation granularity
and affected-only verification are cost rules as much as correctness rules. To prove a fix
generalises, **write a test** — it proves the invariant permanently and costs once, where a corpus
sweep proves it once and evaporates.

**Scope is one example AND one language.** Fix the example for the language it actually failed under.
Do **not** generate it for the other registered languages to discover whether they are affected too —
that multiplies the cost of the task you were given by the number of targets, to answer a question
nobody asked. Widening scope that way is Jon's budget decision: **ask in one line and wait.** Group
generation (`-All`/`-Domains`/`-TestSet`) is hard-blocked by `PreToolUse` →
`validate-script-invocation.py` and cannot be overridden.

### 10.7 Interrupted work is not banked

An agent killed mid-run may have produced nothing, and its partial edits are unverified. Re-measure
from disk before assuming any of it landed. Budget already spent on a killed agent is gone — do not
compound it by trusting its unproven output.

---

## 11. Your own tool calls are spend too

§10 governs what you buy from OTHER agents. This section governs what you spend yourself. The two
are the same budget, and an orchestrator that sizes its dispatches perfectly while burning a hundred
redundant tool calls of its own has not managed anything.

**Every tool call costs its arguments plus its entire result, in tokens, forever** — the output stays
in context for the rest of the session. A command whose output you will not read is pure loss. A
command you have already run, whose answer has not changed, is pure loss. Time is the same resource
seen from the other side: a five-minute regeneration to confirm a one-line change tells you what a
five-second targeted check would have.

### 11.0 Economical means read NARROWLY — never read LESS

**This section is not a license to cut corners, and reading it that way inverts it.** Everything
below is about eliminating calls that buy *nothing* — a rerun whose answer cannot have changed, a
result you will not read, a sweep for information you already hold. **A call that would tell you
something you do not know is never the thing to cut.**

The arithmetic is asymmetric and it always points the same way: **a check has a small bounded cost;
the defect it would have caught has an unbounded one.** A `grep` costs one call. Missing what it
would have shown costs a failed deploy, Jon's time, the re-diagnosis, and the re-run — routinely
three orders of magnitude more, and paid in the expensive currencies (wall-clock, cloud spend,
Jon's attention) rather than the cheap one. **Economy is minimizing expected TOTAL cost, not
per-step cost.** Skipping a cheap load-bearing check is the single most anti-economical thing you
can do, and it feels like compliance the entire time it is happening.

So the test is never "is this call cheap?" — it is **"is this question load-bearing?"** If the
answer changes what you do next, buy it, at whatever it costs. If it does not, skip it, however
cheap it looks. Narrow the *form* of every check to the least it can be (a `grep` over a read, one
targeted test over a suite, a parse over a regeneration) — but never narrow the *set* of questions
you must answer to be correct.

### 11.1 Wait by notification, never by polling

**A background task notifies you when it completes. Do not poll it.** Launch it with
`run_in_background`, end the turn, and resume when the notification arrives. That is the supported
mechanism and it costs nothing while waiting.

Do **not** write `until <check>; do sleep N; done` loops to keep a turn alive while a task you
started finishes. Each poll is a tool call plus its result; a long loop can exceed the tool timeout
and get moved to the background itself, leaving a background task waiting on a background task.

This mistake comes from a specific misreading, so name it to avoid it: **"do not end the turn with
work unfinished" (§8A) is not "do not yield control between tool calls."** Waiting for a task
notification is not handing back — the harness re-invokes you and the work continues. §8A forbids
*reporting partial progress as if it were an outcome*, not pausing for a mechanism that resumes you.

**Foreground `sleep` is blocked by the harness.** If you find yourself constructing a loop to route
around that block, stop: a guard you have to work around is a signal you are doing the wrong thing,
not an obstacle to defeat. Poll only external state the harness cannot observe (a CI run, a remote
queue), and then match the interval to how fast that state actually changes.

### 11.2 Do not re-establish what you already know

- **Do not re-read a file you just wrote.** `Edit`/`Write` fail loudly if they did not apply; a
  confirming read buys nothing and costs the whole file.
- **Do not re-run a passing check to feel better.** Green does not decay because you changed an
  unrelated file. Re-run a suite when your change could plausibly affect it — not as punctuation.
- **Do not regenerate a project to verify a change you can verify at the source.** Regeneration is
  minutes and a large output; reading the emitted template or running its unit test is seconds.
  Regenerate when the artifact is the deliverable, or when nothing cheaper can prove the point.
- **Do not restate context back to yourself.** Re-printing a file you already hold, re-listing a
  directory you already listed, or dumping a log you have already read adds tokens and no knowledge.

### 11.3 Ask the cheapest question that distinguishes the answers

Before running anything, know what each outcome would change. If both outcomes lead to the same next
action, the command is not worth running. Prefer the narrowest form that settles it: one targeted
test over a suite, one `grep` over a full read, one `--query` over a full JSON dump, `head` over
the whole file. **Then actually read what came back** — an unread result is the most expensive kind,
because you paid for it and learned nothing.

### 11.4 A retry needs a reason, not just hope

Re-running a failed command unchanged is a bet that the world changed. Sometimes it did (a
propagation delay, an async purge) — and then the retry belongs in the *code*, bounded and explained,
not in your fingers. Otherwise, change something first: read the error, narrow the scope, fix the
cause. Two identical failures are one failure and one wasted call.

### 11.5 Report the spend when it was large

If a task cost far more than it should have, say so plainly in the report, with the cause. Cost
overruns that nobody names repeat. This is not self-flagellation — it is the same
report-what-happened discipline §9 applies to correctness.

## 12. Prove it statically before you prove it at runtime

§2A says act on evidence, not on a hunch. This section says **where to go get that evidence**: the
cheapest rung that can actually falsify the claim, which is almost never a deploy.

A deployment or a runtime run is the **most expensive and latest-arriving** evidence in the repo. It
costs minutes to hours, it costs real cloud money, it reports one failure at a time, and it reports
it *after* the artifact is already out in the world. Nearly every defect it finds was sitting in a
file on disk the whole time, discoverable by reading or parsing that file. Waiting for a deploy to
tell you something a `grep` would have told you is not thoroughness — it is the slowest possible way
to be wrong.

### 12.1 The evidence ladder — start at the top, stop as soon as the question is settled

Each rung costs roughly an order of magnitude more than the one above it, and reports later:

1. **Read the source / template / config** that produces the artifact.
2. **Parse the emitted artifact** and compute over it (set difference, key census, structural query).
3. **Targeted unit test** in the owning package (`test.ps1 <pkg> -Specific "…"`).
4. **A repo static gate** — the scans and parity gates listed in 12.5.
5. **The affected package suites** (`affected-gate.ps1 -Projects …`).
6. **Generate the affected project** and inspect the output.
7. **Deploy / run it.**

**Never reach for a lower rung to answer a question an upper rung settles.** "I'll just deploy and
see" is the single most expensive sentence available to you. Conversely, do not stop at an upper rung
that *cannot* settle the question — a unit test does not prove a cloud resource name is free.

### 12.2 Every seam gets a set comparison, and the comparison lives in code

The dominant defect class in a generator is the **seam**: artifact A produces a set of names or
values, artifact B consumes a set, and **nothing compares the two**. A compose file interpolating
variables nobody supplies; a config-store key declared but never given a value; an environment file
assigning a key blank and shadowing the real value; a bicep member key the resolver spells
differently. Every one of these is a **set difference you can compute without running anything**.

So, whenever you touch a producer or a consumer:

- Name both sides explicitly — *this* code writes the keys, *that* code reads them.
- Compute `consumed − produced`. It must be empty, or every element must be explained.
- **Then put that comparison somewhere it runs by itself** — a generation-time validator in the
  owning package, or a test. A set difference you computed by hand proves today's tree; a validator
  proves every tree from now on. This is the same rule as CLAUDE.md's "to prove a fix generalises,
  write a test," applied to seams.

A validator that fails **at generation time** with the key, the producer that should have supplied
it, and the fix, is worth more than any amount of deploy-time diagnosis.

### 12.3 A runtime failure is first a static-analysis failure

When a deploy or a run fails, the fix is only half the work. The other half is a mandatory second
question:

> **What check would have caught this before the run, and where does it live?**

Land that check together with the fix. If you fix the instance and ship no check, you have
guaranteed that the next member of the same defect class also waits for a deploy to be discovered —
and you will pay the same minutes and the same money again. "Found it, you fix it" (§5) covers the
instance; this covers the class.

### 12.4 Parse structure; do not eyeball it with a regex

A matcher that cannot see what it claims to cover is worse than no matcher — it produces a confident
"clean" result and it will be believed. This has already cost a full deploy cycle here: a single-line
`grep -o '\${[^}]*}'` over a generated compose file found **10** mandatory interpolations where
**44** existed, because the YAML emitter wraps them across lines. The count was reported as fixed on
that basis.

- Use a real parser (`yaml`, `json`, Python `ast`, the tree-sitter parser) or normalize first
  (collapse whitespace) before matching.
- **Prove your matcher is non-vacuous**: check that it finds an instance you already know is there.
  A scan that can only return zero is not evidence.
- Report the census, not the verdict — "44 required variables, 44 supplied" beats "looks fine."

### 12.5 Use the checks that already exist before writing a new one

These are cheap, already maintained, and cover most cross-cutting classes. Run the ones whose surface
you touched (paths relative to `d:/datrix/datrix/scripts/`):

| Surface | Check |
|---|---|
| Python anti-patterns | `dev/semgrep.ps1` (`-ListRules`, `-Rule <name>`), `dev/libcst.ps1` |
| Layering / target-name leakage | `dev/check-import-boundaries.ps1` (`-CheckTargetLiterals`, `-CheckProviderConditionals`, `-CheckSharedVocabulary`, `-CheckSharedTargetNames`) |
| Debug scatter, stale bytecode | `dev/check-debug-artifacts.ps1`, `dev/check-python-bytecode.ps1` |
| Docs drift | `dev/check-docs.ps1`, `test/check-docs-conformance.ps1` |
| Generated-output drift | `test/reference-example-parity-gate.ps1` |
| Realization / parity holes | `test/block-realization-parity-gate.ps1`, `test/standing-conformance-gate.ps1`, `test/supported-domain-parity-gate.ps1`, `test/observability-axis-parity-gate.ps1`, `test/gendsl-corpus-resolution-gate.ps1` |
| Duplicate logic | `dev/logic-map.ps1` + a `markers.db` query (CLAUDE.md § Logic Map) |

Full selection rules: `_shared/verification-strategy.md`. **Never run a standalone type-checker** —
`mypy` and equivalents are not part of verification here (CLAUDE.md § Running Python).

### 12.6 Be systematic: fix the class, not the instance

Symptom-by-symptom is how a five-minute defect becomes a five-hour deploy loop — each round trip
surfaces exactly one more instance of a class you could have enumerated in one pass.

When a defect appears, **characterize the class before fixing the instance**: what is the general
shape (a seam, a missing validator, an own-vs-shared enumeration mismatch, a blank-shadowing key),
and where else does that shape occur? Enumerate all occurrences with one static pass, then fix them
together and land the check from §12.3. One pass over the whole class beats N deploys that each
reveal one member of it.

### 12.7 An insertion is an integration — there is no "just placing a call"

Adding a step to a pipeline, a leg to a release script, a stage to a generator, a hook to a chain, or
a call between two existing functions **is an integration by default**, and it is only complete when
you have read the neighbours. A step's real contract is not its own body — it is **the postcondition
it must leave behind and the precondition the next step demands.** That contract lives in the
neighbouring code, so it cannot be established by reading the thing you inserted.

Before the insertion lands, know all three:

- **What the upstream step guarantees** when it hands over.
- **What the downstream step requires** to start — its explicit guards, its `Test-Path`s, its
  early `raise`/`Write-Error` blocks, and the assumptions its header prose states.
- **What both sides believe about any shared resource** the new step touches: which file, which
  path, which key, written by whom, on which machine. Two steps holding different answers is the
  seam of §12.2, and it is found by one `grep` for the resource name across the directory.

Two traps make this feel unnecessary at exactly the moment it is not:

- **Editing the frame is not reading the contents.** You can add a leg, renumber the banner, add a
  skip flag, and wire a probe — touching the orchestrator repeatedly — without any of those edits
  forcing you to read what a single step does. Structural familiarity is not knowledge of behavior.
- **An answer settled in a neighbouring context is not settled here.** A decision made for one
  profile, target, or environment is a *hypothesis* about this one (§2A), not a conclusion. Carrying
  it across unexamined is how an assumption enters without ever feeling like a guess. Re-derive it,
  or confirm the neighbour's code agrees — especially when a sibling file's own documentation says
  it does the opposite.

---

## 13. Security is a ranked requirement, not a trade-off axis

**When two implementations differ in security posture, you build the more secure one.** Not
"consider it", not "recommend it and offer the convenient alternative", not "note the risk and ship
the easy path". Build it. **Never propose or implement a less secure option when a more secure one
is available.**

This is a *ranking*, not a preference to balance. Convenience, brevity, familiarity, fewer moving
parts, and finishing sooner do not outrank it. If the secure option costs more code, more
configuration, an extra dependency, or an extra hour, **that cost is the price of the correct
option** — it is not evidence that the other option was reasonable.

### 13.1 It is never a B2, and never Jon's problem to notice

A difference in security posture **settles** a design choice; it does not create a tie. Two options
that differ only in that one is safer are not "two genuinely defensible designs" — that is one
defensible design and one defect (§1, B2). Do not escalate it, do not present it as a menu, and do
not implement the weaker one because it was easier to explain.

The **one** case where a less-secure option is on the table is **B3 USER_FORBADE**: Jon's explicit
constraint rules the secure option out. Then, and only then, you say so in one line, **name the
exposure the constraint creates**, and implement **the most secure option compatible with the
constraint**. You never present the weaker option as your recommendation, and you never implement
one silently.

### 13.2 What the generator emits counts double

Datrix writes production code and production infrastructure for someone else's system. **An
insecure default in a generator is not one defect — it is one defect per project generated from
then on, in codebases nobody on this team will ever read.** A default emitted by a template is a
security policy applied to every future user of that template.

So the rule applies with equal force to both surfaces:

- **The framework code you write** — parsers, resolvers, validators, CLI, scripts.
- **Every artifact the generator emits** — service code, SQL, Dockerfiles and compose files, IaC
  templates, gateway config, CI/ops scripts, generated defaults, and sample/example projects.
  Examples are copied; an example that authenticates weakly teaches weak authentication.

### 13.3 The surfaces this covers

You do not get to decide a task is "not a security task". Relevance is set by the surface you
touched, not by whether the word appeared in the request:

- **Authentication and authorization** — per-request enforcement, object-level/tenant isolation, no
  ambient authority, no "trust the caller", no client-supplied identity.
- **Secrets and credentials** — never hardcoded, never logged, never defaulted to a literal, never
  committed; sourced from the platform's secret mechanism.
- **Transport and storage** — TLS on by default and verified; encryption at rest where the platform
  offers it; no plaintext channel because it was simpler to wire.
- **Input handling at trust boundaries** — validate and normalize where untrusted data crosses in,
  not three layers later "where it's convenient".
- **Injection surfaces** — parameterized queries, argument vectors instead of shell strings, safe
  template/path/deserialization handling. Never compose a query, command, path, or markup by string
  concatenation from external input.
- **Exposure and permissions** — no public bind, no `0.0.0.0/0`, no wildcard IAM, no public bucket,
  no permissive CORS, no debug endpoint, and no default-open port because closing it needed a
  config field.
- **Error and log content** — no credentials, tokens, PII, or internal detail in responses or logs.
- **Cryptography** — standard primitives, current parameters, a CSPRNG for anything
  security-bearing. Never home-rolled.
- **Dependencies and base images** — pinned, current, from the expected registry.

### 13.4 Fail closed

A security control whose input is missing, unparseable, or unknown **denies**. A guard that permits
when it cannot evaluate its condition is the banned silent fallback (CLAUDE.md § Anti-patterns)
applied to the one place it is most expensive: it converts an unknown into an approval, and it is
invisible in every green test suite. An unrecognized identity provider, an absent claim, an
unresolved policy, a missing key — each raises with a message naming what was missing and what to
supply. Never `except: pass` around a check, and never `if not configured: allow`.

### 13.5 Never weaken a control to make something pass

If a test, build, generation run, or deploy fails **against** a security control, the control is the
requirement and the thing failing it is the defect. Disabling it, loosening it, adding an exemption,
or widening a permission so the red turns green is a workaround (CLAUDE.md § No Workarounds) *and* a
silent change to the product's threat model. It is banned even when it is the only thing standing
between you and a green suite, and especially then.

An existing insecure pattern is not a licence either. "The neighbouring module does it this way" is
evidence about the neighbour, not permission (§12.7). Found it → §5: fix it, or file it.

### 13.6 A security assumption is a fact you confirm by reading

"That input is validated upstream", "that endpoint is internal-only", "that secret never reaches the
client" are claims, and §2A governs them: open the file and confirm. The seam discipline of §12.2 is
the tool — name the producer and the consumer of every trust boundary, compute what crosses it, and
land the comparison as a validator. A trust boundary nobody compares is the same defect class as an
unsupplied compose variable, with a worse blast radius.

When a change touches any surface in §13.3, the mandatory second question of §12.3 has a security
form: **what check would have caught this insecure state before the run, and where does it live?**
Land it with the fix.

### 13.7 When the design itself specifies the weaker option

A design doc is a scope boundary (`.claude/rules/design-and-docs.md`) and you never edit one during
implementation. But a security downgrade is not a scope question — it changes the product's threat
model, which is a decision reserved to Jon. So:

1. **Say it in one line, before you implement that part.** Name the weaker option the design
   specifies, the exposure it creates, and the secure alternative. That is the whole message.
2. **Keep working everything that does not depend on the answer** (§6, §8A). This is an escalation
   to keep going, not a stop.
3. **Never silently implement the weaker option, and never silently substitute the stronger one.**
   Silently downgrading is §13; silently overriding the design is a scope violation. One line to
   Jon settles both.

The same applies to a task file, an issue report, or a bug report that asks for the weaker option.
An instruction to build something less secure than the available alternative is worth one sentence
of confirmation, every time.

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
