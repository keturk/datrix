---
model: claude-opus-5-5
effort: high
description: Turn the consolidated-NNN-*.md findings files in d:\datrix\reports\finding into implementation-ready design documents in d:\datrix\design — numbered from 010 in steps of 10, each at most 100 lines, never referencing a later design, and consistent across every platform and every language the change reaches. Scripts and local models do the reading, grouping and checking; this skill writes the designs. Writes no findings files: whatever the work turns up goes into an existing design or a new one. Deletes each consolidated file once its content is in designs. Use when Jon asks to "turn the findings into designs", "consolidate to design", or runs /consolidate-to-design.
---

# Consolidate to Design

`consolidated-NNN-<slug>.md` files (output of `/consolidate-findings`) hold defects grouped by
theme. This skill turns them into **designs** that `/implement-design-direct` can implement
without a question: one design per fix shape, in the order they must be built.

It writes designs under `d:\datrix\design\` and deletes converted consolidated files, nothing
else. It fixes no code, files no tasks, and **never writes a findings file** — Jon's order for
this skill, which overrides the "nothing you notice is dropped" rule in CLAUDE.md. Anything you
notice that no source mentions goes into an existing unimplemented design that owns the surface,
or into a new design.

**How the work is split.** Scripts and local models do what needs no judgement; you do the design.
A script lists the inbox, the designs and the registered targets, a local model says which defects
still hold and which sections form one fix, and a script checks every design and deletes only what
is carried. Do not read the inbox file by file and do not count lines, check numbers or hunt
references by hand: a real inbox is hundreds of sections, and that reading is where tokens go.
Read source code by range only for the facts a design cites.

Work alone: no subagents. The only agent you may dispatch is the `decision-advisor` (Phase 2).

## How to invoke

```
/consolidate-to-design
```

All commands below are `powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" <command> ...`
(`skill/quick-reference.md`). Exit 3 means no local model answered: do that phase yourself.
Every model answer is a lead: prove it with a ranged Read before a design relies on it.

## Hard rules for every design

1. **At most 100 lines**, counting every line including the conformance section. A fix shape
   that needs more is split along its natural seam into several designs, each complete on its own.
