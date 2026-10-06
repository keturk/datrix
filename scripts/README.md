# Datrix Scripts

PowerShell wrapper scripts and their Python implementations for development, testing, and maintenance of the Datrix ecosystem.

## Folder Structure

```
scripts/
├── common/       # Shared PowerShell modules, venv.ps1, and lib/datrix_scripts (the shared Python package)
├── config/       # Configuration: test projects, baselines, exemptions, scanner rules
│   ├── semgrep-rules/      # Individual YAML rule files for the Semgrep anti-pattern scanner
│   ├── ast-grep-rules/     # Individual YAML rule files for the ast-grep structural scanner
│   └── conformance-specs/  # Committed specs for the standing conformance gate
├── dev/          # Generation, the code index, local model servers, ineedtoknow, docs checks, code-health digests
├── generation/   # Parser rebuild, example snapshots, seed datasets, generation status/triage, evaluation scans
├── scan/         # Anti-pattern scanners, import boundaries, compile/syntax checks, generated-output audits
├── workspace/    # Project listing, structure files, counts, cache and empty-folder cleanup
├── codemods/     # Bowler/libCST codemods for refactoring Datrix Python code
├── test/         # The test runner, status and failure analysis, test-tooling gates
├── gates/        # Repo-level validation gates
│   ├── parity/        # Every target realizes the same thing the same way
│   ├── realization/   # A declared capability is actually realized
│   ├── ratchet/       # Counts that only move one way
│   └── repo-hygiene/  # What may be committed; docs, examples, hard-zero code shapes
├── git/          # Git operations across all repositories
├── metrics/      # Code metrics: Radon, Vulture, Ruff, dependency, duplicate-code, Bandit, coverage
├── review/       # Task-file review (Tier 1 local model, Tier 2 Codex)
├── skill/        # Headless skill chains and skill assists
├── tasks/        # Task-file management and phase analysis
└── visualize/    # Diagrams, OpenAPI/AsyncAPI documents, schema snapshots
```

## Architecture

The scripts follow a **wrapper pattern**:

1. **PowerShell wrappers** (`.ps1`) in each folder handle virtual environment activation, dependency
   installation, argument parsing and validation, and logging and cleanup.
2. **Python implementations** (`.py`) sit beside the wrapper that runs them, in that folder's `lib/`
   (`gates/<family>/lib/` for gates). A module imported from more than one folder, by a hook, or by
   a package test lives in `common/lib/datrix_scripts/` and is imported as `datrix_scripts.<name>`;
   a wrapper runs one of those with `python -m datrix_scripts.<name>`.

