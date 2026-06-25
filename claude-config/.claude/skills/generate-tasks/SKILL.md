---
model: opus
---

# Generate Tasks Skill

Generate structured task files from a design document for AI agent execution across Datrix repositories.

## When to Use

- User has a design document and wants to break it into implementable tasks
- User asks to "create tasks", "generate tasks", or "break this into tasks"
- User references a design document and asks for task files or phases

## How to Invoke

Ask Claude Code directly:
```
"Generate tasks from CODE_GENERATION_DESIGN.md"
"Create tasks for datrix-codegen-python from the design doc"
"Break this design into phase tasks"
```

Or with options:
```
"Generate tasks for phase 3 only from CODE_GENERATION_DESIGN.md"
"Create tasks for datrix-common from sections 4-5 of the design doc"
```

## Inputs

The user provides:
1. **Design document path** — The `.md` file containing the design to decompose
2. **Target repository** (optional) — Which repo(s) the tasks belong to (e.g., `datrix-common`, `datrix-codegen-python`)
3. **Phase filter** (optional) — Generate tasks for a specific phase only
4. **Section filter** (optional) — Focus on specific sections of the design document

## Output Principle

All skill outputs (summaries, generated artifacts like dependencies.md) must be lean and data-dense. No decorative headers, horizontal rules, or verbose markdown formatting in console output. No "Next steps" sections. No dependency graphs in console output — that data lives in dependencies.md. One line per data point. If it fits on one line, don't use three.

## Workflow

When invoked, follow these steps:

### Step 1: Read and Understand the Design Document

1. Read the design document completely
2. Identify implementation phases (look for "Implementation Phases", "Phases", or numbered phase sections)
3. Map each phase item to the correct target repository based on the package it references
4. Identify dependencies between tasks
5. Identify test coverage needs — which new modules, classes, or pipelines need tests. **Tests ride inside the implementation task that creates the code** (same task, same wave), not as separate `-tests` tasks. Carve out a standalone test task ONLY for an integration/e2e suite that genuinely spans multiple implementation tasks and cannot live inside any one of them.
6. Identify documentation impacts — which docs need to be created or updated. **Doc updates ride inside the implementation task whose feature they document.** Carve out a standalone docs task ONLY for a substantial doc deliverable that documents several tasks at once — and place it OUTSIDE the dependency chain (nothing depends on it), so it never anchors a wave.
7. **Read the migration/rollout/adoption section** (look for "Migration", "Rollout", "Adoption", numbered migration steps). List every step. Each step that says "convert X", "migrate Y", or "create Z" is a task — not future work.
8. **Identify dual-implementation risk** — if the design introduces a new path alongside an old one, inventory all test fixtures, examples, and project configs that currently exercise the old path. These need migration tasks or the new path ships untested.

### Step 2: Check for Ambiguities and Open Questions

Before generating any tasks, review the design document for ambiguities, gaps, and open questions. **If any are found, do NOT proceed to task generation.** Instead, output a prerequisites report and stop.

**What to look for:**

- **Undefined behavior:** The design says "handle X" but doesn't specify how (e.g., "handle errors appropriately" without defining the error strategy)
- **Missing details:** Referenced concepts, modules, or patterns that are not defined or explained
- **Contradictions:** Two sections that describe conflicting approaches or rules
- **Implicit assumptions:** The design assumes something exists or works a certain way without stating it
- **Unresolved alternatives:** The design presents options (e.g., "we could use A or B") without making a decision
- **Missing scope boundaries:** Unclear what's in scope vs. out of scope for this phase
- **Missing examples or edge cases:** Complex logic described without examples of expected input/output
- **Vague requirements:** Qualitative language like "fast", "simple", "clean" without concrete criteria
- **Cross-cutting concerns not addressed:** Error handling, logging, configuration, testing strategy left undefined when the design introduces new patterns

**Output format when ambiguities are found:**

