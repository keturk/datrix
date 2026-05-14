# Operationalize Design Document

End-to-end pipeline that takes a design document and produces: resolved decisions, updated architecture docs, implementation tasks, and cleanup — collapsing what previously took multiple sessions into a single orchestrated workflow.

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

## Mandatory Reading (BEFORE any work)

1. **`d:\datrix\.claude\CLAUDE.md`** — Project rules
2. **`C:\Users\KErca\.claude\projects\d--datrix\memory\MEMORY.md`** — Persistent memory
3. **`d:\datrix\datrix\docs\architecture\architecture-overview.md`** — Current architecture (index with links to sub-documents: `architecture/pipeline-and-capabilities.md`, `architecture/repository-architecture.md`, `architecture/builtin-traits-enums.md`)
4. **`d:\datrix\datrix\docs\architecture\design-principles.md`** — Design principles

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

---

### Phase 1: Analysis — Audit the Design Document

**Goal:** Understand the design completely and identify all decision points.

1. Read the design document in full
2. Cross-reference against existing architecture docs in `d:\datrix\datrix\docs\architecture\`
3. Identify:
   - **Open questions** — explicitly marked or implicit
   - **Decision points** — alternatives presented without resolution
   - **Content overlap** — sections that duplicate or conflict with existing docs
   - **Implementation scope** — which packages/modules are affected
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

**End-of-phase output:**

```
ANALYSIS COMPLETE:

Design: {title}
Scope: {packages affected}
Open questions: {N}
Decision points: {N}
Content overlap with existing docs: {N} conflicts
Dependencies: {list}
```

## Phase 1 Self-Check

Before proceeding to Phase 2, answer:
1. Did I investigate each "open question" to determine if it's actually open?
2. Did I check the codebase for existing patterns that resolve ambiguities?
3. Did I follow the "Goal:" statement above exactly?
4. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

**If there are BLOCKING open questions** (ambiguities that prevent task generation):
- Present them with recommended answers and evidence from the codebase
- WAIT for user to confirm or override

**If the design presents explicit alternatives** (Option A vs Option B, multiple approaches listed):
- These are ALWAYS open questions that require user input, even when codebase patterns suggest one option
- Research the codebase and existing patterns to inform a recommendation
- Present the alternatives with your recommendation and evidence
- WAIT for user to choose — never auto-select

**If all questions have clear answers from the codebase AND the design presents no explicit alternatives** → proceed automatically.

---

### Phase 2: Decisions — Resolve All Open Questions

**Goal:** Make every decision required by the design, with rationale.

For each open question or decision point:

1. **Research the codebase** — find evidence for the best approach
2. **Check existing patterns** — query logic map markers if relevant
3. **Classify the question:**
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

**End-of-phase output:**

```
DECISIONS:

1. {Decision title}
   Decision: {what was decided}
   Rationale: {why}
   Confidence: HIGH
   Evidence: {file:line or architectural principle}

2. {Decision title}
   Decision: {what was decided}
   Rationale: {why}
   Confidence: MEDIUM — flagged for review
   Evidence: {what was found}
```

## Phase 2 Self-Check

Before proceeding to Phase 3, answer:
1. Did I make a decision for EVERY open question from Phase 1?
2. Did I provide evidence from the codebase (not just opinions)?
3. Did I follow the confidence gate rules?
4. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

**Confidence gate:**
- **All HIGH** → proceed to Phase 3 automatically
- **Any MEDIUM** → flag for review but proceed (include in final summary)
- **Any LOW** → STOP, present decisions, WAIT for user input

---

### Phase 3: Documentation — Transfer Knowledge to Official Docs

**Goal:** Update existing architecture and documentation files with the design's content.

For each section of the design document that adds NEW information:

1. Identify the correct target document in `d:\datrix\datrix\docs\` or package `docs/` directories
2. Determine where in the target document the information belongs
3. Write the content into the target document, adapting style to match

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

**End-of-phase output:**

```
DOCUMENTATION UPDATED:

