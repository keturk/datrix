# Development Scripts

Tools for code generation, parser building, and code quality.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/dev/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `audit.ps1` | Audit generated Python for placeholders and syntax (see Audit generated code) |
| `compile.ps1` | Compile all Python in Datrix project folders (syntax and import check) |
| `generate.ps1` | Generate code from .dtrx source files |
| `projects.ps1` | List all Datrix projects; use `-Src` or `-Tests` for full paths to src/tests folders |
| `rebuild-parser.ps1` | Rebuild Tree-sitter parser from grammar.js |
| `run-codemod.ps1` | Run a Bowler codemod (rename, add/remove args, replace patterns). See [codemods/README.md](codemods/README.md). |
| `libcst.ps1` | Scan Python code for anti-patterns using LibCST (AST-level analysis) |
| `semgrep.ps1` | Scan Python code for anti-patterns using Semgrep (YAML rule-based) |
| `ruff-checker.ps1` | Check Jinja2 templates with ruff linter |
| `syntax-checker.ps1` | Validate .dtrx file syntax |
| `status-generation.ps1` | Show generation status for projects |
| `datrix-count.ps1` | Count .dtrx files in the workspace |
| `file-count.ps1` | Count files by type |
| `empty-folders.ps1` | Find empty folders |
| `cleanup_temps.ps1` | Clean up temporary files |

## generate.ps1

Main code generation script. Generates Python/TypeScript code from .dtrx source files.

### Single Project Mode

```powershell
# Basic generation
.\generate.ps1 examples/01-tutorial/system.dtrx .generated/python/docker/my-project

# With custom language and platform
.\generate.ps1 examples/01-tutorial/system.dtrx .generated/typescript/kubernetes/my-project -L typescript -P kubernetes

# Enable debug logging
.\generate.ps1 examples/01-tutorial/system.dtrx .generated/python/docker/my-project -Dbg
```

### Batch Mode

```powershell
# Generate all examples
.\generate.ps1 -All

# Generate specific category
.\generate.ps1 -Tutorial # examples/01-tutorial
.\generate.ps1 -Domains # examples/02-domains
# With options
.\generate.ps1 -All -Language typescript -Platform kubernetes
```

### Parameters

| Parameter | Alias | Default | Description |
|-----------|-------|---------|-------------|
| `-Source` | | | Path to .dtrx file (single mode) |
| `-Output` | | | Output directory (single mode) |
| `-All` | | | Generate all projects |
| `-Tutorial` | | | Generate tutorial examples only |
| `-Domains` | | | Generate domain examples only |
| `-Language` | `-L` | `python` | Target language (python, typescript) |
| `-Platform` | `-P` | `docker` | Target platform (docker, kubernetes) |
| `-OutputBase` | | `.generated` | Output base directory (batch mode) |
| `-TestSet` | | `generate-all` | Test set name (batch mode) |
| `-Dbg` | | | Enable debug logging |

### Logs

Generation logs are saved to `.generated/.results/generate-results-TIMESTAMP.log`. Old logs are not deleted automatically.

## rebuild-parser.ps1

Rebuilds the Tree-sitter parser from `grammar.js`.

```powershell
# Normal rebuild (skips if unchanged)
.\rebuild-parser.ps1

# Force rebuild
.\rebuild-parser.ps1 -Force
```

## run-codemod.ps1