```
## Prerequisites — Open Questions

The following ambiguities must be resolved before tasks can be generated.

### 1. {Short title}
**Section:** {design doc section reference}
**Issue:** {Clear description of what is ambiguous or missing}
**Why it blocks task generation:** {How this affects task scope, implementation, or ordering}
**Suggestion:** {If you have a reasonable suggestion, provide it — otherwise "Needs author input"}

### 2. {Short title}
...
```

**When to proceed despite minor ambiguities:**
- Cosmetic or naming-only questions that don't affect architecture → note them in the relevant task's "Implementation notes" section
- Details that are well-established project conventions (check CLAUDE.md and architecture docs) → use the convention, don't ask

**If all clear:** State "No blocking ambiguities found" and proceed to Step 3.

### Step 3: Read Project Context

Read these mandatory context files:
- `d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md` — Agent rules and code quality standards (index with links to sub-documents: `ai-agent-rules/prohibited-patterns.md`, `ai-agent-rules/code-quality-standards.md`, `ai-agent-rules/repo-specific-rules.md`, `ai-agent-rules/canonical-imports.md`)
- `d:\datrix\.claude\rules.md` — Claude Code rules for the project
- Architecture and design principle docs referenced in the design document

Identify relevant example `.dtrx` files from `d:\datrix\datrix\examples\`:
- `01-foundation/` — Minimal library service (single entity + REST API)
- `02-features/` — Focused feature examples organized by category
- `03-domains/` — Real-world domain models (ecommerce, healthcare, blog-cms, etc.)

Also check test fixtures at:
- `d:\datrix\datrix-language\tests\fixtures\` — Parser test fixtures

### Step 4: Determine Phase and Task Numbers

Run the latest-phase script to find the highest existing phase number:
```powershell
powershell -File d:\datrix\datrix\scripts\tasks\latest-phase.ps1 -BaseDir "D:\datrix"
```

Check existing tasks **across all repos** in the target phase to determine the next task number:
```bash
ls d:\datrix\*/.tasks\phase-{NN}/
```

**Numbering convention:** Task numbers (`{TT}`) are **unique within a phase across all repositories.** If phase 05 has tasks `05-01` through `05-03` in `datrix-common` and task `05-04` in `datrix-codegen-python`, the next task in any repo for phase 05 is `05-05`. This ensures every task ID (`{NN}-{TT}`) is globally unique within the phase, regardless of which repo it lives in.

### Step 5: Generate Task Files

For each task, create a file following this exact structure:

#### File Naming
- Path: `d:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md`
- `{NN}` = zero-padded phase number (e.g., `01`, `02`)
- `{TT}` = zero-padded task number within phase (e.g., `01`, `02`)
- `{slug}` = kebab-case description (e.g., `generator-base-and-file-writer`)

#### File Structure

Every task file MUST follow this template:

```markdown
> **Peruse 'd:\datrix\datrix-common\docs\contributing\ai-agent-rules.md' (and its sub-documents) and follow the rules**

# Task {NN}-{TT}: {Title}

## Overview

{2-3 sentence description of what this task accomplishes and its architectural context.}

