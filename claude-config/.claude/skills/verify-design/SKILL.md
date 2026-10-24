---
description: Decide whether design documents under d:\datrix\design are ready for implementation, against one fixed checklist, so repeated reviews converge instead of finding something new each time. Reads the design's whole dependency chain and the guidelines first, proves every finding against the code, the docs or the engine's own documentation, classes each one as BLOCKING, IMPLEMENTER_CHOICE or FALSE_POSITIVE, and records a READY verdict with the files' hashes so an unchanged design is never reviewed again. With --fix it also fixes the blocking findings a rule or a fact settles. Use when Jon asks whether a design is ready, to "verify the design", "review the design for readiness", or runs /verify-design.
model: claude-opus-5-5
effort: medium
---

# Verify Design

A design is ready when an implementer can build it without a question and the result behaves the
same on every registered target. This skill answers that against **one closed checklist**. Anything
outside the checklist does not block, and a finding no evidence proves is not reported. That is what
lets a second review of an unchanged design reach the same verdict as the first.

It reads designs and the code; it edits only designs (with `--fix`) and its own ledger. It writes no
findings file (`.claude/docs/design-and-docs.md`, "Design work files no findings"), files no task and
changes no code. Work alone: no subagents. A question goes to the `decision-advisor`, or straight to
Jon when `DATRIX_NO_SUBAGENTS=1`.

## How to invoke

```
/verify-design <scope> [--fix] [--force]
```

- `<scope>`: a design path or number (`170`), a range (`100-360`), or `all` (every design in
  `d:\datrix\design`).
- `--fix`: also fix every BLOCKING finding whose fix follows from a rule, a doc, the code or an
  engine's documentation (Phase 5). Without it the skill only reports.
- `--force`: review even when the ledger says the scope is READY and unchanged.

Never edit a design that is implemented (`Status: Implemented`) or being implemented (a
`d:\datrix\.tmp\implement-direct-<stem>.md` ledger exists): verify it and report only.

## Phase 0 — The ledger

