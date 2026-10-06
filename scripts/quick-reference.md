# Quick Reference for AI Agents

Fast lookup guide for finding the right script for common tasks. Each script category has its own detailed reference — read only the one you need.

## Bash Shell Invocation (CRITICAL)

AI agents run in a **bash** shell, not PowerShell. All examples below use PowerShell-native syntax (e.g., `.\test\test.ps1`). To run them from bash:

1. **Prefix with** `powershell -File`
2. **Use forward slashes** in all paths (never `\\`)
3. **Quote the script path**

**Conversion pattern:**

| PowerShell (in docs) | Bash (what you run) |
|---|---|
| `.\test\test.ps1 datrix-common` | `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common` |
| `.\dev\generate.ps1 -All -L python` | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -All -L python` |
| `.\metrics\complexity.ps1 datrix-common` | `powershell -File "d:/datrix/datrix/scripts/metrics/complexity.ps1" datrix-common` |
| `.\metrics\code-analyzer.ps1 datrix-common` | `powershell -File "d:/datrix/datrix/scripts/metrics/code-analyzer.ps1" datrix-common` |
| `.\git\status.ps1 -Detailed` | `powershell -File "d:/datrix/datrix/scripts/git/status.ps1" -Detailed` |
| `.\git\commit-and-push.ps1` | `powershell -File "d:/datrix/datrix/scripts/git/commit-and-push.ps1"` |
| `.\tasks\todo.ps1` | `powershell -File "d:/datrix/datrix/scripts/tasks/todo.ps1"` |

**Base path:** `d:/datrix/datrix/scripts/`

**Workspace root:** For scripts under `datrix/scripts/`, `Get-DatrixRoot` (venv) and `Get-DatrixWorkspaceRoot` (DatrixPaths) both refer to the monorepo root. Shared helpers live in `common/DatrixScriptCommon.psm1`.

**Common mistakes to avoid:**
- `d:\\datrix\\...` — bash strips `\\`, producing broken paths
- `d:\datrix\...` — bash interprets `\d`, `\t`, etc. as escape sequences
- Omitting quotes around paths with spaces

---

## Category Quick References

Read the category-specific file for the script you need:

| Category | File | Scripts |
|----------|------|---------|
| **Testing** | [test/quick-reference.md](test/quick-reference.md) | test.ps1, run-complete.ps1, dual-target.ps1, test-single.ps1, mypy.ps1, compare-tests.ps1, cleanup.ps1, status-*.ps1, collect-failure-data.ps1, extract-warnings.ps1, classify-run-delta.ps1, gate-verdict.ps1, affected-set.ps1, affected-gate.ps1, and the test-tooling gates: shared-library-gate.ps1 (also the scripts-tree layout), runner-plugin-gate.ps1, test-tooling-parsing-gate.ps1, test-specific-selection-gate.ps1, run-log-exclusivity-gate.ps1, toolchain-free-suites-gate.ps1 |
| **Gates** | [gates/README.md](gates/README.md) | One quick-reference per family: [parity](gates/parity/quick-reference.md) (type-mapping-completeness, supported-domain, behaviour, shared-home-body, observability-axis, manifest-import, third-party-dependency, framework-header, web-security-header, problem-type, field-error-path, artifact-role, generated-suite, block-realization, builtin-claims, body-wire-naming, route-wire-contract, enum-classifier), [realization](gates/realization/quick-reference.md) (conformance-gate, standing-conformance, typescript-whole-system, generation-determinism, ingress-migration, shared-builder-reachability, zero-environment-runtime, model-realization, pooled/shared-cache, shared-rdbms, documentation-realization, gendsl-corpus-resolution), [ratchet](gates/ratchet/quick-reference.md) (check-generated-file-ratchet, dependency-declaration, migration-upgrade-op-family, capability-gap-ledger, slow-test), [repo-hygiene](gates/repo-hygiene/quick-reference.md) (customer-domain-isolation, design-task-reference, ignored-source, polystring-case-roundtrip, python-lint-correctness, import-name-existence, check-docs-conformance, instruction-surface, cross-package-fixture-reads, enum-value-literals, handler-name-dedup, observability-native-only, emitted-escape-integrity, app-probe-path-literal, example-registry/snapshot/secret-seed/config-load) |
| **Development** | [dev/quick-reference.md](dev/quick-reference.md) | generate.ps1, generate-doc-fragments.ps1, check-docs.ps1, code-index.ps1, logic-map-report.ps1, local-llm.ps1, ineedtoknow.ps1, code-scan.ps1, generate-test-rules.ps1, and their gates (code-index-gate.ps1, local-llm-gate.ps1, ineedtoknow-gate.ps1) |
| **Generation** | [generation/quick-reference.md](generation/quick-reference.md) | rebuild-parser.ps1, refresh-example-snapshot.ps1, refresh-seed-datasets.ps1, status-generation.ps1, triage-failures.ps1, compare-generated.ps1, evaluate-generated-scan.ps1, evaluate-service-scan.ps1, evaluate-services.ps1, delete-generated.ps1 |
| **Scan** | [scan/quick-reference.md](scan/quick-reference.md) | syntax-checker.ps1, config-linter.ps1, datrix-linter.ps1, datrix-format.ps1, libcst.ps1, semgrep.ps1, ast-grep.ps1, check-debug-artifacts.ps1, check-python-bytecode.ps1, extra-parens.ps1, ruff-checker.ps1, check-import-boundaries.ps1, compile.ps1, compile-any-path.ps1, audit.ps1, gendsl-census.ps1 |
| **Workspace** | [workspace/quick-reference.md](workspace/quick-reference.md) | projects.ps1, project-structure.ps1, datrix-count.ps1, file-count.ps1, cleanup-temps.ps1, empty-folders.ps1 |
| **Codemods** | [codemods/README.md](codemods/README.md) | run-codemod.ps1 |
| **Git** | [git/quick-reference.md](git/quick-reference.md) | status.ps1, pull.ps1, pre-review.ps1, pre-review-gate.ps1, commit-and-push.ps1 (refuses to commit customer domain language — see `gates/repo-hygiene/customer-domain-isolation-gate.ps1` — a tree where a `.gitignore` rule shadows a source file — see `gates/repo-hygiene/ignored-source-gate.ps1` — a `to_*_case(str(name))` round trip — see `gates/repo-hygiene/polystring-case-roundtrip-gate.ps1` — a pyflakes finding in a pending `.py` file — see `gates/repo-hygiene/python-lint-correctness-gate.ps1` — or a design-doc, task-file or item-label reference — see `gates/repo-hygiene/design-task-reference-gate.ps1`) |
| **Metrics** | [metrics/quick-reference.md](metrics/quick-reference.md) | complexity.ps1, ruff.ps1, bandit.ps1, vulture.ps1, coverage.ps1, test-gen.ps1, duplicate.ps1, loc.ps1, find-constants.ps1, ... |
| **Visualization** | [visualize/quick-reference.md](visualize/quick-reference.md) | visualize.ps1, openapi-gen.ps1, schema-diff.ps1, schema-snapshot.ps1, all-reports.ps1, status-docs.ps1 |
| **Tasks** | [tasks/quick-reference.md](tasks/quick-reference.md) | todo.ps1, complete.ps1, completed.ps1, cleanup.ps1, latest-phase.ps1, phase-status.ps1, plan-waves.ps1, plan-waves-multi.ps1, validate-dependencies.ps1, validate-task.ps1, task-orientation-gate.ps1 |
| **Review** | [review/quick-reference.md](review/quick-reference.md) | review.ps1 (Tier 1 + Tier 2 task file reviewer), apply-reviews-prep.ps1, review-library-gate.ps1 |
| **Skills** | [skill/quick-reference.md](skill/quick-reference.md) | implement-design.ps1, implement-design-direct.ps1, skill-chain.ps1, skill-assist.ps1, skill-assist-gate.ps1 |

**Agents never run a whole test suite.** They run `test.ps1 <pkg> -Specific "…"` (files) and `test.ps1 <pkgs> -Tag <tags>` (feature tags), and list tags with `-ListTags`. Every whole-suite form — a bare package, `-All`, `-Rerun`, a tier switch, `affected-gate.ps1` — is Jon's alone and refused by `guard-full-suite-runs.py`.

---

## Generation Categories

For `generate.ps1` and `run-complete.ps1` batch mode:

| Flag | Path / Test Set | Content |
|------|------|---------|
| `-TestSet foundation` | `examples/01-foundation/` | Foundation examples |
| `-Domains` | `examples/03-domains/` (`domains`) | Domain examples |
| `-TestSet non-foundation` | `all` minus `foundation` | Everything except foundation examples |
| `-TestSet <name>` | Any test set from test-projects.json | Custom test set |

### Available Test Sets

| Test Set | Content |
|----------|---------|
| `foundation` | Foundation examples (`examples/01-foundation`) |
| `non-foundation` | Everything except foundation examples |
| `features-core` | Core feature examples (entities, enums, REST API, etc.) |
| `features` | All feature examples (`examples/02-features`) |
| `typescript-validation` | Representative subset for TypeScript validation (01-basic-entity, 03-basic-api, 05-relationships, 09-events, 15-cache, 20-cqrs, 21-background-jobs, blog-cms) |
| `domains` | All domain examples (`examples/03-domains`) |
| `all` | Every example (default for `-All`) |

---

## Project Names

Project names are **discovered from disk** — any `datrix-*` directory in the workspace is a valid `-Projects` value (`Get-DatrixDirectories`). The venv scripts narrow to packages carrying a `pyproject.toml`; the test scripts narrow to packages carrying a *suite*, which is a `tests/` folder (pytest) or a `package.json` declaring a `test` script (Node). A new `datrix-codegen-<lang>` package becomes a valid project name as soon as its directory exists, with no edit here. The list below is therefore **illustrative, not closed**:

- `datrix` (showcase repo — docs, examples, scripts)
- `datrix-cli`
- `datrix-common`
- `datrix-language`
- `datrix-codegen-common`
- `datrix-codegen-component`
- `datrix-codegen-python`
- `datrix-codegen-typescript`
- `datrix-codegen-sql`
- `datrix-codegen-docker`
- `datrix-codegen-aws`
- `datrix-codegen-azure`
- `datrix-codegen-angular` (frontend client target)
- `datrix-codegen-flutter` (frontend client target)
- `datrix-extensions`
- `datrix-vscode` (VS Code client — TypeScript; its suite runs under Node, not pytest)

---

## Working Directory

Commands assume you are in `datrix/` (showcase root). From workspace root (parent of `datrix`), prefix paths with `.\datrix\` (e.g. `.\datrix\scripts\test\test.ps1`).

**This applies to the source arguments too, not just the script path.** An `examples/...` argument
is resolved against the current working directory, so from the workspace root it must be given as
`datrix/examples/...`. Passing the documented `examples/...` form from the workspace root fails
with `Source file or directory not found`:

```powershell
# from workspace root D:\datrix
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" "datrix/examples/03-domains/ecommerce/system.dtrx" -L python
```

## Common Options

Most scripts support:
- `-Dbg` - Enable debug logging
- `-All` - Process all projects
- Folder paths as input (e.g., `.\datrix-common\` instead of `datrix-common`)

## File Locations

| What | Where |
|------|-------|
| Virtual environment | `D:\datrix\.venv` |
| Generation logs | `.generated/.results/generate-results-<timestamp>-<language>[-<profile>][-N].log` — the `-N` suffix appears when another run already claimed that name |
| Test results | `<project>/.test_results/test-results-YYYYMMDD-HHMMSS/` for package tests; generated projects also use `unit-tests-YYYYMMDD-HHMMSS/` and `deploy-test-YYYYMMDD-HHMMSS/` |
| Ruff check logs | `D:\datrix\.test-output\ruff\<project>\ruff-YYYYMMDD-HHMMSS.log` — outside every package repo |
| Test config | `scripts/config/test-projects.json` |
| Semgrep rules | `scripts/config/semgrep-rules/` |
| ast-grep rules | `scripts/config/ast-grep-rules/` |
| Metrics scripts | `scripts/metrics/` |
| Anti-pattern scanners | `scripts/scan/libcst.ps1`, `scripts/scan/semgrep.ps1`, `scripts/scan/ast-grep.ps1` |
| ConfigDSL lint/format | `scripts/scan/config-linter.ps1` |
| Code index (per machine) | `d:\datrix\.code-index\` — built and refreshed by `scripts/dev/code-index.ps1` (set up each machine once with `-Setup`) |
| Local model servers (per machine) | `scripts/dev/local-llm.ps1` — `-Setup` puts the agents' local-model MCP tools in `d:\datrix\.mcp.json` and approves them, once per machine; `-Status`/`-Usage` show what answers and what used it (`d:\datrix\.local-llm\usage.jsonl`) |
| Knowledge base (per machine) | `scripts/dev/ineedtoknow.ps1 "<question>"` — brief answer from the docs and earlier learned answers, or a local-model read of the closest docs that is kept only when its citations hold; database `d:\datrix\.knowledge\knowledge.db`, committed text copy of learned answers `datrix\docs\knowledge\learned\` |
| Logic map database | `d:\datrix\.logic-map\markers.db` — rewritten by the code index whenever markers change |
| Logic map scripts | `scripts/dev/code-index.ps1 -Canonical`, `scripts/dev/logic-map-report.ps1` |
| Python implementations | `scripts/<folder>/lib/` (`scripts/gates/<family>/lib/`) beside the wrapper that runs them; shared modules in `scripts/common/lib/datrix_scripts/` |
| Cleanup utilities | `scripts/common/CleanupUtils.psm1` |
| Shared helpers | `scripts/common/DatrixScriptCommon.psm1` |
| Run-log naming/claiming | `scripts/common/DatrixRunLog.psm1` |
| Skill scripts | `scripts/skill/` — headless skill chains (each step a `claude -p` run on its skill's own model) and the skill assists; Python in `scripts/skill/lib/` |

---

## Workflow Examples

### Full Test Cycle
```powershell
.\test\test.ps1 -All -Coverage
```

### Generate and Test
```powershell
.\dev\generate.ps1 -TestSet foundation -L python
.\test\test.ps1 datrix-codegen-python
```

### Single Example End-to-End
```powershell
.\test\run-complete.ps1 "examples/01-foundation/system.dtrx" -L python
```

### Generate Single + Validate
```powershell
.\dev\generate.ps1 examples/02-features/01-core-data-modeling/rest-api/system.dtrx -L python
.\scan\compile-any-path.ps1 .\.generated\python\docker\02-features\01-core-data-modeling\rest-api\library_book_service\src
```

### Code Review Prep
```powershell
.\git\status.ps1 -Detailed
.\test\test.ps1 -All
.\metrics\ruff.ps1 -All
.\metrics\bandit.ps1 -All
.\metrics\duplicate.ps1 -All
.\scan\libcst.ps1 -All
.\scan\semgrep.ps1 -All
.\scan\ast-grep.ps1 -All
```

### Full Cleanup
```powershell
.\workspace\cleanup-temps.ps1 -Force
.\test\cleanup.ps1 -Force
.\metrics\cleanup-ruff.ps1 -Force
.\generation\delete-generated.ps1
```

### Documentation Checks
```powershell
.\dev\check-docs.ps1
.\dev\generate-doc-fragments.ps1 -Check
```

### Check Generation Status
```powershell
.\generation\status-generation.ps1
.\test\status-tests.ps1
.\test\status-deploy-tests.ps1
```
