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
| `.\git\auto-commit-and-push.ps1` | `powershell -File "d:/datrix/datrix/scripts/git/auto-commit-and-push.ps1"` |
| `.\git\l-commit-and-push.ps1` | `powershell -File "d:/datrix/datrix/scripts/git/l-commit-and-push.ps1"` |
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
| **Testing** | [test/quick-reference.md](test/quick-reference.md) | test.ps1, run-complete.ps1, dual-target.ps1, test-single.ps1, mypy.ps1, compare-tests.ps1, cleanup.ps1, status-*.ps1 |
| **Development** | [dev/quick-reference.md](dev/quick-reference.md) | generate.ps1, syntax-checker.ps1, config-linter.ps1, compile.ps1, libcst.ps1, semgrep.ps1, ast-grep.ps1, audit.ps1, check-docs.ps1, generate-doc-fragments.ps1, cleanup-temps.ps1, ... |
| **Git** | [git/quick-reference.md](git/quick-reference.md) | status.ps1, pull.ps1, auto-commit-and-push.ps1, commit-and-push.ps1, l-commit-and-push.ps1 |
| **Metrics** | [metrics/quick-reference.md](metrics/quick-reference.md) | complexity.ps1, ruff.ps1, bandit.ps1, vulture.ps1, coverage.ps1, test-gen.ps1, duplicate.ps1, loc.ps1, ... |
| **Visualization** | [visualize/quick-reference.md](visualize/quick-reference.md) | visualize.ps1, openapi-gen.ps1, schema-diff.ps1, schema-snapshot.ps1, all-reports.ps1, status-docs.ps1 |
| **Tasks** | [tasks/quick-reference.md](tasks/quick-reference.md) | todo.ps1, complete.ps1, completed.ps1, cleanup.ps1, latest-phase.ps1 |
| **Review** | [review/quick-reference.md](review/quick-reference.md) | review.py (Tier 1 + Tier 2 task file reviewer) |

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

Valid project names for `-Projects` parameter:
- `datrix` (shared library)
- `datrix-cli`
- `datrix-common`
- `datrix-language`
- `datrix-codegen-component`
- `datrix-codegen-python`
- `datrix-codegen-typescript`
- `datrix-codegen-sql`
- `datrix-codegen-docker`
- `datrix-codegen-aws`
- `datrix-codegen-azure`
- `datrix-extensions`
- `datrix-projects`

---

## Working Directory

Commands assume you are in `datrix/` (showcase root). From workspace root (parent of `datrix`), prefix paths with `.\datrix\` (e.g. `.\datrix\scripts\test\test.ps1`).

## Common Options

Most scripts support:
- `-Dbg` - Enable debug logging
- `-All` - Process all projects
- Folder paths as input (e.g., `.\datrix-common\` instead of `datrix-common`)

## File Locations

| What | Where |
|------|-------|
| Virtual environment | `D:\datrix\.venv` |
| Generation logs | `.generated/.results/` |
| Test results | `<project>/.test_results/test-results-YYYYMMDD-HHMMSS/` for package tests; generated projects also use `unit-tests-YYYYMMDD-HHMMSS/` and `deploy-test-YYYYMMDD-HHMMSS/` |
| Ruff check logs | `<project>/.ruff_check/` |
| Test config | `scripts/config/test-projects.json` |
| Semgrep rules | `scripts/config/semgrep-rules/` |
| ast-grep rules | `scripts/config/ast-grep-rules/` |
| Metrics scripts | `scripts/metrics/` |
| Anti-pattern scanners | `scripts/dev/libcst.ps1`, `scripts/dev/semgrep.ps1`, `scripts/dev/ast-grep.ps1` |
| ConfigDSL lint/format | `scripts/dev/config-linter.ps1` |
| Logic map database | `d:\datrix\.logic-map\markers.db` |
| Logic map scripts | `scripts/dev/logic-map.ps1`, `scripts/dev/logic-map-report.ps1` |
| Python implementations | `scripts/library/` |
| Cleanup utilities | `scripts/common/CleanupUtils.psm1` |
| Shared helpers | `scripts/common/DatrixScriptCommon.psm1` |

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
.\dev\compile-any-path.ps1 .\.generated\python\docker\02-features\01-core-data-modeling\rest-api\library_book_service\src
```

### Code Review Prep
```powershell
.\git\status.ps1 -Detailed
.\test\test.ps1 -All
.\metrics\ruff.ps1 -All
.\metrics\bandit.ps1 -All
.\metrics\duplicate.ps1 -All
.\dev\libcst.ps1 -All
.\dev\semgrep.ps1 -All
.\dev\ast-grep.ps1 -All
```

### Full Cleanup
```powershell
.\dev\cleanup-temps.ps1 -Force
.\test\cleanup.ps1 -Force
.\metrics\cleanup-ruff.ps1 -Force
.\dev\delete-generated.ps1
```

### Documentation Checks
```powershell
.\dev\check-docs.ps1
.\dev\generate-doc-fragments.ps1 -Check
```

### Check Generation Status
```powershell
.\dev\status-generation.ps1
.\test\status-tests.ps1
.\test\status-deploy-tests.ps1
```
