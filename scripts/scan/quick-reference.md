# Quick Reference — Scan Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each scan detects, the rule catalogues, the ratchet and self-test details: [README.md](README.md).

Static checks over source: `.dtrx`/`.dcfg` syntax and formatting, anti-pattern scanners, import boundaries and their ratchets, compile/import checks, generated-output audits, code-structure reports. Every script takes `-SelfTest` and has a POSIX twin `scan\<name>.sh` with `--kebab` flags.

**Whole-package scans are phase-boundary acts.** Inside a fix, run `semgrep.ps1`/`libcst.ps1`/`ast-grep.ps1` only with a named `-Rule` (or `-Pattern`, or `-SelfTest`) or a stated `SCAN_QUESTION:`. `guard-untargeted-scans.py` refuses the rest, also for their `.sh` twins and `python -m datrix_scripts.scan.{semgrep,libcst,ast_grep}` (reading `--rule` / `--pattern` / `--all` / `--self-test`). `-Rule`, `-All` and their `--kebab` forms keep exactly these spellings.

## DSL and Config

### `scan\syntax-checker.ps1`

Validate `.dtrx` syntax with the tree-sitter parser.

| Form | Command |
|------|---------|
| All repos | `.\scan\syntax-checker.ps1` |
| One file | `.\scan\syntax-checker.ps1 path/to/file.dtrx` |
| A directory | `.\scan\syntax-checker.ps1 examples/` |

Parameters: `-Path` (positional, default all repos), `-Dbg`, `-SelfTest`

### `scan\config-linter.ps1`

Lint and format `.dcfg` config documents.

| Form | Command |
|------|---------|
| Format all repos | `.\scan\config-linter.ps1 -All` |
| Check only, no writes | `.\scan\config-linter.ps1 -All -Check` |
| A directory | `.\scan\config-linter.ps1 examples\01-foundation\config` |
| One file, check | `.\scan\config-linter.ps1 path\to\system.dcfg -Check` |

Parameters: `-All`, `-Path` (positional, variadic), `-Check`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed.

### `scan\datrix-linter.ps1` and `scan\datrix-format.ps1`

`datrix-linter.ps1`: full semantic analysis of every `system.dtrx` entry point under the paths, each diagnostic reported; exit 1 on an error (a warning under `-Strict`). `datrix-format.ps1`: lossless `.dtrx` formatting (as `datrix format`), writing nothing if any file fails. `Get-Help .\scan\<script>.ps1 -Full` lists parameters.

| Form | Command |
|------|---------|
| Lint | `.\scan\datrix-linter.ps1 examples` |
| Format check | `.\scan\datrix-format.ps1 -All -Check` |

Parameters (options of the modules): linter `-Path`, `-All`, `-Strict`, `-Dbg`, `-ResolveConfigs`, `-Profile`, `-SelfTest`; formatter `-Path`, `-All`, `-Check`, `-Diff`, `-IndentSize`, `-Dbg`, `-SelfTest`

## Anti-Pattern Scanners

### `scan\libcst.ps1`

LibCST scan: silent-fallback, empty-except, missing-encoding, banned-test-import, placeholder-body.

| Form | Command |
|------|---------|
| One project | `.\scan\libcst.ps1 datrix-common` |
| Several | `.\scan\libcst.ps1 datrix-common datrix-language` |
| Whole monorepo | `.\scan\libcst.ps1 -All` |
| Markdown report | `.\scan\libcst.ps1 -All -Report libcst-report.md` |

Parameters: `-Projects` (positional, variadic), `-All`, `-Report <path>`, `-SelfTest`

### `scan\semgrep.ps1`

Semgrep with the rules of `scripts/config/semgrep-rules/`. One `-Rule` takes ~2-3 minutes; every rule ~20-25.

| Form | Command |
|------|---------|
| One project | `.\scan\semgrep.ps1 datrix-common` |
| One rule | `.\scan\semgrep.ps1 -All -Rule empty-except-pass` |
| Several rules | `.\scan\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup` |
| List rule names | `.\scan\semgrep.ps1 -ListRules` |
| Markdown report | `.\scan\semgrep.ps1 -All -Report semgrep-report.md` |
| Raw output | `.\scan\semgrep.ps1 -All -ShowRaw` |

Parameters: `-Projects` (positional, variadic), `-All`, `-Rule <name>` (repeatable), `-ListRules`, `-Report <path>`, `-ShowRaw`, `-SinglePass`, `-SelfTest`

### `scan\ast-grep.ps1`

ast-grep structural rules from `scripts/config/ast-grep-rules/`, or a one-off pattern. Single-quote metavariable patterns (`'$MSG'`) so PowerShell does not expand them.

| Form | Command |
|------|---------|
| One project | `.\scan\ast-grep.ps1 datrix-common` |
| One rule | `.\scan\ast-grep.ps1 -All -Rule empty-except-pass` |
| Several rules | `.\scan\ast-grep.ps1 -All -Rule empty-except-pass -Rule placeholder-notimplemented-body` |
| One-off pattern | `.\scan\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'` |
| List rule names | `.\scan\ast-grep.ps1 -ListRules` |
| Markdown report | `.\scan\ast-grep.ps1 -All -Report ast-grep-report.md` |
| Raw output | `.\scan\ast-grep.ps1 -All -Rule empty-except-pass -ShowRaw` |

