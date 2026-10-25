# Quick Reference for AI Agents

Index of the script categories. Each category has its own quick reference — read only the one you need. Background, file locations and longer workflows: [README.md](README.md).

## Bash Shell Invocation (CRITICAL)

AI agents run in **bash**; the docs show PowerShell-native syntax (`.\test\test.ps1`). To run a script from bash: prefix `powershell -File`, use **forward slashes**, quote the script path.

| PowerShell (in docs) | Bash (what you run) |
|---|---|
| `.\test\test.ps1 datrix-common` | `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common` |
| `.\dev\generate.ps1 -All -L python` | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -All -L python` |
| `.\git\status.ps1 -Detailed` | `powershell -File "d:/datrix/datrix/scripts/git/status.ps1" -Detailed` |

**Base path:** `d:/datrix/datrix/scripts/`. Never write `d:\\datrix\\...` (bash strips `\\`) or `d:\datrix\...` (bash reads `\d`, `\t` as escapes).

**Working directory:** commands assume `datrix/` (the showcase root). From the workspace root, prefix script paths with `.\datrix\` and give source arguments as `datrix/examples/...`; the documented `examples/...` form fails there with `Source file or directory not found`.

## Category Quick References

| Category | File | Scripts |
|----------|------|---------|
| **Testing** | [test/quick-reference.md](test/quick-reference.md) | test.ps1, cases.ps1, model-contracts.ps1, tables.ps1, run-complete.ps1, dual-target.ps1, test-single.ps1, mypy.ps1, compare-tests.ps1, cleanup.ps1, status-*.ps1, collect-failure-data.ps1, extract-warnings.ps1, classify-run-delta.ps1, gate-verdict.ps1, affected-set.ps1, affected-gate.ps1, and the test-tooling gates (shared-library, runner-plugin, test-tooling-parsing, test-specific-selection, run-log-exclusivity, toolchain-free-suites) |
| **Gates** | [gates/README.md](gates/README.md) | One quick reference per family: [parity](gates/parity/quick-reference.md) (parity-cases and the cross-target gates), [realization](gates/realization/quick-reference.md) (conformance and realization gates), [ratchet](gates/ratchet/quick-reference.md) (counts that only move one way), [repo-hygiene](gates/repo-hygiene/quick-reference.md) (what may be committed; docs, examples, hard-zero code shapes, script-catalogue, thin-entrypoint) |
| **Development** | [dev/quick-reference.md](dev/quick-reference.md) | generate.ps1, generate-doc-fragments.ps1, find-imports.ps1, who-imports.ps1, print-sexp.ps1, check-docs.ps1, code-index.ps1, logic-map-report.ps1, local-llm.ps1, line-edit.ps1, ineedtoknow.ps1, code-scan.ps1, generate-test-rules.ps1, and their gates |
| **Generation** | [generation/quick-reference.md](generation/quick-reference.md) | rebuild-parser.ps1, refresh-example-snapshot.ps1, refresh-seed-datasets.ps1, status-generation.ps1, triage-failures.ps1, compare-generated.ps1, tree-hash.ps1, evaluate-generated-scan.ps1, evaluate-service-scan.ps1, evaluate-services.ps1, delete-generated.ps1 |
| **Scan** | [scan/quick-reference.md](scan/quick-reference.md) | syntax-checker.ps1, config-linter.ps1, datrix-linter.ps1, datrix-format.ps1, libcst.ps1, semgrep.ps1, ast-grep.ps1, check-debug-artifacts.ps1, check-python-bytecode.ps1, extra-parens.ps1, ruff-checker.ps1, check-import-boundaries.ps1, compile.ps1, audit.ps1, dgen-census.ps1, find-duplicate-bodies.ps1, find-unimplemented-abstracts.ps1 |
| **Workspace** | [workspace/quick-reference.md](workspace/quick-reference.md) | projects.ps1, project-structure.ps1, file-count.ps1, cleanup-temps.ps1, empty-folders.ps1 |
| **Codemods** | [codemods/README.md](codemods/README.md) | run-codemod.ps1, split-module.ps1 |
| **Git** | [git/quick-reference.md](git/quick-reference.md) | status.ps1, pull.ps1, fix-line-endings.ps1, resolve-pull.ps1, resolve-pull-gate.ps1, pre-review.ps1, pre-review-gate.ps1, commit-and-push.ps1 |
| **Metrics** | [metrics/quick-reference.md](metrics/quick-reference.md) | complexity.ps1, dependency.ps1, agent-spend.ps1, ruff.ps1, bandit.ps1, dead-code-report.ps1, coverage.ps1, test-gen.ps1, duplicate.ps1, loc.ps1, find-constants.ps1, ... |
| **Visualization** | [visualize/quick-reference.md](visualize/quick-reference.md) | visualize.ps1, openapi-gen.ps1, schema-diff.ps1, schema-snapshot.ps1, all-reports.ps1, status-docs.ps1 |
| **Tasks** | [tasks/quick-reference.md](tasks/quick-reference.md) | todo.ps1, complete.ps1, completed.ps1, cleanup.ps1, latest-phase.ps1, phase-status.ps1, plan-waves.ps1, plan-waves-multi.ps1, validate-dependencies.ps1, validate-task.ps1, task-orientation-gate.ps1 |
| **Review** | [review/quick-reference.md](review/quick-reference.md) | review.ps1, apply-reviews-prep.ps1, review-library-gate.ps1 |
| **Skills** | [skill/quick-reference.md](skill/quick-reference.md) | implement-design.ps1, implement-finding.ps1, organize-findings.ps1, skill-chain.ps1, skill-assist.ps1, skill-assist-gate.ps1 |

**Agents never run a whole test suite.** They run `test.ps1 <pkg> -Specific "…"` (files) and `test.ps1 <pkgs> -Tag <tags>` (feature tags), and list tags with `-ListTags`. Every whole-suite, whole-corpus or whole-package sweep form (a bare package, `-All`, `-Rerun`, a tier switch, `affected-gate.ps1`, `ruff.ps1 -All`, `semgrep.ps1 -All`, …) is Jon's alone and refused by the hooks (`guard-full-suite-runs.py`, `validate-script-invocation.py`, `guard-untargeted-scans.py`).

## Test Sets

`generate.ps1` and `run-complete.ps1` batch mode select from `scripts/config/test-projects.json`: `-TestSet <name>` or `-Domains`.

| Test Set | Content |
|----------|---------|
| `foundation` | `examples/01-foundation` |
| `non-foundation` | Everything except foundation |
| `features-core` | Core feature examples (entities, enums, REST API, etc.) |
| `features` | All of `examples/02-features` |
| `typescript-validation` | Representative subset for TypeScript validation |
| `domains` | All of `examples/03-domains` (`-Domains`) |
| `all` | Every example (default for `-All`) |

## Project Names

Any `datrix-*` directory in the workspace is a valid `-Projects` value, discovered from disk; `datrix` is the showcase repo. Test scripts narrow to packages with a suite (a `tests/` folder, or a `package.json` with a `test` script).

## Common Options

Each script declares its own parameters, and its folder's quick reference lists exactly those (held by `gates\repo-hygiene\script-catalogue-gate.ps1`). Many take `-Dbg` (debug logging) and folder paths as input (`.\datrix-common\` instead of `datrix-common`).

## Workflow Examples

Forms an agent may run: targeted tests (`-Specific`, `-Tag`), one project's generation, one named scan `-Rule`.

```powershell
# Test what you changed
.\test\test.ps1 datrix-common -Specific "tests/unit/test_a.py,tests/unit/test_b.py"
.\test\test.ps1 datrix-common datrix-cli -Tag config-resolution

# One example end to end
.\test\run-complete.ps1 "examples/01-foundation/system.dtrx" -L python

# Generate one example, then compile the output
.\dev\generate.ps1 examples/02-features/01-core-data-modeling/rest-api/system.dtrx -L python
.\scan\compile.ps1 -Path .\.generated\python\docker\02-features\01-core-data-modeling\rest-api\library_book_service\src

# Code review prep
.\git\status.ps1 -Detailed
.\metrics\ruff.ps1 datrix-common
.\metrics\duplicate.ps1 datrix-common
.\scan\semgrep.ps1 datrix-common -Rule silent-fallback-none
.\scan\ast-grep.ps1 datrix-common -Rule empty-except-pass
```
