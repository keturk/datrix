# Quick Reference — Code Quality & Metrics Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `metrics\complexity.ps1`

Radon metrics: cyclomatic complexity, cognitive complexity, raw, Halstead, maintainability index.

| Mode | Command | Description |
|------|---------|-------------|
| **Check one project** | `.\metrics\complexity.ps1 datrix-common` | Enforce max complexity (default mode=check, max=15) |
| **Check all** | `.\metrics\complexity.ps1 -All` | All projects |
| **Custom max** | `.\metrics\complexity.ps1 datrix-language -Max 10` | Lower threshold |
| **Cyclomatic only** | `.\metrics\complexity.ps1 datrix-common -Mode cc` | Cyclomatic complexity report |
| **Raw metrics** | `.\metrics\complexity.ps1 datrix-common -Mode raw` | SLOC, comments, blanks |
| **Halstead metrics** | `.\metrics\complexity.ps1 -All -Mode halstead` | Halstead complexity |
| **Maintainability index** | `.\metrics\complexity.ps1 datrix-common -Mode mi` | MI score per file |
| **Fix with Ollama** | `.\metrics\complexity.ps1 datrix-common -Fix` | Fix worst violation (mode=check only) |
| **Fix + test** | `.\metrics\complexity.ps1 datrix-common -Fix -Test` | Fix and verify with pytest |
| **Stop on first fail** | `.\metrics\complexity.ps1 -All -StopOnError` | Stop on first failure |
| **Verbose** | `.\metrics\complexity.ps1 datrix-common -VerboseOutput` | Verbose output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (check\|cc\|raw\|halstead\|mi, default: check), `-Max` (default: 15), `-Fix`, `-Test` (with -Fix), `-StopOnError`, `-VerboseOutput`, `-Dbg`

---

## `metrics\error-messages.ps1`

Error message quality checker: detects substandard error messages (missing context, suggestions, valid options) via AST-based scoring, with optional Ollama-powered auto-fix.

| Mode | Command | Description |
|------|---------|-------------|
| **Check one project** | `.\metrics\error-messages.ps1 datrix-common` | Enforce min score (default mode=check, min-score=2) |
| **Check all** | `.\metrics\error-messages.ps1 -All` | All projects |
| **Stricter threshold** | `.\metrics\error-messages.ps1 -All -MinScore 3` | Higher minimum score |
| **Report (audit)** | `.\metrics\error-messages.ps1 datrix-common -Mode report` | List all error sites with scores |
| **Fix with Ollama** | `.\metrics\error-messages.ps1 datrix-common -Fix` | Fix worst violation |
| **Fix all** | `.\metrics\error-messages.ps1 datrix-common -FixAll -Test` | Fix all violations with test verification |
| **Stop on first fail** | `.\metrics\error-messages.ps1 -All -StopOnError` | Stop on first failure |
| **Verbose** | `.\metrics\error-messages.ps1 datrix-common -VerboseOutput` | Verbose output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (check\|report, default: check), `-MinScore` (default: 2), `-Fix`, `-FixAll`, `-Test` (with -Fix/-FixAll), `-MaxRetries` (default: 3), `-StopOnError`, `-VerboseOutput`, `-Dbg`

---

## `metrics\vulture.ps1`

Dead-code detection using Vulture. Runs a combined scan across selected projects' `src/` trees (cross-project reference detection).

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\vulture.ps1 datrix-common` | Scan datrix-common |
| **All projects** | `.\metrics\vulture.ps1 -All` | Combined scan of all |
| **Multiple projects** | `.\metrics\vulture.ps1 datrix-common datrix-language` | Combined scan of selected |
| **High confidence** | `.\metrics\vulture.ps1 datrix-common -MinConfidence 100` | Only 100% confidence findings |
| **Sort by size** | `.\metrics\vulture.ps1 -All -SortBySize` | Largest dead code first |
| **Generate whitelist** | `.\metrics\vulture.ps1 datrix-common -MakeWhitelist` | Output false-positive whitelist |
| **Verbose** | `.\metrics\vulture.ps1 datrix-common -VerboseOutput` | Show command details |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-MinConfidence` (60-100, default: 80), `-SortBySize`, `-MakeWhitelist`, `-StopOnError` (deprecated), `-VerboseOutput`