Files modified:
1. {target-doc-path} — Added: {section title} ({N} lines)
2. {target-doc-path} — Updated: {section title} ({N} lines changed)
3. {target-doc-path} — Created: {new file} ({N} lines)

Content transferred: {N} sections from design document
Conflicts resolved: {N}
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

**MANDATORY FIRST STEP:** Read `d:\datrix\.claude\skills\generate-tasks\SKILL.md` completely before generating any tasks. This skill follows the same workflow as `/generate-tasks` with one critical override described below.

**BEFORE generating tasks:**
1. Count total tasks needed from the design (implementation + test + docs + quality gates)
2. Re-read this entire Phase 4 section completely
3. Confirm in your internal reasoning: "I will generate ALL {N} task files now, not a subset or roadmap"

**CRITICAL:** This phase generates ALL task files. Do NOT:
- Generate only some tasks and create a "roadmap" or "summary" for the rest
- Wait for approval mid-phase
- Ask "should I continue?" after generating a subset of tasks
- Stop task generation before all tasks are created
- Create a TASK-GENERATION-SUMMARY.md instead of actual task files

**Self-containment requirement (critical):** Because Phase 5 deletes the design document, every task file generated in this phase MUST be fully self-contained. Specifically:

- **Inline, do not reference.** Where `/generate-tasks` uses `**Design reference:** {path} -- Section(s) {X.Y}`, replace the path and section reference with the actual content from those sections. The task must contain the relevant design details (requirements, rationale, constraints, examples) directly in its body.
- **No file path references to the design document.** Task files must NOT contain any path pointing to the design document being operationalized — not in the header, not in "Files to Review", not in prose. The design document will not exist when the task is executed.
- **Include "why" context.** Each task must include enough rationale and design-decision context that an implementer understands not just what to build but why it was designed that way — without needing the original design doc.
- **Replace "Files to Review" design-doc entries.** Instead of listing the design document under "Files to Review Before Starting", list only the architecture docs, code files, and test guidelines that the implementer actually needs. If specific design content is needed, inline it in the task body.
- **All file paths MUST be absolute.** Every file path in the generated task files must use absolute paths (e.g., `d:\datrix\datrix\docs\architecture\...`), never relative paths (e.g., `docs/architecture/...`). This applies to all sections: "Files to Review Before Starting", "Design reference", example file references, etc.

**Pre-requisite:** Verify you have read `/generate-tasks` SKILL.md. If not, STOP and read it now.

1. Determine the next phase number:
   ```
   powershell -File "d:/datrix/datrix/scripts/tasks/latest-phase.ps1" -BaseDir "D:\datrix"
   ```
   Use the NEXT phase number (latest + 1), unless PHASE was specified.

2. Review the task file template in `/generate-tasks` SKILL.md (lines 127-200+) to ensure correct formatting.

