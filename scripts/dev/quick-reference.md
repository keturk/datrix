# Quick Reference — Development Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## Code Generation

### `dev\generate.ps1`

Generates Datrix projects from `.dtrx` source files. `-Language`/`-L` is **mandatory** — you must always specify the target language. `-Platform`/`-P` controls output-path derivation (default: docker). Use `-Hosting`/`-H` to pass `--hosting` and `-ServicePlatform` to pass `--platform` (service flavor: compose, ecs-fargate, etc.).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project (auto output)** | `.\dev\generate.ps1 <source.dtrx> -L python` | Output path derived from test-projects.json |
| **Single project (explicit output)** | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python` | Explicit output directory |
| **Single + language/platform** | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L typescript -P kubernetes` | Override language and platform |
| **Single + hosting/flavor** | `.\dev\generate.ps1 <source.dtrx> <out> -L python -H kubernetes -ServicePlatform kubernetes` | Override hosting and service platform |
| **All examples** | `.\dev\generate.ps1 -All -L python` | Generate all (test set all) |
| **All + TypeScript** | `.\dev\generate.ps1 -All -L typescript` | All examples for TypeScript |
| **All + custom output base** | `.\dev\generate.ps1 -All -L python -OutputBase .generated2` | Custom output root |
| **Foundation only** | `.\dev\generate.ps1 -TestSet foundation -L python` | examples/01-foundation |
| **Non-foundation only** | `.\dev\generate.ps1 -TestSet non-foundation -L python` | Everything except foundation examples |
| **Domains only** | `.\dev\generate.ps1 -Domains -L python` | examples/03-domains |
| **Custom test set** | `.\dev\generate.ps1 -TestSet features-core -L python` | Any named test set |
| **TypeScript validation subset** | `.\dev\generate.ps1 -TestSet typescript-validation -L typescript` | Quick TS validation |
| **Debug logging** | `.\dev\generate.ps1 -All -L python -Dbg` | Enable DEBUG level logging |

**Parameters:** `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (python\|typescript, **mandatory**), `-Platform`/`-P` (docker\|kubernetes\|k8s, default: docker), `-Hosting`/`-H`, `-ServicePlatform`, `-OutputBase` (default: .generated), `-TestSet` (default: all), `-Dbg`

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

### `dev\generate-doc-fragments.ps1`

Generates documentation fragments from source code. Extracts semantic pipeline stages (from `SemanticAnalyzer.analyze()` via AST parsing) and CLI help output (from `datrix generate --help`) into markdown files under `datrix/docs/generated/`.

| Mode | Command | Description |
|------|---------|-------------|
| **All fragments** | `.\dev\generate-doc-fragments.ps1` | Generate all fragments |
| **Semantic only** | `.\dev\generate-doc-fragments.ps1 semantic-pipeline` | Generate pipeline stages only |
| **CLI help only** | `.\dev\generate-doc-fragments.ps1 cli-help` | Generate CLI help only |
| **Check mode** | `.\dev\generate-doc-fragments.ps1 -Check` | Verify fragments are up-to-date (non-zero exit if stale) |
| **With debug** | `.\dev\generate-doc-fragments.ps1 -Dbg` | Show detailed output |

**Parameters:** `-Fragment` (positional 0: all\|semantic-pipeline\|cli-help, default: all), `-Check`, `-Dbg`

---

## Documentation Checks

### `dev\check-docs.ps1`

Lints documentation for common drift patterns: deprecated CLI flags, fixed phase counts, CDX doc naming/structure, missing capability status labels.

| Mode | Command | Description |
|------|---------|-------------|
| **All checks** | `.\dev\check-docs.ps1` | Run all docs lint checks |
| **Specific check** | `.\dev\check-docs.ps1 -Check deprecated-cli-flags` | Run one check |
| **Multiple checks** | `.\dev\check-docs.ps1 -Check cdx-filenames -Check cdx-structure` | Run selected checks |
| **Detailed output** | `.\dev\check-docs.ps1 -Detailed` | Show content and suggestions |
| **Custom docs dir** | `.\dev\check-docs.ps1 path\to\docs` | Scan specific directory |
| **Debug** | `.\dev\check-docs.ps1 -Dbg` | Debug logging |

**Parameters:** `-DocsDir` (positional, variadic — defaults to all monorepo docs/), `-Check` (deprecated-cli-flags\|fixed-phase-count\|cdx-filenames\|cdx-structure\|capability-status-labels, repeatable), `-Detailed`, `-Dbg`

**Exit codes:** 0 = clean, 1 = lint failures found

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

### `dev\check-debug-artifacts.ps1`

Detects leftover debug/logging artifacts in source code (print, breakpoint, console.log, debugger, temp comments). Use as a pre-commit check to catch debug scatter.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\check-debug-artifacts.ps1 datrix-codegen-python` | Scan one project |
| **All projects** | `.\dev\check-debug-artifacts.ps1 -All` | Scan entire monorepo |
| **Strict mode** | `.\dev\check-debug-artifacts.ps1 -All -Strict` | Also flag logger.debug/info with f-strings |
| **With details** | `.\dev\check-debug-artifacts.ps1 datrix-common -Dbg` | Show matching line content |

