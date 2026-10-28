---
description: Process feature requests (Datrix gaps) filed by products built on Datrix — first check whether Datrix already solves the need (the named feature, another spelling, or a composition of existing features) and, if so, write no code and append the proven solution to the request; only for a verified gap design the capability generically against the binding design guidelines, realize it on every target it reaches with neutral-fixture tests, docs and parity rows, and append a resolution the product can adopt
model: claude-sonnet-5-5
effort: high
---

# Implement Feature Request

**Reasoning effort: HIGH.** A feature is a new promise the toolchain makes to every product, present and future. Read the grammar, the model, the validators and every emitter the capability reaches before you design it. One capability designed once, at the right layer, beats a per-target patch set.

A product that hits something Datrix cannot express files a **feature request**: a work item, not a record of a fix. This skill takes one or more of them, checks each against the current toolchain, and **implements the capability in Datrix** — language, model, analysis, generators, migration, tooling, docs and tests — then appends a resolution to the request so the product's own agent can adopt it.

**This skill serves every product built on Datrix and carries no knowledge of any of them.** Nothing it writes into a framework repo (code, tests, docs, comments, findings, commit messages) may name a product, customer, service, profile, gap id, or request file. The request is evidence about a *capability gap*; the capability you build is the toolchain's.

**A request is not an order to write code.** Its author cannot see the toolchain, so it often asks for something Datrix already does under another name, or something several existing features already compose into. Every request therefore passes the **Existing-solution gate** (Phase 1.2) before any design: when Datrix already meets the need, the request gets **no code** and instead gets a Resolution with the proven solution appended, so the product's agent can adopt it. Building a capability that already exists is a defect (a second spelling of one fact, G9), not thoroughness.

**For a request whose gap is verified, invoking this skill is Jon's authorization to build the capability the request names**, at the size the capability needs, on every target it reaches. It is not authorization to build *more or different behaviour* than the request asks for (see "Growth gate").

## How to Invoke

```
/implement-feature-request D:\<Product>\.feature-request\2026-10-27-202518-gap-append-only-entity-modifier.md
/implement-feature-request D:\<Product>\.feature-request\*.md
/implement-feature-request <request-1>.md <request-2>.md
```

The argument is one or more absolute paths to feature-request markdown files (or a glob). Requests are processed **one capability at a time, each to completion** (implemented, proven, documented, resolution appended) before the next starts; requests that share a surface (the same grammar rule, config model or emitter) are grouped and designed together so they cannot conflict.

## The request is a proposal, not a spec

Requests are written by another agent that works inside a product and **cannot see the Datrix toolchain**. Read each section for what it is:

| Section | Treat it as |
|---|---|
| Summary / Symptom / Root Cause | **Evidence of a gap** — verify it (Phase 1.2), do not assume it |
| Evidence citations (`file:line`) | Leads — lines drift; follow symbols with the code index |
| "Why no DSL fix" | A **claim** — confirm it; if the DSL already expresses the need, the answer is the solution in the Resolution, not code |
| The requested change itself | One way to meet a **need**. Judge the need, not the proposal: if existing features meet it, the proposal is not built |
| Proposed syntax and semantics | The **required behaviour is binding; the spelling is a proposal.** Spell it like its neighbours in the grammar and config models, and record any difference in the resolution |
| Proposed defaults | Checked against the security ranking (§13): a proposed default that is the less secure one is replaced by the secure one, and the existing-behaviour change is declared and pinned (G10, no backward compatibility) |
| Runtime patch / interim workaround | The product's own stopgap. Evidence of the need; **not touched here** |
| Scope of impact / Impact on other applications | A hypothesis. Your reach census (Phase 1.4) replaces it |
| Testing recommendation | The minimum behaviours your tests must prove, never the maximum |

A request with a required behaviour the toolchain should refuse (it weakens a security control, breaks a design guideline, only works for one target) is not implemented as written: implement the behaviour that satisfies the need within the guidelines and say so in the resolution.

## Request Structure

Requests follow this shape; layouts vary, so read what the file contains:

