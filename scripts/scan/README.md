# Scan Scripts

Static checks over source and generated output: anti-pattern scanners, compile/import checks,
`.dtrx`/`.dcfg` syntax and formatting, generated-output audits, and the import-boundary scanner.
Every wrapper runs its Python from `lib/`. Command-by-command reference:
[quick-reference.md](quick-reference.md).

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/scan/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `libcst.ps1` | Scan Python code for anti-patterns using LibCST (AST-level analysis) |
| `semgrep.ps1` | Scan Python code for anti-patterns using Semgrep (YAML rule-based) |
| `ast-grep.ps1` | Scan Python code for structural anti-patterns using ast-grep rules or one-off patterns |
| `check-debug-artifacts.ps1` | Leftover debug/logging artifacts in source |
| `check-python-bytecode.ps1` | Python bytecode under package `src/` trees |
| `check-import-boundaries.ps1` | Cross-package import boundaries and their ratchets |
| `extra-parens.ps1` | Remove extraneous parentheses (Ruff UP034) |
| `ruff-checker.ps1` | Check Jinja2 templates with ruff linter |
| `compile.ps1` / `compile-any-path.ps1` | Syntax and import check for Datrix projects / any Python path |
| `audit.ps1` | Audit generated Python for placeholders and syntax |
| `gendsl-census.ps1` | Per-domain census of a language's compiled genDSL definitions |
| `syntax-checker.ps1` | Validate `.dtrx` file syntax |
| `datrix-linter.ps1` / `datrix-format.ps1` | Semantic lint / lossless format of `.dtrx` files |
| `config-linter.ps1` | Lint and format ConfigDSL `.dcfg` files |

Whole-package anti-pattern scans are phase-boundary acts: inside a fix, run `semgrep.ps1`,
`libcst.ps1` or `ast-grep.ps1` only with a named `-Rule` or a stated question
(`guard-untargeted-scans.py` refuses the rest).

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

- **PowerShell:** `scripts/scan/libcst.ps1` — Activates venv, ensures `libcst` is installed, invokes the scanner.
- **Python:** `scripts/scan/lib/libcst_scanner.py` — LibCST visitor that traverses the AST and collects findings.

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

- **PowerShell:** `scripts/scan/semgrep.ps1` — Activates venv, ensures `semgrep` is installed, invokes the scanner.
- **Python:** `scripts/scan/lib/semgrep_scanner.py` — Discovers rules, expands directories into file lists, runs semgrep per rule, aggregates findings.
- **Rules:** `scripts/config/semgrep-rules/*.yaml` — Individual YAML rule files.

### Notes

- Semgrep uses `git ls-files` for file discovery in directories. In non-git workspaces, the scanner expands directories into explicit `.py` file paths to bypass this limitation.
- Full monorepo scans with all 11 rules take ~20-25 minutes. Running individual rules (`-Rule <name>`) is much faster (~2-3 minutes per rule).
- Jinja2 template files (`.j2`) are automatically excluded from scanning.

---

## ast-grep.ps1

