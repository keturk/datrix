# Claude Code Rules for Datrix

**On-demand skills:** `/imports`, `/logic-map`, `/fix`, `/fix-issue`, `/codegen-review`, `/fix-tests`, `/scope`, `/checkpoint-debug`, `/troubleshoot-and-fix`, `/codegen-fix-loop`, `/operationalize-design`, `/operationalize-design-v2`, `/execute-tasks`, `/execute-tasks-parallel`, `/absorb-design`, `/commit-and-push`, `/evaluate-generated`, `/evaluate-generated-service`, `/fix-cli`, `/fix-common`, `/fix-extensions`, `/fix-language`, `/fix-codegen-{aws,azure,common,component,docker,k8s,python,sql,typescript}`.

## Core Principles

- Own every issue (when reviewing, stay in task scope). Never assume/fabricate — look it up.
- No GitHub Actions. No backward compat (delete old code). Editor context: don't act on open file unless mentioned.
- **No git reverts.** Never use `git checkout`, `git restore`, `git reset`, `git stash`, `git revert`, or any variant to revert or discard changes. The agent does not know how many prior tasks have modified working tree files — reverting may destroy uncommitted work. Undo your own edits manually.

## Temporary File Policy

**Never create temporary files in arbitrary locations.** No test logs, scratch scripts, result dumps, or temp files anywhere in the repo tree outside the designated folders. These stray files end up committed and pushed — this is banned.

| Purpose | Location |
|---|---|
| Temporary scripts (runners, one-off helpers) | `D:\datrix\.scripts\` |
| Test output / result logs | `D:\datrix\.test-output\` |
| All other temp / scratch files | `D:\datrix\.tmp\` |

These folders are cleared regularly — never store anything important in them. Create the folder if it doesn't exist. If a tool or command defaults to writing output elsewhere, redirect it to the appropriate folder above.

## STOP AND THINK

Before touching code: read all relevant code, trace root cause, understand full impact, design the fix, ask if uncertain. One correct fix > five quick patches.

## Investigation & Debugging

Read before hypothesizing (build scripts, generators, existing code). Confirm Python vs TypeScript generator scope before changes. No debug scatter (track+remove all temp logging). Investigate before asking — come with findings. Don't repeat acknowledged info. Fix root causes not symptoms.

## Task Scope Back-Off

If a task spans 3+ unrelated subsystems, requires chain-debugging, or would fill context — STOP and propose splitting. Don't silently attempt massive tasks.

## Fix Execution

Understand→Fix→Verify (`/fix` for full workflow). Implement "Recommended Fix" from issue reports first. STOP+report when: not confident, new test failures appear, scope grows beyond estimate.

## Design Doc Workflow

Docs in `design/` numbered by priority. Read full doc + cross-ref architecture before implementing. Design docs are scope boundaries — don't add unspecified features. Operationalize before coding: `/operationalize-design-v2` (production, with review) or `/operationalize-design` (rapid). Absorb after completion (`/absorb-design`). Never modify design docs during implementation.

## Logic Map

Query `d:/datrix/.logic-map/markers.db` before implementing significant new logic. `/logic-map` for syntax.

## Architecture

- Pipeline: `.dtrx → TreeSitterParser + Transformers → Application (validated AST) → Generators` — no IR layer.
- Cheat sheets: `datrix/docs/architecture/architecture-cheat-sheet.md`, `design-principles-cheat-sheet.md`
- Scripts: `datrix/scripts/quick-reference.md` (index) → category files under `test/`, `dev/`, `git/`, `metrics/`, `visualize/`, `tasks/`
- Full docs: `datrix/docs/architecture/architecture-overview.md` (index → sub-docs: `pipeline-and-capabilities.md`, `repository-architecture.md`, `builtin-traits-enums.md`), `design-principles.md`
- Agent rules: `datrix-common/docs/contributing/ai-agent-rules.md` (index → sub-docs: `prohibited-patterns.md`, `code-quality-standards.md`, `repo-specific-rules.md`, `canonical-imports.md`)
- Test guidelines: `datrix-common/docs/contributing/test-guidelines/` (unit + integration index → shared sub-docs)

## Code Standards

Type hints on all fns; `mypy --strict` must pass. No `Any` (exception: Pydantic `@model_validator(mode="before")` data param). Logging: `logging.getLogger(__name__)`, %-style. Cognitive complexity ≤15; max 3 nesting; early returns. DRY — search existing fns first. Named constants only. Error msgs: what went wrong + expected + valid options + fix suggestion. Testing: real objects only, no `unittest.mock`/`SimpleNamespace`/fakes; guidelines in `datrix-common/docs/contributing/test-guidelines/`.

## Anti-Patterns

No placeholders/TODOs. No silent fallbacks (`dict.get(key, None)`). No default type mappings (`get(t, "Any")`). No `except: pass`. No raw string concat for code. No `T | None` error returns. No deep inheritance. No platform-specific DSLs. No implicit/magic logic. No mechanical grep-and-replace. No unverified answers. No SQLite in generated code.

## Project Domain Isolation

Customer/project domain language MUST NOT appear in framework packages (datrix, datrix-cli, datrix-codegen-*, datrix-common, datrix-extensions, datrix-language).

**CurvAero prohibited terms:** aviation, airport, runway, airspace, navaid, taxiway, waypoint (aviation context), curvaero/CurvAero, AIRAC, NASR, TFR, NOTAM, any CurvAero service name.

**Framework docs/tests/examples:** use neutral e-commerce domain (Product, Order, Customer, Warehouse, Variant, LineItem) or fictional domain.

## Cannot Complete?

Report with blockers and questions instead of submitting pretend code.

## Before Submitting

Invoke `/codegen-review` for the full checklist.