3. Break the design into tasks. Four categories of tasks MUST be generated:

   **a) Implementation tasks:**
   - One task per discrete unit of work
   - Each task is independently implementable and testable
   - Tasks have clear acceptance criteria
   - Dependencies between tasks are explicit

   **b) Test tasks:**
   - For each implementation task, generate a corresponding test task
   - Test tasks follow the conventions in `d:\datrix\datrix-common\docs\contributing\test-guidelines\`:
     - `unit-test-guidelines.md` — unit tests (real objects, no mocks; index with links to shared sub-documents under `shared/`)
     - `integration-test-guidelines.md` — integration tests (index with links to shared sub-documents under `shared/`)
     - `e2e-test-guidelines.md` — end-to-end tests
   - Each test task specifies which test level(s) are required (unit, integration, e2e)
   - Test tasks depend on their corresponding implementation task
   - Test task slug should mirror the implementation task with a `-tests` suffix
     (e.g., `task-{NN}-{TT}-add-widget.md` → `task-{NN}-{TT+1}-add-widget-tests.md`)

   **c) Documentation tasks:**
   - Generate tasks for updating or adding documentation in the affected repo's `docs/` folder
   - Each documentation task identifies the target doc file(s) and what content to add/update
   - Target the correct repo's docs directory based on scope:

     | Repo | Docs path |
     |------|-----------|
     | datrix | `d:\datrix\datrix\docs\` |
     | datrix-cli | `d:\datrix\datrix-cli\docs\` |
     | datrix-codegen-aws | `d:\datrix\datrix-codegen-aws\docs\` |
     | datrix-codegen-azure | `d:\datrix\datrix-codegen-azure\docs\` |
     | datrix-codegen-common | `d:\datrix\datrix-codegen-common\docs\` |
     | datrix-codegen-component | `d:\datrix\datrix-codegen-component\docs\` |
     | datrix-codegen-docker | `d:\datrix\datrix-codegen-docker\docs\` |
     | datrix-codegen-k8s | `d:\datrix\datrix-codegen-k8s\docs\` |
     | datrix-codegen-python | `d:\datrix\datrix-codegen-python\docs\` |
     | datrix-codegen-sql | `d:\datrix\datrix-codegen-sql\docs\` |
     | datrix-codegen-typescript | `d:\datrix\datrix-codegen-typescript\docs\` |
     | datrix-common | `d:\datrix\datrix-common\docs\` |
     | datrix-extensions | `d:\datrix\datrix-extensions\docs\` |
     | datrix-language | `d:\datrix\datrix-language\docs\` |

   - Documentation tasks should cover:
     - Architecture docs (`architecture.md`) — when the design changes architectural patterns
     - API reference docs — when new public APIs are introduced or changed
     - Extension/integration docs — when extension points are added or modified
     - Contributing docs — when development workflows change
   - Documentation tasks depend on the implementation tasks they document
   - Doc task slug should use a `-docs` suffix
     (e.g., `task-{NN}-{TT}-update-codegen-docs.md`)

   **d) Quality gate tasks:**
   - For each package that has 2+ code tasks (implementation + test combined) in this phase, generate a quality gate task
   - Quality gate tasks run the full test suite + `mypy --strict` as final verification — no implementation code
   - Quality gate tasks depend on ALL other tasks targeting the same package
   - Quality gate task numbering comes AFTER all other tasks for the phase
   - Use the quality gate template from `/generate-tasks` (no "Files to Create" section)
   - Quality gate slug: `quality-gate-{package-name}` (e.g., `task-{NN}-{TT}-quality-gate-datrix-common.md`)
   - Include `**Category:** Quality Gate` in the header metadata
   - Do NOT generate quality gates for packages with only 1 code task in the phase

4. Generate task files following the **exact template format** from `/generate-tasks` SKILL.md (lines 127-200+):

   **File naming:**
   ```
   d:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md
   ```

   **File structure (from `/generate-tasks`):**
   ```markdown
   > **Peruse 'd:\datrix\datrix-common\docs\contributing\ai-agent-rules.md' (and its sub-documents) and follow the rules**

   # Task {NN}-{TT}: {Title}

   ## Overview
   ...
   ```

   **CRITICAL:** The first H1 heading MUST be `# Task {NN}-{TT}: {Title}` (e.g., `# Task 39-01: Remove Dead Code in TypeScript Relationship Generation`). The `todo.ps1` script parses this heading to display tasks.

5. Report dependency graph with parallelizable groups

## Phase 4 Completion Gate

This phase is COMPLETE when:
- [ ] ALL implementation tasks generated as actual .md files (not a roadmap)
- [ ] ALL test tasks generated (one per implementation task)
- [ ] ALL documentation tasks generated
- [ ] ALL quality gate tasks generated (one per package with 2+ code tasks)
- [ ] Every task file is self-contained (no design doc references)
- [ ] Dependency graph created showing parallelizable groups
- [ ] Output lists ALL task file paths (not "23 tasks remaining")

If any task is described but not generated: Phase 4 is NOT complete.

**End-of-phase output:**