Runs a [Bowler](https://pybowler.io/) codemod from `dev/codemods/` (rename function/class/variable, add/remove arguments, replace patterns). Activates the Datrix venv and invokes `run_codemod.py`, which runs `python -m bowler run <script> -- <args>`.

Requires `pip install bowler` in the venv. See [codemods/README.md](codemods/README.md) for the list of codemods and usage.

```powershell
# Preview: rename function (diff only)
.\run-codemod.ps1 01_rename_function parse_file parse_path datrix-language\src

# Rename class
.\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src

# Update imports when module is renamed
.\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src
```

Implementation: **PowerShell** `scripts/dev/run-codemod.ps1`; **Python** `scripts/library/dev/run_codemod.py`.

## libcst.ps1

Scans Datrix Python code for `.cursorrules` anti-patterns using [LibCST](https://github.com/Instagram/LibCST) (deep AST analysis). LibCST parses Python into a Concrete Syntax Tree, enabling precise detection of patterns that text-based tools miss.

### Patterns Detected

| Rule | Description |
|------|-------------|
| `silent-fallback` | `dict.get(key, None)` — use explicit lookup + raise on missing |
| `empty-except` | `except: pass` / `except Exception: pass` — handle or re-raise |
| `missing-encoding` | `read_text()` / `write_text()` / `open()` without `encoding="utf-8"` |
| `banned-test-import` | `MagicMock` / `Mock` / `patch` / `SimpleNamespace` in test files |
| `placeholder-body` | `pass` or `raise NotImplementedError` as sole function body |

### Usage

```powershell
# Scan one project
.\libcst.ps1 datrix-common

# Scan multiple projects
.\libcst.ps1 datrix-common datrix-language

# Scan all projects
.\libcst.ps1 -All

# Scan all projects and write a markdown report
.\libcst.ps1 -All -Report libcst-report.md
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `Projects` | string[] | One or more project names (positional) |
| `-All` | switch | Scan all projects in the monorepo |
| `-Report` | string | Write markdown report to this path (relative to monorepo root) |

### Implementation

- **PowerShell:** `scripts/dev/libcst.ps1` — Activates venv, ensures `libcst` is installed, invokes the scanner.
- **Python:** `scripts/library/dev/libcst_scanner.py` — LibCST visitor that traverses the AST and collects findings.

---

## semgrep.ps1

Scans Datrix Python code for `.cursorrules` anti-patterns using [Semgrep](https://semgrep.dev/) with declarative YAML rules. Each rule is stored as an individual YAML file in `scripts/config/semgrep-rules/`, making rules easy to test, debug, and extend.

### Rules

Rules are loaded from `scripts/config/semgrep-rules/`. Each YAML file contains one or a closely related set of Semgrep rules.

| Rule | Pattern | Severity |
|------|---------|----------|
| `silent-fallback-none` | `dict.get(key, None)` | WARNING |
| `default-type-mapping` | `type_map.get(t, "Any")` | ERROR |
| `empty-except-pass` | `except: pass` / `except Exception: pass` | WARNING |
| `missing-encoding-read` | `Path.read_text()` without `encoding=` | WARNING |
| `missing-encoding-write` | `Path.write_text()` without `encoding=` | WARNING |
| `banned-mock-import` | `from unittest.mock import MagicMock/Mock/patch` | ERROR |
| `banned-simple-namespace` | `from types import SimpleNamespace` in tests | ERROR |
| `return-none-lookup` | `return None` in `get_*/find_*/lookup_*/resolve_*` | WARNING |
| `string-concat-codegen` | `code += f"..."` string concatenation | WARNING |
| `todo-comment` | `# TODO` comments | INFO |
| `magic-number-status` | Bare `200`/`404`/`500` in comparisons | WARNING |

See [config/semgrep-rules/README.md](../config/semgrep-rules/README.md) for adding new rules.

### Usage

```powershell
# List available rules
.\semgrep.ps1 -ListRules

# Scan all projects with all rules
.\semgrep.ps1 -All

# Scan all projects with a specific rule
.\semgrep.ps1 -All -Rule missing-encoding-read

# Scan all projects with two specific rules
.\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup

# Scan one project
.\semgrep.ps1 datrix-common

# Scan all and write a markdown report
.\semgrep.ps1 -All -Report semgrep-report.md

# Show raw semgrep output for each rule
.\semgrep.ps1 -All -ShowRaw
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `Projects` | string[] | One or more project names (positional) |
| `-All` | switch | Scan all projects in the monorepo |
| `-Rule` | string[] | Run only these rules (repeatable); name matches YAML filename without `.yaml` |
| `-ListRules` | switch | List all available rules and exit |
| `-Report` | string | Write markdown report to this path (relative to monorepo root) |
| `-ShowRaw` | switch | Show raw semgrep output for each rule |

### Implementation

- **PowerShell:** `scripts/dev/semgrep.ps1` — Activates venv, ensures `semgrep` is installed, invokes the scanner.
- **Python:** `scripts/library/dev/semgrep_scanner.py` — Discovers rules, expands directories into file lists, runs semgrep per rule, aggregates findings.
- **Rules:** `scripts/config/semgrep-rules/*.yaml` — Individual YAML rule files.

### Notes

- Semgrep uses `git ls-files` for file discovery in directories. In non-git workspaces, the scanner expands directories into explicit `.py` file paths to bypass this limitation.
- Full monorepo scans with all 11 rules take ~20-25 minutes. Running individual rules (`-Rule <name>`) is much faster (~2-3 minutes per rule).
- Jinja2 template files (`.j2`) are automatically excluded from scanning.

---

## ruff-checker.ps1

Checks Jinja2 templates for Python syntax issues using ruff.

```powershell
# Check templates in current directory
.\ruff-checker.ps1
```

The script:
1. Finds all `.j2` template files
2. Renders them with sample values
3. Runs ruff on the rendered Python
4. Reports issues in `ruff-report-TIMESTAMP.txt`

## compile.ps1

Compiles all Python in Datrix project folders to find **syntax** and **import** issues. Use this before pushing to catch broken imports (including cross-project imports like `from datrix_language.parser import ...`).

### What it does

1. **Syntax check** – Discovers all `.py` files under the given directories and runs `py_compile` on each.
2. **Import check** – For each installable package (has `src/` and `pyproject.toml`), imports the package and **all its submodules** in a subprocess with `PYTHONPATH` set to all Datrix projects’ `src` directories. That exercises cross-package imports; if a module does `from datrix_language.parser import ModuleNode` and that fails, the run reports an import error.

You must pass either `-All` or one or more project directories. If you run the script with no arguments, it prints usage and exits (no error).

### Examples

```powershell
# Check all Datrix repositories
.\compile.ps1 -All

# Check one or more projects (names resolved against workspace root)
.\compile.ps1 datrix-common
.\compile.ps1 datrix-common datrix-language

# Full path
.\compile.ps1 D:\datrix\datrix-common

# Debug output (shows each file/submodule being checked)
.\compile.ps1 datrix-common datrix-language -Dbg
```

### Parameters

| Parameter   | Type     | Description |
|------------|----------|-------------|
| `-All`     | switch   | Check all Datrix repositories (same list as `Get-DatrixDirectoryPaths`). |
| `ProjectDir` | string[] | One or more project directories (positional). Names (e.g. `datrix-common`) or full paths. Resolved against workspace root. |
| `-Dbg`     | switch   | Enable debug logging. |

### Implementation

- **PowerShell:** `scripts/dev/compile.ps1` – Activates the Datrix virtual environment, resolves paths, and runs `compile.py`.
- **Python:** `scripts/library/dev/compile.py` – File discovery, `py_compile` syntax check, and per-package import check (with PYTHONPATH and submodule walk).

## audit.ps1

Audits generated Python code under `.generated/python/docker` for placeholder patterns and syntax errors. Use after `generate.ps1 -All` to check for `pass`, `raise NotImplementedError`, `# Test fixtures placeholder`, and Python syntax (ast.parse).

**Allowlist:** Paths containing `db/base.py` or `_microservice_helpers.py` are treated as intentional (empty base class, event-subscription stub) and excluded from the placeholder failure count. Only actionable files (e.g. routes, services, jobs, validators, conftest) cause `--fail-on-placeholders` to exit non-zero.

```powershell
# Summary only
.\audit.ps1

# Write markdown report
.\audit.ps1 -Report examples-generated-audit-report.md

# Fail CI on syntax or placeholders
.\audit.ps1 -FailOnSyntax -FailOnPlaceholders
```

Implementation: `scripts/library/dev/audit_generated.py`.

**CI:** The Generate and audit workflow (`.github/workflows/generate-and-audit.yml`) runs after generation and fails the job if the audit reports syntax errors (`--fail-on-syntax`) or actionable placeholder patterns (`--fail-on-placeholders`). Allowlisted paths are excluded from placeholder failure.

## syntax-checker.ps1

Validates .dtrx file syntax without full generation.

```powershell
.\syntax-checker.ps1 path/to/file.dtrx
```