---

## `metrics\dead-code-report.ps1`

Two-pass Vulture dead-code report: classifies findings as "never referenced" or "only referenced by tests".

| Mode | Command | Description |
|------|---------|-------------|
| **Default projects** | `.\metrics\dead-code-report.ps1` | Every installable `datrix-*` package discovered on disk (same set as `-All`) |
| **All projects** | `.\metrics\dead-code-report.ps1 -All` | All datrix-* projects |
| **Specific projects** | `.\metrics\dead-code-report.ps1 datrix-common .\datrix-language\` | Selected projects by name or path |
| **JSON output** | `.\metrics\dead-code-report.ps1 -All -Output json` | JSON format |
| **High confidence** | `.\metrics\dead-code-report.ps1 -All -MinConfidence 100` | Only 100% confidence |
| **Save to file** | `.\metrics\dead-code-report.ps1 -All -OutputPath dead-code.md` | Write report to file |
| **Raw (no filters)** | `.\metrics\dead-code-report.ps1 -All -Raw` | Disable false-positive filters |
| **Quiet** | `.\metrics\dead-code-report.ps1 -All -OutputPath report.md -Quiet` | Only write to file |

**Parameters:** `-Projects` (positional, variadic; package names or folder paths), `-All`, `-MinConfidence` (60-100, default: 60), `-Output` (text\|json), `-OutputPath`, `-VerboseOutput`, `-Raw`, `-Quiet`

---

## `metrics\ruff.ps1`

Ruff linter/formatter. Logs output to `.ruff_check/` per project.

| Mode | Command | Description |
|------|---------|-------------|
| **Lint one project** | `.\metrics\ruff.ps1 datrix-common` | Check (lint) mode |
| **Lint all** | `.\metrics\ruff.ps1 -All` | All projects |
| **Format check** | `.\metrics\ruff.ps1 datrix-common -Mode format -Check` | Dry run: exit non-zero if needs formatting |
| **Format diff** | `.\metrics\ruff.ps1 datrix-common -Mode format -Diff` | Show what would change |
| **Apply fixes** | `.\metrics\ruff.ps1 datrix-common -Fix` | Auto-fix lint issues |
| **JSON output** | `.\metrics\ruff.ps1 -All -OutputFormat json` | JSON lint output |
| **Statistics** | `.\metrics\ruff.ps1 -All -Statistics` | Rule violation counts |
| **Lint tests** | `.\metrics\ruff.ps1 -All -Test` | Lint tests/ instead of src/ |
| **Stop on fail** | `.\metrics\ruff.ps1 -All -StopOnError` | Stop on first failure |
| **Verbose** | `.\metrics\ruff.ps1 datrix-common -VerboseOutput` | Verbose output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (check\|format, default: check), `-OutputFormat` (full\|concise\|json\|json-lines\|junit\|grouped\|github, default: full), `-Fix`, `-Diff`, `-Statistics`, `-Check`, `-Test`, `-StopOnError`, `-VerboseOutput`

---

## `metrics\bandit.ps1`

Bandit security scanner for Python code.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\bandit.ps1 datrix-common` | Default severity=medium, confidence=medium |
| **All projects** | `.\metrics\bandit.ps1 -All` | Scan all |
| **High severity only** | `.\metrics\bandit.ps1 datrix-common -Severity high` | Only high severity |
| **JSON output** | `.\metrics\bandit.ps1 -All -Format json` | JSON format |
| **SARIF output** | `.\metrics\bandit.ps1 -All -Format sarif` | SARIF format |
| **Stop on fail** | `.\metrics\bandit.ps1 -All -StopOnError` | Stop on first failure |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Severity` (low\|medium\|high, default: medium), `-Confidence` (low\|medium\|high, default: medium), `-Format` (screen\|json\|csv\|html\|yaml\|sarif, default: screen), `-StopOnError`, `-VerboseOutput`

---

## `metrics\duplicate.ps1`

Pylint duplicate-code detection (R0801).

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\duplicate.ps1 datrix-common` | Default min-lines=4 |
| **All projects** | `.\metrics\duplicate.ps1 -All` | Each project separately |
| **Monorepo-wide** | `.\metrics\duplicate.ps1 -Mono` | Cross-project duplicate detection |
| **Custom min lines** | `.\metrics\duplicate.ps1 datrix-common -MinLines 6` | Higher threshold |
| **Include tests** | `.\metrics\duplicate.ps1 datrix-common -Tests` | Also scan tests/ |
| **Stop on fail** | `.\metrics\duplicate.ps1 -All -StopOnError` | Stop on first failure |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mono` (mutually exclusive with -All), `-MinLines` (default: 4), `-Tests`, `-StopOnError`, `-VerboseOutput`

---

## `metrics\coverage.ps1`

Pytest coverage reports via pytest-cov.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\coverage.ps1 datrix-common` | Default: term-missing report |
| **All projects** | `.\metrics\coverage.ps1 -All` | All projects |
| **HTML report** | `.\metrics\coverage.ps1 datrix-common -Format html` | HTML coverage report |
| **XML report** | `.\metrics\coverage.ps1 datrix-common -Format xml` | XML coverage report |
| **Fail threshold** | `.\metrics\coverage.ps1 -All -FailUnder 90` | Fail if below 90% |
| **Stop on fail** | `.\metrics\coverage.ps1 -All -StopOnError` | Stop on first failure |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Format` (term\|term-missing\|html\|xml, default: term-missing), `-FailUnder` (default: 0), `-StopOnError`, `-VerboseOutput`

---

## `metrics\test-gen.ps1`

Coverage-driven unit test generation via local Ollama. Finds uncovered functions from coverage JSON, ranks candidates, and can generate validated `_generated` test files. Generated files are kept only after target-reference checks, Ruff auto-fix/check, the generated test file, and the full project test suite pass; failures are deleted. Prompts are compacted for local models with selective imports, summarized related tests, minimal class context, target literals/attributes, and short retry prompts. Successful generated tests are tracked in `.generated/test-gen-manifest.json`, and already tracked/output-existing candidates are skipped.

| Mode | Command | Description |
|------|---------|-------------|
| **Report candidates** | `.\metrics\test-gen.ps1 datrix-common` | Ranked uncovered functions (default mode=report) |
| **Generate top candidate** | `.\metrics\test-gen.ps1 datrix-common -Generate` | Generate, validate, run project tests, and print added tests |
| **Generate all candidates** | `.\metrics\test-gen.ps1 datrix-common -GenerateAll -MaxRetries 3` | Attempt generation for all ranked functions; summary includes generated, skipped, and failed |
| **Target specific function** | `.\metrics\test-gen.ps1 datrix-common -Generate -TargetFunction "validate_external"` | Generate for one named function; use `Class.method`, `module.function`, or the report candidate id when a bare name is ambiguous |
| **Custom Ollama model** | `.\metrics\test-gen.ps1 datrix-common -Generate -Model "qwen3-coder-cline:latest"` | Override the model used for generation; default URL is `http://10.94.0.100:11434` |
| **Debug prompts** | `.\metrics\test-gen.ps1 datrix-common -Generate -VerbosePrompts -MaxPromptTokens 4000` | Print prompts and warn above the token budget |
| **All projects report** | `.\metrics\test-gen.ps1 -All -Mode report` | Report candidates for all projects |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (report\|generate\|generate-all, default: report), `-Generate`, `-GenerateAll`, `-TargetFunction`, `-MaxRetries` (default: 3), `-MinUncoveredRatio` (default: 0.5), `-MaxPromptTokens` (default: 6000), `-VerbosePrompts`, `-OllamaUrl` (default: `http://10.94.0.100:11434`), `-Model` (default: `qwen3-coder-cline:latest`), `-StopOnError`, `-VerboseOutput`

