# Code Quality & Metrics Scripts

Code metrics: Radon, Vulture, Ruff, dependency, duplicate-code, Bandit, coverage and agent spend. The
commands and parameters of each script are in [quick-reference.md](quick-reference.md); this file holds
what they measure and how they are built.

Each script is rendered from `common/templates/entrypoint.ps1` around the `datrix_scripts.metrics.*`
module named below, with a POSIX twin `metrics\<name>.sh`. `-SelfTest` runs the module's checks over
planted inputs and the wrapper seam checks; where a row says so, no model is asked and no test is run.

Every `-Fix`/LLM mode in this category searches the local machines' Ollama servers through
`common/lib/datrix_scripts/local_llm.py`: models already in memory are used first, and a model that
fails hands over to the next. `-LocalMachines` defaults to the list in that module, `-Model` to any model
already in memory.

Tools that come with the shared venv: `radon` (the datrix-* packages' `[dev]` extras), and
`cognitive_complexity`, Vulture, Bandit and pygount (the `scripts` dependency group of
`datrix/pyproject.toml`). When one cannot be imported the script refuses before measuring anything,
naming the tool and `common\venv.ps1 -EnsurePackages` as the repair; it runs the tool as the venv
interpreter's module, never whichever copy PATH finds.

## `complexity.ps1`

Radon metrics: cyclomatic complexity, cognitive complexity, raw, Halstead, maintainability index. The
default mode checks against `-Max` (15). The cognitive check measures `def` and `async def` alike, and
the script never checks one metric alone. `-Files` runs mode=check only, on exactly the files an edit
touched, and does not combine with `-Fix`/`-FixAll`, `-All` or project names. `-Fix` fixes the worst
violation with a local model (mode=check only); `-Test` verifies with pytest.

`-SelfTest`: planted packages (a violation fails only its project, `-Files` split on commas, a report
mode never fails, the refused combinations, the usage).

Module: `datrix_scripts.metrics.complexity` (also imported by `dev\code-scan.ps1` and the scripts
contract checks).

## `error-messages.ps1`

Error message quality checker: detects substandard error messages (missing context, suggestions, valid
options) via AST-based scoring, with optional local-model auto-fix. Default mode=check with a minimum
score of 2; `-Mode report` lists all error sites with scores; `-VerboseOutput` also lists the error sites
the exclusion list skips.

`-SelfTest`: planted projects (check, report, skipped sites, a missing project and `-StopOnError`,
refused combinations, the debug log); no model is asked.

Module: `datrix_scripts.metrics.error_messages`.

## `dead-code-report.ps1`

Two-pass Vulture dead-code report: classifies findings as "never referenced" or "only referenced by
tests". It is the one Vulture entry point: `-SortBySize` and `-MakeWhitelist` are Vulture's own options
carried through (the latter writes Vulture's `--make-whitelist` output per package to
`D:\datrix\.test-output\vulture\<package>-whitelist-candidates.py`, never into a package; review before
merging into `vulture_whitelist.py`). With no project it covers every installable `datrix-*` package
discovered on disk (the same set as `-All`). `-OutputPath` receives the report alone (progress and model
notes stay on the console), so a JSON report file is pure JSON.

`-SelfTest`: planted packages (showcase refusal, project normalization, whitelist path outside every
package, a planted unused function reported by a real Vulture run).

Module: `datrix_scripts.metrics.dead_code_report`.

## `ruff.ps1`

Ruff linter/formatter. Logs output to `D:\datrix\.test-output\ruff\<project>\ruff-YYYYMMDD-HHMMSS.log` —
outside every package repo, because a log folder created inside one gets committed and pushed unless a
human notices. An `-OutputFormat` outside the listed values is refused before a project runs.

`-SelfTest`: planted projects (a lint issue fails and is shown and logged, format check, `-Test`, every
flag reaching Ruff, refusals).

Module: `datrix_scripts.metrics.ruff`.

## `bandit.ps1`

Bandit security scanner for Python code. Findings are always printed; the script excludes only `tests`
and `__pycache__` and passes Bandit no skip-rule or `nosec` option, so no rule is disabled to make a
project pass.

`-SelfTest`: planted projects scanned by the real Bandit (a high finding fails and is printed,
thresholds and `-Format` reach Bandit, a missing `src/` and `-StopOnError`, refusals).

Module: `datrix_scripts.metrics.bandit`.

## `duplicate.ps1`

Pylint duplicate-code detection (R0801): similar runs of lines anywhere — inside functions, across class
bodies, in module-level tables. It does not compare whole function bodies by structure;
`scan\find-duplicate-bodies.ps1` finds AST-identical function bodies with renamed identifiers, which line
similarity misses. `datrix-codegen-python/pyproject.toml` mirrors this script's arguments.

**Mono runs and cross-language duplication:** with `-Mono`, Pylint compares all Python under every
project's `src/`. Duplicates between two language generators (same feature, different output language)
are expected: the stacks implement parallel generators kept in sync by design. Mono runs therefore
default to `min-similarity-lines=30` so those cross-language pairs are not reported; pass `-MinLines 4`
(or lower) with `-Mono` to see every duplicate, cross-language included.

`-SelfTest`: planted packages and the wrapper seam checks.

Module: `datrix_scripts.metrics.duplicate` (also imported by `dev\code-scan.ps1`).

## `coverage.ps1`

Pytest coverage reports via pytest-cov. Each project form runs that project's whole test suite under
coverage: it is Jon's run, never an agent's.

`-SelfTest`: planted projects (the coverage source and pytest command, the TOTAL line and per-file
detail, why a total is unknown, a missing `tests/` or root failing before pytest, a failed install check
stopping the run, refusals); no test is run.

Module: `datrix_scripts.metrics.coverage`.

## `test-gen.ps1`

Coverage-driven unit test generation via a local model. Finds uncovered functions from coverage JSON,
ranks candidates, and can generate validated `_generated` test files. Generated files are kept only after
target-reference checks, Ruff auto-fix/check, the generated test file, and the full project test suite
pass; failures are deleted. Prompts are compacted for local models with selective imports, summarized
related tests, minimal class context, target literals/attributes, and short retry prompts. Successful
generated tests are tracked in `D:\datrix\.test-output\test-gen\<project>\test-gen-manifest.json` —
outside the package repo — and already tracked/output-existing candidates are skipped. `-GenerateAll`
prints a summary of generated, skipped and failed. `-Model` uses only that model, on any searched machine
serving it.

`-SelfTest`: planted projects (both generate switches refused before selection, the mode shortcuts,
refusals, a missing `src/`, `tests/` or root failing before pytest, candidate ranking from a coverage
report); no test is run, no model is asked.

Module: `datrix_scripts.metrics.test_gen`.

## `code-analyzer.ps1`

AST inventory of classes, methods, module functions, constants (UPPER_SNAKE heuristic), and type
aliases, plus a **duplicate top-level names** section (same class/function name in two or more files) to
spot accidental parallel architectures. Uses metrics **`-All`** semantics (`datrix-*` packages only).
Report path defaults to **`./code-structure-report.md` under the process cwd** (where you run the
script); relative `-Output` resolves against cwd. `-LlmReview` adds an advisory "Duplicate-name triage"
section: one local-model request ranking which duplicate names are one concept with two homes. No
duplicate group → no request; a ranked name that is not a duplicate group is called out as made up. It
never changes the exit code.

`-SelfTest`: the duplicate-triage checks (planted sites, no model server), the refusals, a planted
duplicate in the report.

Module: `datrix_scripts.metrics.code_analyzer`.

## `dependency.ps1`

Reports dependency relationships between Datrix packages (from pyproject.toml), or the third-party
runtime dependencies each package declares. `-Mode third-party` lists every non-datrix runtime
dependency, each declaring package and its spec; `SPEC DRIFT` marks specifiers that differ by package
(the shared venv resolves one version).

`-SelfTest`: planted packages (tree, list and json, third-party spec drift, an unknown package, the
showcase alone refused, the usage text).

Module: `datrix_scripts.metrics.dependency`.

## `large-files.ps1`

Lists top N files by line count for Datrix projects. A report only: `-Threshold` filters what is listed,
and no line count fails the run.

`-SelfTest`: planted packages (a threshold filters the listing and never fails the run).

Module: `datrix_scripts.metrics.large_files`.

## `call-count.ps1`

Counts calls to named functions, and every subprocess launch, while one workload runs in-process: one
`datrix generate`, or importing named modules. The counters are installed before any workload module
loads, and installing one also rebinds the names modules bound earlier with `from x import y`, so
nothing is under-counted. No profiler, so the wall time is the real one. `-Expect` bounds make the run a
pass/fail check, which is how a design acceptance property about call volume (registry constructions,
template compiles, `resolve()` calls, subprocesses) is proved in one command. A self-test of the counter
runs first on every invocation.

Output: the JSON (`counts`, `expectations`, `wall_s`, `workload_exit`), then
`CALL_COUNT PASSED|FAILED wall_s=<s> workload_exit=<n>`. Generated output goes to
`D:\datrix\.tmp\call-count\<timestamp>\`.

`-SelfTest` proves the counter counts a planted function, a method and an early `from x import y`
binding, and checks the wrapper seam.

Module: `datrix_scripts.metrics.call_count`; POSIX twin `metrics\call-count.sh` (`--source`,
`--language`, `--import`, `--count`, `--expect`, `--json`, `--self-test`).

## `loc.ps1`

Lines-of-code counting using pygount, run as the venv interpreter's module (`pygount.command`). A report
only: no count fails the run. With `-All`, a project whose JSON pass yields a document missing a count is
named in a `[WARN]` line and left out of the rollup.

`-SelfTest`: planted packages (the `-All` rollup sums and formats, a document without a count is refused,
a project without `src/` fails).

Module: `datrix_scripts.metrics.loc`.

## `cleanup-ruff.ps1`

Cleans up Ruff check log files from the workspace-level `D:\datrix\.test-output\ruff\<project>\`
folders. A deletion asks for a typed "yes" first; any end of input answers no. Only files directly
inside a `<BaseDir>\.test-output\ruff\<project>\` folder are deleted, and the script runs no Ruff.

`-SelfTest`: planted logs (the listing deletes nothing, "no" and end of input cancel, `-KeepLatest`, a
full delete removing only logs and emptied folders, an empty root, size units).

Module: `datrix_scripts.metrics.cleanup_ruff`.

## `find-constants.ps1`

Finds string literals in Datrix Python projects and writes a grouped Markdown report (magic-constant
audit). The report defaults to the current working directory — always pass `-Output` pointing into
`D:\datrix\.test-output\`.

`-SelfTest`: planted projects (grouping, docstrings, min length, usage).

Module: `datrix_scripts.metrics.find_constants`.

## `agent-spend.ps1`

Where subagents spend their context, measured from Claude Code transcripts rather than guessed. It reads
the subagent transcripts of this workspace's Claude Code project folder
(`~\.claude\projects\<workspace slug>\<session>\subagents\agent-*.jsonl`, labelled by the `meta.json`
beside each) and reports:

- tool calls and tool-result size by tool;
- Read results by kind of file (task file, design doc, rules, tests, source), and the whole-file share;
- the files read whole most often, and by how many agents;
- how much source/test reading went to files the reading agent never edited;
- one line per agent.

This measures the spend rules (`execution-contract-spend.md` §10–§11). Token figures are estimates
(characters / 4).

`-SelfTest`: a planted transcript (measured, the report names the agent and a bad line, comma lists
split, out-of-range values refused with exit 2, a missing project folder names the fix).

Module: `datrix_scripts.metrics.agent_spend`.
