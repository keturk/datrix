# Quick Reference for AI Agents

Fast lookup guide for finding the right script for common tasks.

## Bash Shell Invocation (CRITICAL)

AI agents run in a **bash** shell, not PowerShell. All examples below use PowerShell-native syntax (e.g., `.\test\test.ps1`). To run them from bash:

1. **Prefix with** `powershell -File`
2. **Use forward slashes** in all paths (never `\\`)
3. **Quote the script path**

**Conversion pattern:**

| PowerShell (in docs) | Bash (what you run) |
|---|---|
| `.\test\test.ps1 datrix-common` | `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common` |
| `.\dev\generate.ps1 -All` | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -All` |
| `.\metrics\complexity.ps1 datrix-common` | `powershell -File "d:/datrix/datrix/scripts/metrics/complexity.ps1" datrix-common` |
| `.\git\status.ps1 -Detailed` | `powershell -File "d:/datrix/datrix/scripts/git/status.ps1" -Detailed` |
| `.\tasks\todo.ps1` | `powershell -File "d:/datrix/datrix/scripts/tasks/todo.ps1"` |

**Base path:** `d:/datrix/datrix/scripts/`

**Workspace root:** For scripts under `datrix/scripts/`, `Get-DatrixRoot` (venv) and `Get-DatrixWorkspaceRoot` (DatrixPaths) both refer to the monorepo root. Shared helpers live in `common/DatrixScriptCommon.psm1`.

**Common mistakes to avoid:**
- `d:\\datrix\\...` — bash strips `\\`, producing broken paths
- `d:\datrix\...` — bash interprets `\d`, `\t`, etc. as escape sequences
- Omitting quotes around paths with spaces

## Task → Script Mapping

### Code Generation

Language and platform default to config values (`system-config.yaml` and service configs). `.\dev\generate.ps1 -Language` / `-Platform` forward to `datrix generate` as `--language` and `--hosting` (the script’s `-Platform` is the output-path segment: docker / kubernetes / k8s). Use `-ServicePlatform <flavor>` to pass `datrix generate --platform` (service flavor: compose, ecs-fargate, …). You can also call `datrix generate` with `--language/-L`, `--hosting/-H`, `--platform/-P` directly. Do not use `--target`, `--generators`, or `--platforms` (removed).

| Task | Command |
|------|---------|
| Generate single project | `.\dev\generate.ps1 <source.dtrx> <output-dir>` |
| Generate all examples | `.\dev\generate.ps1 -All` |
| Generate tutorials only | `.\dev\generate.ps1 -Tutorial` |
| Generate by test set | `.\dev\generate.ps1 -TestSet tutorial01-10` |
| Generate for TypeScript | `.\dev\generate.ps1 -All -L typescript` |
| Validate TypeScript subset | `.\dev\generate.ps1 -TestSet typescript-validation -L typescript` |
| Override language (single project) | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L typescript` |
| Override hosting + service flavor | `.\dev\generate.ps1 <source.dtrx> <out> -Platform kubernetes -ServicePlatform kubernetes` |
| Override via CLI only | `datrix generate --source system.dtrx --output ./gen --hosting aws --platform ecs-fargate` |
| Check .dtrx syntax | `.\dev\syntax-checker.ps1 <file.dtrx>` |

### Testing

| Task | Command |
|------|---------|
| Test one project | `.\test\test.ps1 datrix-common` |
| Test all projects | `.\test\test.ps1 -All` |
| Test with coverage | `.\test\test.ps1 datrix-common -Coverage` |
| Run unit tests only | `.\test\test.ps1 datrix-common -Unit` |
| Run fast tests | `.\test\test.ps1 datrix-common -Fast` |
| Run specific test | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py"` |
| Run by keyword | `.\test\test.ps1 datrix-common -Keyword "test_parse"` |

### Git Operations

| Task | Command |
|------|---------|
| Check all repo status | `.\git\status.ps1` |
| Detailed git status | `.\git\status.ps1 -Detailed` |
| Pull all repos | `.\git\pull.ps1` |
| Batch commit/push | `.\git\commit-and-push.ps1 <messages.json>` |

### Task Management

| Task | Command |
|------|---------|
| List incomplete tasks | `.\tasks\todo.ps1` |
| List completed tasks | `.\tasks\completed.ps1` |

### Code Quality