```markdown
# {Title}
**Date** · **Services affected** · **Category** (Datrix Gap) · **Status** (DATRIX GAP) · **gap id**
## Summary
## Symptom            (error text / behaviour, how to reproduce)
## Root Cause         (what's wrong, why, evidence citations)
## Runtime Patch / Interim
## Required: Permanent Fix
   Capability · Proposed syntax and semantics · Why no DSL fix
   Scope of impact · Impact on other applications · Testing recommendation
## Staging Verification
```

A short request may carry only Summary, Interim, "Why no DSL fix" and "Requested change". A request may list several numbered changes: **every numbered change is part of the request** and is implemented.

## Prereqs

Read first (the hooks block edits until the two cores are read): `datrix/docs/architecture/architecture-cheat-sheet.md` and `datrix-common/docs/contributing/ai-agent-rules.md`. Then, **before designing**, read:

- `datrix/docs/architecture/design-principles.md` § Design Guidelines (Binding), G1–G12 — every decision below is ranked by them first;
- the knowledge pack of **each surface the capability touches** (cheat sheet table: `dsl-features`, `target-plugins`, `parity-and-obligation`, `migrations`, `auth`, `frontend-clients`, `codegen-engine`, `runtime-and-deploy`, `language-server`, `pipeline-stages`, …) — only those;
- `datrix-common/docs/contributing/ai-agent-rules/multi-target-invariants.md`, `secure-by-default.md` (anything touching auth, secrets, transport, input, permissions, an emitted default), `code-quality-standards.md`, and `test-guidelines/` + `feature-tags.md`;
- `.claude/skills/_shared/verification-strategy.md` ("Which packages a change reaches", "Case or test").

Don't know where something is documented? `powershell -File "d:/datrix/datrix/scripts/dev/ineedtoknow.ps1" "<question>"`. Don't read the product's tree, DSL or generated output: the request's text is all the product evidence you are entitled to.

---

## Workflow

### Phase 1: Triage and Design (Read Only)

1. **Read every request.** Extract per request: the **need** in one neutral sentence (*what must be producible or guaranteed, on which targets*), the capability the request proposes (*construct → what it must do*), each numbered change, the proposed syntax, the "why no DSL fix" claim, the cited evidence, and the testing recommendation.

