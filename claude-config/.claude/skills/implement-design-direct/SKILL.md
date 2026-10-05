---
description: Implement a design document directly, with no task generation and no orchestrator - build it in this session from the design itself, then verify against the design and absorb it into the docs
model: claude-sonnet-5-5
effort: medium
disable-model-invocation: true
---

# Implement Design Direct

Takes one design document and carries it all the way **without task files**: **implement → verify → absorb**. The design is the work order. There is no `/operationalize-design`, no `.tasks\` folder, no `dependencies.md`, no `/task-orchestrator`, no subagent. Every rule of the skill it hands to (`/verify-implementation`, `/absorb-design`) still binds inside that hand-off.

```
DOCUMENT ──► read in full ──► ambiguity + security gate ──► work plan (scratch ledger)
                                                                    ▼
                                      implement in dependency order, enforcement first,
                                      each step: code + tests + docs + author's proof
                                                                    ▼
                                      /verify-implementation (fixes what it finds)
                                                                    ▼
                                      design PROVEN? ── yes ──► /absorb-design (deletes the doc)
```

## When to Use

- Jon has an approved design document and wants it built **in one session, with no task machinery**
- Jon says "implement this design directly", "no tasks, just build it"

`/implement-design` decides between this and the task path on size; this skill makes that decision for Jon: always direct. The cost of that choice is real, and it is yours to carry (see Run discipline): the task path gave ordering, per-surface coverage, and a bounded unit of review for free. Here you reproduce all three yourself, in the work plan.

## How to Invoke

```
/implement-design-direct

DOCUMENT: d:\datrix\datrix\docs\designs\some-design.md
```

With options:
```
/implement-design-direct

