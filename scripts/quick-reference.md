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

---

## Code Generation

### `dev\generate.ps1`

Generates Datrix projects from `.dtrx` source files. Language and platform default to config values (`system-config.yaml` and service configs). `-Language`/`-L` and `-Platform`/`-P` control output-path derivation. Use `-Hosting`/`-H` to pass `--hosting` and `-ServicePlatform` to pass `--platform` (service flavor: compose, ecs-fargate, etc.).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project (auto output)** | `.\dev\generate.ps1 <source.dtrx>` | Output path derived from test-projects.json |
| **Single project (explicit output)** | `.\dev\generate.ps1 <source.dtrx> <output-dir>` | Explicit output directory |
| **Single + language/platform** | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L typescript -P kubernetes` | Override language and platform |
| **Single + hosting/flavor** | `.\dev\generate.ps1 <source.dtrx> <out> -H kubernetes -ServicePlatform kubernetes` | Override hosting and service platform |
| **All examples** | `.\dev\generate.ps1 -All` | Generate all (test set generate-all) |
| **All + language** | `.\dev\generate.ps1 -All -L typescript` | All examples for TypeScript |
| **All + custom output base** | `.\dev\generate.ps1 -All -OutputBase .generated2` | Custom output root |
| **Tutorials only** | `.\dev\generate.ps1 -Tutorial` | examples/01-tutorial (test set tutorial-all) |
| **Non-tutorial only** | `.\dev\generate.ps1 -NonTutorial` | Everything except tutorials |
| **Domains only** | `.\dev\generate.ps1 -Domains` | examples/02-domains |
| **Custom test set** | `.\dev\generate.ps1 -TestSet tutorial01-10` | Any named test set |
| **TypeScript validation subset** | `.\dev\generate.ps1 -TestSet typescript-validation -L typescript` | Quick TS validation |
| **Debug logging** | `.\dev\generate.ps1 -All -Dbg` | Enable DEBUG level logging |

**Parameters:** `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Tutorial`, `-NonTutorial`, `-Domains`, `-Language`/`-L` (python\|typescript, default: python), `-Platform`/`-P` (docker\|kubernetes\|k8s, default: docker), `-Hosting`/`-H`, `-ServicePlatform`, `-OutputBase` (default: .generated), `-TestSet` (default: generate-all), `-Dbg`

### `dev\syntax-checker.ps1`

Validates `.dtrx` file syntax using the tree-sitter parser.

| Mode | Command | Description |
|------|---------|-------------|
| **All repos** | `.\dev\syntax-checker.ps1` | Check all .dtrx files in all datrix repos |
| **Single file** | `.\dev\syntax-checker.ps1 path/to/file.dtrx` | Check one file |
| **Directory** | `.\dev\syntax-checker.ps1 examples/` | Check all .dtrx in a directory |
| **With debug** | `.\dev\syntax-checker.ps1 . -Dbg` | Debug logging |

**Parameters:** `-Path` (positional, default: all repos), `-Dbg`

### `dev\status-generation.ps1`

Reports generation status from the latest `generate-results-*.log` file. Lists which projects succeeded/failed.

| Mode | Command |
|------|---------|
| **Show status** | `.\dev\status-generation.ps1` |

**Parameters:** (none)

---

## Visualization & Documentation

### `visualize\all-reports.ps1`

Runs all visualization and documentation scripts for a project: diagrams, schema snapshot, OpenAPI/AsyncAPI specs, and status report. All output is written next to the `.dtrx` source files (language-agnostic). Each step runs independently — a failure in one does not block subsequent steps.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\all-reports.ps1 <source.dtrx>` | All reports for one project |
| **All projects** | `.\visualize\all-reports.ps1 -All` | All reports for all projects |
| **Tutorials only** | `.\visualize\all-reports.ps1 -Tutorial` | Tutorial examples only |
| **Domains only** | `.\visualize\all-reports.ps1 -Domains` | Domain examples only |
| **Custom test set** | `.\visualize\all-reports.ps1 -TestSet tutorial01-10` | Named test set |
| **Debug** | `.\visualize\all-reports.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Tutorial`, `-Domains`, `-TestSet` (default: generate-all), `-Dbg`

### `visualize\visualize.ps1`

