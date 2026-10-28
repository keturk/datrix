---
description: Implement a design document directly, with no task generation and no orchestrator - build it in this session from the design itself, then verify against the design and absorb it into the docs
model: claude-opus-5-5
effort: high
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
| LEDGER | No | The ledger path to use in Step 2 (default: `D:\datrix\.tmp\implement-direct-{slug}.md`). If it already exists, it is the work so far: read it and the DOCUMENT, and continue at the first unchecked unit |
| STOP AFTER | No | `plan`: end the run after Step 2 with the reply `PLANNED: <ledger path>`, and implement no unit. `implement`: end the run after Step 3 with the reply `IMPLEMENTED: <ledger path>`, and do not verify or absorb |
| UNIT | No | A ledger unit id (`U03`); needs an existing ledger. Skip Steps 1-2, read the ledger and the DOCUMENT, and do only that unit's Step 3 items 1-7. List the unit's changed files under `## Files changed` in its proof file (never in the ledger) and tick its row. When the prompt carries a `LEDGER LIMITS EXCEEDED` line, shrink the ledger to the limits first (Step 2). End with the reply `UNIT DONE: <id>`, and do not verify or absorb |
| GAPS | No | A file holding a `/verify-implementation` report that ended INCOMPLETE. Add a ledger unit for each finding it did not fix, with its acceptance check, and implement those units (with `STOP AFTER: plan`, only add the units) |

## Run it from the CLI

Typed here, the whole run is on this skill's model: `/verify-implementation` and `/absorb-design` invoked through the Skill tool run on the caller's model, not their own. `datrix/scripts/skill/implement-design.ps1 -Design <path>` runs the same chain with each step in its own headless session on its own skill's model: this skill with `STOP AFTER: implement`, then verify, then absorb, with the checks between them done by the script. Every response re-reads the whole context, so one session over all units costs far more than the sum of its units: the script runs the implement step as a `STOP AFTER: plan` session (Steps 1-2, the ledger), then one fresh `UNIT: <id>` session per unchecked unit. What carries from one session to the next is the code on disk and the ledger, so a unit's row must say everything its session needs: files, requires, acceptance, tests.

## Prereqs — read first

- `d:\datrix\.claude\CLAUDE.md`, `MEMORY.md`, `.claude/docs/design-and-docs.md`, `.claude/docs/repo-boundaries.md`
- The DOCUMENT **in full** — it is the scope boundary
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md), [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md), [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) (each is a core with a read-when pack index: open the packs for the surfaces the design touches)
- **Don't know where something is documented?** `powershell -File "d:/datrix/datrix/scripts/dev/ineedtoknow.ps1" "<question>"` — a brief answer with the file and line range to open (a lead: open the lines before acting).
- `datrix/scripts/quick-reference.md` before calling any repo script

## Run discipline