2. **Ready for implementation.** An implementer needs nothing but the design and the code.
   Every fact is looked up now and cited `path:line` (code you read this session, never the
   finding's old line numbers). No `TBD`, "verify during implementation", "decide later", open
   questions, or "for now". Work items name package, file, symbol and the change; contracts and
   test lists, not code bodies. Size is a **census** (what it names, with the count and the query
   that produced it) — no hours, days or effort figure (`design-and-docs.md`).
3. **Numbering.** Files are `NNN-<slug>.md`, `NNN` three digits, first design `010`, then `020`,
   `030`… An inserted design takes a free number between its neighbours (Phase 4).
4. **No design references a later design.** A design cites another only by full file stem
   (`020-shared-hosting-plan`), only a lower number, and only as `Depends on:` or where it builds
   on it. Anything a design needs from a later design means the order is wrong: renumber.
5. **Platform consistency.** A design that changes what a platform (docker, aws, azure, any
   other registered one) realizes states how **every** registered platform realizes the same
   capability in this design — a work item per platform, or the platform already does it
   (cite `path:line`). G2/G3: no platform ends up lacking what another has; a gap is never
   an exemption.
6. **Language consistency.** A design that changes what a language (python, typescript, any other
   registered one) emits does the same for **every** registered language, from one shared
   implementation at the most agnostic layer that can own it (G1, G4, G9). When copies disagree,
   the strongest behaviour (fails closed, reads everything the DSL declares) wins in the shared
   layer. Client and artifact generators (angular, flutter, …) follow the same rule when the change
   reaches them.
7. **The target set comes from registration, never from memory** — `design-inventory` prints it
   (read from the `datrix.languages`, `datrix.platforms` and `datrix.generators` entry points).
   Name no target in shared code.
8. **A design never references a consolidated file or a finding**, by name, number or section. It
   is self-contained.
9. **Jon's orders bind.** Check every decision against CLAUDE.md and the memory index: no mypy, no
   whole-suite runs, no LOC-ratchet work, framework tests are static (they never compile, run or
   deploy generated output), no design or task number in code comments, docs or commit text, no
   customer term (use Product/Order/Customer). A conflicting part is cut, not offered.
10. **Security posture is stated** for any design touching auth, secrets, transport, trust-boundary
    input, permissions, logs or an emitted default. The more secure option wins; it is never a
    trade-off to weigh.
11. **Docs ride with the code.** A doc change is a work item of the design that creates the surface
    it documents, never an earlier or separate design (the docs gate forbids forward references).

## Phase 1 — Inventory and verify (scripts and local models)

```
skill-assist.ps1 design-inventory
skill-assist.ps1 design-verify
```

`design-inventory` writes `d:\datrix\.tmp\assist\design-inventory.md`: the registered targets, every
existing design (status, lines, dependencies, whether it can still be extended), the number an
appended design takes and the free numbers in each gap, and every unconverted section with the
files it cites. A consolidated file still in the inbox is unconverted; there is no register. If
none exists, say so in one line and stop.

`design-verify` writes `design-verify.md`: per section, the cited files that no longer exist
(exact) and a local model's STILL HOLDS / FIXED / UNCLEAR with citations checked against what it
was sent. `--no-model` lists only the sections with no usable cited file.

Use the verdicts to skip reading: a section read as **FIXED** is proven fixed with a ranged Read
of the lines it cites before you drop it (list it, with those lines, in your report); a section
that **STILL HOLDS** is re-read only at the lines its design will cite; **UNCLEAR** you read.

## Phase 2 — Group into fix shapes (local model, then you)

```
skill-assist.ps1 design-plan
```

`design-plan.md` proposes the fix shapes: sections one implementer fixes with one change, each with
its size, the repositories and registered targets its cited files sit in, a flag where it is likely
over 100 lines, the existing design a shape was placed in, and a `REVIEW` line per model decision.
Settle every `REVIEW` line (open a section only to settle what its title does not). Split a shape
the plan marks large, merge shapes the model kept apart, and move a defect to the design that owns
its seam. Place each fix at the most agnostic layer that can own it.

**The failure to avoid:** one design per consolidated file, or one per section. A shape is what one
implementer builds as one change, whatever files the findings were filed under. A 100-line design
carries about four or five sections, so check the ratio (the plan's header gives both counts): a plan
with nearly as many shapes as sections has not grouped, and one with shapes of ten sections has not split.

If a shape needs a decision the docs, the guidelines and the security ranking do not settle,
dispatch the `decision-advisor` with the question, evidence, options and your recommendation, and act on
`RECOMMEND`. On `ASK_JON`, ask Jon in one line and keep writing every design that does not depend on
the answer.

To learn how existing code does something before you cite it, ask `ask_files` (a lead; confirm the
lines it cites with a ranged Read). Definitions and call sites come from the code index.

## Phase 3 — Target reach

The plan lists which registered targets each shape's cited files sit in; that is the floor, not the
set. For each fix shape decide for every registered platform, language and generator: **this design
changes it** (work item), **already behaves so** (`path:line`), or **the change does not reach it**
(why, in a clause). These rows are the design's `## Target consistency` section. A target the shape
leaves different from another is a defect in the draft, not a result. `design-check` proves the set
comparison: a design that names a `datrix-codegen-<key>` repository of a kind must name every
registered target of that kind in this section.

## Phase 4 — Order and number

1. **Already-written designs first.** A defect that belongs to an existing design that
   `design-inventory` marks extendable (not implemented, no implementer ledger) is **added to that
   design** (edit it: problem, work items, acceptance, conformance), if it still fits 100 lines;
   otherwise it becomes a new design. A design that is implemented or being implemented is never edited.
2. **Dependencies set the order.** If design A builds on B, B has the lower number. Otherwise order
   by priority: security, then correctness, then target parity, then tests, tooling and docs.
3. **Pick the number** from the inventory: an unconstrained design takes the appended number
   (first `010`, then +10). An insertion needs a free integer greater than every design it depends
   on and less than every existing design that must depend on it: the inventory lists the free
   numbers, multiples of 5 first. If none is free, renumber the later designs upward in steps of 10,
   rename the files, and rewrite every stem reference to them in `design\`.

## Phase 5 — Write the design

One `Write` per design (the guard refuses a design lacking the conformance section). Template:

```markdown
# NNN-<slug>

Status: Draft
Depends on: 030-<slug>, 060-<slug>   (or "none")

## Problem
What is wrong now, per defect: the construct, `path:line` read this session, the observed wrong
behaviour, and the consequence. Facts only.

## Decisions
D1. … each with the rule or evidence that settles it (guideline, doc, code). No alternatives left open.

## Work items
1. `<package>`: `<file>` — the change, contract or signature. Census: <count> via <query>.
2. …

## Target consistency
| Target | Realization |   one row per registered platform / language / generator the shape reaches
|---|---|

## Security posture
Stated, or "not touched: <why>".

## Acceptance
Negative and positive properties, each checkable statically, with the feature tag and the
`-Specific` files; the set comparison (`consumed − produced`) that lands as a validator or test.

## Design guidelines conformance
- G1: <how> | N/A: <why>
…
- G12: …
```

Write for an implementer who has not seen the finding: no "as discussed", no finding wording
carried over, and **no reference to a consolidated file, a finding or its section numbers**. The
design's Problem section carries every fact the implementer needs from the finding, with its own
`path:line` citations (which is also what lets `design-close` prove the defect was carried). Do not
name a design or task number inside anything the design tells the implementer to commit.

## Phase 6 — Check, then delete what is converted

```
skill-assist.ps1 design-check
```

Exact, over the whole folder: unique numbers from 010; at most 100 lines; `Status:` and
`Depends on:` lines with every dependency an existing lower-numbered design; no mention of a design
with an equal or higher number; every guideline answered (read from design-principles.md); no
placeholder, deferral, effort figure or reference to a consolidated file; target consistency as a
set comparison. Fix every line it prints (a `[review]` line is judged: a retention period of "days"
is fine, an effort figure is not) and run it again until it prints `PASS`.

```
skill-assist.ps1 design-close --finding <consolidated file>... [--fixed C013.2 ...] [--apply]
```

Deletes a consolidated file only when `design-check` has no error and every file path cited by each
section (except the `--fixed` sections you proved already fixed with the cited lines) appears in a
design. It lists the sections it could not prove carried (a cited path no design mentions, or a
section citing no file): carry the defect into a design, or add `--fixed` when the code proves it
gone, and run again. Run it without `--apply` first; with it, a passing file is deleted. For a file
holding a section that waits on an `ASK_JON` answer, delete nothing: remove only its converted
sections from the file by hand, keeping the waiting ones unchanged, so a re-run does not convert
them twice.

Never move or copy a finding anywhere, and never delete a consolidated file by hand.

**Report to Jon**, short: consolidated files read and deleted, designs written (number, slug,
one-line shape) and designs extended, sections found already fixed (with the lines proving it),
renumbering done, the `design-check` result. No "remaining" section: a section neither converted
nor waiting on a question to Jon means you are not finished.