Generates Mermaid diagrams from `.dtrx` source files. Produces ERD, service map, event flow, API catalog, CQRS flow, inheritance tree, infrastructure topology, and system context diagrams. Output is written next to the `.dtrx` source (e.g., `examples/.../docs/diagrams/`).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\visualize.ps1 <source.dtrx>` | All diagram types, Markdown output |
| **Single + type** | `.\visualize\visualize.ps1 <source.dtrx> -Type erd` | Single diagram type |
| **Single + service** | `.\visualize\visualize.ps1 <source.dtrx> -Type erd -Service "ns.SvcName"` | Scoped to one service |
| **Raw Mermaid** | `.\visualize\visualize.ps1 <source.dtrx> -Format mmd` | Output .mmd files instead of .md |
| **All projects** | `.\visualize\visualize.ps1 -All` | Batch: all test-projects.json |
| **Tutorials only** | `.\visualize\visualize.ps1 -Tutorial` | Batch: tutorial examples |
| **Domains only** | `.\visualize\visualize.ps1 -Domains` | Batch: domain examples |
| **Custom test set** | `.\visualize\visualize.ps1 -TestSet tutorial01-10` | Named test set |
| **Debug** | `.\visualize\visualize.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Tutorial`, `-Domains`, `-TestSet` (default: generate-all), `-Type` (erd\|service-map\|event-flow\|api-catalog\|cqrs-flow\|inheritance\|infrastructure\|system-context\|all, default: all), `-Service`, `-Format` (md\|mmd, default: md), `-Dbg`

### `visualize\schema-diff.ps1`

Compares two `.dtrx` files and reports structural changes (breaking vs non-breaking).

| Mode | Command | Description |
|------|---------|-------------|
| **Markdown diff** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx` | Print Markdown report to stdout |
| **JSON diff** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Format json` | JSON output |
| **To file** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Output changes.md` | Write to file |
| **Debug** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Dbg` | Debug logging |

**Parameters:** `-Before` (positional 0, required), `-After` (positional 1, required), `-Format` (markdown\|json, default: markdown), `-Output`, `-Dbg`

### `visualize\schema-snapshot.ps1`

Saves `.dtrx` Application as a JSON snapshot for future diffs. Output is written next to the `.dtrx` source (e.g., `examples/.../docs/snapshots/`).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\schema-snapshot.ps1 <source.dtrx>` | Save to source dir docs/snapshots/ |
| **Explicit output** | `.\visualize\schema-snapshot.ps1 <source.dtrx> -Output snap.json` | Custom output path |
| **All projects** | `.\visualize\schema-snapshot.ps1 -All` | Batch: all test-projects.json |
| **Tutorials only** | `.\visualize\schema-snapshot.ps1 -Tutorial` | Batch: tutorial examples |
| **Domains only** | `.\visualize\schema-snapshot.ps1 -Domains` | Batch: domain examples |
| **Debug** | `.\visualize\schema-snapshot.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Tutorial`, `-Domains`, `-TestSet` (default: generate-all), `-Output`, `-Dbg`

### `visualize\openapi-gen.ps1`

Generates OpenAPI 3.1 YAML per REST API and AsyncAPI 3.0 YAML per PubSub block. Output is written next to the `.dtrx` source (e.g., `examples/.../docs/openapi/`).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\openapi-gen.ps1 <source.dtrx>` | Generate all spec types |
| **OpenAPI only** | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type openapi` | Only OpenAPI specs |
| **AsyncAPI only** | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type asyncapi` | Only AsyncAPI specs |
| **All projects** | `.\visualize\openapi-gen.ps1 -All` | Batch: all test-projects.json |
| **Tutorials only** | `.\visualize\openapi-gen.ps1 -Tutorial` | Batch: tutorial examples |
| **Domains only** | `.\visualize\openapi-gen.ps1 -Domains` | Batch: domain examples |
| **Debug** | `.\visualize\openapi-gen.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Tutorial`, `-Domains`, `-TestSet` (default: generate-all), `-Type` (openapi\|asyncapi\|all, default: all), `-Dbg`

### `visualize\status-docs.ps1`

Reports documentation status for Datrix projects (diagrams, OpenAPI, AsyncAPI, snapshots). Scans project source directories for docs artifacts.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\status-docs.ps1 <source.dtrx>` | Status for one project |
| **All projects** | `.\visualize\status-docs.ps1 -All` | All test-projects.json |
| **Tutorials only** | `.\visualize\status-docs.ps1 -Tutorial` | Tutorial examples only |
| **Domains only** | `.\visualize\status-docs.ps1 -Domains` | Domain examples only |
| **Debug** | `.\visualize\status-docs.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Tutorial`, `-Domains`, `-TestSet` (default: generate-all), `-Dbg`

