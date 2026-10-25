# Quick Reference — Code Quality & Metrics Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each script measures, its module and self-test: [README.md](README.md).

Project scripts take `-Projects` (positional, variadic) or `-All`. Every script takes `-SelfTest`; each has a POSIX twin `metrics\<name>.sh`.

## `metrics\complexity.ps1`

Radon cyclomatic and cognitive complexity, raw, Halstead, maintainability index.

| Form | Command |
|------|---------|
| Check one project (max 15) | `.\metrics\complexity.ps1 datrix-common` |
| Check all | `.\metrics\complexity.ps1 -All` |
| Check exactly these files | `.\metrics\complexity.ps1 -Files a.py,b.py` |
| Custom max | `.\metrics\complexity.ps1 datrix-language -Max 10` |
| Cyclomatic report | `.\metrics\complexity.ps1 datrix-common -Mode cc` |
| Raw / Halstead / MI | `.\metrics\complexity.ps1 datrix-common -Mode raw` (`halstead`, `mi`) |
| Fix worst violation with a local model | `.\metrics\complexity.ps1 datrix-common -Fix` |
| Fix and verify with pytest | `.\metrics\complexity.ps1 datrix-common -Fix -Test` |

Parameters: `-Projects`, `-All`, `-Files <path,...>` (mode check only; not with `-Fix`, `-FixAll`, `-All` or project names), `-Mode` (check\|cc\|raw\|halstead\|mi, default check), `-Max` (default 15), `-Fix`, `-FixAll`, `-Test` (with `-Fix`), `-MaxRetries` (default 3), `-LocalMachines`, `-Model`, `-LlmTimeout` (default 180), `-LlmNumPredict` (default 4096), `-LlmTemperature` (default 0.1), `-MaxContextChars` (default 8000), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

## `metrics\error-messages.ps1`

Score error messages for context, suggestions and valid options; optional local-model fix.

| Form | Command |
|------|---------|
| Check one project (min score 2) | `.\metrics\error-messages.ps1 datrix-common` |
| Check all | `.\metrics\error-messages.ps1 -All` |
| Stricter | `.\metrics\error-messages.ps1 -All -MinScore 3` |
| Report every site | `.\metrics\error-messages.ps1 datrix-common -Mode report` |
| Also list skipped sites | `.\metrics\error-messages.ps1 datrix-common -Mode report -VerboseOutput` |
| Fix worst violation | `.\metrics\error-messages.ps1 datrix-common -Fix` |
| Fix all, verified | `.\metrics\error-messages.ps1 datrix-common -FixAll -Test` |

Parameters: `-Projects`, `-All`, `-Mode` (check\|report, default check), `-MinScore` (default 2), `-Fix`, `-FixAll` (both need `-Mode check`), `-Test`, `-MaxRetries` (default 3), `-LocalMachines`, `-Model`, `-LlmTimeout` (default 300), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

## `metrics\dead-code-report.ps1`

Two-pass Vulture report: "never referenced" vs "only referenced by tests".