- **One run, no hand-backs.** Finishing the code is not a stopping point; verify starts in the same turn. The run ends at the absorb summary, at a valid B1–B4 blocker, when every remaining unit waits on an `APPROVAL_REQUIRED` question, or when Jon says stop. The one exception is `STOP AFTER: implement`, where the caller runs verify and absorb itself: the run ends when every ledger unit is ticked.
- **The design is the approved scope.** What the DOCUMENT names, you build, completely. Behaviour it does not ask for — a capability, model field, phase or diagnostic its requirements do not need — or a job measuring a multiple of what the design names is not approved: ask Jon in one line starting `APPROVAL_REQUIRED:` (what, why with `file:line`, and its measured size: the counted census × the rate this run measured on its own ticked units, in tokens and agent minutes — never human hours/days, and never scaled from or compared against an effort figure the design states; execution-contract §4) and keep working the ledger units that do not depend on it (execution-contract §4). If every remaining unit depends on it, end the turn on the question. Anything you find that the design does not need goes in a findings file (§5). Do not create a phase, a `.tasks\` folder, or a task file; "file a task" is not an exit in this skill.
- **How and where you build it is yours — never a wait.** Placing code at the layer the architecture assigns (including moving existing code into a package the design does not list, cutting the imports the move makes illegal and updating every importer), a library a required behaviour needs, names, signatures, emitted spellings and fixture shapes are implementation decisions (execution-contract §4): decide from the design, the architecture docs and the security ranking, record each under the ledger's `## Decisions` heading (the choice, the rule or `file:line` it follows), and keep building. If your question would carry "(I recommend X)" and X follows from a rule, a doc or the design, it is not a question: do X. Offering to narrow a test, fixture set or acceptance check so a requirement holds on fewer cases is a cut-down fix (execution-contract §14), never an alternative to put to Jon.
- **Context compaction is not an exit.** What survives compaction is the code on disk and the ledger (Step 2). Re-read the ledger and the DOCUMENT after a compaction and continue at the first unchecked step.
- **The only legitimate waits:** an unresolved design question or an explicit alternative the DOCUMENT leaves unchosen (Step 1), an `APPROVAL_REQUIRED` growth in what is built (above), a design that specifies a less secure option than one plainly available (execution-contract §13.7), and `/absorb-design`'s "no clear target" / "content missed" prompts. Each goes to the decision advisor first; ask Jon in one line only with its `ASK_JON` question, and keep working everything that does not depend on the answer.
- **Never modify the design document.** Only `/absorb-design` touches it (it deletes it). This path never rewrites its `Status:` line either: that edit belongs to `/task-orchestrator`.
- **Never cite the design in a committed artifact** — no design number, filename, or path in code comments, docstrings, docs, tests, or commit messages (`design-and-docs.md`).
- **No subagents, except the decision advisor.** Only `/task-orchestrator` dispatches work. Do every step yourself, sequentially. A subagent never runs this skill. A question you cannot settle (an open item, a growth request, a B2) goes to the `decision-advisor` agent (`decision-adjudication-protocol.md` §5): act on its `VERDICT: RECOMMEND` and record it under `## Decisions`; only its `VERDICT: ASK_JON` question goes to Jon.
- **Read narrowly, never less.** Use the code-index tools (`find_canonical`, `find_symbol`, `find_references`, `outline`, `search`) and ranged reads; `ask_files` for "what does this do" is a lead you confirm with a ranged Read; `ineedtoknow.ps1 "<question>"` for documented knowledge (a rule, an invariant, which pack holds what). Do not read large source files whole: to see a Python function, class or variable use `read_symbol` (`datrix-edit` MCP, dotted names from `outline`).
- **Batch independent calls: one response, many tool calls.** Every response re-reads the whole context, so each turn costs what the context weighs. Reads, greps, code-index lookups and `read_lines` whose arguments do not depend on each other's results go in the same response, as do independent edits (or one `edit_lines` call). A measured run spent 65% of its turns on a single read-only call; open every file of the unit's `files` column and every neighbour you already know you need together, then decide.
- **Mechanical work goes to the scripts, not to your edits or your context** (each in `datrix/scripts/quick-reference.md`; preview first, every time):
  - moving definitions to a sibling module, importers included: `codemods\split-module.ps1 -Module <file> -Plan <json under D:\datrix\.tmp> -DryRun`, then without `-DryRun`. A refusal names what blocks (a cycle with its names, a text reference); fix that, never hand-copy the code;
  - renaming a function, class, variable or module's imports, adding or removing an argument: `codemods\run-codemod.ps1 <NN_recipe> <args> <paths>` (a diff), then `-Write`. Recipe 08 rewrites import statements only: finish a module rename with a text search for the old name;
  - the worklist of a move, rename or deletion: `dev\find-imports.ps1 -Module <dotted,...>` (exact sites, src and tests), and the code index's `find_references` for a symbol;
  - many line edits across files: one `edit_lines` call (`datrix-edit` MCP) rather than N `Edit` calls; replacing or adding a whole Python function, class or variable: `edit_lines` by `symbol` / `after_symbol` with the `span_hash` that `read_symbol` showed;
  - a test fact over many cases: a case row (`cases.ps1 observe|new|migrate|accept`) or a table (`tables.ps1`), per test-guidelines, never N near-identical test functions;
  - names for unnamed `validate` rules: `skill\skill-assist.ps1 rule-names --sites-file <sites>`, a local model's checked proposals, `--apply` after review;
  - a test, generation or deploy log: `digest_log` (datrix-local-llm MCP) for the distinct failures, then a ranged Read of the lines it cites; never the log whole.

---

## Step 1: Gate — ambiguity, security, scope

Read the DOCUMENT in full, then clear these gates **by investigation, never by assumption** (a plausible guess is an assumption).