---

## Testing

### `test\test.ps1`

Runs tests for one or more Datrix projects.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\test\test.ps1 datrix-common` | Test one project |
| **By folder path** | `.\test\test.ps1 .\datrix-common\` | Test using folder path |
| **Multiple projects** | `.\test\test.ps1 datrix-common datrix-language` | Test several projects |
| **All projects** | `.\test\test.ps1 -All` | Test everything |
| **With coverage** | `.\test\test.ps1 datrix-common -Coverage` | Generate coverage report |
| **Unit tests only** | `.\test\test.ps1 datrix-common -Unit` | Only unit tests |
| **Integration tests** | `.\test\test.ps1 datrix-common -Integration` | Only integration tests |
| **E2E tests** | `.\test\test.ps1 datrix-common -E2E` | Only end-to-end tests |
| **Fast tests** | `.\test\test.ps1 datrix-common -Fast` | Exclude slow tests |
| **Slow tests** | `.\test\test.ps1 datrix-common -Slow` | Only slow tests |
| **Specific test file** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py"` | Run one test file |
| **Keyword filter** | `.\test\test.ps1 datrix-common -Keyword "test_parse"` | Match by keyword (-k) |
| **Verbose output** | `.\test\test.ps1 datrix-common -VerboseOutput` | Verbose pytest output |
| **Skip dependency install** | `.\test\test.ps1 datrix-common -SkipInstall` | Skip pip install |
| **No log save** | `.\test\test.ps1 datrix-common -NoSave` | Don't save output to log files |
| **Debug logging** | `.\test\test.ps1 datrix-common -Dbg` | Enable DEBUG level |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Coverage`, `-VerboseOutput`, `-NoSave`, `-NoAutoInstall`, `-SkipInstall`, `-Unit`, `-Integration`, `-E2E`, `-Fast`, `-Slow` (mutually exclusive), `-Specific <path>`, `-Keyword <expr>`, `-Dbg`

### `test\run-complete.ps1`

Complete workflow: syntax check, code generation, unit tests, deployment tests.

| Mode | Command | Description |
|------|---------|-------------|
| **Single (auto output)** | `.\test\run-complete.ps1 "examples/.../system.dtrx"` | Output derived from test-projects.json |
| **Single (explicit output)** | `.\test\run-complete.ps1 "examples/.../system.dtrx" ".generated/python/docker/..."` | Explicit output path |
| **Single + lang/platform** | `.\test\run-complete.ps1 "examples/.../system.dtrx" -L python -P docker` | Override language/platform |
| **All examples** | `.\test\run-complete.ps1 -All` | Full workflow for all |
| **Tutorials only** | `.\test\run-complete.ps1 -Tutorial` | Tutorial examples only |
| **Non-tutorial** | `.\test\run-complete.ps1 -NonTutorial` | Everything except tutorials |
| **Domains only** | `.\test\run-complete.ps1 -Domains` | Domain examples only |
| **Custom test set** | `.\test\run-complete.ps1 -TestSet tutorial01-10` | Named test set |
| **Skip syntax check** | `.\test\run-complete.ps1 -All -Skip1` | Skip Step 1 (syntax checker) |
| **Skip generation** | `.\test\run-complete.ps1 -All -Skip2` | Skip Step 2 (code generation) |
| **Skip unit tests** | `.\test\run-complete.ps1 -All -Skip4` | Skip Step 4 (generated unit tests) |
| **Skip deploy tests** | `.\test\run-complete.ps1 -All -Skip5` | Skip Step 5 (deploy/integration tests) |
| **Generate only (skip tests)** | `.\test\run-complete.ps1 -All -Skip4 -Skip5` | Steps 1-2 only |
| **Skip venv** | `.\test\run-complete.ps1 -All -SkipVenv` | Use system Python |
| **Debug** | `.\test\run-complete.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-ExamplePath` (positional 0), `-OutputPath` (positional 1), `-All`, `-Tutorial`, `-NonTutorial`, `-Domains`, `-Language`/`-L` (python\|typescript), `-Platform`/`-P` (docker\|kubernetes\|k8s), `-Hosting`/`-H`, `-TestSet` (default: generate-all), `-SkipVenv`, `-Skip1`, `-Skip2`, `-Skip4`, `-Skip5`, `-Dbg`/`-DebugLogging`

### `test\status-tests.ps1`

Reports test results from latest test logs for all datrix projects.

| Mode | Command |
|------|---------|
| **Show status** | `.\test\status-tests.ps1` |
| **With debug** | `.\test\status-tests.ps1 -Dbg` |

**Parameters:** `-Dbg`

### `test\status-deploy-tests.ps1`

Reports deployment test results from `.generated/` tree.

| Mode | Command |
|------|---------|
| **Show status** | `.\test\status-deploy-tests.ps1` |
| **With debug** | `.\test\status-deploy-tests.ps1 -Dbg` |

**Parameters:** `-Dbg`

### `test\status-run-tests.ps1`

Reports run test results from `.generated/` tree.

| Mode | Command |
|------|---------|
| **Show status** | `.\test\status-run-tests.ps1` |
| **With debug** | `.\test\status-run-tests.ps1 -Dbg` |

**Parameters:** `-Dbg`

### `test\cleanup.ps1`

Lists/deletes `.test_results` folders under each datrix project and `.generated/`.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\test\cleanup.ps1` | Show what would be deleted |
| **Delete** | `.\test\cleanup.ps1 -Force` | Delete after confirmation |
| **Custom base dir** | `.\test\cleanup.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Force`, `-Dbg`