2. **Existing-solution gate — does Datrix already meet the need?** Restate the request as a **need** (*what the product must be able to produce or guarantee*), separate from the requested construct, then try to meet that need with what exists **before** deciding anything is missing. Start from the need, not from the proposed spelling: the same need is often met by a differently named construct, a config key, a stdlib module, an extension, a platform or target setting, or several features used together. Check each, and write down what you looked at and where:

   - **Docs and examples:** the syntax reference, language reference, stdlib reference, the knowledge pack of the surface, `datrix/examples/`, and the docs fences (`ineedtoknow.ps1 "<the need in neutral words>"` first; it points at the file and lines).
   - **Grammar, model and config:** the code index (`search` by what it does, `find_symbol` for sibling constructs and modifiers, `outline`) over `datrix-language` (rules, keyword manifest), `datrix-common` (model, config models), `datrix-semantic` (validators, which also name what the toolchain supports in their diagnostics).
   - **Generators:** whether a registered target already emits the artifact the request wants, even if no construct name matches (search the templates and emitters for the artifact, not for the request's words).
   - **Extensions and stdlib:** registered `datrix.extensions` packs and `.dtrx` stdlib modules.
   - **Composition:** whether two or more existing constructs together give the required behaviour (for example a modifier plus a policy, a block-level config plus a service-level override). A composition counts as "available" only if the result is the behaviour the request requires on every target the request names, not an approximation of it.

   Citations in the request are leads and drift; read the code at and around them. Prove an **absence** by reading (the grammar has no rule, the model has no field, no generator emits it), never by assuming. Prove a **presence** by running it: write a small neutral `.dtrx` fixture that uses the existing solution in the scratchpad (never in a repo and never the product's DSL) and analyze it with the toolchain (`scan\datrix-linter.ps1` or `dev\probe-fixture.ps1`, see their quick references); where the need is an emitted artifact, read the artifact that the existing solution produces for the targets the request names. "I believe it works" is not a finding.

   The outcome decides the request:

   | Finding | Outcome |
   |---|---|
   | An existing construct, config or composition meets the need (any spelling, any documentation state) | **ALREADY AVAILABLE** — write **no code**. Phase 3 appends the solution. If the doc does not describe it well enough for the request's author to have found it, that is a doc defect: fix the doc (the one edit this outcome allows in a framework repo) |
   | The DSL can already express the need, contrary to the "why no DSL fix" claim | **ALREADY AVAILABLE**, same treatment |
   | It exists in part | Implement **only the remainder**; the resolution says which part was already there and shows how it composes with the new part |
   | Existing features approximate the need but differ in a way the product cannot accept (a weaker guarantee, one target missing, a security property) | The gap holds, and the *difference* is the capability: name it, and build only that |
   | The gap holds | Continue |

   The gate decides with evidence. A solution that exists but is **less secure, per-target, or does not meet the stated requirement** does not make the request "already available": record precisely why it falls short and continue as a gap. The converse is equally binding: a gap is never declared because the existing solution is unfamiliar, undocumented or spelled differently from the request.

   **A request that leaves the gate as ALREADY AVAILABLE skips steps 3–7 and Phase 2 entirely** and goes to Phase 3. Steps 3–7 and Phase 2 apply to the gap (or the remainder) that survives the gate.

3. **State the defect in neutral terms**, as with any toolchain change: *which construct, on which target, produces or lacks which artifact, and what the correct artifact is.* If you cannot state it without the product's names, values or domain, you have not understood the capability yet — keep reading. Choose the neutral fixture domain now (Product, Order, Customer, Warehouse, Variant, LineItem, or a fictional one).

4. **Build the reach census — by counting, from registration, never from memory.** For the capability, list every surface it crosses and every registered target on each:

   | Surface | Enumerate from |
   |---|---|
   | Language: grammar, transformers, `.dtrx`/`.dcfg`/`.dseed` syntax, keyword manifest, LSP, editor grammar | `datrix-language` (`rebuild-parser.ps1` regenerates the parser), `language-server` pack |
   | Model and config contract | `datrix-common` (`datrix_model`, config models) |
   | Analysis: validators, diagnostics, synthesis | `datrix-semantic`; the diagnostics catalog and per-code fixtures |
   | Shared derivations and plans | `datrix-codegen-kernel`, `datrix-codegen-common` |
   | Language targets | registered `datrix.languages` plugins (`registered_language_names()`) |
   | Platform targets | registered `datrix.platforms` plugins |
   | Client/frontend targets | registered artifact-phase `datrix.generators` that activate on an app declaration |
   | SQL / schema / migration | `datrix-codegen-sql`, `datrix-migration` (snapshot, diff, policy), engines registered for RDBMS |
   | Documentation | syntax reference, language reference, the pack, the package docs the capability makes wrong |

   For each target the capability reaches, the answer is **realized**, or **one counted `capability_gaps` row on that target's own declaration** where the parity pack permits one — never an exemption, never silence (G1, G3). A target that cannot host the capability safely is refused at generation with a diagnostic naming what it offers (G2, G8).

5. **Design the capability against G1–G12.** Settle, in order: (a) *where it lives* — the most agnostic layer that can own it, shared plans computed once in the kernel/common and rendered per target (G4, G9); (b) *spelling and shape* — find the nearest existing constructs with the code index and match them; a new modifier/clause/config key reads like its siblings; (c) *semantics and validation* — what it excludes, what it requires, every misuse a located diagnostic with a new code (G8); (d) *defaults and security posture* — fail closed, the more secure option wins (G7); (e) *migration impact* — whether the schema snapshot, diff or policy must know it; (f) *tooling* — keyword manifest, LSP, editor grammar, docs. A design that breaks a guideline is a defective draft: fix the draft. Decisions that follow from a rule, a doc or the design are made and recorded with their evidence — they are never questions.

6. **Growth gate.** Compare what you designed with what the request asks.
   - More or different *behaviour* than requested (an extra capability, model field, phase or diagnostic the requirements do not need), or a measured size that is a multiple of what the request names → **stop that part**; put it to the `decision-advisor`; on `ASK_JON`, ask Jon in one line starting `APPROVAL_REQUIRED:` with what, why, and its measured size (a counted census × this run's measured rate; never human hours or days). Keep working everything that does not depend on the answer.
   - Two defensible designs, expensive to reverse, nothing in the docs or guidelines settling it (a B2): `decision-advisor` with both options and your recommendation. Where Jon forbids subagents (`DATRIX_NO_SUBAGENTS=1` or his instruction), no advisor is dispatched and the question goes straight to him in one line.
   - *How and where* you build what was asked (package, module, names, signatures, the library a behaviour needs, fixtures) is never a question. Do not ask; decide and record.
   - Never resolve a size problem by shipping a smaller capability: an unapproved expansion and a cut-down feature are both wrong (§14).

7. **Size as a census.** State size as what you counted — packages, files, units, call sites, targets, with the code-index query or command behind each number. No effort figure in hours, days or sprints.

8. **End-of-phase report:**

   ```
   TRIAGE COMPLETE

   Requests: {N}   (grouped: {request sets that share a surface})
   For each request:
     Need: {what must be producible or guaranteed, neutral wording}
     Existing-solution gate: {looked at: docs, code-index queries, generators, extensions, compositions tried}
                             {ALREADY AVAILABLE as {spelling or composition}, documented at {doc | undocumented},
                              proven by {fixture + command + printed result, or artifact read at file:line}
                              | PARTIAL: {what exists} + remainder {…}
                              | GAP: nothing meets the need — absent at file:line …; closest existing {…} falls short because {…}}
   For each capability still to build (gap or remainder):
     Capability: {construct → behaviour → targets, neutral wording}
     Design: spelling {…} | layer {…} | differs from the proposal: {nothing | what and why}
     Security posture: {default, failure mode}
     Reach: packages {…} | language targets {…} | platform targets {…} | client targets {…}
            realized {…} | counted capability_gaps {… | none, with the reason}
     Migration: {schema impact | none}   Tooling: {manifest/LSP/editor | none}   Docs: {files}
     Guidelines: {one line for each of G1–G12 the design touches, and why the rest are untouched}
     Neutral fixture: {…}   Already-correct neighbour pinned byte-identical: {…}
     Size (counted): {…}
   Growth gate: {no growth | APPROVAL_REQUIRED: …}
   Execution order: {1. … 2. …}
   ```

9. **If confident → Phase 2.** If not, **keep investigating**: an unclear design is a state of your knowledge, not a blocker. Present triage and wait only for a real B2/`APPROVAL_REQUIRED`, bringing your recommendation.

---

### Phase 2: Implement

Only for a gap or a remainder that survived the Existing-solution gate. Work the layers in dependency order; each layer's consumer is built against the finished producer, and each seam gets its set comparison in code (G12): `consumed − produced = ∅`, landed as a validator or test.

1. **Model and contract** in `datrix-common` (zero dependencies on other Datrix packages). Language-neutral: a target-specific field in a shared model is wrong (G4).
2. **Grammar and transformers** in `datrix-language`; regenerate the parser with `datrix/scripts/generation/rebuild-parser.ps1` (never hand-edit generated parser output). Grammar snapshot and syntax docs move with it.
3. **Analysis**: validators, new diagnostic codes in the catalog (each with a per-code fixture line: `// @expect CODE.variant`; the census test holds the catalog to its fixtures), synthesis. A declared knob that no validator constrains and no target consumes is deleted, not shipped (G6).
4. **Shared derivation** in the kernel or `datrix-codegen-common`: the capability's plan/contract is computed **once** and every target renders it. No target re-derives a fact from bodies, and no private copy of a shared function is left behind (G9).
5. **Every reached target**, each through its own plugin: use the owning package's fix skill for its package-specific context (`datrix-codegen-<x>` → `/fix-codegen-<x>`; `datrix-migration` → `/fix-migration`; …). Handoff is routing, never a way to put the work down. Language targets realize the same behaviour with different syntax only; platform targets use their native primitive (G2).
6. **Migration and schema**: when the capability changes what the database holds (a column, constraint, trigger, comment), the snapshot, diff and policy know it, so a change is planned as a migration (`migrations` pack). SQL Datrix writes is checked against the engine that runs it (G11's live-database exception).
7. **Tooling**: keyword manifest, LSP completions/hover, editor grammar/snippets in `datrix-vscode` when the capability adds syntax (`language-server` pack).
8. **Documentation** that describes the behaviour the code now has: the syntax reference, the language reference, the owning pack or package doc, and a neutral usage example in a `datrix` docs fence (docs fences are parsed, and analyzed when whole applications). No design-doc, task-file or request reference, no product or gap-id term, in any committed file (`design-and-docs.md`).
9. **Tests, with the carrier the fact chooses** (G11; `verification-strategy.md` "Case or test"): a fact about one fixture line is a `// @expect` annotation; a literal fact about a stage result is a case row (`cases.ps1 new …`); a config-model fact is a committed `.dcfg` fixture the model-contract runner proves; a fact about a registered table row is the row; an invariant over a set, an exception path or an algorithm is a test function. **A cross-target fact is a parity row** in `datrix/scripts/gates/parity/cases/`, read on every registered target against an authored expectation — never a per-target copy and never a new gate module. Real objects only; every test carries a feature tag.

**Two proofs every capability carries** (Product Isolation rule 5):
- **the capability works:** a neutral-fixture test that the construct now produces the correct artifact on each reached target;
- **opt-in means untouched:** a test that a source *not* using the construct emits **byte-identical** output before and after. A deliberate change to what existing sources emit (a secure default replacing an insecure one) is declared in the resolution and pinned by its own test, never landed silently.

Implement to the finished standard on the first pass: no stubs, no `pass`, no `NotImplementedError`, no silent fallback, no TODO, no accepted-but-ignored syntax. Type hints everywhere, complexity ≤15, `%`-style logging, no `Any`; check logic-map markers (`@canonical`, `@pattern`, `@boundary`, `@invariant`) before modifying a function.

#### After each capability

```
CHECKPOINT — Capability: {neutral name}
Status: IMPLEMENTED
Changed: {package}: {file:line} — {what}   (one line per package)
Targets: realized {…} | counted gaps {…}
Diagnostics added: {codes}      Parity rows: {ids}      Docs: {files}
Requests resolved: {list}
```

#### Verification Gate

Static first (G12): read and parse the artifact before anything else runs. Framework tests never compile, run or deploy generated output (G11). **No product tree is generated, read or touched**; a neutral fixture is generated only for a question the static ladder cannot answer.

1. **Reproduce first**: a new test or annotation that fails on the unchanged toolchain for the right reason, then passes.
2. **Targeted runs, in the foreground** (never a whole suite; at most 3 tags per run; `-Keyword` in one package only; no selection above 25% of a package): `test.ps1 <pkg> -Specific <files you changed>` and `-Tag <the feature tag>` in **every package the change reaches** (`verification-strategy.md`, "Which packages a change reaches"). A piped run counts only when its output still ends with `test.ps1`'s own `Total: N | Passed: N | Failed: 0` line.
3. **Parity rows**: `parity-cases-gate.ps1 -Tag <the behaviour's tag>` for a cross-target fact. A failing row is fixed in the target; a reading is never copied into an expectation to turn it green.
4. **Gates for code no `test.ps1` reaches** (the `datrix` repo hosts no test suite): the relevant `*-gate.ps1` with `-Only <check>`, last line `[GATE] <name> PASSED exit=0`.
5. **Live-database test** when the capability emits SQL: on every registered RDBMS engine through the shared live-database fixture, tagged `live-database`; it fails, never skips, when Docker is unreachable.
6. **The framework-hygiene gates your change can trip**: customer-domain isolation, documentation realization, keyword manifest, whichever the capability's surfaces name. A failure is yours to fix at its root.

Paste the commands and what they printed. A run you did not do, or a target you did not check, is an unverified claim. The gate passes only when the capability works on each reached target, the opt-in neighbour is byte-identical, every reached package's tagged tests are green, and the last run is green.

A regression you introduced is the unfinished half of the job: read the error text, trace it, fix it at the root (`fix-conventions.md`). Never revert; never ship a known failure with a note.

**Confidence gate:** low confidence means read more. Stop only on a proven B1–B4 blocker with the four-part proof (`execution-contract.md` §1), or an `APPROVAL_REQUIRED` from the growth gate.

---

### Phase 3: Update the Request

For each request resolved, **append** a Resolution to the end of the request file (never edit the original text; the product repo owns that file, and this is the one thing written there):

```markdown

---

## Resolution

**Date**: {YYYY-MM-DD}
**Status**: Resolved | Already available | Partially resolved | Unresolved
**Capability as shipped**: {one neutral sentence}

### Syntax and semantics (final)

{The spelling that shipped, the rules it enforces, the diagnostics it adds, its defaults and failure mode.}

**Differs from the proposal**: {nothing | what changed, and why (guideline, security, convention)}

### How a product adopts it

{A short, neutral usage example in the product's own terms of use — the construct, where it goes, what it generates — plus the doc that describes it ({framework doc path}). Name the interim workaround in the request that the capability now makes removable; **do not remove it here** — that edit is the product's.}

### Reach

| Surface | Result |
|---|---|
| {package / target} | realized / counted gap `{id}` / not reached — {why} |

### Verification

| Check | Command | Result |
|---|---|---|
| {capability works on {target}} | `{command}` | {printed result} |
| {opt-in neighbour byte-identical} | `{command}` | {printed result} |
```

The Resolution lists no changed files: the product needs the capability and its doc, not the framework's diff. For a request that could **not** be implemented, write `**Status**: Unresolved`, the reason, and the four-part proof (verbatim error, the attempt at `file:line`, why it failed, the B1–B4 code). #### Resolution for an Already-available request

The Resolution is the deliverable here: it must let the product's agent solve its problem without asking anyone. It replaces the template above with this one:

````markdown

---

## Resolution

**Date**: {YYYY-MM-DD}
**Status**: Already available
**Summary**: {one neutral sentence: Datrix already meets this need with {construct / config / composition}; no toolchain change was made.}

### Why the proposed change is not needed

{Which part of the request's claim does not hold, with the Datrix doc or construct that shows it. If the proposal also had a weakness (less secure default, one target only), say so.}

### The solution to use

{The exact spelling, where it goes (file kind, block, level), the rules it enforces and the diagnostics it raises on misuse, its defaults and failure mode, and what it generates on each target the request names. Written in the request's own entities (taken from the request's text, never from the product's tree).}

```datrix
{A complete, minimal example. It must be the one that was analyzed in Phase 1.2, with the request's names substituted only where the substitution cannot change the result.}
```

### How a product adopts it

{Concrete steps: what to add or change in the DSL/config, the command to regenerate, and what to look for in the generated output to confirm it. Name the interim workaround in the request that this makes removable; **do not remove it here**, that edit is the product's.}

### What it does not cover

{Anything in the request the existing solution does not meet. If any part is unmet, the status is **Partially resolved**, that part was built through Phase 2, and this section says so. If nothing is unmet, write "nothing".}

### Evidence

| Check | Command or location | Result |
|---|---|---|
| {the existing solution is accepted} | `{linter / probe command on the neutral fixture}` | {printed result} |
| {the generated artifact is what the request needs} | `{file:line of the emitted artifact or template}` | {what it shows} |
| {documented at} | `{framework doc path}` | {section, or "undocumented: doc fixed in {file}"} |
````

The Resolution's example is checked against the toolchain's own analysis, never against memory of the grammar.

### Phase 4: Final Report

```
IMPLEMENT-FEATURE-REQUEST COMPLETE

Requests processed: {N}   Implemented: {N}   Already available: {N}   Unresolved: {N}

Capabilities shipped:
1. {neutral name} — syntax {…} — {packages} — resolves: {request files}
   Targets: realized {…} | counted gaps {…}
   Diagnostics: {codes}   Parity rows: {ids}   Docs: {files}
   Differs from the proposal: {…}

Verification (commands and results):
- {package}: {command} → {Total/Passed/Failed line}
- parity: {command} → {line}
- opt-in byte-identical: {test} → {result}

Resolved requests (absolute paths):
- {request file}: {title} — Resolved | Already available
```

End with exactly one line per request: `Feature request: IMPLEMENTED` · `Feature request: ALREADY AVAILABLE` · `Feature request: PARTIAL — {what remains and why}` · `Feature request: BLOCKED B<n>` (with the four-part proof above it) · `Feature request: APPROVAL_REQUIRED` (with the question above it).

**Noticing other things.** A defect, gap or design flaw the capability does not need — another instance elsewhere, a pre-existing failure, an unrelated problem — gets a findings file (`d:\datrix\findings\YYYYMMDD-HHMMSS-<slug>.md`, `execution-contract-reporting.md` §5A) and is not fixed here. Do not look for an existing one. Findings are neutral too: no product term.

---

## Runaway Detection

See `d:\datrix\.claude\skills\_shared\fix-conventions.md`. More than double the estimated files, cascading changes in unrelated files, or the same symptom patched in more than one place means your design is probably at the wrong layer: re-diagnose, find the single owner, and continue. It is never a reason to stop, and never a reason to ship the smaller version.

---

## Anti-Patterns

- **NO implementing the request's spelling blindly** — the behaviour binds; the spelling is checked against the grammar and config neighbours, and any difference is recorded.
- **NO implementing before the Existing-solution gate** — judge the need, not the proposal; if the need is already met by a construct, config, or composition of existing features, write no code and append the proven solution.
- **NO assuming the gap** — verify absence in the current code first; a capability that already exists is a Resolution with the solution, not new code.
- **NO "already available" from memory or inference** — the existing solution is proven by analyzing a neutral fixture with the toolchain (or by reading the artifact it emits), and the Resolution carries that evidence. An unproven pointer sends the product's agent back with the same problem.
- **NO declaring "already available" for a solution that falls short** — a weaker guarantee, a missing target, or a less secure behaviour is a gap; build only the difference.
- **NO product, customer, service, profile, gap-id or request-file term in a framework repo** — code, tests, docs, comments, diagnostics, findings, commit messages. Use the neutral fixture; the isolation gate rejects the commit otherwise.
- **NO per-target copy** — a capability one target realizes is an obligation for every target; shared plan once, rendering per target. A gap is one counted `capability_gaps` row, never an exemption or a silent omission.
- **NO naming a target in shared code** — shared layers ask, targets answer; registries, not lists.
- **NO accepted-but-unrealized syntax** — a declared knob changes the output in a functional position on every reached target, or it is deleted (G6).
- **NO silent defaults or fallbacks** — unsupported combinations and misuse are located diagnostics naming the fix (G8).
- **NO less secure option** — not as a proposed default, not for brevity, not because the request asked (§13). Fail closed.
- **NO new behaviour beyond the request without the growth gate**, and **NO smaller capability shipped to fit the budget** (§14).
- **NO backward-compat shim** — a replaced path is deleted in the same change (G10).
- **NO test without a fact to prove** — carrier follows the fact (G11); no mocks; no whole-suite or sweep runs.
- **NO opt-in capability without the byte-identical neighbour test.**
- **NO reading, editing, regenerating or deploying a product's DSL, generated tree or environment** — the request's text is the evidence; adoption is the product's work.
- **NO editing the product's interim workaround** — name it in the resolution as removable.
- **NO modifying original request content** — append the Resolution only (an Already-available request included: the solution goes in the appended Resolution, never into the request body).
- **NO editing generated parser output or generated code** — fix the grammar source or the generator, then regenerate with the repo script.
- **NO debug scatter** — zero temporary logging.
- **NO committing** — Jon decides when (`/commit-and-push`).
- **NO git restore/checkout/reset/stash/revert** — undo your own edits manually.
- **NO dodging** — "out of scope", "pre-existing", "separate follow-up", "not my package", "too large" are not blockers; they are the work or an `APPROVAL_REQUIRED`.