The ledger is `d:\datrix\.tmp\verify-design\<stem>.md`, one per design. It holds the verdict, the
date, the checklist version (`checklist: 1`; raise it whenever this file's checklist changes) and
the SHA-256 of the design and of every design in its dependency chain
(`Get-FileHash -Algorithm SHA256`). A design whose ledger says READY, under the current checklist
version, with every hash unchanged, is reported `READY (unchanged since <date>)` and not reviewed
again unless `--force` is given. Any changed hash (an edit to the design, or to any design it
depends on) means a full review.

## Phase 1 — Context, before any judgement

A finding made without this context is the commonest false positive. Read, in full:

1. `datrix/docs/architecture/design-principles.md` § Design Guidelines (G1–G12) and
   `.claude/docs/design-and-docs.md`.
2. Each design in scope, and every design it depends on, transitively (its `Depends on` line and
   every lower design it cites by number). For a range, every design in it. A series header (such
   as 100's `Series` paragraph) applies to every member.
3. The registered targets: `skill-assist.ps1 design-inventory` (languages, platforms, generators,
   from their entry points); the RDBMS engines from `all_rdbms_engines()`
   (`datrix_common/config/datasource/rdbms_engine.py`).
4. `skill-assist.ps1 design-check` (`datrix/scripts/skill/quick-reference.md`). Every line it prints
   is a candidate, judged in Phase 3 like any other.

Decisions a design records as Jon's ("by Jon's decision", an accepted size) are settled. A finding
that only reopens one is a FALSE_POSITIVE. A recorded decision that causes a checklist defect is
BLOCKING, and the finding names the decision.

## Phase 2 — The checklist (closed)

Check every design in scope against each item. These are the only questions.

| Id | Check | How |
|---|---|---|
| C1 | **Order.** The design depends only on lower-numbered designs; no decision of it needs something a later design defines. A later design may be named as a pointer ("320 deletes it"), never as a premise. | `design-check`; read each mention of a higher number |
| C2 | **No contradiction.** No other design in the folder defines the same name, symbol, change kind, diagnostic code, entry kind, file or behaviour differently, and the design agrees with itself. | grep the folder for every name the design introduces or changes |
| C3 | **Code facts hold.** Every `path:line`, symbol and census in it exists and says what the design claims, in the current code. | ranged Read or the code index for each; re-run each census command |
| C4 | **Every registered target is covered.** For each language, platform, generator and engine the design reaches, its behaviour is stated, and it matches the others' (or the difference is a counted `capability_gaps` row). A vendor fact the design relies on (an engine's limit, a platform's API) is cited from the vendor's documentation. | registration (Phase 1); the vendor's docs |
| C5 | **Everything it adds is consumed.** Each new change kind, diagnostic, model field, entry kind, verb or knob has its consumer stated: its outcome, phase, renderer, refusal, and a test. | trace each to the design or the lower design that consumes it |
| C6 | **One reading.** No sentence admits two readings that would build different behaviour, and every work item names its package, file or symbol and the change. Detail the code standards or existing conventions settle (names, signatures, test placement, fixture layout) is not ambiguity. | for each candidate, write both readings and the behaviour each builds |
| C7 | **Rules.** All twelve guideline bullets answered and true; security posture stated where it touches auth, secrets, transport, trust-boundary input, permissions, logs or an emitted default, and the more secure option chosen; no Jon order or standing decision contradicted; no `TBD`, deferral, open question or effort figure. | `design-check`; design-principles.md; design-and-docs.md |

Size is reported, never judged: a design over 100 lines is listed with its count for Jon.

## Phase 3 — Prove, then class each candidate

A candidate becomes a finding only with evidence read in this session: the design's line, and the
conflicting line, code (`path:line`) or vendor documentation (URL) that proves it, plus the concrete
failure: what an implementer would build wrong, or which target or engine would behave differently
or fail. No evidence, no finding.

| Class | Meaning | Reported as |
|---|---|---|
| **BLOCKING** | It fails C1–C7: a contradiction, a dependency on a later design, a wrong code fact, a target that would behave differently or fail, something added with no consumer, two readings that build different behaviour, or a guideline, security or order breach | each, in full |
| **IMPLEMENTER_CHOICE** | A detail the design leaves open that the code standards, conventions or the design's own rules settle the same way for any implementer | one line each, with the rule that settles it |
| **FALSE_POSITIVE** | The design, a lower design, the guidelines or the code already answers it | one line each, with the line that answers it |

**Never a finding:** wording, style or "could be clearer" where only one reading builds anything;
a feature, test or target the design does not need; a hypothetical future target; a preference
between two correct options; a `design-check` line about format when the design states the same
fact in another form; reopening a decision recorded as Jon's.

## Phase 4 — Verdict

**READY** when no BLOCKING finding remains in the design. **NOT READY** otherwise. A range is READY
when every design in it is.

## Phase 5 — Fix (`--fix` only)

1. Fix each BLOCKING finding whose fix follows from a rule, a doc, the code or vendor documentation:
   the change in the design that closes it, with its evidence cited in the design, the design's
   tests and conformance bullets kept true. Never close a finding by deleting what the design needs,
   or by compressing it into vaguer text.
2. A finding that needs a genuine choice between correct options goes to Jon (through the
   `decision-advisor` unless subagents are forbidden) in one line: the finding, the options and your
   recommendation. Keep fixing every finding that does not depend on the answer.
3. **A fix is new text.** After the fixes, run C1–C3 again over each design you edited and over
   every design that names something a fix introduced or changed (grep the folder for each name).
   A finding a fix caused is fixed now. Then stop: the scope is not reviewed again in this run.

## Phase 6 — Ledger and report

Write the ledger (Phase 0) for every design reviewed, READY or NOT READY, with the hashes of the
files as they are after any fixes.

Report to Jon, short:

- the verdict per design (and `READY (unchanged since <date>)` for the ones skipped);
- each BLOCKING finding: design `file:line`, check id, evidence, failure, and the fix applied (with
  `--fix`) or recommended;
- IMPLEMENTER_CHOICE and FALSE_POSITIVE findings, one line each with the line or rule that settles
  them, so the next reviewer sees they were considered;
- designs over 100 lines, with their counts;
- the questions sent to Jon, if any.