`Ensure-DatrixVenv` puts `common/lib` on `PYTHONPATH`, so every wrapper's Python can import the
shared package. The placement rule, how hooks and MCP servers reach the package, and how to add a
script are in [common/README.md](common/README.md#where-python-lives).
`test\shared-library-gate.ps1 -Only check_scripts_tree` holds the layout.

## Project discovery (PowerShell)

Different scripts use different ways to decide which packages to include:

| Use case | Helper (see `common/DatrixScriptCommon.psm1`) | Meaning |
|----------|-----------------------------------------------|---------|
| Metrics `-All` (Ruff, complexity, …) | `Get-DatrixPackageNamesGlob` | Every directory under the workspace named `datrix-*` |
| `test.ps1 -All` | `Get-DatrixTestablePackageNames` | `datrix-*` directories carrying a test suite: a `tests/` folder (pytest) or a `package.json` with a `test` script (Node) |
| `duplicate.ps1 -Mono` | `Get-DatrixMonoProjectNames` | Ordered canonical package names (`Get-DatrixDirectories`) where the path exists |
| `dependency.ps1` help text | `Get-DatrixPackageNamesGlobWithPyProject` | `datrix-*` directories that contain `pyproject.toml` |

`Get-DatrixTestablePackageNames` is the PowerShell half of one fact; the Python half is
`common/lib/datrix_scripts/package_suites.py`, which `status-tests.ps1`, `test_project.py` and
`gate-verdict.ps1` use. Neither can call the other — the PowerShell answer is needed before
the venv is activated — so `test/test-tooling-parsing-gate.ps1` compares the two sets on every
run rather than leaving them to drift.

## Bash Shell Invocation

All examples in this documentation use **PowerShell-native** syntax (e.g., `.\test\test.ps1`). If you are running from a **bash** shell (e.g., AI agents, Git Bash, WSL), you must:

1. Prefix with `powershell -File`
2. Use **forward slashes** in paths (never `\\` or unquoted `\`)
3. Quote the script path

```bash
# PowerShell:  .\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py"
# Bash equivalent:
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Specific "tests/unit/test_foo.py"
```

See [quick-reference.md](quick-reference.md) for the full conversion table and links to category-specific references.

## Quick Start

### Run Tests
```powershell
# The tests of the files you changed
.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py"

# The tests of the behaviour you changed, in every package it reaches
.\test\test.ps1 datrix-common datrix-cli -Tag config-resolution

# Compare timestamped unit/deploy results for one generated project
.\test\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results
```

Whole-suite runs (a bare package, `-All`, `-Rerun`, a tier switch) are Jon's; agents run only targeted forms.

### Generate Code
```powershell
# Generate a single project
.\dev\generate.ps1 examples/01-foundation/system.dtrx .generated/python/docker/my-project -L python

# Generate foundation examples only (Jon's: batch forms are refused for agents)
.\dev\generate.ps1 -TestSet foundation -L python
```

### Lint/Format ConfigDSL
```powershell
# Check all .dcfg files (no writes)
.\scan\config-linter.ps1 -All -Check

# Format all .dcfg files
.\scan\config-linter.ps1 -All
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

Three scanners enforce `.cursorrules` coding standards across the monorepo:

```powershell
# LibCST — deep Python AST analysis (silent-fallback, empty-except, missing-encoding, banned imports, placeholder bodies)
.\scan\libcst.ps1 datrix-common
.\scan\libcst.ps1 -All -Report libcst-report.md

# Semgrep — declarative YAML rules (11 rules covering all .cursorrules anti-patterns)
.\scan\semgrep.ps1 -All
.\scan\semgrep.ps1 -All -Rule missing-encoding-read
.\scan\semgrep.ps1 -ListRules
.\scan\semgrep.ps1 -All -Report semgrep-report.md

# ast-grep — fast structural Python rules and one-off AST patterns
.\scan\ast-grep.ps1 -All
.\scan\ast-grep.ps1 -All -Rule placeholder-notimplemented-body
.\scan\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'
.\scan\ast-grep.ps1 -ListRules
.\scan\ast-grep.ps1 -All -Report ast-grep-report.md
```

See [scan/README.md](scan/README.md) for all options, [config/semgrep-rules/README.md](config/semgrep-rules/README.md) for the Semgrep catalog, and [config/ast-grep-rules/README.md](config/ast-grep-rules/README.md) for the ast-grep catalog.

### Codemods (Bowler / libCST)

AST-based refactors for Datrix Python code (rename functions/classes/variables, add arguments, custom transforms). Requires `pip install bowler`. See [codemods/README.md](codemods/README.md).

```powershell
.\codemods\run-codemod.ps1 01_rename_function OLD_NAME NEW_NAME datrix-language\src
```

## Virtual Environment

All scripts use a shared virtual environment at `D:\datrix\.venv`. The `common/venv.ps1` module handles:

- Automatic venv creation if missing
- Activation/deactivation, and `PYTHONPATH` for the shared scripts package
- Package installation with locking (prevents concurrent pip operations)
- Editable install management for all datrix-* packages

## Prerequisites

- PowerShell 5.1+ or PowerShell Core 7+
- Python 3.11+
- Git

## See Also

- [quick-reference.md](quick-reference.md) - AI agent quick reference (index with links to category files)
- [test/quick-reference.md](test/quick-reference.md) - Test runner, status, failure analysis, test-tooling gates
- [gates/README.md](gates/README.md) - Repo-level gates by family
- [dev/quick-reference.md](dev/quick-reference.md) - Generation, code index, local models, ineedtoknow, docs checks
- [generation/quick-reference.md](generation/quick-reference.md) - Parser, snapshots, triage, evaluation
- [scan/quick-reference.md](scan/quick-reference.md) - Anti-pattern scanners, import boundaries, compile checks
- [workspace/quick-reference.md](workspace/quick-reference.md) - Listing, counting, cleanup
- [git/quick-reference.md](git/quick-reference.md) - Git operations
- [metrics/quick-reference.md](metrics/quick-reference.md) - Code quality and metrics
- [review/quick-reference.md](review/quick-reference.md) - Task-file review
- [visualize/quick-reference.md](visualize/quick-reference.md) - Visualization and documentation
- [tasks/quick-reference.md](tasks/quick-reference.md) - Task management
- [skill/quick-reference.md](skill/quick-reference.md) - Headless skill chains and skill assists
- Individual folder READMEs for detailed documentation