---

## Git Operations

### `git\status.ps1`

Shows git status for all repositories under the workspace root.

| Mode | Command | Description |
|------|---------|-------------|
| **Summary** | `.\git\status.ps1` | Clean/has-changes per repo |
| **Detailed** | `.\git\status.ps1 -Detailed` | Branch, ahead/behind, changed files |

**Parameters:** `-Detailed`, `-Dbg`

### `git\pull.ps1`

Pulls all git repositories under the workspace root.

| Mode | Command |
|------|---------|
| **Pull all** | `.\git\pull.ps1` |

**Parameters:** `-Dbg`

### `git\commit-and-push.ps1`

Batch commits and pushes repos using messages from a JSON file. Format: `{ "datrix": "message", "datrix-common": "message", ... }`. Only repos with entries in the JSON are committed. Stops on first failure.

| Mode | Command | Description |
|------|---------|-------------|
| **Default file** | `.\git\commit-and-push.ps1` | Uses `commit-messages.json` in current dir |
| **Explicit file** | `.\git\commit-and-push.ps1 commit-messages.json` | Specified JSON file |
| **Absolute path** | `.\git\commit-and-push.ps1 D:\datrix\commit-messages.json` | Full path to JSON |

**Parameters:** `-MessagesPath` (positional, default: commit-messages.json), `-Dbg`

---

## Task Management

### `tasks\todo.ps1`

Lists incomplete tasks (without `COMPLETED:` prefix) and incomplete bugs (without `FIXED:` prefix) from `.tasks/` and `.bugs/` folders across all projects.

| Mode | Command | Description |
|------|---------|-------------|
| **List all** | `.\tasks\todo.ps1` | All incomplete tasks and bugs |
| **Filter** | `.\tasks\todo.ps1 -Filter "parser"` | Filter by filename or title (case-insensitive) |
| **Custom base dir** | `.\tasks\todo.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Filter`, `-Dbg`

### `tasks\completed.ps1`

Lists completed tasks (`COMPLETED:` prefix) and fixed bugs (`FIXED:` prefix) from `.tasks/` and `.bugs/` folders.

| Mode | Command | Description |
|------|---------|-------------|
| **List all** | `.\tasks\completed.ps1` | All completed tasks and fixed bugs |
| **Filter** | `.\tasks\completed.ps1 -Filter "parser"` | Filter by filename or title |
| **Custom base dir** | `.\tasks\completed.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Filter`, `-Dbg`

### `tasks\cleanup.ps1`

