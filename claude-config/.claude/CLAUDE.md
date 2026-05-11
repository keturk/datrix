# Claude Code Rules for Datrix

**On-demand skills:** `/imports` (module paths), `/logic-map` (markers), `/fix` (phased fix workflow), `/codegen-review` (submission checklist + repo rules + code examples), `/fix-tests` (one-at-a-time test fix workflow), `/scope` (session scope anchor), `/checkpoint-debug` (checkpoint-based multi-bug debugging), `/troubleshoot-and-fix` (autonomous diagnose→fix→verify pipeline), `/codegen-fix-loop` (iterative fix with test feedback), `/operationalize-design` (design doc to tasks+docs pipeline), `/operationalize-design-v2` (design doc to tasks+docs with Task Review System validation), `/execute-tasks` (implement task files with verify+complete loop), `/execute-tasks-parallel` (parallel execution of independent tasks), `/absorb-design` (transfer design doc knowledge into repo docs + delete source), `/commit-and-push` (scan repos, build commit messages, commit and push).

## Core Principles

- **Own every issue.** If we see a bug, we fix it. No blame-shifting. Scope note: when *reviewing*, only flag issues within the task's stated scope.
- **Never assume, never fabricate.** Look it up: category-specific `quick-reference.md` under `datrix/scripts/{category}/` for scripts, grammar for DSL, source for APIs.
- **No GitHub Actions.** Not used in this project.
- **No backward compatibility.** Delete old code, don't wrap it. One way to do each thing.
- **Editor context.** Do not act on the open editor file unless explicitly mentioned.

## STOP AND THINK

Before touching code: read all relevant code, trace root cause, understand full impact, design the fix, ask if uncertain. One correct fix > five quick patches.

## Investigation & Debugging Discipline

- **Read before hypothesizing.** When investigating bugs or unfamiliar code, ALWAYS read the relevant build scripts, generation scripts, and existing code BEFORE forming hypotheses. Never fabricate assumptions about what code does — read it first.
- **Confirm language/generator scope.** This is a polyglot project with Python AND TypeScript generators. Confirm which language/generator is relevant BEFORE making changes. Do NOT generate Python fixes for TypeScript issues or vice versa.
- **No debug scatter.** Do NOT scatter debug/logging statements throughout the codebase. If temporary debug code is needed, track every insertion and remove it all before completing the task. Never leave debug artifacts that break builds.
- **Investigate before asking.** Do your own codebase research FIRST before asking clarifying questions. Come with findings, not just questions.
- **Don't repeat acknowledged info.** When the user says 'OK' or acknowledges a summary, proceed to the next action. Do not repeat or re-summarize.
- **Fix root causes, not symptoms.** Prefer removing the root cause (e.g., removing dual naming/aliases) over adding workarounds. Ask: does this fix eliminate the problem or just paper over it?

## Task Scope Back-Off

If a task spans 3+ unrelated subsystems, requires chain-debugging, or would fill the context window — STOP and propose a split into smaller tasks. Don't silently attempt massive tasks.

## Fix Execution Discipline

Follow the phased approach: Understand → Fix → Verify. Invoke `/fix` for the full workflow reference. Key rules:

- **Issue reports with Root Cause Analysis:** If the issue includes a "Recommended Fix" section, implement that approach first. Don't rediscover what's already documented. If the recommendation is unclear (e.g., "in spec test context" without obvious flags), STOP and ASK before investigating alternatives.
- **STOP and report when not confident.** Don't spend tool calls investigating — ask for direction.
- **STOP on new test failures.** Present options, don't immediately attempt fix.
- **STOP when scope grows beyond estimate.** Report growth, get approval to continue.

## Design Doc Workflow

Design docs live in `design/` numbered by priority (e.g., `01-core.md`, `09-workflow.md`).

- **Read first.** Before implementing a design doc: read the FULL doc, cross-reference architecture docs, and understand dependencies on other designs.
- **Scope boundary.** Design docs define WHAT to build and WHY — they are scope boundaries. Do not add features the design doc does not specify.
- **Operationalize before coding.** Convert a design doc into actionable task files before writing code. Track implementation progress in task files, not in the design doc.
  - **Use `/operationalize-design-v2`** for production-bound designs (default) — integrates Task Review System (Tier 1 local LLM + optional Tier 2 Codex) to validate tasks before execution. Adds ~5-15 minutes but catches defects early.
  - **Use `/operationalize-design`** for rapid prototyping or when review system unavailable — generates tasks without validation.