Scans Datrix Python code for structural anti-patterns using [ast-grep](https://ast-grep.github.io/). Saved rules live in `scripts/config/ast-grep-rules/`; one-off structural patterns can be passed with `-Pattern`.

### Rules

Rules are loaded from `scripts/config/ast-grep-rules/`. Each YAML file contains one ast-grep rule.

| Rule | Pattern | Severity |
|------|---------|----------|
| `silent-fallback-none` | `dict.get(key, None)` | warning |
| `default-type-mapping-any` | `.get(..., "Any")` | error |
| `empty-except-pass` | `except ...: pass` | warning |
| `return-none-lookup` | lookup-style functions returning `None` | warning |
| `missing-encoding-read-text` | `Path.read_text()` without arguments | warning |
| `missing-encoding-write-text` | `Path.write_text(value)` without `encoding=` | warning |
| `open-without-encoding` | `open(path)` / `open(path, mode)` | warning |
| `placeholder-function-body` | function body with only `pass` / ellipsis | warning |
| `placeholder-notimplemented-body` | `raise NotImplementedError(...)` | warning |
| `generic-exception-raise` | `raise Exception(...)` | warning |
| `legacy-compatibility-call` | `legacy_*` / `*_compatibility` calls | warning |
| `banned-mock-import` | `from unittest.mock import ...` | error |
| `banned-simple-namespace` | `from types import SimpleNamespace` | error |
| `codegen-string-append` | `code += f"..."` string append | warning |

See [config/ast-grep-rules/README.md](../config/ast-grep-rules/README.md) for usage examples and rule details.

### Usage

```powershell
# List available rules
.\ast-grep.ps1 -ListRules

# Scan all projects with all saved rules
.\ast-grep.ps1 -All

# Scan all projects with a specific rule
.\ast-grep.ps1 -All -Rule placeholder-notimplemented-body

# Scan one project
.\ast-grep.ps1 datrix-common

# Run a one-off structural pattern
.\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'

# Scan all and write a markdown report
.\ast-grep.ps1 -All -Report ast-grep-report.md
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `Projects` | string[] | One or more project names (positional) |
| `-All` | switch | Scan all projects in the monorepo |
| `-Pattern` | string | Run a one-off ast-grep Python pattern |
| `-Rule` | string[] | Run only these rules (repeatable); name matches YAML filename without extension |
| `-ListRules` | switch | List all available rules and exit |
| `-Report` | string | Write markdown report to this path (relative to monorepo root) |
| `-ShowRaw` | switch | Show raw ast-grep output for each invocation |

### Implementation

- **PowerShell:** `scripts/scan/ast-grep.ps1` — Activates venv, ensures `sg` / `ast-grep` is installed, invokes the scanner.
- **Python:** `scripts/scan/lib/ast_grep.py` — Discovers rules, expands directories into file lists, runs ast-grep per rule, aggregates findings.
- **Rules:** `scripts/config/ast-grep-rules/*.yaml` — Individual YAML rule files.

### Notes

- PowerShell expands `$NAME` in double-quoted strings. Use single quotes for ast-grep metavariable patterns, for example `-Pattern 'raise Exception($MSG)'`.
- The npm install exposes `sg.cmd` and `ast-grep.cmd` on Windows; the wrapper prefers those command shims.
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

- **PowerShell:** `scripts/scan/compile.ps1` – Activates the Datrix virtual environment, resolves paths, and runs `compile.py`.
- **Python:** `scripts/scan/lib/compile.py` – File discovery, `py_compile` syntax check, and per-package import check (with PYTHONPATH and submodule walk).

## audit.ps1

Audits generated Python code under `.generated/python/docker` for placeholder patterns and syntax errors. Use after generating to check for `pass`, `raise NotImplementedError`, `# Test fixtures placeholder`, and Python syntax (ast.parse).

**Allowlist:** Paths containing `db/base.py` or `_microservice_helpers.py` are treated as intentional (empty base class, event-subscription stub) and excluded from the placeholder failure count. Only actionable files (e.g. routes, services, jobs, validators, conftest) cause `--fail-on-placeholders` to exit non-zero.

```powershell
# Summary only
.\audit.ps1

# Write markdown report
.\audit.ps1 -Report examples-generated-audit-report.md

# Exit non-zero on syntax errors or actionable placeholders
.\audit.ps1 -FailOnSyntax -FailOnPlaceholders
```

Implementation: `scripts/scan/lib/audit_generated.py`.

## syntax-checker.ps1

Validates .dtrx file syntax without full generation.

```powershell
.\syntax-checker.ps1 path/to/file.dtrx
```

## config-linter.ps1

Lints and formats ConfigDSL `.dcfg` files using the shared ConfigDSL parser (`datrix_common.config.dcfg.parser`).

You must pass either `-All` or one/more file-system paths.

```powershell
# Format all .dcfg files across all datrix repos
.\config-linter.ps1 -All

# Check only (no writes)
.\config-linter.ps1 -All -Check

# Format one directory
.\config-linter.ps1 examples\01-foundation\config

# Check one file
.\config-linter.ps1 examples\01-foundation\config\system.dcfg -Check
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `-All` | switch | Scan all datrix repositories (from `Get-DatrixDirectoryPaths`) |
| `Path` | string[] | One or more file/directory paths to scan (positional) |
| `-Check` | switch | Report only; do not write formatted output |
| `-Dbg` | switch | Enable debug logging |