Parameters: `-Projects` (positional, variadic), `-All`, `-Pattern <pattern>`, `-Rule <name>` (repeatable), `-ListRules`, `-Report <path>`, `-ShowRaw`, `-SelfTest`

### `scan\check-debug-artifacts.ps1`

Leftover debug artifacts (print, breakpoint, console.log, debugger, temp comments). A pre-commit check.

| Form | Command |
|------|---------|
| One project | `.\scan\check-debug-artifacts.ps1 datrix-codegen-python` |
| Whole monorepo | `.\scan\check-debug-artifacts.ps1 -All` |
| Also logger.debug/info with f-strings | `.\scan\check-debug-artifacts.ps1 -All -Strict` |
| Show matching lines | `.\scan\check-debug-artifacts.ps1 datrix-common -Dbg` |

Parameters: `-ProjectDir` (positional, variadic), `-All`, `-Strict`, `-IncludeGenerated`, `-SelfTest`, `-Dbg`. Exit: 0 clean, 1 artifacts found, 2 usage error or self-test failure.

### `scan\check-python-bytecode.ps1` and `scan\extra-parens.ps1`

`check-python-bytecode.ps1`: fails on `.pyc`/`.pyo` files or `__pycache__` directories under a package's `src/`. `extra-parens.ps1`: removes extraneous parentheses (Ruff `UP034` only). `Get-Help .\scan\<script>.ps1 -Full` lists parameters.

| Form | Command |
|------|---------|
| Bytecode check | `.\scan\check-python-bytecode.ps1 -ProjectDir datrix-common` |
| Preview paren fixes | `.\scan\extra-parens.ps1 -All -DryRun` |

Parameters (options of the modules): bytecode `-BaseDir`, `-ProjectDir`, `-SelfTest`; parens `-Projects`, `-All`, `-DryRun`, `-Diff`, `-SelfTest`

### `scan\ruff-checker.ps1`

Render Jinja2 Python templates with mock values and run ruff on the output. Report: `D:\datrix\.test-output\ruff-checker\ruff-report-<yyyyMMdd-HHmmss>.txt`.

| Form | Command |
|------|---------|
| Templates under the current directory | `.\scan\ruff-checker.ps1` |
| One template folder | `.\scan\ruff-checker.ps1 -TemplatesDir D:\datrix\datrix-codegen-python\src\datrix_codegen_python\templates` |

Parameters: `-TemplatesDir` (default current directory), `-Dbg`, `-SelfTest`

## Import Boundaries

### `scan\check-import-boundaries.ps1`