Lists/deletes task files from `.tasks/` folders. Optionally filters by phase number.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\tasks\cleanup.ps1` | Show all task files |
| **Delete all** | `.\tasks\cleanup.ps1 -Force` | Delete after confirmation |
| **Delete phases < N** | `.\tasks\cleanup.ps1 -Force -Phase 60` | Delete only phases before 60 |

**Parameters:** `-BaseDir`, `-Force`, `-Phase` (delete phases < N), `-Dbg`

### `tasks\latest-phase.ps1`

Returns the highest phase number found in `.tasks/` folders. Outputs only the number (for scripting).

| Mode | Command | Description |
|------|---------|-------------|
| **Get latest** | `.\tasks\latest-phase.ps1` | Outputs phase number only |
| **With debug** | `.\tasks\latest-phase.ps1 -Dbg` | Shows all found phases |
| **Custom base dir** | `.\tasks\latest-phase.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Dbg`

---

## Code Quality

### `metrics\complexity.ps1`

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

### `metrics\vulture.ps1`

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

### `metrics\dead_code_report.ps1`

Two-pass Vulture dead-code report: classifies findings as "never referenced" or "only referenced by tests".

| Mode | Command | Description |
|------|---------|-------------|
| **Default projects** | `.\metrics\dead_code_report.ps1` | Default 11 packages |
| **All projects** | `.\metrics\dead_code_report.ps1 -All` | All datrix-* projects |
| **Specific projects** | `.\metrics\dead_code_report.ps1 datrix-common datrix-language` | Selected projects |
| **JSON output** | `.\metrics\dead_code_report.ps1 -All -Output json` | JSON format |
| **High confidence** | `.\metrics\dead_code_report.ps1 -All -MinConfidence 100` | Only 100% confidence |
| **Save to file** | `.\metrics\dead_code_report.ps1 -All -OutputPath dead-code.md` | Write report to file |
| **Raw (no filters)** | `.\metrics\dead_code_report.ps1 -All -Raw` | Disable false-positive filters |
| **Quiet** | `.\metrics\dead_code_report.ps1 -All -OutputPath report.md -Quiet` | Only write to file |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-MinConfidence` (60-100, default: 60), `-Output` (text\|json), `-OutputPath`, `-VerboseOutput`, `-Raw`, `-Quiet`

### `metrics\ruff.ps1`

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

### `metrics\bandit.ps1`

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

### `metrics\duplicate.ps1`

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

### `metrics\coverage.ps1`

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

### `metrics\dependency.ps1`

Reports dependency relationships between Datrix packages (from pyproject.toml).

| Mode | Command | Description |
|------|---------|-------------|
| **All (tree)** | `.\metrics\dependency.ps1 -All` | Dependency tree for all packages |
| **All (list)** | `.\metrics\dependency.ps1 -All -Mode list` | Edge list (package -> dep) |
| **All (json)** | `.\metrics\dependency.ps1 -All -Mode json` | JSON format |
| **Specific packages** | `.\metrics\dependency.ps1 datrix-common datrix-language -Mode tree` | Selected packages |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (tree\|list\|json, default: tree), `-VerboseOutput`, `-Dbg`

### `metrics\large-files.ps1`

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

### `metrics\loc.ps1`

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

### `metrics\cleanup_ruff.ps1`

