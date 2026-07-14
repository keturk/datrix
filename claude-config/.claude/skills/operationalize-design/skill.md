---
model: opus
effort: xhigh
---

# Operationalize Design Document

End-to-end pipeline that takes a design document and produces: resolved decisions, updated architecture docs, implementation tasks, and cleanup — collapsing what previously took multiple sessions into a single orchestrated workflow.

## Your Role — Orchestrate, Delegate, Decide

You run on Opus 4.8 at extra-high effort. That capability is for **judgment, not typing**. You are the orchestrator and decision-maker across the five phases: you own understanding the design, identifying and resolving decision points, deciding the task decomposition and its dependency/enforcement ordering, and every gate in this skill. **Execution** — reading the design doc and architecture docs, searching the codebase for evidence, inventorying affected packages/fixtures, transferring content into official docs, and writing the individual task files — goes to subagents on cheaper models.

Two resources are scarce and both are yours to protect:
- **Opus tokens** — work a cheaper model can do well (recon reads, per-question codebase searches, writing N task files to a fixed template) must not be done inline.
- **Your context window** — it must last all five phases. Delegating recon and file-writing keeps your context for the decisions only you can make: the ambiguity hard-gate, the confidence gate, the decomposition, the enforcement ordering, the invariant-surface coverage.

Delegation is not abdication. Every gate in this skill is still **yours** and is decided on evidence you verify — a subagent's recon or self-report is input to your judgment, never a substitute for it. The ambiguity hard-gate, the confidence gate, and every Phase-4 completeness check are decided by you, on the returned evidence, exactly as written. No gate is relaxed because a subagent did the legwork.

### Model tiers

| Tier | Use for | Examples in this pipeline |
|---|---|---|
| `haiku` | Mechanical, high-volume, low-ambiguity | Reading the design doc / architecture docs and returning a structured digest; globbing for fixtures/examples/configs on the old path; Phase-5 content-transfer verification |
| `sonnet` | Well-scoped implementation to a clear spec | Per-question codebase research with a specific answer to find; Phase-3 doc transfer to a target you named; **Phase-4 writing of individual task files to the template and decomposition you specified** |
| `opus` | Recon/analysis needing strong reasoning | Ambiguous scope investigation, tracing a subtle dual-implementation risk, cross-cutting impact analysis you want a second strong read on |
| Opus @ xhigh (you) | Judgment — never delegated | Decision-point identification, every decision + confidence gate, the ambiguity hard-gate, the task **decomposition** (numbering, dependencies, enforcement ordering, invariant-surface coverage), and every phase completion gate |

