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

## Workflow

When invoked, follow these steps:

### Step 1: Read and Understand the Design Document

1. Read the design document completely
2. Identify implementation phases (look for "Implementation Phases", "Phases", or numbered phase sections)
3. Map each phase item to the correct target repository based on the package it references
4. Identify dependencies between tasks
5. Identify test coverage needs — which new modules, classes, or pipelines require dedicated test tasks
6. Identify documentation impacts — which docs need to be created or updated in the affected packages' `docs/` folders
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

> **Used by `/execute-tasks` Step 3 to run focused verification instead of the full test suite.**
> When tasks run in parallel, each task runs only its targeted tests to avoid redundant full-suite runs.
> A quality gate task at the end runs the full suite to catch cross-task integration issues.

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
8. Every implementation task that introduces significant new code has a corresponding test task (or justification for why inline tests suffice)
9. Every implementation task (or group of 2-3 related implementation tasks) has a corresponding verification task with `**Category:** Verification`
10. Documentation tasks exist for any new user-facing features, APIs, or architectural changes — targeting the correct `docs/` folder per the Documentation Folders table
11. Every package with 2+ code tasks has a quality gate task that depends on ALL tasks targeting that package
12. Quality gate tasks include the `**Category:** Quality Gate` marker in their header metadata
13. Every implementation and test task has a `## Targeted Tests` section specifying which tests to run for focused verification
14. **Migration coverage check:** Count the numbered steps in the design's migration/rollout section. Count the migration tasks generated. If the second number is less than the first, tasks are missing. Every "convert X", "migrate Y", "create Z" step needs a task.
15. **Dual-path coverage check:** If the design introduces a new path alongside an old one, verify that migration tasks exist to convert old test fixtures, examples, and configs to the new format. Without these, the new path is untested dead code.
16. **Cross-repo coverage check:** Tasks span all affected repos, not just the primary package. If the design changes `datrix-common` but examples live in `datrix`, migration tasks exist in `datrix`.

### Step 7: Report Summary and Dependency Graph

Print a summary table (grouped by category) followed by a dependency graph:

```
Phase {NN} — {Phase Title}

  Implementation:
    {repo}/.tasks/phase-{NN}/task-{NN}-{TT}-{slug}.md — {Title}
    {repo}/.tasks/phase-{NN}/task-{NN}-{TT}-{slug}.md — {Title}

  Tests:
    {repo}/.tasks/phase-{NN}/task-{NN}-{TT}-{slug}.md — {Title}

  Verification:
    {repo}/.tasks/phase-{NN}/task-{NN}-{TT}-verify-{slug}.md — Verify {Feature} Implementation

  Documentation:
    {repo}/.tasks/phase-{NN}/task-{NN}-{TT}-{slug}.md — {Title}

  Quality Gates:
    {repo}/.tasks/phase-{NN}/task-{NN}-{TT}-quality-gate-{package}.md — Quality Gate -- {package-name}

Task Dependencies:
  {NN}-{TT} {Title}
    └── depends on: (none — can start immediately)
  {NN}-{TT} {Title}
    └── depends on: {NN}-{TT}
  {NN}-{TT} {Title}
    └── depends on: {NN}-{TT}, {NN}-{TT}
  {NN}-{TT} Quality Gate -- {package-name}
    └── depends on: {NN}-{TT}, {NN}-{TT}, {NN}-{TT}  (all {package} tasks)
  ...

Parallelizable groups (tasks within a group can run concurrently):
  Group 1: {NN}-{TT}, {NN}-{TT}          (no dependencies — implementation)
  Group 2: {NN}-{TT}, {NN}-{TT}          (after Group 1 — tests)
  Group 3: {NN}-{TT}, {NN}-{TT}          (after Group 2 — verification, by different agent)
  Group 4: {NN}-{TT}                      (after Group 3 — docs)
  Group 5: {NN}-{TT}, {NN}-{TT}          (after all package tasks — quality gates)
```