Cleans up Ruff check log files from `.ruff_check/` folders.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\metrics\cleanup_ruff.ps1` | Show all log files |
| **Delete all** | `.\metrics\cleanup_ruff.ps1 -Force` | Delete all log files |
| **Keep latest** | `.\metrics\cleanup_ruff.ps1 -Force -KeepLatest` | Delete old, keep latest per project |

**Parameters:** `-BaseDir`, `-Force`, `-KeepLatest`, `-Dbg`

---

## Anti-Pattern Scanners

### `dev\libcst.ps1`

Scans for anti-patterns using LibCST: silent-fallback, empty-except, missing-encoding, banned-test-import, placeholder-body.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\libcst.ps1 datrix-common` | Scan one project |
| **Multiple projects** | `.\dev\libcst.ps1 datrix-common datrix-language` | Scan several |
| **All projects** | `.\dev\libcst.ps1 -All` | Scan entire monorepo |
| **With report** | `.\dev\libcst.ps1 -All -Report libcst-report.md` | Write markdown report |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Report <path>`

### `dev\semgrep.ps1`

Runs Semgrep with Datrix-specific rules from `scripts/config/semgrep-rules/`.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\semgrep.ps1 datrix-common` | All rules on one project |
| **All projects** | `.\dev\semgrep.ps1 -All` | All rules on all projects |
| **Single rule** | `.\dev\semgrep.ps1 -All -Rule empty-except-pass` | One specific rule |
| **Multiple rules** | `.\dev\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup` | Selected rules |
| **List rules** | `.\dev\semgrep.ps1 -ListRules` | Show available rule names |
| **With report** | `.\dev\semgrep.ps1 -All -Report semgrep-report.md` | Write markdown report |
| **Show raw output** | `.\dev\semgrep.ps1 -All -ShowRaw` | Show raw semgrep output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rule <name>` (repeatable), `-ListRules`, `-Report <path>`, `-ShowRaw`

### `dev\ruff-checker.ps1`

Checks Jinja2 templates by rendering with mock values and running ruff. No parameters.

| Mode | Command |
|------|---------|
| **Check templates** | `.\dev\ruff-checker.ps1` |

**Parameters:** (none)

---

## Development

### `dev\projects.ps1`

Lists Datrix project directories and subfolders.

| Mode | Command | Description |
|------|---------|-------------|
| **Project names** | `.\dev\projects.ps1` | List all project directory names |
| **Src paths** | `.\dev\projects.ps1 -Src` | Full path to each project's src/ |
| **Tests paths** | `.\dev\projects.ps1 -Tests` | Full path to each project's tests/ |
| **Docs paths** | `.\dev\projects.ps1 -Docs` | Full path to each project's docs/ |

**Parameters:** `-Src`, `-Tests`, `-Docs`

### `dev\compile.ps1`

Compiles all Python in Datrix project folders (syntax + import check, including cross-project).

| Mode | Command | Description |
|------|---------|-------------|
| **All projects** | `.\dev\compile.ps1 -All` | Check all datrix repos |
| **One project** | `.\dev\compile.ps1 datrix-common` | Check one project |
| **Multiple projects** | `.\dev\compile.ps1 datrix-common datrix-language` | Check several |
| **By full path** | `.\dev\compile.ps1 D:\datrix\datrix-common` | Full path input |
| **With debug** | `.\dev\compile.ps1 -All -Dbg` | Debug output |

**Parameters:** `-All`, `-ProjectDir` (positional, variadic), `-Dbg`

### `dev\compile-any-path.ps1`

Syntax + import check for any Python path (files, directories, subfolders). Unlike `compile.ps1`, works for arbitrary paths (e.g., a routes folder inside generated code). Finds the containing installable package and runs that package's full import check.

| Mode | Command | Description |
|------|---------|-------------|
| **Directory** | `.\dev\compile-any-path.ps1 .\.generated\...\routes` | Check a subfolder |
| **Src dir** | `.\dev\compile-any-path.ps1 D:\datrix\datrix-common\src` | Check a src directory |
| **Multiple paths** | `.\dev\compile-any-path.ps1 path1 path2` | Check multiple paths |
| **With debug** | `.\dev\compile-any-path.ps1 path -Dbg` | Debug output |

**Parameters:** `-Path` (positional, variadic), `-Dbg`

### `dev\rebuild-parser.ps1`

Rebuilds the tree-sitter parser from `grammar.js`.

| Mode | Command | Description |
|------|---------|-------------|
| **Rebuild** | `.\dev\rebuild-parser.ps1` | Rebuild if grammar changed |
| **Force rebuild** | `.\dev\rebuild-parser.ps1 -Force` | Rebuild even if unchanged |

**Parameters:** `-Force`

### `dev\audit.ps1`

Audits generated Python code for placeholders and syntax errors under `.generated/python/docker`.

| Mode | Command | Description |
|------|---------|-------------|
| **With report** | `.\dev\audit.ps1 -Report examples-generated-audit-report.md` | Write markdown report |
| **Fail on issues** | `.\dev\audit.ps1 -Report report.md -FailOnSyntax -FailOnPlaceholders` | Non-zero exit on issues |
| **Custom output base** | `.\dev\audit.ps1 -OutputBase .generated2 -Report report.md` | Different generated root |

**Parameters:** `-OutputBase` (default: .generated), `-Report <path>`, `-FailOnSyntax`, `-FailOnPlaceholders`

### `dev\compare-generated.ps1`

Compares `.generated` vs `.generated_saved` with content-level feature detection. Writes a markdown report.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\dev\compare-generated.ps1` | Compare defaults, write report |
| **Custom report** | `.\dev\compare-generated.ps1 -Report my-report.md` | Custom report path |
| **Custom dirs** | `.\dev\compare-generated.ps1 -Current .generated -Saved .generated_saved` | Explicit directories |

**Parameters:** `-Current` (default: .generated), `-Saved` (default: .generated_saved), `-Report` (default: generated-comparison-report.md)