---

## `metrics\code-analyzer.ps1`

AST inventory of classes, methods, module functions, constants (UPPER_SNAKE heuristic), and type aliases, plus a **duplicate top-level names** section (same class/function name in two or more files) to spot accidental parallel architectures. Uses metrics **`-All`** semantics (`datrix-*` packages only). Report path defaults to **`./code-structure-report.md` under the process cwd** (where you run the script); relative `-Output` resolves against cwd.

| Mode | Command | Description |
|------|---------|-------------|
| **One project (src)** | `.\metrics\code-analyzer.ps1 datrix-common` | Default: `src/` only |
| **All packages (src)** | `.\metrics\code-analyzer.ps1 -All` | Every `datrix-*` package, `src/` only |
| **Tests only** | `.\metrics\code-analyzer.ps1 datrix-common -Tests` | `tests/` tree only |
| **Src and tests** | `.\metrics\code-analyzer.ps1 -All -Src -Tests` | Both trees, all packages |
| **Custom output** | `.\metrics\code-analyzer.ps1 -All -Output reports\structure.md` | Markdown under cwd (or absolute path) |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Src`, `-Tests`, `-Output`, `-Dbg`

---

## `metrics\dependency.ps1`

Reports dependency relationships between Datrix packages (from pyproject.toml).

| Mode | Command | Description |
|------|---------|-------------|
| **All (tree)** | `.\metrics\dependency.ps1 -All` | Dependency tree for all packages |
| **All (list)** | `.\metrics\dependency.ps1 -All -Mode list` | Edge list (package -> dep) |
| **All (json)** | `.\metrics\dependency.ps1 -All -Mode json` | JSON format |
| **Specific packages** | `.\metrics\dependency.ps1 datrix-common datrix-language -Mode tree` | Selected packages |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (tree\|list\|json, default: tree), `-VerboseOutput`, `-Dbg`

---

## `metrics\large-files.ps1`

Lists top N files by line count for Datrix projects.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\large-files.ps1 datrix-common` | Top 20 Python files by line count |
| **All projects** | `.\metrics\large-files.ps1 -All` | All projects |
| **Custom top count** | `.\metrics\large-files.ps1 datrix-language -Top 30` | Top 30 files |
| **Line threshold** | `.\metrics\large-files.ps1 datrix-language -Threshold 500` | Only files >= 500 lines |
| **JSON format** | `.\metrics\large-files.ps1 datrix-language -Top 30 -Format json` | JSON output |
| **All file types** | `.\metrics\large-files.ps1 -All -Suffix ""` | Include all extensions |
| **Specific suffix** | `.\metrics\large-files.ps1 -All -Suffix "j2,py"` | Jinja + Python files |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Top` (default: 20), `-Threshold` (default: 0), `-Format` (summary\|json, default: summary), `-Suffix` (default: py, "" for all), `-StopOnError`, `-VerboseOutput`, `-Dbg`

---

## `metrics\loc.ps1`

Lines-of-code counting using pygount.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\loc.ps1 datrix-common` | Summary format |
| **All projects** | `.\metrics\loc.ps1 -All` | All projects |
| **JSON format** | `.\metrics\loc.ps1 datrix-common -Format json` | JSON output |
| **CLOC XML** | `.\metrics\loc.ps1 datrix-common -Format cloc-xml` | CLOC-compatible XML |
| **Python only** | `.\metrics\loc.ps1 -All -Suffix py` | Only Python files |
| **Multiple suffixes** | `.\metrics\loc.ps1 -All -Suffix "py,js"` | Python + JS files |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Format` (summary\|cloc-xml\|json, default: summary), `-Suffix` (comma-separated, default: "" = all), `-StopOnError`, `-VerboseOutput`, `-Dbg`

---

## `metrics\cleanup-ruff.ps1`

Cleans up Ruff check log files from `.ruff_check/` folders.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\metrics\cleanup-ruff.ps1` | Show all log files |
| **Delete all** | `.\metrics\cleanup-ruff.ps1 -Force` | Delete all log files |
| **Keep latest** | `.\metrics\cleanup-ruff.ps1 -Force -KeepLatest` | Delete old, keep latest per project |

**Parameters:** `-BaseDir`, `-Force`, `-KeepLatest`, `-Dbg`