The dependency graph must:
1. List every task with its direct dependencies
2. Identify which tasks can run in parallel (share no dependency chain)
3. Present parallelizable groups in execution order — Group 1 has no dependencies, Group 2 depends only on Group 1 tasks, etc.
4. Be consistent with the "Depends on" field inside each task file

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
The core work — new code, modifications, refactoring. These follow the standard task template defined in Step 5.

#### Test Tasks
Dedicated tasks for adding or updating test coverage. Generate these when:
- The implementation introduces new modules, classes, or significant logic that warrants standalone test tasks
- Integration or E2E tests span multiple implementation tasks and are better as their own task
- Existing test coverage needs to be updated or expanded due to the changes

Test tasks should:
- Reference the implementation tasks they cover in "Depends on"
- Specify the test level (unit, integration, e2e) in the title — e.g., `Task {NN}-{TT}: Unit Tests for TypeResolver`
- Include complete test code following the test guidelines
- List test files to create/modify under "Files to Create"
- Use the same task file template as implementation tasks but focus the "Files to Create" section on test files

**Note:** Implementation tasks may still include a lightweight "Tests" section for basic smoke tests. Test tasks provide the comprehensive coverage.

#### Documentation Tasks
Dedicated tasks for adding or updating documentation. Generate these when:
- The implementation introduces new concepts, APIs, patterns, or user-facing features
- Existing documentation becomes outdated or inaccurate due to changes
- New reference docs, guides, or architecture docs are needed

Documentation tasks should:
- Reference the implementation tasks they document in "Depends on"
- Use a title like `Task {NN}-{TT}: Document {Feature} API` or `Task {NN}-{TT}: Update Code Generation Docs`
- Target the `docs/` folder of the relevant package (see Documentation Folders table below)
- Specify which doc files to create or update under "Files to Create"
- Include the content outline or draft for each documentation file
- Follow existing documentation conventions in the target `docs/` folder

#### Verification Tasks
Independent verification tasks that confirm implementation tasks were actually completed — not just marked complete. These are executed by a **different agent session** than the one that implemented the code. Generate one verification task per implementation task (or per logical group of 2-3 closely related implementation tasks).

Verification tasks should:
- **Be assigned to a different agent than the implementer** — this is the core purpose
- Depend on the corresponding implementation task(s) AND their test task(s)
- Have a title like `Task {NN}-{TT}: Verify {Feature} Implementation`
- Have a slug with a `-verify` suffix (e.g., `task-{NN}-{TT}-verify-gendsl-parser.md`)
- Include `**Category:** Verification` in the header metadata
- NOT contain any implementation code or new tests
- Specify concrete checks (see template below)

Verification task template:

```markdown
> **Peruse 'd:\datrix\datrix-common\docs\contributing\ai-agent-rules.md' (and its sub-documents) and follow the rules**

# Task {NN}-{TT}: Verify {Feature} Implementation

## Overview

Independent verification that {implementation task(s)} were completed correctly. This task is executed by a different agent than the implementer.

**Package:** `{package-name}` (`d:\datrix\{repo}\`)
**Depends on:** {implementation task ID}, {test task ID}
**Category:** Verification

## Verification Checklist

### 1. File Existence
Confirm every file listed in the implementation task's "Files to Create" section exists on disk:
{list each expected file path}

### 2. Non-Trivial Implementation
For each created file, confirm it contains real implementation (not stubs):
- File has >10 lines of non-comment, non-import code
- No `pass` statements in function/method bodies
- No `# TODO` or `# FIXME` markers
- No `NotImplementedError` raises in production code
- Classes/functions have actual logic, not just signatures

### 3. Test Execution
Run the targeted tests and capture raw output:
```
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path}"
```

### 4. Test Coverage Sanity
Confirm tests exercise the implementation (not just import it):
- At least one test per public class/function
- Tests include both success and error cases
- Tests use real objects (no mocks/fakes)