**Parameters:** `-ProjectDir` (positional, variadic), `-All`, `-Strict`, `-IncludeGenerated`, `-Dbg`

**Exit codes:** 0 = clean, 1 = artifacts found, 2 = usage error

### `dev\check-import-boundaries.ps1`

Enforces cross-package import boundary rules across the monorepo. Scans each package's `src/`, `tests/`, `fixtures/`, and `helpers/` directories for forbidden imports using Python AST analysis. See [Import Boundaries](../../../datrix-common/docs/architecture/import-boundaries.md) for the full rule table.

| Mode | Command | Description |
|------|---------|-------------|
| **Fail mode** | `.\dev\check-import-boundaries.ps1` | Report violations, exit 1 on any |
| **Warning mode** | `.\dev\check-import-boundaries.ps1 -Warn` | Report violations, exit 0 |
| **Custom base dir** | `.\dev\check-import-boundaries.ps1 -BaseDir D:\other` | Different workspace |
| **Show files** | `.\dev\check-import-boundaries.ps1 -ShowFiles` | Print each file being scanned |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-Dbg`

**Exit codes:** 0 = clean (or warning mode), 1 = violations found

### `dev\triage-failures.ps1`

Parses test/generation logs and groups failures by likely root cause. Produces a triage report suitable for feeding into `/fix-tests` or `/checkpoint-debug`.

| Mode | Command | Description |
|------|---------|-------------|
| **Parse log** | `.\dev\triage-failures.ps1 "path/to/results.log"` | Auto-detect format, output to stdout |
| **Force format** | `.\dev\triage-failures.ps1 "path/to/output.log" -Format pytest` | Force pytest parser |
| **Save report** | `.\dev\triage-failures.ps1 "path/to/results.log" -OutputFile "triage.md"` | Write Markdown report |
| **Debug** | `.\dev\triage-failures.ps1 "path/to/results.log" -Dbg` | Show auto-detect reasoning |

**Parameters:** `-LogPath` (positional 0, mandatory), `-Format` (pytest\|generate\|deploy), `-OutputFile <path>`, `-Dbg`

**Supported formats:** pytest output, generation result logs, deploy test logs. Auto-detected from file content.

### `dev\ruff-checker.ps1`

Checks Jinja2 templates by rendering with mock values and running ruff. No parameters.

| Mode | Command |
|------|---------|
| **Check templates** | `.\dev\ruff-checker.ps1` |

**Parameters:** (none)

---

## Build & Compile

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

---

## Audit & Comparison

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

---

## Utilities

### `dev\projects.ps1`

Lists Datrix project directories and subfolders.

| Mode | Command | Description |
|------|---------|-------------|
| **Project names** | `.\dev\projects.ps1` | List all project directory names |
| **Src paths** | `.\dev\projects.ps1 -Src` | Full path to each project's src/ |
| **Tests paths** | `.\dev\projects.ps1 -Tests` | Full path to each project's tests/ |
| **Docs paths** | `.\dev\projects.ps1 -Docs` | Full path to each project's docs/ |

**Parameters:** `-Src`, `-Tests`, `-Docs`

### `dev\project-structure.ps1`

Generates `.project-structure.md` files containing annotated ASCII directory trees (src/, tests/, templates/) for specified projects.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\project-structure.ps1 datrix-codegen-typescript` | Generate for one project |
| **Multiple projects** | `.\dev\project-structure.ps1 datrix-codegen-typescript datrix-codegen-python` | Generate for several |
| **All projects** | `.\dev\project-structure.ps1 -All` | All projects with src/ or tests/ |
| **Custom depth** | `.\dev\project-structure.ps1 datrix-codegen-typescript -Depth 6` | Deeper tree traversal |
| **Debug** | `.\dev\project-structure.ps1 datrix-codegen-typescript -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Depth` (default: 4), `-Dbg`

**Output:** Writes `.project-structure.md` to each project's root directory. File is gitignored.

### `dev\logic-map.ps1`

Extracts logic map markers from Python source files into a SQLite database (`d:\datrix\.logic-map\markers.db`). Markers are structured comments (`@canonical`, `@pattern`, `@boundary`, `@invariant`) that document canonical implementations and patterns.

| Mode | Command | Description |
|------|---------|-------------|
| **All projects** | `.\dev\logic-map.ps1 -All` | Rebuild entire database |
| **One project** | `.\dev\logic-map.ps1 datrix-language` | Scan one project |
| **Multiple projects** | `.\dev\logic-map.ps1 datrix-language datrix-common` | Scan several |
| **Src only** | `.\dev\logic-map.ps1 -All -Src` | Only src/ directories |
| **Tests only** | `.\dev\logic-map.ps1 -All -Tests` | Only tests/ directories |
| **Debug** | `.\dev\logic-map.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Src`, `-Tests`, `-Dbg`

### `dev\logic-map-report.ps1`

Dumps the logic map SQLite database to a readable Markdown report for human verification.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\dev\logic-map-report.ps1` | Write logic-map-report.md to current dir |
| **Custom output** | `.\dev\logic-map-report.ps1 -Output docs\logic-map.md` | Custom output path |

**Parameters:** `-Output` (positional 0)

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