**Package:** `{package-name}` (`d:\datrix\{repo}\`)
**Design reference:** `{design-doc-path}` -- Section(s) {X.Y}
**Depends on:** {List of prerequisite tasks or "None"}

## Codebase Context

**Architecture:** `.dtrx -> TreeSitterParser + Transformers -> Application (validated AST) -> Generators` -- no IR layer.
**Logging:** Standard Python `logging` (`logger = logging.getLogger(__name__)`, %-style formatting) -- NOT structlog.
**Code generation:** Jinja2 templates + ruff format (Python) / Prettier (TypeScript) -- NOT PythonClassBuilder or raw string concatenation.

Key module paths:
- `datrix_language.datrix_model.entity` -> Entity, Field
- `datrix_language.datrix_model.containers` -> Service, Application
- `datrix_language.datrix_model.blocks` -> RdbmsBlock, CacheBlock
- `datrix_language.datrix_model.pubsub` -> PubsubBlock, Topic, Event, Subscription
- `datrix_language.datrix_model.cqrs` -> CqrsBlock, View, Command, Query
- `datrix_language.datrix_model.api` -> RestApi, Endpoint
- `datrix_language.types` -> TypeRegistry, ScalarType, DatrixType
- `datrix_common.template_generator` -> TemplateGenerator
- `datrix_common.utils.text` -> to_snake_case, to_camel_case, to_pascal_case, to_kebab_case, to_screaming_snake_case, to_plural, to_singular, extract_simple_name
- `datrix_common.generator` -> Generator, GeneratedFile
- `datrix_common.paths` -> ServicePaths

## Files to Review Before Starting

**IMPORTANT:** All file paths in this section MUST be absolute paths (e.g., `d:\datrix\...`), never relative paths.

1. **Agent rules:** `d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md` (index with links to sub-documents)
2. **Test guidelines:** `d:\datrix\datrix-common\docs\contributing\test-guidelines\` (unit, integration, e2e — each an index with links to shared sub-documents under `shared/`)
3. **Design doc:** `{absolute-design-doc-path}` -- Section(s) {X.Y}
{4. Additional files: architecture docs, existing code, example .dtrx files relevant to this task — ALL with absolute paths}

## Files to Create

### 1. `{relative-path}` -- {Purpose}

{Detailed description of what to implement.}

```python
{Code skeleton with class/function signatures, type hints, docstrings.}
```

**Implementation notes:**
- {Specific implementation guidance}
- {Patterns to follow}
- {Edge cases to handle}

{Repeat ### N. for each file to create/modify}

## Architecture Constraints

- {Key constraint with explanation}
- {Boundary rules}
- {What NOT to do}

## Anti-Patterns to Avoid

- **Silent fallbacks:** Do NOT use `dict.get(key, None)` -- raise explicit errors instead
- **Default type mappings:** Do NOT use `type_map.get(t, "Any")` -- raise on unknown types
- **Empty exception blocks:** Do NOT use bare `except: pass` -- always log and re-raise
- **String-based code generation:** Do NOT use `code += f"class {name}:"` -- use Jinja2 templates
- **Placeholder code or stubs:** Do NOT use `# TODO` / `pass` -- implement completely
- **Returning None on errors:** Do NOT use `-> T | None` lookups -- raise descriptive errors
- **Deep inheritance chains:** Favor shallow inheritance + composition
- **Platform-specific DSLs:** Do NOT use `@AzureCosmosDB(...)` -- keep generators generic
- **Implicit or "magic" logic:** Make all behavior explicit and documented
- **Over-engineering:** Do NOT add unnecessary abstractions or feature flags
- **Workarounds:** Do NOT steer around issues or paper over them — fix the root cause or STOP and report (CLAUDE.md rule)
- **Mocks/fakes in tests:** Do NOT use `MagicMock`, `Mock`, `patch`, `SimpleNamespace`, or any fake stand-in — use real objects, `.dtrx` fixtures, and factories from `datrix_common.testing`
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

## Best Practices to Follow

- **Fail fast and loud:** `raise ExplicitError(f"message with context")`
- **Provide helpful messages:** `"Not found. Available: [...]"`
- **Use Jinja2 templates + formatter:** Jinja2 + ruff format (Python) / Prettier (TypeScript)
- **Apply full type hints:** `def foo(x: str) -> int:`
- **Use immutable models:** `ConfigDict(frozen=True)`
- **Enforce exhaustive type mappings:** raise on unknown types
- **Use standard logging with key=value format:** `logger.info("event key=%s", value)`
- **Write comprehensive tests:** include error and success cases
- **Favor shallow inheritance + traits:** e.g., `extends Base with Auditable`
- **Prefer explicit over implicit definitions**

## Success Criteria

1. {Concrete, testable outcome}
2. {Measurable quality threshold}
{... 8-15 specific criteria}
- All tests pass: `python -m pytest tests/ -q`
- >90% test coverage
- No TODO/pass/placeholder code

## Estimated Complexity

- `{file}`: ~{N} lines ({description})
{... per file}
- Tests: ~{N} lines
- Total: ~{N} lines of production code

## Targeted Tests

> **Used by the executors to run focused verification instead of the full test suite.**
> Each task runs only its targeted tests (which cover the code AND the tests this task created) to avoid redundant full-suite runs.
> The per-package quality gate runs the full suite once to catch cross-task integration issues; intra-phase orchestrator waves run targeted tests only.

**Package:** `{package-name}`
**Test command:**
```
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path-1}"
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path-2}"
```

**Test files:**
- `{test-path-1}` -- {what it covers}
- `{test-path-2}` -- {what it covers}

When generating this section:
- List the test files that the task creates or that cover the code being modified
- For tasks that create new test files, list those paths (they will exist after Step 2: Implement)
- For tasks that modify existing code without creating tests, identify existing test files that exercise the modified code
- If no targeted tests can be identified, use: `**Scope:** No targeted tests -- falls back to full suite.`

## Tests

> **MANDATORY for every implementation task.** The task that writes the code also writes its unit + integration tests, in the same task and the same wave. There is no separate `-tests` task. The `## Targeted Tests` section above must list the test files created here.

### Unit Tests — `tests/unit/{test-path}`

{Description of unit test coverage — single component, isolated.}

```python
{Complete test code with fixtures, test classes, and assertions.
Include happy path, error cases, and edge cases.
Mark with @pytest.mark.unit.}
```

### Integration Tests — `tests/integration/{test-path}` (if applicable)

{Description of integration test coverage — multi-component pipelines, full generation.}

```python
{Tests that exercise multiple components together.
Full .dtrx → parse → generate → validate all files.
Mark with @pytest.mark.integration.}
```

### E2E Tests — `tests/e2e/{test-path}` (if applicable)

{Description of E2E test coverage — full project generation, CLI workflows.}

```python
{Tests that verify the complete user-facing workflow.
CLI E2E, full project structure.
Mark with @pytest.mark.e2e.}
```
```

### Step 6: Validate Task Files

After generating all task files, verify:
1. Task numbers (`{TT}`) are unique within the phase **across all repos** — no two tasks in the same phase share a task number, even if they are in different repos
2. Task numbers are sequential (no gaps) within the phase
3. Dependencies reference valid task IDs
4. All files are placed in the correct repo's `.tasks/phase-{NN}/` directory
5. No tasks reference non-existent modules from the "Non-existent modules" list
6. Every task file starts with the agent rules perusal instruction
7. Task titles follow the `# Task {NN}-{TT}: {Title}` format
8. Every implementation task that introduces significant new code carries its OWN tests inline (a populated `## Tests` section) — NOT a separate `-tests` task. A standalone test task is allowed only for an integration/e2e suite spanning multiple implementation tasks
9. NO standalone `-verify` tasks are generated — the independent anti-stub / anti-gap / coverage checklist lives in the per-package quality gate (run by a different agent than the implementers). Confirm no task carries `**Category:** Verification`
10. Documentation updates ride inside the implementation task whose feature they document. A standalone docs task exists only for a substantial multi-task doc deliverable, and it is OUTSIDE the dependency chain (no task depends on it)
11. Every package with 2+ code tasks has exactly ONE quality gate task that depends on ALL tasks targeting that package
12. Quality gate tasks include the `**Category:** Quality Gate` marker and carry the embedded verification checklist (anti-stub, coverage sanity, anti-gap, How-Solved self-contradiction scan)
13. Every implementation task has a `## Targeted Tests` section specifying which tests to run for focused verification
14. **Migration coverage check:** Count the numbered steps in the design's migration/rollout section. Count the migration tasks generated. If the second number is less than the first, tasks are missing. Every "convert X", "migrate Y", "create Z" step needs a task.
15. **Dual-path coverage check:** If the design introduces a new path alongside an old one, verify that migration tasks exist to convert old test fixtures, examples, and configs to the new format. Without these, the new path is untested dead code.
16. **Cross-repo coverage check:** Tasks span all affected repos, not just the primary package. If the design changes `datrix-common` but examples live in `datrix`, migration tasks exist in `datrix`.
17. **Dependencies document validation:**
    - Verify the dependencies document includes ALL tasks from the phase
    - Verify each task appears in exactly one group
    - Verify group ordering respects dependencies (no task depends on a task in a later group)
    - Verify tasks within each group are truly parallelizable (no direct or transitive dependencies between them)
    - Verify file paths are absolute Windows-style paths with backslashes

### Step 7: Generate Task Dependencies Document

Create a concise dependencies document at `d:\datrix\datrix\.tasks\phase-{NN}\dependencies.md` with the following format:

```
Group 1

D:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md
D:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md

Group 2

D:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md
D:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md
D:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md

Group 3

D:\datrix\{repo}\.tasks\phase-{NN}\task-{NN}-{TT}-{slug}.md
...
```

**Format rules:**
1. Each group starts with "Group N" (no blank line before the first group)
2. Blank line after the group header
3. List absolute task file paths (Windows-style with backslashes), one per line
4. Blank line between groups (after the last task path, before the next "Group N")
5. Tasks within a group can run in parallel
6. Group ordering reflects execution order — Group 1 has no dependencies, Group 2 depends only on Group 1 tasks, etc.

**Dependency resolution algorithm:**
1. Start with all tasks that have no dependencies → Group 1
2. For each subsequent group N:
   - Include tasks whose dependencies are ALL satisfied by groups 1 through N-1
   - Tasks within the same group have no dependency chain between them (parallelizable)
3. Continue until all tasks are assigned to a group

The dependencies document provides a concise execution plan for task orchestration tools like `/task-orchestrator`.

### Step 8: Report Summary

Print a lean summary — counts + task paths + pointer to dependencies.md. Do NOT duplicate the dependency graph in console output (it is already in `dependencies.md`).

```
Phase {NN}: {N} tasks ({N} impl, {N} migration, {N} QG, {N} standalone-docs/integration if any)

{task-path}
{task-path}
...

Dependencies: datrix\.tasks\phase-{NN}\dependencies.md
```

The summary must:
1. List every task file path (absolute)
2. Be consistent with the "Depends on" field inside each task file
3. Match the groups written to the dependencies document in Step 7

## Task Completion Protocol

When an agent finishes a task, it should update the task file:
1. Change the title from `# Task {NN}-{TT}: {Title}` to `# COMPLETED: Task {NN}-{TT}: {Title}`
2. Add a `## How solved` section immediately after the title with:
   - Bullet points per file created/modified
   - Bold file names followed by implementation summary
   - Key design decisions made
   - Test coverage summary

## Task Decomposition Guidelines

### Sizing
- Each task should be completable by an AI agent in a single session
- Target 200-500 lines of production code per task
- Include test code estimates (usually 1:1 ratio with production code)
- Complex tasks should be split into sub-tasks

### Task Categories

Every phase should include tasks from these categories where applicable:

#### Implementation Tasks
The core work — new code, modifications, refactoring. These follow the standard task template defined in Step 5. **Each implementation task is self-contained: it writes the code, writes its own unit + integration tests (the `## Tests` section), and updates any docs its feature touches — all in one task, one wave.** It is independently testable via its `## Targeted Tests`. Do NOT split a task's tests or docs into separate tasks.

**Test coverage rule:** Tests live inside the implementation task that creates the code. The only standalone test task permitted is an **integration/e2e suite that genuinely spans several implementation tasks** and cannot sensibly live inside any one of them (e.g., a cross-service end-to-end fixture). When you do create one, it depends on the implementation tasks it exercises and uses the standard template focused on test files.

**Documentation rule:** Doc updates ride inside the implementation task whose feature they document — adding/updating the relevant `docs/` file is part of that task's scope. Create a **standalone docs task only** for a substantial doc deliverable that documents several tasks at once; when you do, place it **outside the dependency chain** (no task depends on it) so it runs concurrently with the package quality gate and never anchors a wave. Target the correct `docs/` folder (see Documentation Folders table below) and follow existing doc conventions.

**No standalone verification tasks.** Independent verification is preserved by the per-package **quality gate** (below), which is run by a different agent than the implementers and carries the full anti-stub / coverage-sanity / anti-gap checklist. Do NOT generate per-implementation `-verify` tasks — they multiply waves without adding coverage the gate doesn't already provide.

#### Migration Tasks
Dedicated tasks for converting existing files from the old format/API/system to the new one. Generate these when:
- The design introduces a new subsystem alongside an existing one (new format, new API, new config system)
- The design's migration/rollout/adoption section contains numbered steps calling for conversion
- Existing test fixtures, examples, or project configs exercise the OLD path and must be migrated so the NEW path is actually tested

Migration tasks should:
- Reference the implementation tasks that create the new subsystem in "Depends on"
- Live in the repo whose files they modify (not the repo where the new code lives)
- Use a title like `Task {NN}-{TT}: Migrate {X} Fixtures to {New Format}` or `Task {NN}-{TT}: Create Shared {X} Template Library`
- Include a verification step: "Confirm the new path is exercised by running X and verifying Y"
- Each migration task must state what OLD artifacts it replaces and prove the NEW path works
- Include `**Category:** Migration` in the header metadata

**Why migration tasks are critical:** Without them, the new implementation ships untested. Old tests continue to pass on the old path, creating false confidence. If you build a new config parser but all test fixtures are still YAML, the new parser is dead code — it compiles but nothing exercises it end-to-end.

**Dual-path guard:** Every migration task must include a check that the migrated artifact actually goes through the NEW code path. For example: "Parse this `.dcfg` file and verify the canonical dict matches the expected output" — not just "file exists."

#### Quality Gate Tasks
The single per-package gate that both runs the full suite AND carries the independent verification checklist (the role standalone `-verify` tasks used to play). Generate **exactly one** per package that has 2+ code tasks in the phase. Generate these when:
- A phase includes 2+ implementation tasks targeting the same package
- The full test suite is needed to catch cross-task integration issues across those tasks

**When NOT to generate a quality gate task:**
- When a package has only 1 code task in the phase (that task's own targeted tests + the executor's gate are sufficient)

Quality gate tasks should:
- Be the LAST task in the dependency graph for their package (depend on ALL tasks targeting that package)
- **Be run by a different agent/session than the implementers** — this is what preserves independent verification now that per-task `-verify` tasks are gone
- Have a title like `Task {NN}-{TT}: Quality Gate -- {package-name}` and a slug like `quality-gate-{package-name}`
- NOT contain any implementation code, new tests, or "Files to Create" section
- Include `**Category:** Quality Gate` in the header metadata
- Carry the embedded verification checklist below (static scans + coverage sanity + anti-gap), in addition to the full-suite run

> **Note for orchestrated runs:** `/task-orchestrator`, `/execute-tasks`, and `/execute-tasks-parallel` run the package's full suite themselves as the authoritative gate and **suppress the gate task's own `test.ps1` run** to avoid a duplicate. In those runs the gate agent performs ONLY the static/coverage checklist; the executor owns the pass/fail test verdict.

Quality gate task template:

```markdown
> **Peruse 'd:\datrix\datrix-common\docs\contributing\ai-agent-rules.md' (and its sub-documents) and follow the rules**

# Task {NN}-{TT}: Quality Gate -- {package-name}

## Overview

Final independent verification pass for {package-name}, run by a different agent than the implementers. Runs the full test suite and the anti-stub / coverage / anti-gap checklist to ensure all implementation tasks in this phase integrate correctly and contain real, tested implementation.

**Package:** `{package-name}` (`d:\datrix\{repo}\`)
**Depends on:** {comma-separated list of ALL tasks targeting this package}
**Category:** Quality Gate

## Verification Steps

1. Run full test suite (skip if the orchestrator/executor runs it as the authoritative gate — see note above):
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

2. **Non-trivial-implementation scan** of all files created/modified by this phase's tasks:
   - File has >10 lines of non-comment, non-import code where a real implementation is expected
   - No `pass` in function/method bodies, no `# TODO` / `# FIXME`, no `NotImplementedError` in production code
   - No always-true/always-false validators or checkers (a check that does nothing)
   - No legacy code paths that should have been deleted per task requirements; no dual (old + new) paths where a task required full migration

3. **Coverage & test-quality sanity** for this phase's changes:
   - At least one test per new public class/function; both success and error cases; real objects (no mocks/fakes)
   - No test asserts `NotImplementedError` / `NotImplemented` on a production path (gap-codification)
   - For any "X replaces Y" task: a test proves X works AND no test relies on Y still existing
   - For any validator/checker: at least one test fails when the check is removed

4. **How-Solved self-contradiction scan** — read each COMPLETED task's "How Solved" and flag any containing: "remains unchanged", "legacy", "future migration", "not yet wired", "partial", "workaround", "dual path".

5. If any failures: investigate, classify as task-specific regression or pre-existing, report (identify which implementation task needs rework).

## Success Criteria

1. Full test suite passes (or only pre-existing failures remain)
2. No stub/placeholder/`NotImplementedError`/`pass`/TODO in production code introduced by this phase
3. No always-true checks, legacy paths, or dual paths where a task required replacement
4. Tests exercise real behavior (no gap-codification); "X replaces Y" tasks prove Y is gone
5. No self-contradictory "How Solved" sections in completed tasks

## Targeted Tests

**Package:** `{package-name}`
**Test command:**
```
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
```
**Scope:** Full suite (quality gate)
```

### Documentation Folders

Discover documentation folders dynamically — do NOT rely on a hardcoded list. Run:

```bash
ls -d d:/datrix/datrix*/docs/ 2>/dev/null
```

This finds every `docs/` folder across all Datrix repositories. Use the results to:
1. Map each affected repository to its `docs/` folder
2. Determine which docs already exist (read the folder contents before creating tasks)
3. Target the correct folder in documentation tasks

When creating documentation tasks, **read the existing docs** in the target folder first to understand the conventions, structure, and what already exists. Do not duplicate existing content — update it.

### Ordering
- Infrastructure/framework tasks come first (base classes, utilities)
- Feature tasks build on infrastructure (specific generators, handlers) — each carries its own tests and doc updates
- A standalone integration/e2e task (only when it spans multiple impl tasks) comes after the implementation tasks it exercises
- A standalone docs task (only when substantial/multi-task) sits OUTSIDE the dependency chain — nothing depends on it
- Quality gate tasks come LAST — after ALL implementation and migration tasks for their package
- Tasks within a phase can be parallelized if they share no dependencies

### Repository Assignment
- Tasks go in the `.tasks/` folder of the repository they modify
- If a task spans multiple repos, create separate tasks per repo with cross-references
- Common framework and core code: `datrix-common/.tasks/`
- Target-specific code: `datrix-codegen-{target}/.tasks/`
- Parser/model changes: `datrix-language/.tasks/`
- CLI changes: `datrix-cli/.tasks/`

### Example Files to Reference

When creating tasks, point agents to relevant example `.dtrx` files:

| Task Topic | Example Files |
|---|---|
| Entity/field generation | `examples/01-foundation/`, `examples/02-features/01-core-data-modeling/entities/` |
| Enum generation | `examples/02-features/01-core-data-modeling/enums/` |
| REST API generation | `examples/02-features/01-core-data-modeling/rest-api/` |
| Validation/rules | `examples/02-features/01-core-data-modeling/validation/` |
| Relationships | `examples/02-features/01-core-data-modeling/relationships/` |
| Events/pubsub | `examples/02-features/02-service-architecture/pubsub/` |
| Cache | `examples/02-features/03-infrastructure-blocks/cache/` |
| CQRS | `examples/02-features/03-infrastructure-blocks/cqrs/` |
| Background jobs | `examples/02-features/03-infrastructure-blocks/jobs/` |
| Service dependencies | `examples/02-features/02-service-architecture/multi-service/` |
| Domain models | `examples/03-domains/ecommerce/`, `examples/03-domains/blog-cms/` |

### Documentation to Reference

| Task Topic | Documentation Files |
|---|---|
| All tasks | `d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md` (index with sub-documents under `ai-agent-rules/`) |
| Unit tests | `d:\datrix\datrix-common\docs\contributing\test-guidelines\unit-test-guidelines.md` (index with sub-documents under `shared/`) |
| Integration tests | `d:\datrix\datrix-common\docs\contributing\test-guidelines\integration-test-guidelines.md` (index with sub-documents under `shared/`) |
| E2E tests | `d:\datrix\datrix-common\docs\contributing\test-guidelines\e2e-test-guidelines.md` |
| Parser/AST | `d:\datrix\datrix-language\docs\datrix-language-api.md` |
| Grammar | `d:\datrix\datrix-language\docs\reference\datrix-grammar.md` |
| AST nodes | `d:\datrix\datrix-language\docs\reference\datrix-ast-nodes.md` |
| Type system | `d:\datrix\datrix-language\docs\reference\datrix-type-registry.md` |
| Built-ins | `d:\datrix\datrix-language\docs\reference\datrix-builtins.md` |
| Decorators | `d:\datrix\datrix-language\docs\reference\datrix-decorators.md` |
| Validators | `d:\datrix\datrix-language\docs\reference\datrix-validators.md` |
| Code generation | `d:\datrix\datrix-common\docs\architecture\code-generation.md` |
| Generator API | `d:\datrix\datrix-common\docs\generators-api.md` |
| Syntax reference | `d:\datrix\datrix-language\docs\reference\datrix-syntax-reference.md` |

## Important Rules

1. **Tasks MUST be created inside the `.tasks/` folder of the project they belong to** — never under `d:\datrix\.tasks\` or `d:\datrix\datrix\.tasks\`
2. **Do NOT generate summary documents** — only task files
3. **Every task file MUST start with the agent rules perusal instruction**
4. **Task title format is strict:** `# Task {NN}-{TT}: {Title}` — scripts detect the "Task " prefix
5. **Include complete code skeletons** — not outlines or pseudocode
6. **Include complete test code** — agents should be able to run tests immediately
7. **Reference specific design document sections** — not just the whole document
8. **Reference specific example files** — not just "look at examples"
9. **All module paths must be valid** — check against the canonical and non-existent module lists
10. **ALL file paths in generated task files MUST be absolute paths** — use `d:\datrix\...` format, never relative paths like `docs/...` or `examples/...`
11. **Migration steps are tasks, not aspirations.** If the design's migration section says "convert X to Y", generate a task for it. Do not defer migration to "future work" unless the design explicitly says so.
12. **Tasks span all affected repos.** Do not limit task generation to a single package. If the design changes `datrix-common` but examples live in `datrix` and project configs live in `datrix-projects`, generate tasks in all three repos.
13. **No untested new paths.** If the design introduces a new subsystem alongside an old one, generate migration tasks that convert existing test fixtures, examples, and configs to use the new path. Without these, the new code compiles but nothing exercises it end-to-end.
14. **No bloated outputs.** dependencies.md contains group numbers and absolute paths only — no headers, tables, or prose. Console summaries are data-dense one-liners — no dependency graphs (already in dependencies.md), no "Next steps", no category breakdowns.