1. **Open items.** List every open question, "TBD", "verify during implementation", and explicit alternative (Option A/B) **written in the DOCUMENT**. Close each implicit question with code, docs, or logic-map evidence, and record the evidence. An explicit alternative the DOCUMENT presents and leaves unchosen is not yours to pick: put it, with your evidence and recommendation, to the decision advisor, act on its `VERDICT: RECOMMEND`, and ask Jon only on `VERDICT: ASK_JON`. A choice you raise yourself while planning or building — where code lives, a module to move, a library to add, a name, a fixture shape — is not an open item: it is an implementation decision (execution-contract §4). Decide it, write it under the ledger's `## Decisions` heading with its evidence, and carry on.
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

Write the ledger with `Write` to LEDGER, or to `D:\datrix\.tmp\implement-direct-{slug}.md` when none was given (a scratch folder; never inside a package repo). It is your task graph, your dependency order, and your survival kit across compaction. It is **not** a task file and not committed.

The units are **one markdown table, one row per unit**, with the columns below in this order: `implement-design.ps1` reads a unit as a table row whose first cell is its id and whose last cell is its state, and refuses a ledger with no such row (a unit written as a heading or a bullet list is invisible to it). Keep each cell on one line and write a literal `|` inside a cell as `\|`. Example: `| U01 | delete X; Y records Z | a.py:12 | — | D1. Negative: … Positive: … | test_a.py (tag-x) | [ ] |`. Each row carries:

| Field | Content |
|---|---|
| id | `U01`, `U02`, … in execution order |
| change | one cohesive behaviour in one package (and one language where it is language-specific) |
| files | edit sites, `path:line` where known |
| requires | the units that must be done first |
| acceptance | the design's invariant/requirement this unit satisfies, plus its **negative** check (the old/forbidden state is gone on the whole affected surface) and **positive** check (the new path is exercised) |
| tests | the test files to add and the feature tag each carries |
| state | `[ ]`, or when done `[x]` and one line: the proof command, its result in a few words (`pass 98`, `0 flagged files`), and the unit's proof file |

**The ledger stays small.** Every unit session re-reads the whole ledger before it does anything, so what a row carries is paid again by every later unit. The full proof of a unit — each command, the output that matters, the census counts, the reasoning behind a "nothing here" verdict — goes to its proof file, `D:\datrix\.tmp\implement-direct-{slug}-proof\<id>.md`, written with `Write`; the row's state cell holds one line and that path, never pasted output. A `## Decisions` line is one sentence plus its rule or `file:line`. `/verify-implementation` and Jon open a proof file when they need it.

**The ledger has hard limits, and the script refuses one that breaks them** (`datrix_scripts/skill/ledger_rules.py`): the whole file at most 24,000 bytes; a table cell at most 400 characters and a state cell at most 240; any other line, a decision included, at most 300; and no section but `## Units` and `## Decisions`. Nothing else is kept in it: no list of changed files, no list of findings filed, no copied test output. A session that starts on a ledger over a limit is given a `LEDGER LIMITS EXCEEDED` line naming the breaks, and shrinks the ledger first by moving the detail into proof files; the script stops the chain when that session leaves it over.

**The files a unit changed go in its proof file**, one path per line under a `## Files changed` heading. The script gathers them into the supplement file `D:\datrix\.tmp\implement-direct-{slug}-files.md`, which `/verify-implementation` takes as its `FILES` input.

Ordering rules, the ones the task path enforced for you:

- **Enforcement before what it governs.** A unit that establishes or enforces an invariant (a validator, a fail-loud guard, a parser-level rejection, a conformance check) comes **before**, and is required by, every unit that relies on it or migrates content it polices. Never order a migration ahead of its guard: it would pass against an absent check.
- **Shared layer first.** Place logic at the most language/platform-agnostic layer that can own it (`datrix-common`, `datrix-codegen-kernel`, `datrix-codegen-common`); per-language and per-platform units require the shared unit. A hoist ported to N targets is one shared unit plus N per-target units.
- **Every surface in a set gets a row.** An invariant over a set of surfaces has a unit or an explicit acceptance line for **each** member. A guard shipped on the obvious surface with the rest silently dropped is a failed run even under green tests.
- **Every migration step gets a row**, and every old-path fixture/example/config from the census is converted in the same run. "Convert X to Y" is work here, not future work, unless the design explicitly defers it.
- **Tests and docs ride inside each unit.** No separate test, verify, or docs unit.
- **Sites a run must find are planned after that run, not before it.** When the DOCUMENT says its sites are found by a run — a census, a corpus or fixture run, a gate's report — rather than listing them, do not write a fix unit per package ahead of it: nobody knows yet which packages have work, and a unit with nothing to change still costs a whole session to prove it. Plan the enforcement and harness units, then **one census unit**, then the closing unit that reruns the end-to-end check. The census unit:
  1. runs the census once over the whole surface set — every registered target in one script or test, never one probe per package — keeping the script under `D:\datrix\.tmp\` so any later unit can rerun it unchanged;
  2. writes the result to the **census file**, `D:\datrix\.tmp\implement-direct-{slug}-census.md`: the command, the time, per surface member whether its run completed and how many files it reached (the non-vacuity count), and each site (package, generated file, `path:line` of the producer, what it writes);
  3. **re-plans**: adds one fix unit per package holding at least one site, requiring the census unit, and gives every package with zero sites an acceptance line in the census unit's row citing the census file and its counts. That line is the package's row for "Every surface in a set gets a row"; no session is spent re-proving it.
  
  A census that cannot complete (a run stops early, the workspace does not load) is not a census: the census unit stays unchecked and says why, rather than guessing the site list. A later fix unit reads the census file instead of re-running discovery, and after its own fix reruns the same census command to prove its sites are gone, updating the file.

Keep units bite-sized: one package, one behaviour, roughly 80–250 production lines. A bigger unit is split. There is no ceiling on the number of units.

Below the units, a `## Decisions` heading holds every implementation decision the run made (Step 1, Step 3): one line each, the choice and the rule, doc or `file:line` that settles it. It is how Jon and `/verify-implementation` audit what was decided without being asked.

---

## Step 3: Implement — unit by unit, in ledger order

For each unit, in order:

1. **Find what exists.** `find_canonical` / `find_symbol` / `search` before writing new logic. Read the neighbours (what upstream guarantees, what downstream requires): an insertion is an integration. Mirror an existing pattern by citing it; do not restate it.
2. **Implement it completely** to the code standards in CLAUDE.md: full type hints, no placeholders, no silent fallbacks, no workarounds, security by default, fail closed. A hoist removes **every** private copy. Where per-target copies disagree, the shared implementation takes the strongest behaviour (fails closed, reads everything the DSL declares, most secure, most correct output); no language or platform is the reference by default.
3. **Land every seam comparison as code.** Wherever the unit adds a producer or a consumer of a set of names or values, compute `consumed − produced`, require it empty or explained, and land the comparison as a generation-time validator or a test, not a one-off diff. Parse structure; prove the matcher finds an instance you know exists.
4. **Write the tests of the new behaviour** in the owning package: real objects, no mocks, each test carrying a feature tag, with the negative case alongside the positive. Update the docs the change touches in the owning repo's `docs/`, as content, with no pointer to the design.
5. **Run only the tests of what you changed**, naming first the failure the run could show that your evidence cannot: `test.ps1 <pkg> -Specific "a.py,b.py"` for the files, and `-Tag <tag>[,<tag>]` for the behaviour, **in every package it reaches** (at most 3 tags per run). Never a whole suite, never a sweep assembled from targeting flags.
6. **Prove the unit.** Run the unit's negative and positive acceptance check, write each command and its output, and the files the unit changed under `## Files changed`, to the unit's proof file, and tick the row with its one-line state (Step 2). An unproven unit is not done, whatever the suite colour.
7. **Cross-surface check.** If the unit touched a shared layer, run the tagged tests of the changed behaviour in each package the change reaches before moving on. "datrix-codegen-python is green" is not done for a shared-layer change.

Generation checks follow the one-example, one-language rule: regenerate only the affected project, only for the language it failed under, and prefer a test over a generation run. Never `-All` / `-Domains` / `-TestSet`.

**When a unit fails against a security control, the control is the requirement.** Never loosen, exempt, or widen it to turn the check green.

