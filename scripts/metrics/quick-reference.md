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
| **Check given files** | `.\metrics\complexity.ps1 -Files a.py,b.py` | Cyclomatic + cognitive on exactly these files (the ones an edit touched); exit 1 on a violation |
| **Custom max** | `.\metrics\complexity.ps1 datrix-language -Max 10` | Lower threshold |
| **Cyclomatic only** | `.\metrics\complexity.ps1 datrix-common -Mode cc` | Cyclomatic complexity report |
| **Raw metrics** | `.\metrics\complexity.ps1 datrix-common -Mode raw` | SLOC, comments, blanks |
| **Halstead metrics** | `.\metrics\complexity.ps1 -All -Mode halstead` | Halstead complexity |
| **Maintainability index** | `.\metrics\complexity.ps1 datrix-common -Mode mi` | MI score per file |
| **Fix with a local model** | `.\metrics\complexity.ps1 datrix-common -Fix` | Fix worst violation (mode=check only) |
| **Fix + test** | `.\metrics\complexity.ps1 datrix-common -Fix -Test` | Fix and verify with pytest |
| **Stop on first fail** | `.\metrics\complexity.ps1 -All -StopOnError` | Stop on first failure |
| **Verbose** | `.\metrics\complexity.ps1 datrix-common -VerboseOutput` | Verbose output |
| **Self-test** | `.\metrics\complexity.ps1 -SelfTest` | Planted packages (a violation fails only its project, `-Files` split on commas, a report mode never fails, the refused combinations, the usage) and the wrapper seam checks |

The cognitive check measures `def` and `async def` alike. `-Files` runs mode=check only, and does not combine with `-Fix`/`-FixAll`, `-All` or project names.