```
TASKS GENERATED:

Phase: {NN}
Tasks: {N} total across {M} repos
  Implementation: {N}
  Test: {N}
  Documentation: {N}
  Quality Gate: {N}

d:\datrix\datrix-common\.tasks\phase-{NN}\task-{NN}-01-add-orchestrator.md
d:\datrix\datrix-common\.tasks\phase-{NN}\task-{NN}-02-add-orchestrator-tests.md
d:\datrix\datrix-codegen-python\.tasks\phase-{NN}\task-{NN}-03-python-pipeline.md
d:\datrix\datrix-codegen-python\.tasks\phase-{NN}\task-{NN}-04-python-pipeline-tests.md
d:\datrix\datrix-common\.tasks\phase-{NN}\task-{NN}-05-update-architecture-docs.md
d:\datrix\datrix-codegen-python\.tasks\phase-{NN}\task-{NN}-06-update-codegen-docs.md
d:\datrix\datrix-common\.tasks\phase-{NN}\task-{NN}-07-quality-gate-datrix-common.md
d:\datrix\datrix-codegen-python\.tasks\phase-{NN}\task-{NN}-08-quality-gate-datrix-codegen-python.md

Dependency graph:
  Group 1 (parallel): tasks 01, 03           [implementation]
  Group 2 (after group 1): tasks 02, 04      [tests]
  Group 3 (after group 2): tasks 05, 06      [docs]
  Group 4 (after all): tasks 07, 08          [quality gates]
```

## Phase 4 Self-Check

Before proceeding to Phase 5, answer:
1. Did I generate ALL tasks as actual files (not a summary/roadmap)?
2. Did I inline design content in tasks (not reference the design doc path)?
3. Did I create test tasks for every implementation task?
4. Did I create quality gates for every package with 2+ code tasks?
5. Did I follow the template from `/generate-tasks` exactly?
6. Did I deviate from any instruction in this phase? If yes, why?

If you deviated: STOP and explain the deviation to the user.

---

### Phase 5: Cleanup — Verify Design Document Preservation

**Goal:** Verify all content has been transferred while preserving the design document.

1. Verify ALL content has been transferred to official docs or task files
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

**End-of-phase output:**

```
CLEANUP:

Design document preserved: {path}
All content transferred to:
- {doc 1}
- {doc 2}
- Task files in phase {NN}
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

After all phases complete:

```
OPERATIONALIZATION COMPLETE

Design: {title}
Decisions made: {N} (HIGH: {n}, MEDIUM: {n}, flagged for review: {n})
Docs updated: {N} files
Tasks generated: {N} tasks in phase {NN}
  Implementation: {N}
  Test: {N}
  Documentation: {N}
  Quality Gate: {N}
Design document: PRESERVED at {path}

Medium-confidence decisions to review:
- {decision 1} — {rationale summary}

Next steps:
1. Review medium-confidence decisions above
2. Begin implementation with task group 1: {task list}
3. Run test tasks after corresponding implementation tasks
4. Complete documentation tasks
5. Run quality gate tasks last to verify full-suite integration
```

## Anti-Patterns

- **NO generating tasks without resolving ambiguities first** — Phase 2 before Phase 4
- **NO deleting the design doc** — design docs are preserved as historical reference
- **NO duplicating content** — transfer, don't copy
- **NO creating new standalone docs** — integrate into existing doc structure
- **NO skipping dependency analysis** — task ordering must reflect real dependencies
- **NO fabricating decisions** — every decision needs evidence from the codebase
- **NO task files without acceptance criteria** — every task must be verifiable
- **NO implementation tasks without corresponding test tasks** — every implementation needs tests
- **NO skipping documentation tasks** — if a design changes architecture, APIs, or extensions, the relevant repo docs must be updated
- **NO design document path references in task files** — when operationalizing, tasks must inline design content because Phase 5 deletes the source document
- **NO tasks without targeted tests** — every implementation and test task must have a `## Targeted Tests` section specifying which tests to run for focused verification
- **NO missing quality gates** — every package with 2+ code tasks must have a quality gate task as the final dependency
- **NO partial task generation** — generate ALL tasks in Phase 4, not a subset with a "roadmap"
- **NO asking mid-phase** — complete each phase fully before asking user questions (unless blocked)
- **NO roadmap/summary files** — generate actual task .md files, not summaries of future work
