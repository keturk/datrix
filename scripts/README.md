# Datrix Scripts

PowerShell wrapper scripts and Python implementations for development, testing, and maintenance of the Datrix ecosystem.

## Folder Structure

```
scripts/
├── common/ # Shared PowerShell modules and utilities
├── config/ # Configuration files (test projects, semgrep rules)
│   └── semgrep-rules/ # Individual YAML rule files for Semgrep anti-pattern scanner
├── dev/ # Development tools (code generation, parser, codemods, scanning)
│   └── codemods/ # Bowler/libCST codemods for refactoring Datrix Python code
├── git/ # Git operations across all repositories
├── library/ # Python implementations (called by PowerShell wrappers)
├── metrics/ # Code metrics: Radon, Vulture, Ruff, dependency, duplicate-code, Bandit
├── tasks/ # Task and bug tracking utilities
└── test/ # Test execution scripts
```

## Architecture

The scripts follow a **wrapper pattern**:

1. **PowerShell wrappers** (`.ps1`) in category folders handle:
 - Virtual environment activation
 - Dependency installation
 - Argument parsing and validation
 - Logging and cleanup

2. **Python implementations** (`.py`) in `library/` contain:
 - Core business logic
 - Cross-platform compatibility
 - Complex processing

## Project discovery (PowerShell)

Different scripts use different ways to decide which packages to include:

| Use case | Helper (see `common/DatrixScriptCommon.psm1`) | Meaning |
|----------|-----------------------------------------------|---------|
| Metrics `-All` (Ruff, complexity, …) | `Get-DatrixPackageNamesGlob` | Every directory under the workspace named `datrix-*` |
| `test.ps1 -All` | `Get-DatrixTestablePackageNames` | Canonical repos from `DatrixPaths` that exist and have a `tests/` folder |
| `duplicate.ps1 -Mono` | `Get-DatrixMonoProjectNames` | Ordered canonical package names (`Get-DatrixDirectories`) where the path exists |
| `dependency.ps1` help text | `Get-DatrixPackageNamesGlobWithPyProject` | `datrix-*` directories that contain `pyproject.toml` |

## Bash Shell Invocation

All examples in this documentation use **PowerShell-native** syntax (e.g., `.\test\test.ps1`). If you are running from a **bash** shell (e.g., AI agents, Git Bash, WSL), you must:

1. Prefix with `powershell -File`
2. Use **forward slashes** in paths (never `\\` or unquoted `\`)
3. Quote the script path

```bash
# PowerShell:  .\test\test.ps1 datrix-common -Fast
# Bash equivalent:
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Fast
```

See [quick-reference.md](quick-reference.md) for the full conversion table.

## Quick Start

### Run Tests
```powershell
# Test a specific project
.\test\test.ps1 datrix-common

# Test all projects
.\test\test.ps1 -All

# Test with coverage
.\test\test.ps1 datrix-language -Coverage
```

### Generate Code
```powershell
# Generate a single project
.\dev\generate.ps1 examples/01-tutorial/system.dtrx .generated/python/docker/my-project

# Generate all examples
.\dev\generate.ps1 -All

# Generate tutorial examples only
.\dev\generate.ps1 -Tutorial
```

### Check Git Status
```powershell
# Quick status of all repos
.\git\status.ps1

# Detailed status with changed files
.\git\status.ps1 -Detailed
```

### View Tasks
```powershell
# List incomplete tasks and bugs
.\tasks\todo.ps1

# List completed tasks
.\tasks\completed.ps1
```

### Code Metrics
```powershell
# Cyclomatic complexity check (Radon; default max 15)
.\metrics\complexity.ps1 datrix-common

# Raw metrics, Halstead, or Maintainability Index
.\metrics\complexity.ps1 datrix-common -Mode raw
.\metrics\complexity.ps1 -All -Mode halstead

# Dead-code detection (Vulture)
.\metrics\vulture.ps1 datrix-common

# Package dependency report (tree, list, or json)
.\metrics\dependency.ps1 -All
.\metrics\dependency.ps1 -All -Mode list

# Lint or format (Ruff)
.\metrics\ruff.ps1 datrix-common
.\metrics\ruff.ps1 datrix-common -Mode format -Diff

# Duplicate-code detection (Pylint R0801)
.\metrics\duplicate.ps1 datrix-common
.\metrics\duplicate.ps1 -All

# Security scanning (Bandit)
.\metrics\bandit.ps1 datrix-common
.\metrics\bandit.ps1 -All -Format json
```

See [metrics/README.md](metrics/README.md) for all options (complexity, Vulture, Ruff, dependency, duplicate, Bandit).

### Anti-Pattern Scanning

Two scanners enforce `.cursorrules` coding standards across the monorepo:

```powershell
# LibCST — deep Python AST analysis (silent-fallback, empty-except, missing-encoding, banned imports, placeholder bodies)
.\dev\libcst.ps1 datrix-common
.\dev\libcst.ps1 -All -Report libcst-report.md

# Semgrep — declarative YAML rules (11 rules covering all .cursorrules anti-patterns)
.\dev\semgrep.ps1 -All
.\dev\semgrep.ps1 -All -Rule missing-encoding-read
.\dev\semgrep.ps1 -ListRules
.\dev\semgrep.ps1 -All -Report semgrep-report.md
```

See [dev/README.md](dev/README.md) for all options and [config/semgrep-rules/README.md](config/semgrep-rules/README.md) for the rule catalog.

### Codemods (Bowler / libCST)

AST-based refactors for Datrix Python code (rename functions/classes/variables, add arguments, custom transforms). Use the dev wrapper (requires `pip install bowler`). See [dev/codemods/README.md](dev/codemods/README.md).

```powershell
.\dev\run-codemod.ps1 01_rename_function OLD_NAME NEW_NAME datrix-language\src
```

## Virtual Environment

All scripts use a shared virtual environment at `D:\datrix\.venv`. The `common/venv.ps1` module handles:

- Automatic venv creation if missing
- Activation/deactivation
- Package installation with locking (prevents concurrent pip operations)
- Editable install management for all datrix-* packages

## Prerequisites

- PowerShell 5.1+ or PowerShell Core 7+
- Python 3.9+
- Git

## See Also

- [quick-reference.md](quick-reference.md) - AI agent quick reference
- Individual folder READMEs for detailed documentation