Enforce cross-package import boundaries (AST analysis of each package's `src/`, `tests/`, `fixtures/`, `helpers/`; rule table in [import-boundaries.md](../../../datrix-common/docs/architecture/import-boundaries.md)), plus the ratchets below. Each ratchet compares against a frozen baseline in `scripts/config/`; add `-UpdateBaseline` to re-freeze it (a baseline only goes down). The self-test runs as step 1 of every invocation.

| Form | Command |
|------|---------|
| Boundaries, exit 1 on any violation | `.\scan\check-import-boundaries.ps1` |
| Warn only, exit 0 | `.\scan\check-import-boundaries.ps1 -Warn` |
| Other workspace | `.\scan\check-import-boundaries.ps1 -BaseDir D:\other` |
| Print each file scanned | `.\scan\check-import-boundaries.ps1 -ShowFiles` |
| Target-literal ratchet | `.\scan\check-import-boundaries.ps1 -CheckTargetLiterals` |
| Provider-conditional ratchet (+ zero-tolerance shared packages) | `.\scan\check-import-boundaries.ps1 -CheckProviderConditionals` |
| Function-level-import ratchet | `.\scan\check-import-boundaries.ps1 -CheckFunctionLevelImports` |
| Shared-vocabulary ratchet | `.\scan\check-import-boundaries.ps1 -CheckSharedVocabulary` |
| Shared-layer target-name ratchet | `.\scan\check-import-boundaries.ps1 -CheckSharedTargetNames` |
| Shared-prose platform-name ratchet | `.\scan\check-import-boundaries.ps1 -CheckSharedProsePlatformNames` |
| Own-package target-name ratchet | `.\scan\check-import-boundaries.ps1 -CheckOwnTargetNames` |
| Cross-package vocabulary ratchet | `.\scan\check-import-boundaries.ps1 -CheckCrossPackageVocabulary` |
| Re-export-facade check (hard zero, no baseline) | `.\scan\check-import-boundaries.ps1 -CheckReexportFacades` |
| Facade per-site worklist | `.\scan\check-import-boundaries.ps1 -CheckReexportFacades -ShowFiles -FacadeModule datrix_common.errors -ConsumerPackage datrix-codegen-python` |
| Re-freeze one ratchet's baseline | `.\scan\check-import-boundaries.ps1 -CheckTargetLiterals -UpdateBaseline` |
| Self-test only | `.\scan\check-import-boundaries.ps1 -SelfTest` |

`-CheckFunctionLevelImports`, `-CheckCrossPackageVocabulary` and `-CheckReexportFacades` also run on every invocation that is not `-SelfTest` or `-UpdateBaseline`. `-UpdateBaseline` has no effect on the facade check.

Parameters: `-Warn`, `-ShowFiles`, `-BaseDir`, `-CheckTargetLiterals`, `-UpdateBaseline`, `-CheckProviderConditionals`, `-CheckFunctionLevelImports`, `-CheckSharedVocabulary`, `-CheckSharedTargetNames`, `-CheckSharedProsePlatformNames`, `-CheckOwnTargetNames`, `-CheckCrossPackageVocabulary`, `-CheckReexportFacades`, `-FacadeModule`, `-ConsumerPackage`, `-SelfTest`, `-Dbg`. Exit: 0 clean (or warning mode), 1 violations or a self-test failure, 2 usage or config error (including a ratchet flag with no frozen baseline yet).

## Compile and Audit

### `scan\compile.ps1`

Syntax (`py_compile`) and import check of Python: named Datrix projects, or any file or directory (it finds the containing package and runs its full import check).

| Form | Command |
|------|---------|
| All projects | `.\scan\compile.ps1 -All` |
| One project | `.\scan\compile.ps1 datrix-common` |
| Several | `.\scan\compile.ps1 datrix-common datrix-language` |
| Full path | `.\scan\compile.ps1 D:\datrix\datrix-common` |
| Any path (generated code, say) | `.\scan\compile.ps1 -Path .\.generated\...\routes` |
| Several paths | `.\scan\compile.ps1 -Path path1,path2` |

Parameters: Projects set `-All`, `-ProjectDir` (positional, variadic); Path set `-Path` (one or more); both `-Dbg`; SelfTest set `-SelfTest`

### `scan\audit.ps1`

Audit generated Python under `.generated/python/docker` for placeholders and syntax errors.

| Form | Command |
|------|---------|
| Markdown report | `.\scan\audit.ps1 -Report examples-generated-audit-report.md` |
| Non-zero exit on issues | `.\scan\audit.ps1 -Report report.md -FailOnSyntax -FailOnPlaceholders` |
| Other generated root | `.\scan\audit.ps1 -OutputBase .generated2 -Report report.md` |

Parameters: `-OutputBase` (default `.generated`), `-Report <path>`, `-FailOnSyntax`, `-FailOnPlaceholders`, `-LlmTriage`, `-LlmLimit`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout`, `-LlmNumPredict`, `-LlmTemperature`, `-SelfTest`

### `scan\dgen-census.ps1`

Per-domain census of a language's compiled DAL generator definitions, listing double-emit offenders (declares files and keeps a domain builder) → `D:\datrix\.tmp\dev\dgen-census-<language>.json`.

| Form | Command |
|------|---------|
| Census a target | `.\scan\dgen-census.ps1 -Language python` |
| Self-test only | `.\scan\dgen-census.ps1 -SelfTest` |

Parameters: `-Language <name>` (required unless `-SelfTest`; an unknown target fails listing the installed ones), `-Output <path>`, `-Dbg`, `-SelfTest`. Exit: 0 no offenders, 1 offenders found, 2 usage, unknown target or self-test failure.

## Code Structure Reports

### `scan\find-duplicate-bodies.ps1`

Whole function bodies duplicated across every `datrix-*` package's `src/` (exact and renamed copies). Report only; similar runs of lines are `metrics\duplicate.ps1`.

| Form | Command |
|------|---------|
| Cross-package groups (largest 25) | `.\scan\find-duplicate-bodies.ps1 -CrossPackage` |
| One package | `.\scan\find-duplicate-bodies.ps1 -Package datrix_codegen_python -Limit 0` |
| JSON | `.\scan\find-duplicate-bodies.ps1 -Limit 0 -JsonOut D:\datrix\.tmp\duplicate-bodies.json` |

Parameters: `-CrossPackage`, `-Package <import name,...>`, `-Limit <n>` (default 25; 0 = all), `-JsonOut <path>`, `-Dbg`, `-SelfTest`. Exit: 0 report printed, 1 package install check failed, 2 a source file did not parse or bad argument.

### `scan\find-unimplemented-abstracts.ps1`

Classes that inherit abstract methods they never implement (INCOMPLETE leaves).

| Form | Command |
|------|---------|
| All packages | `.\scan\find-unimplemented-abstracts.ps1` |
| One package, with the intended abstract bases | `.\scan\find-unimplemented-abstracts.ps1 -Package datrix_codegen_python -ShowBases` |

Parameters: `-Package <import name,...>` (default every `datrix-*` package), `-ShowBases`, `-Dbg`, `-SelfTest`. Exit: 0 none incomplete, 1 incomplete class(es) or install check failed, 2 a module failed to import or bad argument.