`radon` (the datrix-* packages' `[dev]` extras) and `cognitive_complexity` (the `scripts` dependency group of `datrix/pyproject.toml`) come with the shared venv. When either cannot be imported the script refuses before measuring anything, naming the tool and `common\venv.ps1 -EnsurePackages` as the repair; it never checks one metric alone.

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Files <path,...>`, `-Mode` (check\|cc\|raw\|halstead\|mi, default: check), `-Max` (default: 15), `-Fix`, `-FixAll`, `-Test` (with -Fix), `-MaxRetries` (default: 3), `-LocalMachines` (default: the list in `common/lib/datrix_scripts/local_llm.py`), `-Model` (default: any model already in memory), `-LlmTimeout` (default: 180), `-LlmNumPredict` (default: 4096), `-LlmTemperature` (default: 0.1), `-MaxContextChars` (default: 8000), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.metrics.complexity` (also imported by `dev\code-scan.ps1` and the scripts contract checks); POSIX twin `metrics\complexity.sh`

Every `-Fix`/LLM mode in this category searches the local machines' Ollama servers through `common/lib/datrix_scripts/local_llm.py`: models already in memory are used first, and a model that fails hands over to the next.

---

## `metrics\error-messages.ps1`

Error message quality checker: detects substandard error messages (missing context, suggestions, valid options) via AST-based scoring, with optional local-model auto-fix.

| Mode | Command | Description |
|------|---------|-------------|
| **Check one project** | `.\metrics\error-messages.ps1 datrix-common` | Enforce min score (default mode=check, min-score=2) |
| **Check all** | `.\metrics\error-messages.ps1 -All` | All projects |
| **Stricter threshold** | `.\metrics\error-messages.ps1 -All -MinScore 3` | Higher minimum score |
| **Report (audit)** | `.\metrics\error-messages.ps1 datrix-common -Mode report` | List all error sites with scores |
| **Fix with a local model** | `.\metrics\error-messages.ps1 datrix-common -Fix` | Fix worst violation |
| **Fix all** | `.\metrics\error-messages.ps1 datrix-common -FixAll -Test` | Fix all violations with test verification |
| **Stop on first fail** | `.\metrics\error-messages.ps1 -All -StopOnError` | Stop on first failure |
| **List skipped sites** | `.\metrics\error-messages.ps1 datrix-common -Mode report -VerboseOutput` | Also list the error sites the exclusion list skips |
| **Self-test** | `.\metrics\error-messages.ps1 -SelfTest` | Planted projects (check, report, skipped sites, a missing project and `-StopOnError`, refused combinations, the debug log) and the wrapper seam checks; no model is asked |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (check\|report, default: check), `-MinScore` (default: 2), `-Fix`, `-FixAll` (both need `-Mode check`), `-Test` (with -Fix/-FixAll), `-MaxRetries` (default: 3), `-LocalMachines`, `-Model`, `-LlmTimeout` (default: 300), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.metrics.error_messages`; POSIX twin `metrics\error-messages.sh`

---

## `metrics\dead-code-report.ps1`

Two-pass Vulture dead-code report: classifies findings as "never referenced" or "only referenced by tests". It is the one Vulture entry point: `-SortBySize` and `-MakeWhitelist` are Vulture's own options carried through. Vulture comes with the shared venv (the `scripts` dependency group of `datrix/pyproject.toml`); when it cannot be imported the report refuses before scanning, naming that group and `common\venv.ps1 -EnsurePackages` as the repair.

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
| **Sort by size** | `.\metrics\dead-code-report.ps1 -All -SortBySize` | Largest unused functions/classes first, each with its size |
| **Whitelist candidates** | `.\metrics\dead-code-report.ps1 datrix-common -MakeWhitelist` | Vulture's `--make-whitelist` output per package to `D:\datrix\.test-output\vulture\<package>-whitelist-candidates.py` (never into a package); review before merging into `vulture_whitelist.py` |
| **Self-test** | `.\metrics\dead-code-report.ps1 -SelfTest` | Planted packages (showcase refusal, project normalization, whitelist path outside every package, a planted unused function reported by a real Vulture run) and the wrapper seam checks |

`-OutputPath` receives the report alone (progress and model notes stay on the console), so a JSON report file is pure JSON.

**Parameters:** `-Projects` (positional, variadic; package names or folder paths), `-All`, `-MinConfidence` (60-100, default: 60), `-SortBySize`, `-MakeWhitelist`, `-Output` (text\|json), `-OutputPath`, `-VerboseOutput`, `-Raw`, `-LlmReview`, `-LlmLimit` (default: 30), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default: 180), `-LlmNumPredict` (default: 4096), `-LlmTemperature` (default: 0.1), `-Quiet`, `-SelfTest`

**Module:** `datrix_scripts.metrics.dead_code_report`; POSIX twin `metrics\dead-code-report.sh`

---

## `metrics\ruff.ps1`

Ruff linter/formatter. Logs output to `D:\datrix\.test-output\ruff\<project>\ruff-YYYYMMDD-HHMMSS.log` — outside every package repo, because a log folder created inside one gets committed and pushed unless a human notices.

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
| **Self-test** | `.\metrics\ruff.ps1 -SelfTest` | Planted projects (a lint issue fails and is shown and logged, format check, `-Test`, every flag reaching Ruff, refusals) and the wrapper seam checks |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (check\|format, default: check), `-OutputFormat` (full\|concise\|json\|json-lines\|junit\|grouped\|github, default: full; any other value is refused before a project runs), `-Fix`, `-Diff`, `-Statistics`, `-Check`, `-Test`, `-StopOnError`, `-VerboseOutput`, `-SelfTest`

**Module:** `datrix_scripts.metrics.ruff`; POSIX twin `metrics\ruff.sh`

---

## `metrics\bandit.ps1`

Bandit security scanner for Python code. Bandit comes with the shared venv (the `scripts` dependency group of `datrix/pyproject.toml`) and runs as the venv interpreter's module; when it cannot be imported the script refuses before scanning, naming that group and `common\venv.ps1 -EnsurePackages` as the repair. Findings are always printed; the script excludes only `tests` and `__pycache__` and passes Bandit no skip-rule or `nosec` option, so no rule is disabled to make a project pass.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\bandit.ps1 datrix-common` | Default severity=medium, confidence=medium |
| **All projects** | `.\metrics\bandit.ps1 -All` | Scan all |
| **High severity only** | `.\metrics\bandit.ps1 datrix-common -Severity high` | Only high severity |
| **JSON output** | `.\metrics\bandit.ps1 -All -Format json` | JSON format |
| **SARIF output** | `.\metrics\bandit.ps1 -All -Format sarif` | SARIF format |
| **Stop on fail** | `.\metrics\bandit.ps1 -All -StopOnError` | Stop on first failure |
| **Self-test** | `.\metrics\bandit.ps1 -SelfTest` | Planted projects scanned by the real Bandit (a high finding fails and is printed, thresholds and `-Format` reach Bandit, a missing `src/` and `-StopOnError`, refusals) and the wrapper seam checks |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Severity` (low\|medium\|high, default: medium), `-Confidence` (low\|medium\|high, default: medium), `-Format` (screen\|json\|csv\|html\|yaml\|sarif, default: screen), `-StopOnError`, `-VerboseOutput`, `-SelfTest`

**Module:** `datrix_scripts.metrics.bandit`; POSIX twin `metrics\bandit.sh`

---

## `metrics\duplicate.ps1`

Pylint duplicate-code detection (R0801): similar runs of lines anywhere — inside functions, across class bodies, in module-level tables. It does not compare whole function bodies by structure; `scan\find-duplicate-bodies.ps1` finds AST-identical function bodies with renamed identifiers, which line similarity misses. `datrix-codegen-python/pyproject.toml` mirrors this script's arguments.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\duplicate.ps1 datrix-common` | Default min-lines=4 |
| **All projects** | `.\metrics\duplicate.ps1 -All` | Each project separately |
| **Monorepo-wide** | `.\metrics\duplicate.ps1 -Mono` | Cross-project duplicate detection |
| **Custom min lines** | `.\metrics\duplicate.ps1 datrix-common -MinLines 6` | Higher threshold |
| **Include tests** | `.\metrics\duplicate.ps1 datrix-common -Tests` | Also scan tests/ |
| **Stop on fail** | `.\metrics\duplicate.ps1 -All -StopOnError` | Stop on first failure |
| **Self-test** | `.\metrics\duplicate.ps1 -SelfTest` | Planted packages and the wrapper seam checks |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mono` (mutually exclusive with -All), `-MinLines` (default: 4 for a single project; multi-root/`-Mono` runs default to 30 unless `-MinLines` is explicitly passed), `-Tests`, `-StopOnError`, `-VerboseOutput`, `-LlmRefactorPlan`, `-LlmLimit` (default: 20), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default: 180), `-LlmNumPredict` (default: 4096), `-LlmTemperature` (default: 0.1), `-SelfTest`

**Module:** `datrix_scripts.metrics.duplicate` (also imported by `dev\code-scan.ps1`); POSIX twin `metrics\duplicate.sh`

**Mono runs and cross-language duplication:** with `-Mono`, Pylint compares all Python under every project's `src/`. Duplicates between two language generators (same feature, different output language) are expected: the stacks implement parallel generators kept in sync by design. Mono runs therefore default to `min-similarity-lines=30` so those cross-language pairs are not reported; pass `-MinLines 4` (or lower) with `-Mono` to see every duplicate, cross-language included.

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
| **Self-test** | `.\metrics\coverage.ps1 -SelfTest` | Planted projects (the coverage source and pytest command, the TOTAL line and per-file detail, why a total is unknown, a missing `tests/` or root failing before pytest, a failed install check stopping the run, refusals) and the wrapper seam checks; no test is run |

Each project form runs that project's whole test suite under coverage: it is Jon's run, never an agent's.

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Format` (term\|term-missing\|html\|xml, default: term-missing), `-FailUnder` (default: 0), `-StopOnError`, `-VerboseOutput`, `-SelfTest`

**Module:** `datrix_scripts.metrics.coverage`; POSIX twin `metrics\coverage.sh`

---

## `metrics\test-gen.ps1`

Coverage-driven unit test generation via a local model. Finds uncovered functions from coverage JSON, ranks candidates, and can generate validated `_generated` test files. Generated files are kept only after target-reference checks, Ruff auto-fix/check, the generated test file, and the full project test suite pass; failures are deleted. Prompts are compacted for local models with selective imports, summarized related tests, minimal class context, target literals/attributes, and short retry prompts. Successful generated tests are tracked in `D:\datrix\.test-output\test-gen\<project>\test-gen-manifest.json` — outside the package repo — and already tracked/output-existing candidates are skipped.

| Mode | Command | Description |
|------|---------|-------------|
| **Report candidates** | `.\metrics\test-gen.ps1 datrix-common` | Ranked uncovered functions (default mode=report) |
| **Generate top candidate** | `.\metrics\test-gen.ps1 datrix-common -Generate` | Generate, validate, run project tests, and print added tests |
| **Generate all candidates** | `.\metrics\test-gen.ps1 datrix-common -GenerateAll -MaxRetries 3` | Attempt generation for all ranked functions; summary includes generated, skipped, and failed |
| **Target specific function** | `.\metrics\test-gen.ps1 datrix-common -Generate -TargetFunction "validate_external"` | Generate for one named function; use `Class.method`, `module.function`, or the report candidate id when a bare name is ambiguous |
| **Pin a model** | `.\metrics\test-gen.ps1 datrix-common -Generate -Model "qwen3-coder:30b-ctx32k"` | Use only this model, on any searched machine serving it |
| **Debug prompts** | `.\metrics\test-gen.ps1 datrix-common -Generate -VerbosePrompts -MaxPromptTokens 4000` | Print prompts and warn above the token budget |
| **All projects report** | `.\metrics\test-gen.ps1 -All -Mode report` | Report candidates for all projects |
| **Self-test** | `.\metrics\test-gen.ps1 -SelfTest` | Planted projects (both generate switches refused before selection, the mode shortcuts, refusals, a missing `src/`, `tests/` or root failing before pytest, candidate ranking from a coverage report) and the wrapper seam checks; no test is run, no model is asked |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (report\|generate\|generate-all, default: report), `-Generate`, `-GenerateAll` (not both), `-TargetFunction`, `-MaxRetries` (default: 3), `-MinUncoveredRatio` (default: 0.5), `-MaxPromptTokens` (default: 6000), `-VerbosePrompts`, `-LocalMachines` (default: the list in `common/lib/datrix_scripts/local_llm.py`), `-Model` (default: any model already in memory), `-LlmTimeout` (default: 300), `-StopOnError`, `-VerboseOutput`, `-SelfTest`

**Module:** `datrix_scripts.metrics.test_gen`; POSIX twin `metrics\test-gen.sh`

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
| **Duplicate-name triage** | `.\metrics\code-analyzer.ps1 -All -LlmReview -LlmLimit 10` | Adds an advisory "Duplicate-name triage" section: one local-model request ranking which duplicate names are one concept with two homes. No duplicate group → no request; a ranked name that is not a duplicate group is called out as made up. Never changes the exit code |
| **Self-test** | `.\metrics\code-analyzer.ps1 -SelfTest` | The duplicate-triage checks (planted sites, no model server), the refusals, a planted duplicate in the report, and the wrapper seam checks |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Src`, `-Tests`, `-Output`, `-Dbg`, `-LlmReview`, `-LlmLimit` (default 20), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (seconds, default 180), `-SelfTest`

**Module:** `datrix_scripts.metrics.code_analyzer`; POSIX twin `metrics\code-analyzer.sh`

---

## `metrics\dependency.ps1`

Reports dependency relationships between Datrix packages (from pyproject.toml), or the
third-party runtime dependencies each package declares.

| Mode | Command | Description |
|------|---------|-------------|
| **All (tree)** | `.\metrics\dependency.ps1 -All` | Dependency tree for all packages |
| **All (list)** | `.\metrics\dependency.ps1 -All -Mode list` | Edge list (package -> dep) |
| **All (json)** | `.\metrics\dependency.ps1 -All -Mode json` | JSON format |
| **Third-party** | `.\metrics\dependency.ps1 -All -Mode third-party` | Every non-datrix runtime dependency, each declaring package and its spec; `SPEC DRIFT` marks specifiers that differ by package (the shared venv resolves one version) |
| **Specific packages** | `.\metrics\dependency.ps1 datrix-common datrix-language -Mode tree` | Selected packages |
| **Self-test** | `.\metrics\dependency.ps1 -SelfTest` | Planted packages (tree, list and json, third-party spec drift, an unknown package, the showcase alone refused, the usage text) and the wrapper seam checks |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Mode` (tree\|list\|json\|third-party, default: tree), `-VerboseOutput`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.metrics.dependency`; POSIX twin `metrics\dependency.sh`

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
| **Self-test** | `.\metrics\large-files.ps1 -SelfTest` | Planted packages (a threshold filters the listing and never fails the run) and the wrapper seam checks |

A report only: `-Threshold` filters what is listed, and no line count fails the run.

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Top` (default: 20), `-Threshold` (default: 0), `-Format` (summary\|json, default: summary), `-Suffix` (default: py, "" for all), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.metrics.large_files`; POSIX twin `metrics\large-files.sh`

---

## `metrics\call-count.ps1`

Counts calls to named functions, and every subprocess launch, while one workload runs in-process: one `datrix generate`, or importing named modules. The counters are installed before any workload module loads, and installing one also rebinds the names modules bound earlier with `from x import y`, so nothing is under-counted. No profiler, so the wall time is the real one. `-Expect` bounds make the run a pass/fail check, which is how a design acceptance property about call volume (registry constructions, template compiles, `resolve()` calls, subprocesses) is proved in one command. A self-test of the counter runs first on every invocation.

| Mode | Command | Description |
|------|---------|-------------|
| **Count during a generation** | `.\metrics\call-count.ps1 -Source datrix/examples/03-domains/ecommerce/system.dtrx -Language python -Count "importlib.metadata:entry_points,jinja2.environment:Environment.compile"` | Counts per target, `subprocess` launches, wall time |
| **Bound the counts** | `.\metrics\call-count.ps1 -Source <system.dtrx> -Language python -Count "importlib.metadata:entry_points" -Expect "importlib.metadata:entry_points<=5"` | Exit 1 when a bound fails |
| **Count during imports** | `.\metrics\call-count.ps1 -Import datrix_codegen_aws -Count "datrix_codegen_kernel.dgen.compiler:generator_definition_file" -Expect "datrix_codegen_kernel.dgen.compiler:generator_definition_file==0"` | Import workload |
| **Keep the result** | `.\metrics\call-count.ps1 -Source <system.dtrx> -Language python -Count "<targets>" -Json D:\datrix\.tmp\call-count\run.json` | Also write the JSON |
| **Self-test only** | `.\metrics\call-count.ps1 -SelfTest` | Prove the counter counts a planted function, a method and an early `from x import y` binding |

**Parameters:** `-Source`, `-Language`, `-Import`, `-Count` (`module:qualname`, comma-separated), `-Expect` (`<target><op><n>`, op `<=`\|`==`\|`>=`, `subprocess` for launches), `-Json`, `-SelfTest`

**Output:** the JSON (`counts`, `expectations`, `wall_s`, `workload_exit`), then `CALL_COUNT PASSED|FAILED wall_s=<s> workload_exit=<n>`. Generated output goes to `D:\datrix\.tmp\call-count\<timestamp>\`. **Exit codes:** 0 = workload succeeded and every bound holds, 1 = a bound failed or the workload failed, 2 = usage error or self-test failure.

**Module:** `datrix_scripts.metrics.call_count`; POSIX twin `metrics\call-count.sh` (`--source`, `--language`, `--import`, `--count`, `--expect`, `--json`, `--self-test`). `-SelfTest` also checks the wrapper seam.

---

## `metrics\loc.ps1`

Lines-of-code counting using pygount. pygount comes with the shared venv (the `scripts` dependency group of `datrix/pyproject.toml`) and runs as the venv interpreter's module (`pygount.command`), never whichever `pygount` PATH finds; when it cannot be imported the script refuses before counting, naming that group and `common\venv.ps1 -EnsurePackages` as the repair.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\loc.ps1 datrix-common` | Summary format |
| **All projects** | `.\metrics\loc.ps1 -All` | All projects |
| **JSON format** | `.\metrics\loc.ps1 datrix-common -Format json` | JSON output |
| **CLOC XML** | `.\metrics\loc.ps1 datrix-common -Format cloc-xml` | CLOC-compatible XML |
| **Python only** | `.\metrics\loc.ps1 -All -Suffix py` | Only Python files |
| **Multiple suffixes** | `.\metrics\loc.ps1 -All -Suffix "py,js"` | Python + JS files |
| **Self-test** | `.\metrics\loc.ps1 -SelfTest` | Planted packages (the `-All` rollup sums and formats, a document without a count is refused, a project without `src/` fails) and the wrapper seam checks |

A report only: no count fails the run. With `-All`, a project whose JSON pass yields a document missing a count is named in a `[WARN]` line and left out of the rollup.

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Format` (summary\|cloc-xml\|json, default: summary), `-Suffix` (comma-separated, default: "" = all), `-StopOnError`, `-VerboseOutput`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.metrics.loc`; POSIX twin `metrics\loc.sh`

---

## `metrics\cleanup-ruff.ps1`

Cleans up Ruff check log files from the workspace-level `D:\datrix\.test-output\ruff\<project>\` folders.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\metrics\cleanup-ruff.ps1` | Show all log files |
| **Delete all** | `.\metrics\cleanup-ruff.ps1 -Force` | Delete all log files |
| **Keep latest** | `.\metrics\cleanup-ruff.ps1 -Force -KeepLatest` | Delete old, keep latest per project |
| **Self-test** | `.\metrics\cleanup-ruff.ps1 -SelfTest` | Planted logs (the listing deletes nothing, "no" and end of input cancel, `-KeepLatest`, a full delete removing only logs and emptied folders, an empty root, size units) and the wrapper seam checks |

A deletion asks for a typed "yes" first; any end of input answers no. Only files directly inside a `<BaseDir>\.test-output\ruff\<project>\` folder are deleted, and the script runs no Ruff.

**Parameters:** `-BaseDir`, `-Force`, `-KeepLatest`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.metrics.cleanup_ruff`; POSIX twin `metrics\cleanup-ruff.sh`

---

## `metrics\find-constants.ps1`

Finds string literals in Datrix Python projects and writes a grouped Markdown report (magic-constant audit). The report defaults to the current working directory — always pass `-Output` pointing into `D:\datrix\.test-output\`.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\metrics\find-constants.ps1 datrix-common -Output D:\datrix\.test-output\strings.md` | Report string literals in one project |
| **Multiple projects** | `.\metrics\find-constants.ps1 datrix-common datrix-language -Output D:\datrix\.test-output\strings.md` | Several projects |
| **All projects** | `.\metrics\find-constants.ps1 -All -Output D:\datrix\.test-output\strings.md` | Entire monorepo |
| **Tests only** | `.\metrics\find-constants.ps1 -All -Tests -Output D:\datrix\.test-output\strings.md` | Scan only tests trees |
| **Self-test** | `.\metrics\find-constants.ps1 -SelfTest` | Planted projects (grouping, docstrings, min length, usage) and the wrapper seam checks |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Src`, `-Tests` (default: both trees), `-Output <path>`, `-IncludeDocstrings`, `-MinLength <n>` (default 1), `-MaxValueChars <n>` (default 120), `-SelfTest`

**Module:** `datrix_scripts.metrics.find_constants`; POSIX twin `metrics\find-constants.sh`

---

## `metrics\agent-spend.ps1`

Where subagents spend their context, measured from Claude Code transcripts rather than guessed. It
reads the subagent transcripts of this workspace's Claude Code project folder
(`~\.claude\projects\<workspace slug>\<session>\subagents\agent-*.jsonl`, labelled by the
`meta.json` beside each) and reports:

- tool calls and tool-result size by tool;
- Read results by kind of file (task file, design doc, rules, tests, source), and the whole-file share;
- the files read whole most often, and by how many agents;
- how much source/test reading went to files the reading agent never edited;
- one line per agent.

This measures the spend rules (`execution-contract-spend.md` §10–§11). Token figures are estimates
(characters / 4).

| Mode | Command | Description |
|------|---------|-------------|
| **Recent subagents** | `.\metrics\agent-spend.ps1 -Days 2` | Subagents whose transcript changed in the last two days |
| **One run** | `.\metrics\agent-spend.ps1 -Session <session-id>` | The subagents of one session (an orchestrator run) |
| **Explicit files** | `.\metrics\agent-spend.ps1 -Transcript a.jsonl,b.jsonl` | Named transcripts |
| **Self-test** | `.\metrics\agent-spend.ps1 -SelfTest` | A planted transcript (measured, the report names the agent and a bad line, comma lists split, out-of-range values refused with exit 2, a missing project folder names the fix) and the wrapper seam checks |

**Parameters:** `-Session <id,...>`, `-Days <n>` (default 7), `-Transcript <path,...>`, `-Top <n>` (default 20), `-SelfTest`. **Exit codes:** 0 = report printed, 1 = no transcript matched, 2 = a bad argument or no project folder.

**Module:** `datrix_scripts.metrics.agent_spend`; POSIX twin `metrics\agent-spend.sh`