| Task | Command |
|------|---------|
| Complexity check (Radon) | `.\metrics\complexity.ps1 datrix-common` |
| Complexity all / raw / halstead / mi | `.\metrics\complexity.ps1 -All -Mode raw` |
| Complexity custom max | `.\metrics\complexity.ps1 datrix-language -Mode check -Max 10` |
| Vulture (dead code) | `.\metrics\vulture.ps1 datrix-common` |
| Ruff (lint/format) | `.\metrics\ruff.ps1 datrix-common` |
| Package dependencies (tree/list/json) | `.\metrics\dependency.ps1 -All` |
| Duplicate-code detection | `.\metrics\duplicate.ps1 datrix-common` |
| Security scan (Bandit) | `.\metrics\bandit.ps1 datrix-common` |
| LibCST anti-pattern scan | `.\dev\libcst.ps1 datrix-common` |
| LibCST scan all projects | `.\dev\libcst.ps1 -All` |
| LibCST scan with report | `.\dev\libcst.ps1 -All -Report libcst-report.md` |
| Semgrep anti-pattern scan | `.\dev\semgrep.ps1 datrix-common` |
| Semgrep scan all projects | `.\dev\semgrep.ps1 -All` |
| Semgrep single rule | `.\dev\semgrep.ps1 -All -Rule empty-except-pass` |
| Semgrep list rules | `.\dev\semgrep.ps1 -ListRules` |
| Semgrep scan with report | `.\dev\semgrep.ps1 -All -Report semgrep-report.md` |
| Coverage (pytest-cov) | `.\metrics\coverage.ps1 datrix-common` |
| Coverage all / fail-under | `.\metrics\coverage.ps1 -All -FailUnder 90` |
| Check Jinja templates | `.\dev\ruff-checker.ps1` |

### Development

| Task | Command |
|------|---------|
| List all Datrix projects | `.\dev\projects.ps1` |
| List full paths to each project's src folder | `.\dev\projects.ps1 -Src` |
| List full paths to each project's tests folder | `.\dev\projects.ps1 -Tests` |
| Compile all Python (syntax + import, incl. cross-project) | `.\dev\compile.ps1 -All` |
| Compile one or more projects | `.\dev\compile.ps1 datrix-common` or `.\dev\compile.ps1 datrix-common datrix-language` |
| Compile with debug | `.\dev\compile.ps1 -All -Dbg` |
| Rebuild parser | `.\dev\rebuild-parser.ps1` |
| Force rebuild parser | `.\dev\rebuild-parser.ps1 -Force` |

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
- `datrix-codegen-k8s`
- `datrix-codegen-aws`
- `datrix-codegen-azure`

## Generation Categories

For `generate.ps1` and `run-complete.ps1` batch mode:

| Flag | Path / Test Set | Content |
|------|------|---------|
| `-Tutorial` | `examples/01-tutorial/` (tutorial-all) | All tutorials (01-41) |
| `-Domains` | `examples/02-domains/` (domains) | Domain examples (blog, ecommerce) |
| `-NonTutorial` | generate-all minus tutorial-all | Everything except tutorials |
| `-TestSet <name>` | Any test set from test-projects.json | Custom test set |

### Available Test Sets

| Test Set | Content |
|----------|---------|
| `tutorial01-10` | Tutorials 01-10 (basic entity through multiple services) |
| `tutorial11-20` | Tutorials 11-20 (service dependencies through CQRS) |
| `tutorial21-30` | Tutorials 21-30 (background jobs through GraphQL) |
| `tutorial31-41` | Tutorials 31-41 (advanced queries through file operations) |
| `tutorial-all` | All tutorials 01-41 |
| `typescript-validation` | Representative subset for TypeScript validation (01-basic-entity, 03-basic-api, 05-relationships, 09-events, 15-cache, 20-cqrs, 21-background-jobs, blog-cms) |
| `domains` | All domain examples (ecommerce, healthcare, etc.) |
| `generate-all` | Every example (default for `-All`) |

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
| Test logs | `<project>/.test_results/` |
| Test config | `scripts/config/test-projects.json` |
| Semgrep rules | `scripts/config/semgrep-rules/` |
| Metrics scripts (complexity, ruff, dependency, duplicate, bandit) | `scripts/metrics/` |
| Anti-pattern scanners (LibCST, Semgrep) | `scripts/dev/libcst.ps1`, `scripts/dev/semgrep.ps1` |
| Python implementations | `scripts/library/` |

## Workflow Examples

### Full Test Cycle
```powershell
.\test\test.ps1 -All -Coverage
```

### Generate and Test
```powershell
.\dev\generate.ps1 -Tutorial
.\test\test.ps1 datrix-codegen-python
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
```