**Dispatch protocol.** Subagents see none of this conversation — every dispatch prompt is self-contained: what to do and why, exact paths (read vs. may-write, and what is out of bounds), the CLAUDE.md constraints that bite (no workarounds, no git reverts, mypy --strict, no mocks, domain isolation, temp files only under `D:\datrix\.tmp\`/`.scripts\`/`.test-output\`, and for Phase-4 the **Task Location Allowlist**), and the exact return format (facts, not prose). Persist substantial subagent outputs under `d:/datrix/.agent_output/<date>-operationalize-<design-slug>/`. Partition write-heavy dispatches so no two agents write the same file; recon/read agents can fan out wider.

**The delegation NEVER moves a decision to a subagent.** You decide; subagents gather and type. In particular: explicit design alternatives (Option A/B) are always YOUR call informed by the user — never handed to an agent to "pick"; the decomposition and dependency graph are yours — agents write the files you specify, they do not invent tasks.

## When to Use

- User has a completed design document ready for implementation
- User says "operationalize", "implement this design", or "turn this into tasks and docs"
- User wants decisions resolved, docs updated, and tasks generated in one pass
- After a design review is complete and the document is approved

## How to Invoke

```
/operationalize-design

DOCUMENT: d:\datrix\datrix\docs\designs\shared-generator-orchestration.md
```

With options:
```
/operationalize-design

DOCUMENT: d:\datrix\datrix\docs\designs\local-variable-syntax.md
TARGET REPOS: datrix-language, datrix-common
PHASE: 6
SKIP: cleanup
```

## Documentation Quick Reference

For complete documentation index with "When to use" guidance, see [doc_index.md](../../../../../datrix/docs/doc_index.md).

**Essential reads (MANDATORY before starting):**
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) → Core rules, STOP AND THINK principle
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md) → System architecture (operative summary)
- [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md) → Design philosophy (operative summary)

**On demand (read only when the design's surfaces need the depth — not a blanket pre-read; the Phase-1 recon agents read the full docs for you):**
- [architecture-overview.md](../../../../../datrix/docs/architecture/architecture-overview.md) → full architecture index + sub-docs
- [design-principles.md](../../../../../datrix/docs/architecture/design-principles.md) → full design principles

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| DOCUMENT | Yes | Path to the design document to operationalize |
| TARGET REPOS | No | Which repos the tasks belong to (auto-detected if not specified) |
| PHASE | No | Phase number for task generation (auto-detected from latest-phase.ps1) |
| SKIP | No | Phases to skip: `analysis`, `decisions`, `docs`, `tasks`, `cleanup` |

## Pipeline Phases

This skill executes five phases. Each phase builds on the previous.

**Execution discipline:**
- Each phase runs to completion unless BLOCKED
- "Blocked" means: missing information, conflicting requirements, or technical impossibility
- "This seems like a lot of work" is NOT a blocker
- Do NOT ask "should I continue?" mid-phase unless blocked
- Do NOT generate partial deliverables and wait for approval
- User invoked this skill to run the full pipeline — execute it completely

**Minimalistic outputs:**
- All skill outputs (phase reports, summaries, generated artifacts) must be lean and data-dense
- No decorative headers, horizontal rules, or markdown formatting in console output
- No "Next steps" sections — the user knows what to do
- No category breakdowns that repeat information already in task files or dependencies.md
- No dependency graphs in console output — that data lives in dependencies.md
- One line per data point. If it fits on one line, don't use three

**Ambiguity resolution — hard gate before Phase 3:**
- Before any official doc is edited (Phase 3) or any task is generated (Phase 4), there must be ZERO unresolved open questions and ZERO unresolved ambiguities. This is a hard gate: execution work does not begin until it is cleared. Phases 1–2 exist to clear it.
- "Resolved" means resolved by **investigation, never by assumption.** A question is closed only when one of these answers it: codebase evidence (read the actual code), existing-doc cross-reference, logic-map markers, or an explicit answer from the user. "I can think of a reasonable answer" does NOT close a question — that is an assumption, and assumptions are banned (CLAUDE.md: "Never assume/fabricate — look it up").
- You may NOT declare "no open questions" unless you have investigated each one. The specific failure mode this gate prevents: listing a question in Phase 1, then silently assuming its answer and proceeding. Every closed question must be traceable to the investigation that closed it.
- Explicit alternatives in the design (Option A/B, multiple named approaches) are ALWAYS user decisions. Investigation informs a recommendation but NEVER closes them — only the user does.
- If, after genuine investigation, ANY question remains unanswerable from the codebase/docs, OR any explicit alternative remains unchosen → STOP. Present each remaining item with your investigation findings and a recommendation, and WAIT for the user. Do not enter Phase 3 or Phase 4 with any open item.
- This is the one class of STOP that overrides "run the full pipeline": an unresolved required decision is a genuine blocker (CLAUDE.md: pipeline skills STOP for "unresolved required decisions, missing required inputs"). It is NOT the same as a missing optional validator — do not confuse the two.

---

### Phase 1: Analysis — Audit the Design Document

**Goal:** Understand the design completely and identify all decision points.

**Delegate the recon, own the analysis.** The reading and cross-referencing in steps 1–2 is mechanical fan-out — dispatch it; the *identification* in step 3 (what is a decision point, what is genuinely open, what conflicts) is your judgment and stays inline.

- Dispatch a **haiku** recon agent to read the design document in full and return a structured digest: every section, every explicitly-marked open question / "TBD" / "Option A vs B", every migration/rollout step (numbered, verbatim), and every place the design says "convert X to Y".
- Dispatch a **haiku/sonnet** recon agent (in parallel) to cross-reference the design against `d:\datrix\datrix\docs\architecture\` and return: sections that duplicate or conflict with existing docs, and the correct target doc for each new piece of content.
- Dispatch a **sonnet** recon agent to inventory implementation scope + dual-implementation risk across the repo: every package that consumes/tests/demonstrates the subsystem being changed, and every test fixture, example, and project config currently exercising the OLD path (glob + read). This is the search that catches the "new path ships untested" trap — give it the old-path markers to grep for.

Read the digests yourself and do step 3's identification on them. Read the design doc directly yourself for any section the digest leaves ambiguous — recon informs you, it does not replace your own read of anything decision-bearing.

1. Read the design document in full (via the recon digest; read the doc directly for any decision-bearing section)
2. Cross-reference against existing architecture docs in `d:\datrix\datrix\docs\architecture\` (via the cross-ref recon agent)
3. Identify (YOUR judgment, on the returned recon):
   - **Open questions** — explicitly marked or implicit
   - **Decision points** — alternatives presented without resolution
   - **Content overlap** — sections that duplicate or conflict with existing docs
   - **Implementation scope** — ALL packages/modules affected, not just the primary one. If the design introduces a new subsystem, identify every repo that consumes, tests, or demonstrates the old subsystem being replaced.
   - **Migration/rollout requirements** — read the design's migration strategy, rollout plan, adoption steps, or similar section. List every numbered step. These are implementation work, not future aspirations. If the design says "convert X to Y", that is a task.
   - **Dual-implementation risk** — if the design introduces a new path alongside an existing one (e.g., new format alongside YAML, new API alongside old API), identify all test fixtures, examples, and project configs that currently exercise the OLD path. These must be migrated or the new path will ship untested while old tests pass on the old path.
   - **Dependencies** — what must exist before this design can be implemented

## Phase 1 Completion Gate

This phase is COMPLETE when:
- [ ] Design document read in full
- [ ] All architecture docs cross-referenced
- [ ] Open questions identified and investigated (not just listed)
- [ ] Decision points classified correctly
- [ ] Implementation scope determined
- [ ] Dependencies identified
- [ ] Output matches the format below exactly

**End-of-phase output (keep it lean — data only, no decoration):**

```
ANALYSIS: {title}
Scope: {packages}
Open questions: {N}, Decision points: {N}, Conflicts: {N}
Migration steps: {N}, Dual-impl risk: {YES/NO}
```

## Phase 1 Self-Check

Before proceeding to Phase 2, answer:
1. Did I investigate each "open question" to determine if it's actually open?
2. Did I check the codebase for existing patterns that resolve ambiguities?
3. Did I identify ALL affected packages — not just the one where new code lives, but every repo with tests, fixtures, examples, or configs that exercise the system being changed?
4. Did I read the design's migration/rollout/adoption section and list every numbered step?
5. Did I identify dual-implementation risk — will old tests pass on the old path while the new path ships untested?
6. Did I follow the "Goal:" statement above exactly?
7. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

**Investigation discipline for open questions:** For each open question you identify, you must actually investigate before classifying it. Read the relevant code, cross-reference the architecture docs, and query logic-map markers where relevant. Record what you found. A question you "answered" without reading anything is unresolved — it is an assumption, and it does NOT clear the ambiguity gate. See **Ambiguity resolution — hard gate** above.

**If there are BLOCKING open questions** (ambiguities that prevent task generation):
- Present them with recommended answers and the investigation evidence behind each (code references, existing patterns, doc cross-refs)
- WAIT for user to confirm or override

**If the design presents explicit alternatives** (Option A vs Option B, multiple approaches listed):
- These are ALWAYS open questions that require user input, even when codebase patterns suggest one option
- Research the codebase and existing patterns to inform a recommendation
- Present the alternatives with your recommendation and evidence
- WAIT for user to choose — never auto-select

**If all questions have clear answers from the codebase (each backed by investigation, not assumption) AND the design presents no explicit alternatives** → proceed automatically.

---

### Phase 2: Decisions — Resolve All Open Questions

**Goal:** Make every decision required by the design, with rationale.

**Delegate the evidence-gathering, own the decision.** For each implicit question, the codebase research (steps 1–2) is delegable; the decision and its confidence rating (steps 3–4 + the confidence gate) are yours and are never delegated. Dispatch the open questions as a batch of **sonnet** research agents (one per question, or grouped by subsystem) — fan out independent questions in a single message. Each agent gets the exact question, the relevant paths, and returns **evidence only**: code references, existing patterns, logic-map marker hits — with a factual finding, NOT a decision. You read the returned evidence and make each call yourself.

**Never delegate a decision.** An agent returns "here is what the code does"; YOU return "therefore the decision is X, confidence HIGH, because <cited evidence>". Explicit design alternatives (Option A/B) are never even sent to an agent to decide — they are always LOW-confidence user decisions (see below); at most an agent gathers evidence for your *recommendation*.

For each open question or decision point:

1. **Research the codebase** — find evidence for the best approach (delegated to a research agent; you consume its evidence)
2. **Check existing patterns** — query logic map markers if relevant (delegated with step 1)
3. **Classify the question (YOUR call):**
   - **Explicit alternative** — the design document presents multiple named options (Option A/B, Approach 1/2, etc.) → confidence is always LOW (requires user input), even if codebase evidence strongly favors one option. The design author listed alternatives for a reason.
   - **Implicit question** — ambiguity or gap in the design that can be resolved from codebase evidence → use the confidence scale below.
4. **Propose a decision** with:
   - The decision itself (one sentence)
   - Rationale (why this approach over alternatives)
   - Evidence (code references, existing patterns, architectural principles)
   - Confidence: HIGH (clear evidence, no explicit alternatives) / MEDIUM (reasonable inference) / LOW (needs user input — always used for explicit alternatives)

## Phase 2 Completion Gate

This phase is COMPLETE when:
- [ ] Every open question from Phase 1 has a decision
- [ ] Every decision has rationale and evidence
- [ ] Confidence level assigned to each decision
- [ ] Output matches the format below exactly

**End-of-phase output (lean — one line per decision):**

```
DECISIONS: {N} total (HIGH: {n}, MEDIUM: {n}, LOW: {n})

1. {title}: {decision} [HIGH]
2. {title}: {decision} [MEDIUM — flagged]
```

## Phase 2 Self-Check

Before proceeding to Phase 3, answer:
1. Did I make a decision for EVERY open question from Phase 1?
2. Did I provide evidence from the codebase (not just opinions)?
3. Did I follow the confidence gate rules?
4. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

**Confidence gate:**
- A decision may be marked **HIGH only if it is backed by cited investigation evidence** (code reference, existing pattern, doc cross-ref). A decision with no evidence behind it is an assumption — it is NOT HIGH; treat it as LOW and surface it. HIGH is earned by investigation, not by confidence in a guess.
- **All HIGH** → proceed to Phase 3 automatically
- **Any MEDIUM** → flag for review but proceed (include in final summary)
- **Any LOW** → STOP, present decisions, WAIT for user input

This gate is the enforcement point for the **Ambiguity resolution — hard gate** declared at the top of this skill: do not enter Phase 3 with any LOW (assumption-based or user-decision) item outstanding.

---

### Phase 3: Documentation — Transfer Knowledge to Official Docs

**Goal:** Update existing architecture and documentation files with the design's content.

**You plan the transfer; subagents write it.** Deciding *what* content moves *where* (target doc, section, conflict resolution) is judgment — do it yourself from the Phase-1 cross-ref recon. The actual writing into each target doc is patterned execution — dispatch it to **sonnet** agents, partitioned so no two agents touch the same file. Give each agent: the exact target doc + section, the content to write (the specific design passage), the conflict-resolution directive for that spot (replace / update / append), and "adapt style to match the surrounding doc." You review each returned diff against your transfer plan before accepting it.

For each section of the design document that adds NEW information:

1. Identify the correct target document in `d:\datrix\datrix\docs\` or package `docs/` directories (YOUR call, from the cross-ref recon)
2. Determine where in the target document the information belongs (YOUR call)
3. Write the content into the target document, adapting style to match (delegated to a sonnet writer; you review the diff)

**What to transfer:**
- Architecture decisions → `architecture-overview.md` (and its sub-documents) or package-specific docs
- Design principles → `design-principles.md`
- API contracts → package docs
- Configuration schemas → relevant config docs
- Usage examples → package READMEs or guides

**What NOT to transfer:**
- Implementation details that belong in code comments or docstrings
- Task-level instructions (those go in task files)
- Temporary notes or discussion context

**Conflict resolution:**
- If the design UPDATES existing content → replace the old content
- If the design CONTRADICTS existing content → update to the new design (no backward compat)
- If the design ADDS to existing content → append in the appropriate section

## Phase 3 Completion Gate

This phase is COMPLETE when:
- [ ] All unique design content transferred to official docs
- [ ] No content duplication between design doc and official docs
- [ ] All conflicts resolved (old content replaced/updated)
- [ ] Target docs match existing doc style and structure
- [ ] Output matches the format below exactly

**End-of-phase output (lean — path + action only):**

```
DOCS UPDATED: {N} files, {N} sections transferred, {N} conflicts resolved

{path} — {action}
{path} — {action}
```

## Phase 3 Self-Check

Before proceeding to Phase 4, answer:
1. Did I transfer ALL unique content from the design to official docs?
2. Did I identify the correct target docs (not create new standalone docs)?
3. Did I adapt content style to match the target docs?
4. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

---

### Phase 4: Tasks — Generate Implementation Task Files

**Goal:** Break the design into implementable tasks with globally unique numbering.

**The decomposition is yours; the file-writing is delegated.** This is the phase where the fan-out pays off most — a design can produce dozens of task files, and writing them inline would exhaust your context. Split it cleanly:

- **You (Opus) own the decomposition — never delegated.** The full task list, the global numbering, the `Depends on` graph, the **enforcement-before-what-it-governs** ordering (a guard/validator/rejection task precedes and gates every task that relies on it or migrates content it governs), the **invariant-surface coverage** (a task or QG criterion for EVERY surface in a design invariant's set — none silently dropped), which repos get tasks, and where each quality gate sits. Produce a complete task manifest first: for every task — its id, slug, target repo (from the Allowlist), category, `Depends on`, its `**Design reference:**` + `**Design acceptance property:**` (the specific D#/G#/numbered invariant + provable negative+positive check), and the inline design content it must carry. This manifest IS the design conformance of the phase; it cannot be delegated.
- **Subagents write the files from your manifest.** Once the manifest is complete, dispatch **sonnet** agents to write the actual `.md` task files to the `/generate-tasks` template — partitioned by repo/wave so no two agents write the same file, fanned out in parallel. Each agent gets: the exact task-file path (which you have already validated against the Allowlist), the template, and its tasks' manifest entries (including the inline design content and Design reference/acceptance-property lines to embed). Agents transcribe your manifest into the template; they do NOT decide scope, numbering, or dependencies.
- **You verify the written files against your manifest and run the Phase-4 completion gate yourself.** Every checkbox in the completion gate is checked by you on the actual files — the allowlist check, the design-reference check, the enforcement-ordering check, the invariant-surface check, the dual-path check, the migration-step coverage count. A subagent writing the files does not move any of these checks off you.

**MANDATORY FIRST STEP:** Read `d:\datrix\.claude\skills\generate-tasks\SKILL.md` completely before generating any tasks (you read it once; include the relevant template slice in each writer agent's prompt so they don't each re-read it). This skill follows the same workflow as `/generate-tasks` with one critical override described below.

**HARD CONSTRAINT — Task Location Allowlist:** the full allowlist (15 framework projects) and its rules live in `/generate-tasks` SKILL.md ("Task Location Allowlist — HARD CONSTRAINT"), which the mandatory first step below makes you read. The bindings that bite here: every task file path AND `dependencies.md` MUST begin with `D:\datrix\{project}\.tasks\` where `{project}` is one of the 15 allowlisted names; **the design document being operationalized often lives inside a customer/generated project (e.g. `D:\g\<customer-project>\`) — the tasks it produces NEVER go there**; tasks with no specific package go in the `D:\datrix\datrix\.tasks` fallback. Task tooling only scans `D:\datrix\*/.tasks` — a `.tasks` folder anywhere else is invisible and its tasks silently never run.

**BEFORE generating tasks:**
1. Count total tasks needed from the design: implementation tasks (each carrying its own tests + doc updates), migration tasks, and one quality gate per package with 2+ code tasks. Do NOT plan separate per-task test, verify, or docs tasks.
2. Re-read this entire Phase 4 section completely
3. Confirm in your internal reasoning: "I will generate ALL {N} task files now, not a subset or roadmap"

**CRITICAL:** This phase generates ALL task files. Do NOT:
- Generate only some tasks and create a "roadmap" or "summary" for the rest
- Wait for approval mid-phase
- Ask "should I continue?" after generating a subset of tasks
- Stop task generation before all tasks are created
- Create a TASK-GENERATION-SUMMARY.md instead of actual task files

**Reference-AND-inline requirement (critical):** Phase 5 **preserves** the design document (see Phase 5 — its goal is "Verify Design Document Preservation"). So every task file generated in this phase both **references** the preserved design doc and is **self-contained**:

- **Reference the design (MANDATORY).** Keep the `/generate-tasks` header lines `**Design reference:** {absolute-design-doc-path} -- Section(s) {X.Y}; implements design decision(s)/invariant(s) {D#/G#/numbered}` and `**Design acceptance property:** {observable end-state proving the task satisfies the design}`. The design doc remains on disk as the durable source of the invariant the task must satisfy — point at it for traceability and re-verification. (Earlier guidance to strip design-doc references stemmed from a since-removed "Phase 5 deletes the doc" behavior; the doc is now preserved, so reference it.)
- **Inline the content too (MANDATORY).** In addition to the reference, inline the relevant design details (requirements, rationale, constraints, examples, and the specific D#/G#/numbered invariant) directly in the task body, so the implementer has full context without opening the doc. Reference for traceability; inline for self-sufficiency.
- **Include "why" context.** Each task must include enough rationale and design-decision context that an implementer understands not just what to build but why it was designed that way.
- **List the design doc in "Files to Review".** Include the absolute design-doc path (with the specific sections) under "Files to Review Before Starting", alongside the architecture docs, code files, and test guidelines the implementer needs.
- **All file paths MUST be absolute.** Every file path in the generated task files must use absolute paths (e.g., `d:\datrix\datrix\docs\architecture\...`), never relative paths (e.g., `docs/architecture/...`). This applies to all sections: "Files to Review Before Starting", "Design reference", example file references, etc.

**Pre-requisite:** Verify you have read `/generate-tasks` SKILL.md. If not, STOP and read it now.

1. Determine the next phase number:
   ```
   powershell -File "d:/datrix/datrix/scripts/tasks/latest-phase.ps1" -BaseDir "D:\datrix"
   ```
   Use the NEXT phase number (latest + 1), unless PHASE was specified.

2. Review the task file template in `/generate-tasks` SKILL.md (lines 127-200+) to ensure correct formatting.

3. **MANDATORY: Read the design's migration/rollout section.** For every numbered migration step, generate a task. Migration steps are implementation work — they produce `.dcfg` files, update test fixtures, convert examples, build template libraries, etc. They are NOT "future work" or "separate effort" unless the design explicitly says so. If the design says "convert X to Y", that is a task in THIS phase.

4. **MANDATORY: Inventory dual-implementation risk.** If the design introduces a new path alongside an old one (new format, new API, new config system), identify every test fixture, example, and project config that currently exercises the OLD path. Generate migration tasks to convert these to the NEW path. Without these tasks, the new implementation ships untested — old tests continue to pass on the old path, creating false confidence.

5. **MANDATORY: Tasks span all affected repos.** Do NOT limit task generation to a single "target package." If the design affects `datrix-common` (new code), `datrix` (examples), and `datrix-cli` (CLI wiring), generate tasks in ALL of those repos. A task lives in the repo it modifies.

6. Break the design into tasks. Generate these categories (lean model — tests and docs ride inside implementation tasks; there are NO standalone per-task test, verify, or docs tasks):

   **a) Implementation tasks (self-contained — code + tests + docs in one):**
   - One task per discrete unit of work; independently implementable and testable; clear acceptance criteria; explicit dependencies
   - **Each implementation task writes its own unit + integration tests** in the same task (a populated `## Tests` section + a `## Targeted Tests` section), following the conventions in `d:\datrix\datrix-common\docs\contributing\test-guidelines\` (`unit-test-guidelines.md`, `integration-test-guidelines.md`, `e2e-test-guidelines.md`). Do NOT emit a separate `-tests` task.
   - **Each implementation task updates the docs its feature touches** as part of its scope (target the correct repo `docs/` folder — see the table below). Do NOT emit a separate `-docs` task.
   - **No separate `-verify` task.** Independent verification is provided by the per-package quality gate (category c), run by a different agent than the implementers.

   Docs-folder targets for the in-task doc updates: each repo's docs live at `d:\datrix\{repo}\docs\` — discover dynamically with `ls -d d:/datrix/datrix*/docs/`; do not rely on a hardcoded list.

   **Narrow exceptions (only when the work genuinely cannot live inside one implementation task):**
   - A standalone **integration/e2e** task is allowed only for a suite that spans multiple implementation tasks (e.g., a cross-service end-to-end fixture) **within a single `datrix-*` package**. It depends on the tasks it exercises. **Never operationalize a cross-package or language/provider matrix test** (a suite importing more than one generator package, or enumerating languages/providers like a LOCAL/AWS/Azure gate): Datrix is a multi-language, multi-platform generator, each package tests only its own surface, and the public `datrix` repo hosts no test suite. Genuine repo-level cross-cutting validation becomes a **script task under `datrix/scripts/test/`**, not a pytest suite.
   - A standalone **docs** task is allowed only for a substantial deliverable documenting several tasks at once. Place it OUTSIDE the dependency chain (nothing depends on it) so it never anchors a wave.

   **b) Migration tasks:**
   - For each numbered step in the design's migration/rollout/adoption section, generate a task
   - Migration tasks convert existing files from the old format/API to the new one
   - Migration tasks live in the repo whose files they modify (not the repo where the new code lives)
   - Migration tasks depend on the implementation tasks that create the new subsystem
   - Types of migration tasks:
     - **Fixture conversion** — convert test fixtures from old format to new (e.g., YAML → `.dcfg`)
     - **Example conversion** — convert example files to demonstrate the new way
     - **Template/library creation** — create reusable shared templates or libraries the design calls for
     - **Project config conversion** — convert real project configs to the new format
     - **Test path verification** — ensure tests actually exercise the NEW path, not just the old one
   - Each migration task must include a verification step: "Confirm the new path is exercised by running X and verifying Y"
   - Do NOT treat migration steps as "future work" unless the design explicitly defers them

   **c) Quality gate tasks (one per package — also the independent-verification gate):**
   - For each package that has 2+ implementation tasks in this phase, generate exactly ONE quality gate task
   - It runs the full test suite AND carries the anti-stub / coverage-sanity / anti-gap checklist that standalone `-verify` tasks used to provide — no implementation code
   - **Run by a different agent/session than the implementers** — this is what preserves independent verification
   - Depends on ALL other tasks targeting the same package; numbered AFTER all other tasks for the phase
   - Use the enhanced quality gate template from `/generate-tasks` (no "Files to Create" section; includes the embedded verification checklist)
   - Quality gate slug: `quality-gate-{package-name}` (e.g., `task-{NN}-{TT}-quality-gate-datrix-common.md`); include `**Category:** Quality Gate`
   - Do NOT generate a quality gate for a package with only 1 code task in the phase (its targeted tests + the executor's gate suffice)

4. Generate task files following the **exact template format** from `/generate-tasks` SKILL.md (lines 127-200+):

   **File naming:**
   ```
   d:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md
   ```
   `{repo}` MUST be one of the 15 framework projects in the **Task Location Allowlist** above — never a customer/generated project, even when the design doc lives in one. Use `datrix` as the fallback bucket when no specific package fits.

   **File structure (from `/generate-tasks`):**
   ```markdown
   > **Peruse 'd:\datrix\datrix-common\docs\contributing\ai-agent-rules.md' (and its sub-documents) and follow the rules**

   # Task {NN}-{TT}: {Title}

   ## Overview
   ...
   ```

   **CRITICAL:** The first H1 heading MUST be `# Task {NN}-{TT}: {Title}` (e.g., `# Task 39-01: Remove Dead Code in TypeScript Relationship Generation`). The `todo.ps1` script parses this heading to display tasks.

5. Generate the dependencies document following generate-tasks Step 7 format exactly — the **JSON document** (with the `provenance` stamp: `generated_by: "/operationalize-design"`, `generated_at`, and the `validated` list of checks that actually ran), nothing else in the file. See `d:\datrix\.claude\skills\generate-tasks\SKILL.md` Step 7 and `dependencies-format.md` for the exact schema. Do NOT emit the legacy "Group N" text format.

## Phase 4 Completion Gate

This phase is COMPLETE when:
- [ ] ALL implementation tasks generated as actual .md files (not a roadmap), each carrying its own `## Tests` and `## Targeted Tests` sections AND its in-scope doc updates
- [ ] NO standalone per-task `-tests`, `-verify`, or `-docs` tasks generated (tests + docs ride inside impl tasks; verification rides in the quality gate)
- [ ] ALL migration tasks generated (one per numbered step in the design's migration/rollout section)
- [ ] ALL quality gate tasks generated (exactly one per package with 2+ code tasks; carries the embedded verification checklist)
- [ ] Any narrow-exception standalone integration/e2e or substantial-docs task is justified and (for docs) placed OUTSIDE the dependency chain
- [ ] Tasks span ALL affected repos (not just the primary package)
- [ ] **Every task file path and `dependencies.md` begins with `D:\datrix\{project}\.tasks\` where `{project}` is one of the 15 in the Task Location Allowlist** — no `.tasks` folder under a customer/generated project or any path outside the allowlist; tasks with no specific package use the `datrix\.tasks` fallback
- [ ] Every task file both REFERENCES the preserved design doc (`**Design reference:**`) AND inlines the relevant design content (self-contained per the Reference-AND-inline requirement)
- [ ] Dependencies document (`dependencies.md`) created as the Step-7 JSON document with a truthful `provenance` stamp — no headers, tables, inventories, or prose around it; NOT the legacy "Group N" text format
- [ ] Output lists ALL task file paths (not "23 tasks remaining")
- [ ] No dual-implementation gap: if the design introduces a new path, migration tasks ensure the new path is exercised by tests/examples
- [ ] **Every task carries `**Design reference:**` + `**Design acceptance property:**`** with the specific D#/G#/numbered invariant and a provable (negative + positive) acceptance check — not "tests pass"/"generates clean"
- [ ] **Enforcement before what it governs:** any task that enforces a design invariant (guard/validator/rejection/conformance check) precedes — and is in `Depends on` of — every task that relies on it or migrates content it governs. No migration is in an earlier or equal wave to its guard
- [ ] **Invariant-surface coverage:** if the design states an invariant over a SET of surfaces, a task or QG criterion covers EVERY surface in that set — none silently dropped

If any task is described but not generated: Phase 4 is NOT complete.

**End-of-phase output (lean — counts + paths + pointer to dependencies.md):**

```
TASKS: phase {NN}, {N} total ({N} impl, {N} migration, {N} QG, {N} standalone-integration/docs if any)

{task-path}
{task-path}
...

Dependencies: datrix\.tasks\phase-{NN}\dependencies.md
```

Do NOT duplicate the dependency graph in console output — it is already in `dependencies.md`.

## Phase 4 Self-Check

Before proceeding to Phase 5, answer:
1. Did I generate ALL tasks as actual files (not a summary/roadmap)?
2. Did I both inline the design content AND keep the `**Design reference:**` pointer in every task (Reference-AND-inline)?
3. Does every implementation task carry its OWN `## Tests` + `## Targeted Tests` and its in-scope doc updates (no separate `-tests`/`-docs` tasks)?
4. Did I avoid generating any standalone `-verify` task (verification rides in the quality gate)?
5. Did I create migration tasks for every numbered step in the design's migration/rollout section?
6. Did I generate tasks in ALL affected repos, not just the primary package?
6a. **Allowlist check:** Does every task file and `dependencies.md` live under `D:\datrix\{one-of-the-15}\.tasks\`? Did I avoid creating any `.tasks` folder inside the (possibly customer-owned) directory where the design document lives? Did unmatched tasks land in the `datrix\.tasks` fallback?
7. Did I create exactly one quality gate (with the embedded verification checklist) for every package with 2+ code tasks?
8. Did I follow the template from `/generate-tasks` exactly?
9. **Dual-path check:** If the design introduces a new path alongside an old one, will the old tests still pass without the new path being exercised? If yes, I am missing migration tasks.
10. **Coverage check:** Count the migration steps in the design. Count the migration tasks I generated. If the second number is less than the first, I stopped early.
10a. **Design-reference check:** Does every task carry `**Design reference:**` + `**Design acceptance property:**` naming the specific D#/G#/numbered invariant, with a provable (negative + positive) acceptance check — not just "tests pass"?
10b. **Enforcement-ordering check:** Does every invariant-enforcing task (guard/validator/rejection) precede and gate the tasks that rely on it? Is any migration in an earlier-or-equal wave to its guard? If yes, reorder.
10c. **Invariant-surface check:** If the design states an invariant over a SET of surfaces, did I create a task (or QG criterion) for EVERY surface — or did I cover the easy ones and silently drop the rest (the phase-01 failure mode)?
11. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

---

### Phase 5: Cleanup — Verify Design Document Preservation

**Goal:** Verify all content has been transferred while preserving the design document.

**Delegate the cross-check, own the verdict.** Comparing the design doc section-by-section against the official docs + task files to find any untransferred content is mechanical — dispatch a **haiku** agent to produce the diff (for each design section: transferred → where, or NOT transferred). You read its report and decide whether transfer is complete; a "nothing remains" claim is accepted only when the agent's per-section evidence supports it. Confirm the design document still exists on disk yourself.

1. Verify ALL content has been transferred to official docs or task files (via the delegated cross-check; you judge the result)
2. Check that no unique information remains only in the design document
3. Report completion (design document is preserved)

**If content was NOT fully transferred** (e.g., a section was skipped):
- Report what remains and why it wasn't transferred
- WAIT for user decision

## Phase 5 Completion Gate

This phase is COMPLETE when:
- [ ] Verified ALL content transferred to official docs or task files
- [ ] Verified no unique information remains only in design document
- [ ] Design document preserved on filesystem
- [ ] Output matches the format below exactly

**End-of-phase output (lean):**

```
CLEANUP: design preserved at {path}, all content transferred
```

## Phase 5 Self-Check

Before reporting completion, answer:
1. Did I verify ALL content was transferred (not just assume)?
2. Did I preserve the design document file?
3. Did I follow the "Goal:" statement above exactly?
4. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

---

## Final Summary

After all phases complete (lean — no "next steps" padding, user knows what to do):

```
DONE: {title}
Decisions: {N} (review: {MEDIUM decision titles, if any})
Docs: {N} files updated
Tasks: {N} in phase {NN}
Dependencies: datrix\.tasks\phase-{NN}\dependencies.md
Design: preserved at {path}
```

## Anti-Patterns

- **NO generating tasks without resolving ambiguities first** — Phase 2 before Phase 4
- **NO closing open questions by assumption** — a question is resolved only when investigation (code, docs, logic-map) or the user answers it. A plausible guess does not clear the ambiguity gate. Every resolved question must be traceable to the investigation that closed it.
- **NO entering Phase 3/4 with any open item** — unresolved questions and unchosen explicit alternatives are hard blockers; STOP and present findings + recommendations, then WAIT
- **NO deleting the design doc** — design docs are preserved as historical reference
- **NO duplicating content** — transfer, don't copy
- **NO creating new standalone docs** — integrate into existing doc structure
- **NO skipping dependency analysis** — task ordering must reflect real dependencies
- **NO fabricating decisions** — every decision needs evidence from the codebase
- **NO task files without acceptance criteria** — every task must be verifiable
- **NO implementation tasks without inline tests** — every implementation task writes its own `## Tests`; tests are not split into a separate task
- **NO standalone `-verify` tasks** — independent verification is provided once per package by the quality gate (run by a different agent), not by a per-task verify task
- **NO separate `-docs` tasks for routine updates** — doc updates ride inside the implementation task whose feature they document; a standalone docs task is only for a substantial multi-task deliverable, placed outside the dependency chain
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO bloated dependencies.md** — the dependencies document is for AI agent consumption only; it is the Step-7 JSON document (tasks + dependencies + provenance stamp), nothing else. No markdown headers, tables, task inventories, dependency text blocks, or prose around it, and never the legacy "Group N" text format. See generate-tasks Step 7 for the exact schema.
- **YES design document references in task files** — Phase 5 preserves the design doc, so every task carries `**Design reference:**` + `**Design acceptance property:**` pointing at it AND inlines the relevant content. (Reference for traceability, inline for self-sufficiency.) Do NOT strip the reference.
- **NO marking a task/phase done on "generates clean" or "suite green" alone** — a task is done only when its `**Design acceptance property:**` is PROVEN by an executable check (negative + positive) whose output is pasted. A green suite over a half-enforced invariant is a false pass (the phase-01 env()-third-path failure).
- **NO tasks without targeted tests** — every implementation and test task must have a `## Targeted Tests` section specifying which tests to run for focused verification
- **NO missing quality gates** — every package with 2+ code tasks must have a quality gate task as the final dependency
- **NO partial task generation** — generate ALL tasks in Phase 4, not a subset with a "roadmap"
- **NO asking mid-phase** — complete each phase fully before asking user questions (unless blocked)
- **NO roadmap/summary files** — generate actual task .md files, not summaries of future work
- **NO single-package scoping** — if the design affects multiple repos, generate tasks in ALL of them. The design's migration strategy tells you which repos have work.
- **NO `.tasks` outside the allowlist** — task files and `dependencies.md` go ONLY under `D:\datrix\{one-of-the-15-framework-projects}\.tasks\`. Never create a `.tasks` folder in the customer/generated project the design doc lives in (e.g. `D:\g\<customer-project>\`), under `D:\g\...`, or anywhere outside `D:\datrix\`. A task with no specific framework package goes in the `datrix\.tasks` fallback. Tooling only scans `D:\datrix\*/.tasks` — anything else is invisible.
- **NO skipping migration tasks** — if the design has a migration/rollout section with numbered steps, every step becomes a task. "Convert X to Y" is not a suggestion — it is implementation work.
- **NO leaving dual implementations untested** — if the design introduces a new path alongside an old one, old tests will pass on the old path regardless of whether the new path works. Migration tasks must convert fixtures, examples, and configs to the new path so the new implementation is actually exercised.
- **NO treating migration as "future work"** — unless the design explicitly defers a migration step to a later phase, it belongs in THIS phase. The design document is the scope boundary.
- **NO delegating a decision or a gate** — subagents gather evidence and write files to your manifest; every decision (each open question, each confidence rating, the task decomposition, the dependency/enforcement ordering) and every phase completion gate is decided by YOU on evidence you verify. A subagent's recon or self-report is input to your judgment, never a substitute for it, and never relaxes a gate.
- **NO inline execution that a cheaper tier can do** — do not read whole docs, glob fixtures, run per-question codebase searches, transfer doc content, or write task files inline on Opus. Dispatch them; spend Opus tokens and context on judgment only.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