### 5. Test Quality (anti-gap-codification)
Confirm tests prove the feature works, not that it's broken:
- No tests that assert `NotImplementedError` or `NotImplemented` on production code paths
- No tests that only verify shallow behavior while core logic is untested
- If the task requires "X replaces Y", verify tests prove X works AND no test relies on Y still being present
- If the task implements a validator/checker, verify at least one test fails when the check is removed (i.e., the check actually does something)

## Success Criteria

1. All files from implementation task exist
2. No stub/placeholder code detected
3. All targeted tests pass
4. Tests exercise actual implementation logic
5. No tests that codify gaps (asserting NotImplementedError on production paths)

## Evidence Required

Paste the following raw output into "How Solved":
- `pytest` output (full, including test names and pass/fail)
- For each file: first 5 lines + line count confirming non-trivial content
```

**When to group verification tasks:** If 2-3 implementation tasks are closely related (e.g., parser + parser tests for the same module), they can share one verification task. Do NOT group more than 3 implementation tasks into one verification task.

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
Dedicated tasks that run the full test suite for a package as a final verification pass. Generate these when:
- A phase includes 2+ code tasks (implementation + test combined) targeting the same package
- The tasks can run in parallel (and would therefore trigger redundant full-suite runs)
- The full test suite is needed to catch cross-task integration issues

**When NOT to generate quality gate tasks:**
- When a package has only 1 code task in the phase (the task's own verification is sufficient)
- When all tasks in a package must run strictly sequentially (no parallel redundancy)

Quality gate tasks should:
- Be the LAST tasks in the dependency graph for their package
- Depend on ALL implementation, test, and documentation tasks targeting the same package
- Have a title like `Task {NN}-{TT}: Quality Gate -- {package-name}`
- Have a slug like `quality-gate-{package-name}`
- NOT contain any implementation code, new tests, or "Files to Create" section
- Include `**Category:** Quality Gate` in the header metadata
- Run the full test suite as their sole verification step

Quality gate task template:

```markdown
> **Peruse 'd:\datrix\datrix-common\docs\contributing\ai-agent-rules.md' (and its sub-documents) and follow the rules**

# Task {NN}-{TT}: Quality Gate -- {package-name}

## Overview

Final verification pass for {package-name}. Runs the full test suite and behavioral checks to ensure all implementation and test tasks in this phase integrate correctly.

**Package:** `{package-name}` (`d:\datrix\{repo}\`)
**Depends on:** {comma-separated list of ALL tasks targeting this package}
**Category:** Quality Gate

## Verification Steps

1. Run full test suite:
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}
   ```

2. Scan for completion red flags in all files created/modified by this phase's tasks:
   - `NotImplementedError` in production code (not test code)
   - `# TODO` / `# FIXME` / `pass` in function bodies
   - Always-true/always-false validators or checkers
   - Legacy code paths that should have been deleted per task requirements
   - Dual paths (old + new) where tasks required full migration

3. Verify each task's "How Solved" section does not self-contradict:
   - Read each COMPLETED task's "How Solved" narrative
   - Flag any containing: "remains unchanged", "legacy", "future migration", "not yet wired", "partial", "workaround", "dual path"

4. If any failures: investigate, classify as task-specific regression or pre-existing, report.

## Success Criteria

1. Full test suite passes (or only pre-existing failures remain)
2. No TODO/pass/placeholder/NotImplementedError in production code introduced by this phase's tasks
3. No self-contradictory "How Solved" sections in completed tasks
4. No dual code paths where tasks required migration

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
- Feature tasks build on infrastructure (specific generators, handlers)
- Test tasks follow their corresponding implementation tasks
- Verification tasks follow their corresponding implementation + test tasks
- Documentation tasks come after the implementation tasks they document
- Integration/testing tasks come after unit test tasks (end-to-end, CLI, multi-target)
- Quality gate tasks come LAST — after ALL implementation, test, verification, and documentation tasks for their package
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
