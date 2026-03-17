# Metrics Scripts

Code metrics and linting for Datrix Python packages: Radon (complexity, raw, Halstead, MI), Vulture (dead code), Ruff (lint/format), dependency (package dependency graph), Pylint duplicate-code detection, Bandit security scanning, and coverage (pytest-cov).

**Working directory:** Commands below assume you are in `datrix/` (showcase root). From workspace root, use `.\datrix\scripts\metrics\` instead of `.\scripts\metrics\`.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/metrics/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `complexity.ps1` | Run Radon metrics: check (enforce max), cc, raw, halstead, mi |
| `vulture.ps1` | Run Vulture dead-code detection |
| `dead_code_report.ps1` | Dead-code report: never referenced vs only referenced by tests (two-pass Vulture) |
| `ruff.ps1` | Run Ruff lint (check) or format |
| `dependency.ps1` | Report datrix package dependencies (tree, list, json) |
| `duplicate.ps1` | Run Pylint duplicate-code detection (R0801) |
| `bandit.ps1` | Run Bandit security scanner |
| `coverage.ps1` | Run pytest with coverage and show coverage details |

## complexity.ps1

Uses [scripts/library/metrics/complexity.py](../library/metrics/complexity.py) and [Radon](https://github.com/rubik/radon).

**Modes:** `check` (enforce max cyclomatic complexity), `cc` (cyclomatic per block), `raw` (SLOC, comment/blank, LOC, LLOC), `halstead`, `mi` (Maintainability Index).

### Usage

```powershell
# From datrix/ (showcase root) or workspace root with .\datrix\scripts\metrics\...
.\scripts\metrics\complexity.ps1 datrix-common

# Check with default max complexity 15 (mode=check)
.\scripts\metrics\complexity.ps1 datrix-common -Mode check -Max 15

# Report raw metrics
.\scripts\metrics\complexity.ps1 datrix-common -Mode raw

# Halstead / MI for all projects
.\scripts\metrics\complexity.ps1 -All -Mode halstead
.\scripts\metrics\complexity.ps1 -All -Mode mi

# Custom max (mode=check)
.\scripts\metrics\complexity.ps1 datrix-language -Mode check -Max 10
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `Projects` | Project names or paths (positional) |
| `-All` | Run for all datrix-* projects |
| `-Mode` | check, cc, raw, halstead, mi (default: check) |
| `-Max` | Max cyclomatic complexity for mode=check (default: 15) |
| `-StopOnError` | Stop on first project failure |
| `-VerboseOutput` | Verbose output |
| `-Dbg` | Debug output |

## vulture.ps1