| Form | Command |
|------|---------|
| Every `datrix-*` package | `.\metrics\dead-code-report.ps1` |
| Specific projects | `.\metrics\dead-code-report.ps1 datrix-common .\datrix-language\` |
| JSON | `.\metrics\dead-code-report.ps1 -All -Output json` |
| High confidence only | `.\metrics\dead-code-report.ps1 -All -MinConfidence 100` |
| Save to a file | `.\metrics\dead-code-report.ps1 -All -OutputPath dead-code.md -Quiet` |
| No false-positive filters | `.\metrics\dead-code-report.ps1 -All -Raw` |
| Largest first | `.\metrics\dead-code-report.ps1 -All -SortBySize` |
| Whitelist candidates | `.\metrics\dead-code-report.ps1 datrix-common -MakeWhitelist` |

Parameters: `-Projects` (names or folder paths), `-All`, `-MinConfidence` (60-100, default 60), `-SortBySize`, `-MakeWhitelist`, `-Output` (text\|json), `-OutputPath`, `-VerboseOutput`, `-Raw`, `-LlmReview`, `-LlmLimit` (default 30), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 180), `-LlmNumPredict` (default 4096), `-LlmTemperature` (default 0.1), `-Quiet`, `-SelfTest`. Whitelist candidates go to `D:\datrix\.test-output\vulture\<package>-whitelist-candidates.py`.

## `metrics\ruff.ps1`

Ruff linter and formatter. Logs to `D:\datrix\.test-output\ruff\<project>\ruff-YYYYMMDD-HHMMSS.log`.

| Form | Command |
|------|---------|
| Lint one project | `.\metrics\ruff.ps1 datrix-common` |
| Lint all | `.\metrics\ruff.ps1 -All` |
| Format check (non-zero if unformatted) | `.\metrics\ruff.ps1 datrix-common -Mode format -Check` |
| Format diff | `.\metrics\ruff.ps1 datrix-common -Mode format -Diff` |
| Apply lint fixes | `.\metrics\ruff.ps1 datrix-common -Fix` |
| JSON | `.\metrics\ruff.ps1 -All -OutputFormat json` |
| Rule counts | `.\metrics\ruff.ps1 -All -Statistics` |
| Lint tests/ | `.\metrics\ruff.ps1 -All -Test` |

Parameters: `-Projects`, `-All`, `-Mode` (check\|format, default check), `-OutputFormat` (full\|concise\|json\|json-lines\|junit\|grouped\|github, default full), `-Fix`, `-Diff`, `-Statistics`, `-Check`, `-Test`, `-StopOnError`, `-VerboseOutput`, `-SelfTest`

## `metrics\bandit.ps1`

Bandit security scan of Python code (excludes only `tests` and `__pycache__`).

| Form | Command |
|------|---------|
| One project | `.\metrics\bandit.ps1 datrix-common` |
| All | `.\metrics\bandit.ps1 -All` |
| High severity only | `.\metrics\bandit.ps1 datrix-common -Severity high` |
| JSON / SARIF | `.\metrics\bandit.ps1 -All -Format json` (`sarif`) |

Parameters: `-Projects`, `-All`, `-Severity` (low\|medium\|high, default medium), `-Confidence` (low\|medium\|high, default medium), `-Format` (screen\|json\|csv\|html\|yaml\|sarif, default screen), `-StopOnError`, `-VerboseOutput`, `-SelfTest`

## `metrics\duplicate.ps1`

Pylint duplicate-code detection (R0801). For AST-identical function bodies use `scan\find-duplicate-bodies.ps1`.

| Form | Command |
|------|---------|
| One project (min 4 lines) | `.\metrics\duplicate.ps1 datrix-common` |
| Each project separately | `.\metrics\duplicate.ps1 -All` |
| Monorepo-wide (default min 30 lines) | `.\metrics\duplicate.ps1 -Mono` |
| Custom min lines | `.\metrics\duplicate.ps1 datrix-common -MinLines 6` |
| Include tests | `.\metrics\duplicate.ps1 datrix-common -Tests` |

Parameters: `-Projects`, `-All`, `-Mono` (not with `-All`), `-MinLines` (default 4; 30 for `-Mono` or multi-root runs unless passed), `-Tests`, `-StopOnError`, `-VerboseOutput`, `-LlmRefactorPlan`, `-LlmLimit` (default 20), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 180), `-LlmNumPredict` (default 4096), `-LlmTemperature` (default 0.1), `-SelfTest`

## `metrics\coverage.ps1`

Pytest coverage via pytest-cov. Each project form runs that project's whole suite under coverage: Jon's run, never an agent's.

| Form | Command |
|------|---------|
| One project | `.\metrics\coverage.ps1 datrix-common` |
| All | `.\metrics\coverage.ps1 -All` |
| HTML / XML | `.\metrics\coverage.ps1 datrix-common -Format html` (`xml`) |
| Fail below a percentage | `.\metrics\coverage.ps1 -All -FailUnder 90` |

Parameters: `-Projects`, `-All`, `-Format` (term\|term-missing\|html\|xml, default term-missing), `-FailUnder` (default 0), `-StopOnError`, `-VerboseOutput`, `-SelfTest`

## `metrics\test-gen.ps1`

Coverage-driven unit test generation on a local model.

| Form | Command |
|------|---------|
| Report ranked candidates | `.\metrics\test-gen.ps1 datrix-common` |
| Generate for the top candidate | `.\metrics\test-gen.ps1 datrix-common -Generate` |
| Generate for all | `.\metrics\test-gen.ps1 datrix-common -GenerateAll -MaxRetries 3` |
| One function | `.\metrics\test-gen.ps1 datrix-common -Generate -TargetFunction "validate_external"` |
| Pin a model | `.\metrics\test-gen.ps1 datrix-common -Generate -Model "qwen3-coder:30b-ctx32k"` |
| Show prompts | `.\metrics\test-gen.ps1 datrix-common -Generate -VerbosePrompts -MaxPromptTokens 4000` |
| All projects, report | `.\metrics\test-gen.ps1 -All -Mode report` |

Parameters: `-Projects`, `-All`, `-Mode` (report\|generate\|generate-all, default report), `-Generate`, `-GenerateAll` (not both), `-TargetFunction` (`Class.method`, `module.function` or the report's candidate id when a bare name is ambiguous), `-MaxRetries` (default 3), `-MinUncoveredRatio` (default 0.5), `-MaxPromptTokens` (default 6000), `-VerbosePrompts`, `-LocalMachines`, `-Model`, `-LlmTimeout` (default 300), `-StopOnError`, `-VerboseOutput`, `-SelfTest`

## `metrics\code-analyzer.ps1`

AST inventory of classes, methods, functions, constants and type aliases, plus duplicate top-level names. Report: `./code-structure-report.md` under the current directory unless `-Output`.

| Form | Command |
|------|---------|
| One project (src) | `.\metrics\code-analyzer.ps1 datrix-common` |
| All packages | `.\metrics\code-analyzer.ps1 -All` |
| Tests only | `.\metrics\code-analyzer.ps1 datrix-common -Tests` |
| Src and tests | `.\metrics\code-analyzer.ps1 -All -Src -Tests` |
| Custom output | `.\metrics\code-analyzer.ps1 -All -Output reports\structure.md` |
| Duplicate-name triage (advisory) | `.\metrics\code-analyzer.ps1 -All -LlmReview -LlmLimit 10` |

Parameters: `-Projects`, `-All`, `-Src`, `-Tests`, `-Output`, `-Dbg`, `-LlmReview`, `-LlmLimit` (default 20), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 180), `-SelfTest`

## `metrics\dependency.ps1`

Dependencies between Datrix packages, or the third-party runtime dependencies each declares.

| Form | Command |
|------|---------|
| Tree | `.\metrics\dependency.ps1 -All` |
| Edge list | `.\metrics\dependency.ps1 -All -Mode list` |
| JSON | `.\metrics\dependency.ps1 -All -Mode json` |
| Third-party (marks `SPEC DRIFT`) | `.\metrics\dependency.ps1 -All -Mode third-party` |
| Some packages | `.\metrics\dependency.ps1 datrix-common datrix-language -Mode tree` |

Parameters: `-Projects`, `-All`, `-Mode` (tree\|list\|json\|third-party, default tree), `-VerboseOutput`, `-Dbg`, `-SelfTest`

## `metrics\large-files.ps1`

Top N files by line count (a report; never fails the run).

| Form | Command |
|------|---------|
| One project (top 20 `.py`) | `.\metrics\large-files.ps1 datrix-common` |
| Top 30 | `.\metrics\large-files.ps1 datrix-language -Top 30` |
| At least 500 lines | `.\metrics\large-files.ps1 datrix-language -Threshold 500` |
| JSON | `.\metrics\large-files.ps1 datrix-language -Top 30 -Format json` |
| Every extension | `.\metrics\large-files.ps1 -All -Suffix ""` |
| Some suffixes | `.\metrics\large-files.ps1 -All -Suffix "j2,py"` |

Parameters: `-Projects`, `-All`, `-Top` (default 20), `-Threshold` (default 0), `-Format` (summary\|json, default summary), `-Suffix` (default `py`; `""` = all), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

## `metrics\call-count.ps1`

Count calls to named functions and every subprocess launch while one workload runs in-process; `-Expect` bounds make it a pass/fail check.

| Form | Command |
|------|---------|
| Count during a generation | `.\metrics\call-count.ps1 -Source datrix/examples/03-domains/ecommerce/system.dtrx -Language python -Count "importlib.metadata:entry_points,jinja2.environment:Environment.compile"` |
| Bound the counts | `.\metrics\call-count.ps1 -Source <system.dtrx> -Language python -Count "importlib.metadata:entry_points" -Expect "importlib.metadata:entry_points<=5"` |
| Count during imports | `.\metrics\call-count.ps1 -Import datrix_codegen_aws -Count "datrix_codegen_kernel.dgen.compiler:generator_definition_file" -Expect "datrix_codegen_kernel.dgen.compiler:generator_definition_file==0"` |
| Keep the JSON | `.\metrics\call-count.ps1 -Source <system.dtrx> -Language python -Count "<targets>" -Json D:\datrix\.tmp\call-count\run.json` |

Parameters: `-Source`, `-Language`, `-Import`, `-Count` (`module:qualname`, comma-separated), `-Expect` (`<target><op><n>`, op `<=`\|`==`\|`>=`; `subprocess` for launches), `-Json`, `-SelfTest`. Last line `CALL_COUNT PASSED|FAILED wall_s=<s> workload_exit=<n>`. Exit: 0 workload succeeded and every bound holds, 1 a bound or the workload failed, 2 usage error or self-test failure.

## `metrics\loc.ps1`

Lines of code with pygount (a report; never fails the run).

| Form | Command |
|------|---------|
| One project | `.\metrics\loc.ps1 datrix-common` |
| All | `.\metrics\loc.ps1 -All` |
| JSON / CLOC XML | `.\metrics\loc.ps1 datrix-common -Format json` (`cloc-xml`) |
| Python only | `.\metrics\loc.ps1 -All -Suffix py` |
| Several suffixes | `.\metrics\loc.ps1 -All -Suffix "py,js"` |

Parameters: `-Projects`, `-All`, `-Format` (summary\|cloc-xml\|json, default summary), `-Suffix` (comma-separated; default all), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

## `metrics\cleanup-ruff.ps1`

List or delete Ruff check logs under `D:\datrix\.test-output\ruff\<project>\` (a deletion asks for a typed "yes").

| Form | Command |
|------|---------|
| List (dry run) | `.\metrics\cleanup-ruff.ps1` |
| Delete all | `.\metrics\cleanup-ruff.ps1 -Force` |
| Keep the latest per project | `.\metrics\cleanup-ruff.ps1 -Force -KeepLatest` |

Parameters: `-BaseDir`, `-Force`, `-KeepLatest`, `-Dbg`, `-SelfTest`

## `metrics\find-constants.ps1`

Magic-constant audit: string literals grouped into a Markdown report. Always pass `-Output` pointing into `D:\datrix\.test-output\`.

| Form | Command |
|------|---------|
| One project | `.\metrics\find-constants.ps1 datrix-common -Output D:\datrix\.test-output\strings.md` |
| Several | `.\metrics\find-constants.ps1 datrix-common datrix-language -Output D:\datrix\.test-output\strings.md` |
| All | `.\metrics\find-constants.ps1 -All -Output D:\datrix\.test-output\strings.md` |
| Tests only | `.\metrics\find-constants.ps1 -All -Tests -Output D:\datrix\.test-output\strings.md` |

Parameters: `-Projects`, `-All`, `-Src`, `-Tests` (default both trees), `-Output <path>`, `-IncludeDocstrings`, `-MinLength <n>` (default 1), `-MaxValueChars <n>` (default 120), `-SelfTest`

## `metrics\agent-spend.ps1`

Where subagents spend their context, measured from Claude Code transcripts (token figures are characters / 4).

| Form | Command |
|------|---------|
| Recent subagents | `.\metrics\agent-spend.ps1 -Days 2` |
| One session | `.\metrics\agent-spend.ps1 -Session <session-id>` |
| Named transcripts | `.\metrics\agent-spend.ps1 -Transcript a.jsonl,b.jsonl` |

Parameters: `-Session <id,...>`, `-Days <n>` (default 7), `-Transcript <path,...>`, `-Top <n>` (default 20), `-SelfTest`. Exit: 0 report printed, 1 no transcript matched, 2 bad argument or no project folder.
