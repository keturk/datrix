# Execution Contract — Spend (§10–§11)

Part of the [execution contract](./execution-contract.md); section numbers are stable and cited by number across the repo.

**Read when:** you are about to dispatch a subagent or plan how much a run may spend (§10), or about to run a command, scan, gate or test whose cost you have not weighed (§11).

---

## 10. Delegation economy — a subagent is a purchase, not a free action

Every dispatched agent costs real budget drawn from a shared, exhaustible pool. A run that reaches
the right answer by spending a week of budget in a day is **not** a good run. Cost is part of the
engineering judgment, exactly like correctness and scope — not a separate concern owned by someone
else. You cannot see the meter; that does not excuse you, because you can see every agent's reported
token count and you can see how many you dispatched.

### 10.0 Depth is one — agents never dispatch agents

The session Jon talks to — an orchestrator running waves — may dispatch agents. Planning and
design skills never do: `/operationalize-design` (and `/generate-tasks`) read, decide and write
every file in the session itself, because a dispatched writer re-reads the template, the design
and the manifest before producing anything — a three-writer fan-out once spent 339k tokens and
wrote no task file. **An agent that was itself dispatched may not dispatch more.** A nested
fan-out multiplies token cost with no added coverage (one such child burned >140k tokens almost
entirely on dispatch overhead) and fragments reporting. If you are a subagent, do the work
yourself, sequentially, and report any expansion to the dispatcher. `guard-no-nested-agents.py`
refuses the `Agent`/`Task` tool for any caller that is a subagent, with no override. Every
dispatch brief you write as an orchestrator says so: `Do NOT spawn subagents. Do this work
yourself, sequentially.`

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
tightly-scoped dispatch, not a request for exhaustive investigation, broad test runs, and
multi-example verification (no agent ever runs a whole suite — §12.1). Every extra acceptance
criterion you write is budget the agent will spend. Ask for the smallest evidence that actually
proves the fix.

### 10.3 Verify centrally, once — never N times in parallel

**Do not put a "regenerate these other examples / re-run these other tests" list in every dispatch.**
If the orchestrator verifies the wave's targeted tests after the wave lands — and it should — then every
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

Regenerating unrelated examples, running whole test suites, or re-verifying already-green work "to
be safe" is the single easiest way to burn budget for no information. No agent runs a whole suite —
`guard-full-suite-runs.py` refuses every form, for every agent, with no override. Generation
granularity and targeted-only verification are cost rules as much as correctness rules. To prove a fix
generalises, **write a test** — it proves the invariant permanently and costs once, where a corpus
sweep proves it once and evaporates.

**A sweep wearing a targeting flag is still a sweep.** `-Tag`, `-Keyword` and `-Specific` exist to
name the behaviour you changed; assembling a wide list of them, or splitting one sweep across
several runs, is a whole-suite run by instalments. Hard ceilings, enforced by the guard and by the
runner's own collection check: at most 3 tags per run, `-Keyword` in one package, and no selection
keeping over 25% of a package's tests. **The guard staying silent is not a verdict** — producing a
blocked result through an allowed flag is routing around a guard, which §14 and CLAUDE.md both ban.
Before any run, name the failure it could reveal that your evidence cannot; if a grep, a read, or an
already-green targeted run answered it, run nothing.

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
targeted test over a tag run, a parse over a regeneration) — but never narrow the *set* of questions
you must answer to be correct.

**A check is bought for a question, never for a rung.** The static-analysis ladder and the
verification tiers are menus ordered by cost, not sequences to execute. Before running any scan,
gate, or test run, write down (to yourself) the defect class it targets and the failure it would
show that the evidence you already hold cannot. If you cannot name both, the check is punctuation:
it can only return "clean" on code you have already read, and its cost — minutes of wall-clock,
Jon's attention, and a background task to babysit — is paid for nothing. The concrete case: a
three-package `semgrep.ps1` run after the targeted tests, the plugin-load proof, and both repo
gates were already green, launched because "repo static gate" was the next rung. Whole-package
anti-pattern scans are phase-boundary acts; `guard-untargeted-scans.py` refuses them inside a fix
without a named `-Rule` or a stated `SCAN_QUESTION:`, and refuses `-All` and subagent runs outright.

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
  unrelated file. Re-run a test when your change could plausibly affect it — not as punctuation.
- **Do not regenerate a project to verify a change you can verify at the source.** Regeneration is
  minutes and a large output; reading the emitted template or running its unit test is seconds.
  Regenerate when the artifact is the deliverable, or when nothing cheaper can prove the point.
- **Do not restate context back to yourself.** Re-printing a file you already hold, re-listing a
  directory you already listed, or dumping a log you have already read adds tokens and no knowledge.

### 11.3 Ask the cheapest question that distinguishes the answers

Before running anything, know what each outcome would change. If both outcomes lead to the same next
action, the command is not worth running. Prefer the narrowest form that settles it: one targeted
test over a tag run, one `grep` over a full read, one `--query` over a full JSON dump, `head` over
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