- **Absorb after completion.** After all tasks are complete, use `/absorb-design` to transfer the design doc's knowledge into permanent repo docs and delete the design doc. Design docs are transient — they guide implementation, then get absorbed and deleted.
- **Never modify during implementation.** If the design needs changes, discuss first — do not silently edit the design doc while implementing it.

## Logic Map

Query `d:/datrix/.logic-map/markers.db` before implementing significant new logic. Invoke `/logic-map` for syntax, queries, and scripts.

## Architecture

- Pipeline: `.dtrx → TreeSitterParser + Transformers → Application (validated AST) → Generators` — no IR layer.
- Cheat sheets: `datrix/docs/architecture/architecture-cheat-sheet.md`, `design-principles-cheat-sheet.md`
- Scripts: `datrix/scripts/quick-reference.md` (index) → category files under `test/`, `dev/`, `git/`, `metrics/`, `visualize/`, `tasks/`
- Full docs: `datrix/docs/architecture/architecture-overview.md` (index → sub-docs: `architecture/pipeline-and-capabilities.md`, `architecture/repository-architecture.md`, `architecture/builtin-traits-enums.md`), `design-principles.md`
- Agent rules: `datrix-common/docs/contributing/ai-agent-rules.md` (index → sub-docs: `ai-agent-rules/prohibited-patterns.md`, `ai-agent-rules/code-quality-standards.md`, `ai-agent-rules/repo-specific-rules.md`, `ai-agent-rules/canonical-imports.md`)
- Test guidelines: `datrix-common/docs/contributing/test-guidelines/` (unit + integration index files → shared sub-docs: `shared/test-utilities-and-fixtures.md`, `shared/assertion-anti-patterns.md`, `shared/repo-specific-testing.md`, `shared/repo-specific-integration.md`)

## Code Standards

- **Type hints** on all functions. `mypy --strict` must pass.
- **No `Any`** — use real types, `Protocol`, `TypeVar`, or `Union`. Exception: Pydantic `@model_validator(mode="before")` `data` parameter.
- **Logging:** standard `logging` (NOT structlog), `logger = logging.getLogger(__name__)`, %-style formatting.
- **Cognitive complexity** ≤15. Max 3 nesting levels. Early returns.
- **DRY** — search for existing functions before writing new code.
- **No magic constants** — named constants only.
- **Error messages** must include: what went wrong, what was expected, valid options, fix suggestions.
- **Testing:** real objects only. NO `unittest.mock`, `SimpleNamespace`, or fake objects. Test output, validate syntax, test error cases. Guidelines: `datrix-common/docs/contributing/test-guidelines/`

## Anti-Patterns

No placeholders/TODOs. No silent fallbacks (`dict.get(key, None)`). No default type mappings (`get(t, "Any")`). No `except: pass`. No raw string concatenation for code. No `T | None` error returns. No deep inheritance. No platform-specific DSLs. No implicit/magic logic. No mechanical grep-and-replace (fix root cause). No unverified answers. No SQLite in generated code.

## Project Domain Isolation

Customer/project-specific domain language MUST NOT appear in any framework package (datrix, datrix-cli, datrix-codegen-*, datrix-common, datrix-extensions, datrix-language). This applies to code, tests, docs, examples, and comments.

**CurvAero prohibited terms** (never use in framework packages):
- aviation, airport, runway, airspace, navaid, taxiway, waypoint (in aviation context)
- curvaero, CurvAero
- AIRAC, NASR, TFR, NOTAM
- Any CurvAero service name (AviationDataService, AirspaceService, ObstacleService, etc.)

**For framework docs/tests/examples:** use neutral e-commerce domain (Product, Order, Customer, Warehouse, Variant, LineItem) or invent a fictional domain unrelated to any customer project.

## Cannot Complete?

Report with blockers and questions instead of submitting pretend code.

## Before Submitting

Invoke `/codegen-review` for the full checklist.