DOCUMENT: d:\datrix\datrix\docs\designs\some-design.md
KEEP SOURCE: true      # absorb the content but keep the design file
FIX: false             # verify-implementation reports only, changes no code
```

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| DOCUMENT | Yes | Path to the design document |
| KEEP SOURCE | No | Passed to `/absorb-design` |
| FIX | No | Passed to `/verify-implementation` (default: fix what is wrong) |

## Prereqs — read first

- `d:\datrix\.claude\CLAUDE.md`, `MEMORY.md`, `.claude/rules/design-and-docs.md`, `.claude/rules/repo-boundaries.md`
- The DOCUMENT **in full** — it is the scope boundary
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md), [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md), [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) (each is a core with a read-when pack index: open the packs for the surfaces the design touches)
- **Don't know where something is documented?** `powershell -File "d:/datrix/datrix/scripts/dev/ineedtoknow.ps1" "<question>"` — a brief answer with the file and line range to open (a lead: open the lines before acting).
- `datrix/scripts/quick-reference.md` before calling any repo script

## Run discipline

- **One run, no hand-backs.** Finishing the code is not a stopping point; verify starts in the same turn. The run ends at the absorb summary, at a valid B1–B4 blocker, or when Jon says stop.
- **Size never changes the path.** A design spanning several packages or languages is still done here. Discovering the job is bigger than it looked is grounds to **expand and continue**, never to stop or to hand the remainder to task files. Do not create a phase, a `.tasks\` folder, or a task file; "file a task" is not an exit in this skill.
- **Context compaction is not an exit.** What survives compaction is the code on disk and the ledger (Step 2). Re-read the ledger and the DOCUMENT after a compaction and continue at the first unchecked step.
- **The only legitimate waits:** an unresolved design question or unchosen explicit alternative (Step 1), a design that specifies a less secure option than one plainly available (execution-contract §13.7), and `/absorb-design`'s "no clear target" / "content missed" prompts. Ask in one line with your recommendation and keep working everything that does not depend on the answer.
- **Never modify the design document.** Only `/absorb-design` touches it (it deletes it). This path never rewrites its `Status:` line either: that edit belongs to `/task-orchestrator`.
- **Never cite the design in a committed artifact** — no design number, filename, or path in code comments, docstrings, docs, tests, or commit messages (`design-and-docs.md`).
- **No subagents.** Only `/task-orchestrator` dispatches. Do every step yourself, sequentially. A subagent never runs this skill.
- **Read narrowly, never less.** Use the code-index tools (`find_canonical`, `find_symbol`, `find_references`, `outline`, `search`) and ranged reads; `ask_files` for "what does this do" is a lead you confirm with a ranged Read; `ineedtoknow.ps1 "<question>"` for documented knowledge (a rule, an invariant, which pack holds what). Do not read large source files whole.

---

## Step 1: Gate — ambiguity, security, scope

Read the DOCUMENT in full, then clear these gates **by investigation, never by assumption** (a plausible guess is an assumption).

1. **Open items.** List every open question, "TBD", "verify during implementation", and explicit alternative (Option A/B). Close each implicit question with code, docs, or logic-map evidence, and record the evidence. An **explicit alternative is always Jon's call**: your evidence only informs the recommendation. Ask in one line and wait; do not pick.
2. **Security posture.** Every auth, secret, transport, trust-boundary input, injection, permission/exposure, error/log, and crypto surface, and every default the generator emits on them, must state its posture. An unstated posture is an open item. A design specifying a weaker option than one plainly available follows §13.7: say it to Jon in one line (weaker option, exposure, secure alternative), keep working what does not depend on it, and never silently implement the weaker option or silently substitute the stronger one.
3. **Scope census.** From the design, derive:
   - every package the change touches, and every package it **reaches** (consumes the changed surface) — `find_references`
   - every fixture, example, and project config exercising an **old path** that the design replaces (dual-implementation risk: old tests pass on the old path while the new path ships untested)
   - every **set of surfaces** an invariant ranges over (languages, platforms, packages, positions) — registered ones enumerated from the registry, never a literal list
   - every migration, rollout, or adoption step, verbatim and numbered
   - every doc the change touches, by owning repo `docs/`

4. **Sibling-target parity.** When the design is scoped to one target — a language (`datrix.languages`), a platform (docker, AWS, Azure, …), or a frontend target — one Datrix semantics is realized by every target of that kind (architecture cheat sheet, standing rule 2). Enumerate the sibling targets of the same kind **from the registry** (never a literal list) and check each one by reading its code (`find_symbol` / `search` / `outline`, ranged reads):
   - **Sibling already implements the behaviour properly** → the target you are building must produce the **same observable behaviour**; only rendering differs. Take the sibling's semantics as the specification (inputs accepted, outputs, error cases, security posture, defaults). Where the logic is target-agnostic, hoist it to the shared layer (Step 2 "Shared layer first") instead of writing a second copy; where it is rendering, mirror the sibling's contract in the new target. A divergence you would introduce is a defect in your plan, not a design choice.
   - **Sibling implements it but wrongly or more weakly** (fails open, drops a declared input, different semantics) → the strongest correct behaviour wins for all targets; fix the sibling when the fix is small, otherwise write a findings file. Never copy a weaker behaviour for symmetry.
   - **Sibling does not implement it** → not your scope: the design is the boundary. Record it as a counted `capability_gaps` row where the architecture requires one, or a findings file, and carry on. Do not build the feature in siblings.
   Record per sibling: `{target}: same | diverges-fixed | gap | n/a` with the `path:line` read. The Step 2 ledger then carries a row for each sibling change the verdict requires, and its acceptance line names the sibling parity check (a tagged test that runs the same case through both targets' own code, or a registry-driven conformance probe — never a hardcoded target list).

State one line: `SCOPE: {packages} | reaches: {packages} | surface sets: {n} | migration steps: {n} | siblings: {kind: n checked, n same, n gaps}`.

---

## Step 2: Work plan — the ledger replaces the task graph

Write the ledger with `Write` to `D:\datrix\.tmp\implement-direct-{slug}.md` (a scratch folder; never inside a package repo). It is your task graph, your dependency order, and your survival kit across compaction. It is **not** a task file and not committed.

One row per unit of work; each row carries:

| Field | Content |
|---|---|
| id | `U01`, `U02`, … in execution order |
| change | one cohesive behaviour in one package (and one language where it is language-specific) |
| files | edit sites, `path:line` where known |
| requires | the units that must be done first |
| acceptance | the design's invariant/requirement this unit satisfies, plus its **negative** check (the old/forbidden state is gone on the whole affected surface) and **positive** check (the new path is exercised) |
| tests | the test files to add and the feature tag each carries |
| state | `[ ]` / `[x]` with the proof command and its output pasted when done |

Ordering rules, the ones the task path enforced for you:

- **Enforcement before what it governs.** A unit that establishes or enforces an invariant (a validator, a fail-loud guard, a parser-level rejection, a conformance check) comes **before**, and is required by, every unit that relies on it or migrates content it polices. Never order a migration ahead of its guard: it would pass against an absent check.
- **Shared layer first.** Place logic at the most language/platform-agnostic layer that can own it (`datrix-common`, `datrix-codegen-kernel`, `datrix-codegen-common`); per-language and per-platform units require the shared unit. A hoist ported to N targets is one shared unit plus N per-target units.
- **Every surface in a set gets a row.** An invariant over a set of surfaces has a unit or an explicit acceptance line for **each** member. A guard shipped on the obvious surface with the rest silently dropped is a failed run even under green tests.
- **Every migration step gets a row**, and every old-path fixture/example/config from the census is converted in the same run. "Convert X to Y" is work here, not future work, unless the design explicitly defers it.
- **Tests and docs ride inside each unit.** No separate test, verify, or docs unit.

Keep units bite-sized: one package, one behaviour, roughly 80–250 production lines. A bigger unit is split. There is no ceiling on the number of units.

---

## Step 3: Implement — unit by unit, in ledger order

For each unit, in order:

1. **Find what exists.** `find_canonical` / `find_symbol` / `search` before writing new logic. Read the neighbours (what upstream guarantees, what downstream requires): an insertion is an integration. Mirror an existing pattern by citing it; do not restate it.
2. **Implement it completely** to the code standards in CLAUDE.md: full type hints, no placeholders, no silent fallbacks, no workarounds, security by default, fail closed. A hoist removes **every** private copy. Where per-target copies disagree, the shared implementation takes the strongest behaviour (fails closed, reads everything the DSL declares, most secure, most correct output); no language or platform is the reference by default.
3. **Land every seam comparison as code.** Wherever the unit adds a producer or a consumer of a set of names or values, compute `consumed − produced`, require it empty or explained, and land the comparison as a generation-time validator or a test, not a one-off diff. Parse structure; prove the matcher finds an instance you know exists.
4. **Write the tests of the new behaviour** in the owning package: real objects, no mocks, each test carrying a feature tag, with the negative case alongside the positive. Update the docs the change touches in the owning repo's `docs/`, as content, with no pointer to the design.
5. **Run only the tests of what you changed**, naming first the failure the run could show that your evidence cannot: `test.ps1 <pkg> -Specific "a.py,b.py"` for the files, and `-Tag <tag>[,<tag>]` for the behaviour, **in every package it reaches** (at most 3 tags per run). Never a whole suite, never a sweep assembled from targeting flags.
6. **Prove the unit.** Run the unit's negative and positive acceptance check and paste command + output into its ledger row, then tick it. An unproven unit is not done, whatever the suite colour.
7. **Cross-surface check.** If the unit touched a shared layer, run the tagged tests of the changed behaviour in each package the change reaches before moving on. "datrix-codegen-python is green" is not done for a shared-layer change.

Generation checks follow the one-example, one-language rule: regenerate only the affected project, only for the language it failed under, and prefer a test over a generation run. Never `-All` / `-Domains` / `-TestSet`.

**When a unit fails against a security control, the control is the requirement.** Never loosen, exempt, or widen it to turn the check green.

**A defect you find on a surface you touched is yours:** fix it. A design-sized one gets a findings file under `d:\datrix\reports\finding\` (brief: what, `file:line`, evidence, impact) and the run carries on; a small one is fixed in place.

After the last unit, run the ledger's **negative sweep**: for every "X replaces Y" in the design, prove Y is gone everywhere on the surface (structured search, with a matcher proven non-vacuous), pasted as command + output. Then record the list of files changed.

---

## Step 4: Verify

Invoke `/verify-implementation` through the Skill tool with `DESIGN: <path>`, `TASKS: none`, and `FILES:` the changed files from the ledger. Pass `FIX: false` only if Jon set it.

It reviews the code on disk against the design, fixes what is wrong or missing, and ends with `Design conformance: PROVEN | INCOMPLETE`.

- **PROVEN** → Step 5.
- **INCOMPLETE** → the design is not implemented. Fix what verify could not, add the corrected units to the ledger, and run `/verify-implementation` again. A second INCOMPLETE on the same finding means the diagnosis was wrong: re-diagnose rather than patch. Stop only on a valid B1–B4 blocker with the four-part proof (verbatim error text; the fix attempted at `file:line`; why it failed; the B1–B4 code), and then **do not absorb**: report the blocker.
- A design-sized defect verify surfaces gets a findings file and is named in the final report. It does not block absorbing a design that is otherwise PROVEN.
- With `FIX: false`, verify is report-only: print its report and stop here without absorbing.

## Step 5: Absorb

Reached only on `Design conformance: PROVEN`.

Invoke `/absorb-design` through the Skill tool with `DOCUMENT: <path>` (and `KEEP SOURCE: true` if Jon set it). It transfers the content into the official docs, replaces every reference, and deletes the source. Units that already updated their docs report "already present"; that is correct, not a defect. Its "no clear target" and "content missed" prompts are real waits.

## Step 6: Final report

Lean, data only:

```
IMPLEMENT-DESIGN-DIRECT: {title}
Units: {N} done ({N} packages, {N} files changed)
Verify: PROVEN ({n} requirements; {n} fixed by verify)
Absorb: {N} units transferred, {N} files, source DELETED | PRESERVED
Findings filed: {paths | none}
```

If the run ended on a blocker, report that instead: the four-part proof and the step it stopped at. Nothing else.

## Anti-Patterns

- **NO task files, phases, `.tasks\` folders, `dependencies.md`, or orchestrator dispatch** — the ledger in `D:\datrix\.tmp\` is the whole plan, and it is scratch.
- **NO skipping the ledger because the design "looks small"** — it is what carries ordering and per-surface coverage that the task graph used to carry.
- **NO migrating before the guard** — enforcement units precede and gate what they police.
- **NO covering the easy surface and dropping the rest** — every member of an invariant's surface set has a unit or an acceptance line.
- **NO implementing a single-target design without reading its sibling targets** (languages, platforms, frontends) — where a sibling already does it properly, the new target matches its behaviour; a per-target difference is a defect.
- **NO stopping partway because the design is big or context is long** — expand, compact, continue.
- **NO absorbing before PROVEN** — absorb deletes the one document verify measures against.
- **NO editing the design document**, including its `Status:` line.
- **NO design number, filename, or path in code, tests, docs, or commit messages.**
- **NO whole test suites** — targeted `-Specific` / `-Tag` runs only, in every package the change reaches.
- **NO subagents** — this skill does the work itself, sequentially.
- **NO workarounds, NO dodging** ("out of scope", "pre-existing", "track separately" are the work, not blockers), **NO expedient fixes** ("for now" is banned; the defect sets the size).
- **NO git restore/checkout/reset/stash/revert** — undo your own edits manually.