**A defect you find on a surface you touched is yours:** fix it. A design-sized one gets a findings file under `d:\datrix\findings\` (brief: what, `file:line`, evidence, impact) and the run carries on; a small one is fixed in place.

Each unit's own negative acceptance check covers the "X replaces Y" it carries; `/verify-implementation` (Step 4) proves the whole design's negatives again.

With `STOP AFTER: implement`, end here with the reply `IMPLEMENTED: <ledger path>`.

With `UNIT: <id>`, run items 1-7 for that one unit only, list its changed files in its proof file, tick its row with its one-line state, and end with `UNIT DONE: <id>`. Read only what the unit needs: the ledger, the DOCUMENT, the census file when the ledger has one, the unit's files and their neighbours. A census unit also adds the fix units its census found (Step 2), inserted right after its own row and ahead of the closing unit; the script runs unchecked rows in ledger order, so they run next.
---

## Step 4: Verify

Invoke `/verify-implementation` through the Skill tool with `DESIGN: <path>`, `TASKS: none`, and `FILES:` the changed files gathered from the `## Files changed` sections of the proof files (the script passes the supplement file that holds them). Pass `FIX: false` only if Jon set it.

It reviews the code on disk against the design, fixes what is wrong or missing, and ends with `Design conformance: PROVEN | INCOMPLETE`.

- **PROVEN** → Step 5.
- **INCOMPLETE** → the design is not implemented. Fix what verify could not, add the corrected units to the ledger, and run `/verify-implementation` again. A second INCOMPLETE on the same finding means the diagnosis was wrong: re-diagnose rather than patch. Stop only on a valid B1–B4 blocker with the four-part proof (verbatim error text; the fix attempted at `file:line`; why it failed; the B1–B4 code), and then **do not absorb**: report the blocker.
- A design-sized defect verify surfaces gets a findings file and is named in the final report. It does not block absorbing a design that is otherwise PROVEN.
- With `FIX: false`, verify is report-only: print its report and stop here without absorbing.

## Step 5: Absorb

Reached only on `Design conformance: PROVEN`.

Write verify's PROVEN report (its replies, ending in the `Design conformance: PROVEN` line) to `D:\datrix\.tmp\verify-proven-{design file name}.md` with the Write tool, then invoke `/absorb-design` through the Skill tool with `DOCUMENT: <path>`, `VERIFIED: <that file>` (and `KEEP SOURCE: true` if Jon set it). The design's `Status:` line still reads Draft on this path; VERIFIED is what licenses absorb to delete it. It transfers the content into the official docs, replaces every reference, and deletes the source. Units that already updated their docs report "already present"; that is correct, not a defect. Its "no clear target" and "content missed" prompts are real waits.

## Step 6: Final report

Lean, data only:

```
IMPLEMENT-DESIGN-DIRECT: {title}
Units: {N} done
Verify: PROVEN ({n} requirements; {n} fixed by verify)
Absorb: {N} units transferred, {N} files, source DELETED | PRESERVED
```

If the run ended on a blocker, report that instead: the four-part proof and the step it stopped at. Nothing else.

## Anti-Patterns

- **NO task files, phases, `.tasks\` folders, `dependencies.md`, or orchestrator dispatch** — the ledger in `D:\datrix\.tmp\` is the whole plan, and it is scratch.
- **NO skipping the ledger because the design "looks small"** — it is what carries ordering and per-surface coverage that the task graph used to carry.
- **NO migrating before the guard** — enforcement units precede and gate what they police.
- **NO covering the easy surface and dropping the rest** — every member of an invariant's surface set has a unit or an acceptance line.
- **NO implementing a single-target design without reading its sibling targets** (languages, platforms, frontends) — where a sibling already does it properly, the new target matches its behaviour; a per-target difference is a defect.
- **NO stopping partway because the design is big or context is long** — expand, compact, continue.
- **NO asking Jon how or where to build what the design asks** — placement, moves to the right layer, required libraries, names and fixtures are decided and recorded under `## Decisions`, never put as `APPROVAL_REQUIRED`.
- **NO absorbing before PROVEN** — absorb deletes the one document verify measures against.
- **NO editing the design document**, including its `Status:` line.
- **NO design number, filename, or path in code, tests, docs, or commit messages.**
- **NO whole test suites** — targeted `-Specific` / `-Tag` runs only, in every package the change reaches.
- **NO subagents** — this skill does the work itself, sequentially.
- **NO workarounds, NO dodging** ("out of scope", "pre-existing", "track separately" are the work, not blockers), **NO expedient fixes** ("for now" is banned; the defect sets the size).
- **NO git restore/checkout/reset/stash/revert** — undo your own edits manually.
