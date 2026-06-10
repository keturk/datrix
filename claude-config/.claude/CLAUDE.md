# Claude Code Rules for Datrix

**Address user as Jon:** Always address the user as "Jon" in every reply.

**On-demand skills:** `/imports`, `/logic-map`, `/fix`, `/fix-issue`, `/fix-bug-report`, `/codegen-review`, `/fix-tests`, `/scope`, `/checkpoint-debug`, `/troubleshoot-and-fix`, `/codegen-fix-loop`, `/operationalize-design`, `/execute-tasks`, `/execute-tasks-parallel`, `/task-orchestrator`, `/absorb-design`, `/commit-and-push`, `/evaluate-generated`, `/evaluate-generated-service`, `/fix-cli`, `/fix-common`, `/fix-extensions`, `/fix-language`, `/fix-codegen-{aws,azure,common,component,docker,k8s,python,sql,typescript}`.

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

## Task Orchestration

**Task completion script:** Always use `complete.ps1` to mark a task as COMPLETED. Never edit the task heading directly (Edit/Write bypass the validation hook that `complete.ps1` enforces). Read `datrix/scripts/tasks/quick-reference.md` for the exact invocation syntax before calling any task script.

**Completion timing in orchestrator runs:** In `/task-orchestrator` and `/execute-tasks-parallel` runs, mark a task COMPLETED only after the **wave's full test gate passes** (per-package tests for that wave). Do not mark tasks COMPLETED as individual agents return — agent success is necessary but not sufficient.

**Pipeline skills and optional deps:** In pipeline skills like `/operationalize-design`, when an optional dependency is absent but the pipeline can still produce its core deliverable, take the graceful-degradation path, note the degradation in the summary, and continue. Do not halt with an AskUserQuestion gate for missing optional validators. STOP only for genuinely blocking conditions (unresolved required decisions, missing required inputs, technical impossibility).

**Single-service verification:** Do not run `generate.ps1` on the full curvaero-backend system to verify a single-service change. Limit generation to the affected service only.

## Design Doc Workflow

Docs in `design/` numbered by priority. Read full doc + cross-ref architecture before implementing. Design docs are scope boundaries — don't add unspecified features. Operationalize before coding: `/operationalize-design`. Absorb after completion (`/absorb-design`). Never modify design docs during implementation.

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

## No Workarounds

This is production software. When you encounter an issue, fix it properly. Do not steer around it. Do not sweep it under the rug. No band-aid patches, no "good enough for now", no conditional guards that hide a broken code path. If something is wrong, trace it to the root cause and fix it there. If the root cause is outside your current scope, STOP and report it — do not paper over it with a workaround that lets the build pass while the underlying problem festers. A workaround is technical debt with interest.

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