Uses [scripts/library/metrics/vulture.py](../library/metrics/vulture.py) and [Vulture](https://github.com/jendrikseipp/vulture).

### Usage

```powershell
.\scripts\metrics\vulture.ps1 datrix-common
.\scripts\metrics\vulture.ps1 datrix-common -MinConfidence 100
.\scripts\metrics\vulture.ps1 -All -SortBySize
.\scripts\metrics\vulture.ps1 datrix-common -MakeWhitelist | Out-File whitelist.py
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `-MinConfidence` | 60-100 (default: 80) |
| `-SortBySize` | Sort unused classes/functions by size |
| `-MakeWhitelist` | Output whitelist to stdout |

## dead_code_report.ps1

Uses [scripts/library/metrics/dead_code_report.py](../library/metrics/dead_code_report.py) and runs Vulture twice: once on `src/` only (excluding tests) and once on `src/` and `tests/`. Dead code in `src/` is classified as:

- **Never referenced** — unreferenced anywhere (including tests). Safe to remove or whitelist.
- **Only referenced by tests** — referenced only from test code. Consider removing if tests can be simplified, or keep if the code is test-only by design.

The report is **grouped by type**: classes, functions, methods, then variables, attributes, imports, etc. Vulture reports functions, classes, and methods at 60% confidence and variables at 100%; the default min-confidence is **60** so that unused functions/methods/classes are included. Use `-MinConfidence 80` or `100` to restrict to higher-confidence findings (mostly variables).

Only code under each project's `src/` is reported; dead code inside `tests/` is not included. Per-project `vulture_whitelist.py` is respected in both passes.

### Usage

```powershell
# Default: the 11 packages (datrix-cli, datrix-common, ... datrix-language)
.\scripts\metrics\dead_code_report.ps1

# All datrix-* projects (except datrix)
.\scripts\metrics\dead_code_report.ps1 -All

# Specific projects, JSON output
.\scripts\metrics\dead_code_report.ps1 datrix-common datrix-language -Output json

# Save report to file
.\scripts\metrics\dead_code_report.ps1 -All -OutputPath dead-code-report.md
.\scripts\metrics\dead_code_report.ps1 -All -Output json | Out-File report.json
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `Projects` | Optional. Project names (positional). If omitted, uses default 11 packages. |
| `-All` | Scan all datrix-* projects (exclude `datrix`) |
| `-MinConfidence` | Vulture min confidence 60-100 (default: 60; use 80+ to exclude functions/classes) |
| `-Output` | text or json (default: text) |
| `-OutputPath` | Write report to this file (optional) |
| `-VerboseOutput` | Verbose progress to stderr |
| `-Quiet` | When using -OutputPath, do not print to console |

## ruff.ps1

Uses [scripts/library/metrics/ruff.py](../library/metrics/ruff.py) and [Ruff](https://github.com/astral-sh/ruff).

### Usage

```powershell
.\scripts\metrics\ruff.ps1 datrix-common
.\scripts\metrics\ruff.ps1 datrix-common -Mode format -Diff
.\scripts\metrics\ruff.ps1 -All -Mode check -OutputFormat json -Statistics
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `-Mode` | check (lint) or format (default: check) |
| `-OutputFormat` | full, concise, json, json-lines, junit, grouped, github, etc. |
| `-Fix` | Apply fixes (mode=check) |
| `-Diff` | Show diff only |
| `-Statistics` | Show rule counts (mode=check) |
| `-Check` | Dry run for format: exit non-zero if changes needed |

## dependency.ps1

Uses [scripts/library/metrics/dependency.py](../library/metrics/dependency.py). Reads `pyproject.toml` from each datrix-* package and reports which packages depend on which (datrix-to-datrix only). No external dependency (uses stdlib `tomllib`, Python 3.11+).

**Modes:** `tree` (each package with its direct datrix deps, indented), `list` (one `package -> dependency` per line), `json` (machine-readable packages + edges).

### Usage

```powershell
.\scripts\metrics\dependency.ps1 -All
.\scripts\metrics\dependency.ps1 -All -Mode list
.\scripts\metrics\dependency.ps1 -All -Mode json
.\scripts\metrics\dependency.ps1 datrix-common datrix-language -Mode tree
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `Projects` | Optional. Restrict to these package names (positional) |
| `-All` | Include all datrix-* packages |
| `-Mode` | tree, list, json (default: tree) |
| `-VerboseOutput` | Verbose output |
| `-Dbg` | Debug output |

## duplicate.ps1

Uses [scripts/library/metrics/duplicate.py](../library/metrics/duplicate.py) and [Pylint](https://github.com/pylint-dev/pylint) (R0801 rule).

### Usage

```powershell
.\scripts\metrics\duplicate.ps1 datrix-common
.\scripts\metrics\duplicate.ps1 datrix-common -MinLines 6
.\scripts\metrics\duplicate.ps1 -All
.\scripts\metrics\duplicate.ps1 -Mono
.\scripts\metrics\duplicate.ps1 -Mono -MinLines 6
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `Projects` | Project names or paths (positional) |
| `-All` | Run for all datrix-* projects |
| `-Mono` | Run across full monorepo (all projects in one scan). Reports duplicates both within and across packages. |
| `-MinLines` | Minimum similar lines to report (default: 4). For `-Mono`, the script defaults to 30 so cross-language (Python vs TS) pairs are not reported; pass `-MinLines 4` to see all. |
| `-StopOnError` | Stop on first project failure |
| `-VerboseOutput` | Verbose output |

### Mono runs and cross-language duplication

With `-Mono`, Pylint compares all Python under every project's `src/`. Duplicates between **datrix-codegen-python** and **datrix-codegen-typescript** (same feature, different output language) are expected: the two stacks implement parallel generators and are kept in sync by design. The script therefore uses **min-similarity-lines=30** for mono by default so those cross-language pairs are not reported. Use `-MinLines 4` (or lower) with `-Mono` to see all duplicates including cross-language.

## bandit.ps1

Uses [scripts/library/metrics/bandit.py](../library/metrics/bandit.py) and [Bandit](https://github.com/PyCQA/bandit).

### Usage

```powershell
.\scripts\metrics\bandit.ps1 datrix-common
.\scripts\metrics\bandit.ps1 datrix-common -Severity high
.\scripts\metrics\bandit.ps1 -All -Format json
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `Projects` | Project names or paths (positional) |
| `-All` | Run for all datrix-* projects |
| `-Severity` | Minimum severity: low, medium, high (default: medium) |
| `-Confidence` | Minimum confidence: low, medium, high (default: medium) |
| `-Format` | Output format: screen, json, csv, html, yaml, sarif (default: screen) |
| `-StopOnError` | Stop on first project failure |
| `-VerboseOutput` | Verbose output |

## coverage.ps1

Uses [scripts/library/metrics/coverage.py](../library/metrics/coverage.py) and [pytest-cov](https://github.com/pytest-dev/pytest-cov). Runs the test suite with coverage and displays the coverage report. Optionally fails if total coverage is below a threshold.

### Usage

```powershell
.\scripts\metrics\coverage.ps1 datrix-common
.\scripts\metrics\coverage.ps1 datrix-common -Format html
.\scripts\metrics\coverage.ps1 -All -FailUnder 90
.\scripts\metrics\coverage.ps1 datrix-common datrix-language -VerboseOutput
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `Projects` | Project names or paths (positional) |
| `-All` | Run for all datrix-* projects |
| `-Format` | term, term-missing, html, xml (default: term-missing) |
| `-FailUnder` | Minimum coverage percent; exit 1 if below (e.g. 90) |
| `-StopOnError` | Stop on first project failure |
| `-VerboseOutput` | Verbose pytest output |

## Behavior

1. Resolves project root (workspace root + project name or path).
2. Runs the tool on `project_root/src` (tests excluded by default for complexity/vulture).
3. complexity mode=check: exits 1 if any block exceeds `-Max`; otherwise 0.

The complexity threshold aligns with the project guideline: cyclomatic complexity ≤ 15.