### `dev\run-codemod.ps1`

Runs a Bowler codemod from `scripts/dev/codemods/`. All arguments after codemod name are passed through.

| Mode | Command | Description |
|------|---------|-------------|
| **Rename function** | `.\dev\run-codemod.ps1 01_rename_function parse_file parse_path` | Preview diff |
| **Rename class** | `.\dev\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src` | Rename in path |
| **Rename imports** | `.\dev\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src` | Update imports |

**Parameters:** `-CodemodName` (positional 0, required), `-CodemodArgs` (positional, variadic)

### `dev\datrix-count.ps1`

Counts `.dtrx` and `.dtrx.false` files across all datrix project directories.

| Mode | Command |
|------|---------|
| **Count** | `.\dev\datrix-count.ps1` |

**Parameters:** (none)

### `dev\file-count.ps1`

Counts files with a specified extension across all datrix project directories.

| Mode | Command | Description |
|------|---------|-------------|
| **Default (.j2)** | `.\dev\file-count.ps1` | Count Jinja2 template files |
| **Python files** | `.\dev\file-count.ps1 py` | Count .py files |
| **Any extension** | `.\dev\file-count.ps1 exe` | Count .exe files |

**Parameters:** `-Extension` (positional, default: j2)

---

## Cleanup

### `dev\cleanup_temps.ps1`

Lists/deletes temporary cache folders and files across the monorepo (`.pytest_cache`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.coverage`, etc.).

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\dev\cleanup_temps.ps1` | Show cache items with sizes |
| **Delete** | `.\dev\cleanup_temps.ps1 -Force` | Delete after confirmation |
| **Extra folders** | `.\dev\cleanup_temps.ps1 -Force -AdditionalFolders ".coverage","__pycache__"` | Add extra folder names |
| **Custom base** | `.\dev\cleanup_temps.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Force`, `-AdditionalFolders`, `-Dbg`

### `dev\delete-generated.ps1`

Renames `.generated` to `.generated_old` (or `_old_01` through `_old_99`) then deletes the renamed folder in a background job.

| Mode | Command | Description |
|------|---------|-------------|
| **Background delete** | `.\dev\delete-generated.ps1` | Rename + async delete |
| **Wait for delete** | `.\dev\delete-generated.ps1 -Wait` | Synchronous deletion |
| **Custom base** | `.\dev\delete-generated.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Wait`

### `dev\empty-folders.ps1`

Finds and lists all empty folders recursively from a given path.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\dev\empty-folders.ps1` | Find empty folders in current dir |
| **Custom path** | `.\dev\empty-folders.ps1 -Path D:\datrix` | Specific directory |
| **Delete** | `.\dev\empty-folders.ps1 -Force` | Delete after confirmation |
| **Delete at path** | `.\dev\empty-folders.ps1 -Path D:\datrix -Force` | Delete at specific path |

**Parameters:** `-Path` (default: current directory), `-Force`, `-Dbg`

---

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
- `datrix-codegen-k8s`
- `datrix-codegen-aws`
- `datrix-codegen-azure`
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
| Test logs | `<project>/.test_results/` |
| Ruff check logs | `<project>/.ruff_check/` |
| Test config | `scripts/config/test-projects.json` |
| Semgrep rules | `scripts/config/semgrep-rules/` |
| Metrics scripts | `scripts/metrics/` |
| Anti-pattern scanners | `scripts/dev/libcst.ps1`, `scripts/dev/semgrep.ps1` |
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
.\dev\generate.ps1 -Tutorial
.\test\test.ps1 datrix-codegen-python
```

### Single Example End-to-End
```powershell
.\test\run-complete.ps1 "examples/01-tutorial/01-basic-entity/system.dtrx"
```

### Generate Single + Validate
```powershell
.\dev\generate.ps1 examples/01-tutorial/03-basic-api/system.dtrx
.\dev\compile-any-path.ps1 .\.generated\python\docker\01-tutorial\03-basic-api\library_book_service\src
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

### Full Cleanup
```powershell
.\dev\cleanup_temps.ps1 -Force
.\test\cleanup.ps1 -Force
.\metrics\cleanup_ruff.ps1 -Force
.\dev\delete-generated.ps1
```

### Check Generation Status
```powershell
.\dev\status-generation.ps1
.\test\status-tests.ps1
.\test\status-deploy-tests.ps1
```
