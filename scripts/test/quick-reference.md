# Quick Reference — Testing Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `test\test.ps1`

Runs tests for one or more Datrix projects.

**Agents run only targeted forms** — `-Specific`, `-Keyword`, `-Tag` (never with `-All`/`-Rerun`), plus `-ListTags`, which runs nothing. Every whole-suite form (a package with none of those, several bare packages, `-All`, `-Rerun`, a tier switch) is **Jon's alone**: `guard-full-suite-runs.py` refuses it from every agent tool call, main session included, with no override.

| Mode | Command | Description |
|------|---------|-------------|
| **Specific test file** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py"` | Run one test file |
| **Several test files (one session)** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py,tests/unit/test_bar.py"` | Comma-separated files/node-IDs run in ONE pytest session — always batch a targeted set this way instead of one invocation per file (commas inside parametrized IDs `[1,2]` are literal) |
| **Keyword filter** | `.\test\test.ps1 datrix-common -Keyword "test_parse"` | Match by keyword (-k) |
| **Feature tag** | `.\test\test.ps1 datrix-codegen-python datrix-codegen-java -Tag gateway` | Only the tests carrying the tag, in every named package — how a change's behaviour is verified across the packages it reaches |
| **Several tags** | `.\test\test.ps1 datrix-common -Tag config-resolution,secrets` | A test runs when it carries ANY named tag |
| **List tags** | `.\test\test.ps1 datrix-codegen-python -ListTags` | Every tag with its test count, and the untagged tests; runs nothing; exit 1 while any test is untagged or a module fails to collect |
| **List tags (scoped)** | `.\test\test.ps1 datrix-common -ListTags -Specific "tests/unit/config"` | Listing over the named files/directories only |
| **Verbose output** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -VerboseOutput` | Verbose pytest output (Jon; agents never pass it) |
| **No log save** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -NoSave` | Don't save output to log files (Jon; agents never pass it) |
| **Debug logging** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -Dbg` | Enable DEBUG level |
| **Coverage** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -Coverage` | Generate coverage report |

Whole-suite modes (Jon only): a bare package (`.\test\test.ps1` + package names), a folder path, `-All`, `-Rerun` (re-run projects whose latest log reports failures), and the tier switches `-Unit` / `-Integration` / `-E2E` / `-Fast` (excludes slow) / `-Slow`.

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rerun`, `-Coverage`, `-VerboseOutput`, `-NoSave`, `-NoAutoInstall`, `-Unit`, `-Integration`, `-E2E`, `-Fast`, `-Slow` (mutually exclusive), `-Specific <path[,path...]>` (comma-separated files/node-IDs run in one pytest session), `-Keyword <expr>`, `-Tag <tag[,tag...]>` (feature tags; a test runs when it carries any of them), `-ListTags` (list tags, run nothing; with `-Specific`, scoped), `-Dbg`

**Feature tags.** Every test carries one or more feature tags (pytest `tag` marker; Node `#tag` token in a test or `describe()` name). They are declared by `datrix_common.testing.feature_tags`, a `pytest11` plugin every session in the venv loads; `test.ps1` runs every session with `--datrix-require-tags`, so an untagged test fails at setup (an untagged Node test fails the run). `-Tag` fails a package in which no test carries a named tag (a misspelling never shrinks a run silently), refuses a selection that keeps every test of a package's whole test tree (the full suite in disguise), and cannot be combined with `-Keyword` on a Node suite. A tier name (`unit`, `slow`, `serial`, …) is never a tag. Rules and vocabulary: `datrix-common/docs/contributing/test-guidelines/feature-tags.md`. A run's `index.json` records `selection.tags`.

**Log output:** Unless `-NoSave` is used, `test.ps1` creates one timestamped log folder for each project it runs under that project's `.test_results` directory. AI agents do not need to capture full console output; read the final console lines to find the saved log folder, then inspect the files in that folder.

**Selection and suite-input stamp (`index.json` `schema_version: 2`):** every saved run records `selection` — `{"kind": "full"}` for a bare `test.ps1 <package>`, otherwise `{"kind": "targeted", "specific", "keyword", "tier", "marker", "tags"}` for `-Specific`/`-Keyword`/`-Tag`/any tier switch. Only a full run whose every phase completed records `inputs` (the suite-input fingerprint over the package's cone, installed set, interpreter, and observed foreign paths and executables); a targeted run never has an `inputs` key, so it can never stand in for a full one. A full run loads `datrix_common.testing.runner_plugin` (`-p`) in every phase and also leaves `observed-*.json` / `deselected-*.json` / `timings-*.json` / `workers-controller.json` records and a merged `timings.json`; any other saved run loads it in its parallel phase only and is never stamped. **The serial phase runs only when needed:** when every parallel worker's `deselected-<worker>.json` says it deselected 0 items (so no collected test is `serial`), the serial phase is skipped — `full.log` says `Phase 2: serial tests SKIPPED -- …` and `index.json` records `"phases": {"Serial": "skipped (0 serial items)"}` with no `junit-serial.xml`. It runs on any missing evidence (`-NoSave`, a worker the controller listed with no record, a parallel phase that did not complete), under a marker or keyword filter (`-Unit`/`-Fast`/`-Keyword`/…; `-Specific` is not a filter), and when workers deselected items. Workers disagreeing on the count, or an unreadable record, is a runner error: the serial phase runs and the run is FAILED with the reason in `index.json` `runner_errors`. When a full run cannot be stamped (a phase did not complete, a session's records are missing, or a cone tree changed while it ran), `full.log` says why and `index.json` has `selection` but no `inputs`. Field reference: [README.md](README.md#package-run-indexjson-schema-version-2).

**Never run two `test.ps1` invocations at once — batch the projects into ONE call instead.** `-Projects` is variadic and iterates sequentially, so `test.ps1 a b c` is the supported way to cover several packages. Before running anything, `test.ps1` calls `Ensure-DatrixPackagesInstalled`, which takes a **workspace-wide exclusive package lock** (`scripts/common/venv.ps1:1547`, 120s acquisition timeout) shared with `generate.ps1` — it guards the install/repair phase against concurrent writers of the one shared venv. A second concurrent invocation therefore blocks for up to two minutes and then dies with `Could not acquire package lock - another process may be installing packages`, having run **no** tests. The one sanctioned concurrency is `affected-gate.ps1` (Jon's tool — agents never run it), and it does not contend here: it runs that install check **once**, before any child, and launches every `test.ps1` child with `DATRIX_PACKAGES_ENSURED=1`, which makes `test.ps1` skip its own check (with `DATRIX_VENV_VERBOSE=1` it prints `Package install check skipped: the caller already ran it` instead). `test.ps1` restores its caller's value of that variable on exit, so a run started in your own shell never leaves it set for the next direct run — a direct `test.ps1` always performs its own check.

Two consequences worth knowing before you parallelize anything:

- **Concurrency here buys nothing and costs a lot.** The runs serialize on the lock whatever you do, and the loser fails outright rather than queueing. A sweep launched as N parallel invocations finishes later than the same sweep as one invocation, and reports failures that are pure contention.
- **Contention also breaks `npm`-dependent suites in a way that looks like a real defect.** Integration tests that shell out to `npm install` (`datrix-codegen-typescript`, `datrix-codegen-angular`) run under a fixed subprocess timeout and contend for CPU and npm's own cache locks. Oversubscribe the machine and they hit that timeout and report as **errors on setup**, indistinguishable at a glance from a genuine failure. `datrix-codegen-typescript` and `datrix-codegen-angular` both bound this deliberately: a `pytest_collection_modifyitems` hook in each package's `tests/conftest.py` pools every `@pytest.mark.npm_tsc` item into one of `DATRIX_TS_NPM_TSC_POOLS` (default 4) `xdist_group`s keyed by the test's file, and the runner's parallel phase distributes with `--dist loadgroup`, so at most that many npm/tsc chains run at once per session (the runner iterates packages sequentially, so that is the bound in practice). Set `DATRIX_TS_NPM_TSC_POOLS=1` to serialize them completely on a busy machine. Other packages do not bound this at all. If a run shows `npm install ... timed out` or a package-lock error, re-run the affected files on a quiet machine before believing the result — and treat the counts, not the exit code, as the signal.

### Node suites (`datrix-vscode`)

A package is testable when it carries a `tests/` folder (pytest) **or** a `package.json`
declaring a `test` script (Node). `test.ps1` dispatches on which it has, and both write the
same `.test_results/test-results-<stamp>/` artifacts — `full.log`, JUnit XML, `index.json` —
so `status-tests.ps1`, `-Rerun`, `gate-verdict.ps1` and `affected-gate.ps1` work on either
without knowing the difference. Which files hold a package's tests and which npm script
builds them are declared in a `datrix` block in its own `package.json`.

A Node package's dependency on a framework package is **not** declared there. That edge is
invisible to the Python import scan (it is a subprocess contract, not an import), and it
cannot live in a manifest that ships inside a distributable artifact — datrix-vscode's
`verify-package-contents.mjs` fails the build when any archived file names a framework
package. It is declared in the monorepo instead:
`datrix/scripts/config/cross-ecosystem-dependencies.json`, read by `affected-set.ps1` as a
SOURCE edge. A name there that resolves to no package on disk is an error, never an empty
result.

Options that have no counterpart in a Node suite are reported, never silently dropped:

| Option | On a Node suite |
|--------|-----------------|
| `-Specific "serverResolution.test.ts"` | Selects test files. The source-side `.ts` name is accepted for the compiled `.js` file; naming a file that does not exist is an error, not a smaller run |
| `-Keyword <expr>` | Passed to Node's `--test-name-pattern`, which is a **regex** where pytest's `-k` is a boolean name expression. An expression that matches nothing selects zero tests and is reported as a non-pass |
| `-Fast` | Excludes slow-marked tests; a Node suite marks none, so the whole suite runs (stated on stdout). The run is still recorded as the targeted `fast` selection and is never stamped with `inputs` |
| `-Unit` / `-Integration` / `-E2E` / `-Slow` | Select a marked subset a Node suite has none of. The package is skipped with a message, exit 0 — the same convention as pytest collecting nothing for a marker |
| `-Coverage` | Collects no data; the suite runs uninstrumented (stated on stdout) |

---

## `test\run-complete.ps1`

Complete workflow: syntax check, code generation, unit tests, deployment tests. `-Language`/`-L` is **mandatory**.

**Steps:** Step 1 (syntax checker) → Step 2 (code generation) → Step 3 (unit tests) → Step 4 (deployment tests: spec + integration). Step 5 is deprecated (merged into Step 4).

| Mode | Command | Description |
|------|---------|-------------|
| **Single (auto output)** | `.\test\run-complete.ps1 "examples/.../system.dtrx" -L python` | Output derived from test-projects.json |
| **Single (explicit output)** | `.\test\run-complete.ps1 "examples/.../system.dtrx" ".generated/python/docker/..." -L python` | Explicit output path |
| **Single + lang/platform** | `.\test\run-complete.ps1 "examples/.../system.dtrx" -L python -P docker` | Explicit language/platform |
| **All examples** | `.\test\run-complete.ps1 -All -L python` | Full workflow for all |
| **Foundation only** | `.\test\run-complete.ps1 -TestSet foundation -L python` | Foundation examples only |
| **Non-foundation** | `.\test\run-complete.ps1 -TestSet non-foundation -L python` | Everything except foundation examples |
| **Domains only** | `.\test\run-complete.ps1 -Domains -L typescript` | Domain examples only |
| **Custom test set** | `.\test\run-complete.ps1 -TestSet features-core -L python` | Named test set |
| **Skip syntax check** | `.\test\run-complete.ps1 -All -L python -Skip1` | Skip Step 1 (syntax checker) |
| **Skip generation** | `.\test\run-complete.ps1 -All -L python -Skip2` | Skip Step 2 (code generation) |
| **Skip unit tests** | `.\test\run-complete.ps1 -All -L python -Skip3` | Skip Step 3 (unit tests for generated projects) |
| **Skip deploy tests** | `.\test\run-complete.ps1 -All -L python -Skip4` | Skip Step 4 (deployment tests: spec + integration) |
| **Fresh build mode** | `.\test\run-complete.ps1 -TestSet foundation -L python -FreshBuild` | Force --no-cache for deploy tests (maximum validation) |
| **Generate only (skip tests)** | `.\test\run-complete.ps1 -All -L python -Skip3 -Skip4` | Steps 1-2 only |
| **Rerun failed** | `.\test\run-complete.ps1 -Rerun -L python` | Re-run only projects that previously failed or have never been tested |
| **Rerun domains** | `.\test\run-complete.ps1 -Rerun -Domains -L python` | Re-run only failed/untested domain projects |
| **Rerun tests only** | `.\test\run-complete.ps1 -Rerun -L python -Skip2` | Re-run failed/untested projects without regenerating |
| **Verbose output** | `.\test\run-complete.ps1 -All -L python -VerboseOutput` | Show detailed generation and test output |
| **Skip venv** | `.\test\run-complete.ps1 -All -L python -SkipVenv` | Use system Python |
| **Debug** | `.\test\run-complete.ps1 -All -L python -Dbg` | Debug logging |

**Parameters:** `-ExamplePath` (positional 0), `-OutputPath` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (python\|typescript, **mandatory**), `-Platform`/`-P` (output-path runtime segment, default: docker-compose; provider segment comes from each project's `config/system.dcfg`), `-Hosting`/`-H`, `-TestSet` (default: all), `-Rerun`, `-VerboseOutput`, `-SkipVenv`, `-Skip1`, `-Skip2`, `-Skip3`, `-Skip4`, `-Skip5` (deprecated), `-FreshBuild`, `-Dbg`/`-DebugLogging`, `-LlmSummary`, `-LlmLimit` (default: 12), `-OllamaUrl` (default: `http://10.94.0.100:11434`), `-LlmModel` (default: `qwen3-coder:30b-ctx32k`), `-LlmTimeout` (default: 180), `-LlmNumPredict` (default: 4096), `-LlmTemperature` (default: 0.1), `-LlmKeepAlive` (default: `10m`)

**Note:** Deploy tests (Step 4) use Docker cache by default for faster builds and better network resilience. Use `-FreshBuild` to force `--no-cache` for maximum validation confidence. `-Skip5` is accepted but deprecated (Step 5 merged into Step 4).

**LLM advisory summary:** Pass `-LlmSummary` to print a post-run advisory summary generated by a local Ollama model against the aggregate result indexes. All `-Llm*` and `-OllamaUrl` parameters only take effect when `-LlmSummary` is set.

---

## `test\dual-target.ps1`

Runs generation against both Python and TypeScript for the same test set and compares results.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\test\dual-target.ps1` | typescript-validation set, both languages |
| **All examples** | `.\test\dual-target.ps1 -TestSet all` | Full parity check |
| **Skip deploy tests** | `.\test\dual-target.ps1 -Skip4 -Skip5` | Uses `run-complete.ps1` (steps 1-3: syntax + generation + unit tests, skips deployment) |
| **Fresh build** | `.\test\dual-target.ps1 -Skip4 -Skip5 -FreshBuild` | Use --no-cache for deploy tests (when run-complete.ps1 used) |

**Parameters:** `-TestSet` (default: typescript-validation), `-Platform` (any installed `datrix.platforms` plugin name — discovered at runtime; default: docker; fails loud listing the installed platforms if unknown), `-Skip4`, `-Skip5` (both required to use `run-complete.ps1` instead of `generate.ps1`), `-FreshBuild`, `-Dbg`

---

## `test\test-single.ps1`

Lightweight single-test runner for checkpoint-based debugging. Runs exactly what you specify with minimal overhead.

| Mode | Command | Description |
|------|---------|-------------|
| **Single file** | `.\test\test-single.ps1 "D:\datrix\datrix-codegen-python\tests\test_entity.py"` | Run all tests in file |
| **Node ID** | `.\test\test-single.ps1 "tests/test_entity.py::TestEntity::test_basic" -Project datrix-codegen-python` | One test method |
| **Keyword** | `.\test\test-single.ps1 -Project datrix-common -Keyword "test_poly_string"` | Match by keyword |
| **Fail fast** | `.\test\test-single.ps1 "tests/test_enum.py" -Project datrix-codegen-typescript -FailFast` | Stop on first failure |
| **Verbose** | `.\test\test-single.ps1 "tests/test_foo.py" -Project datrix-common -Verbose` | Full pytest output |

**Parameters:** `-TestPath` (positional 0), `-Project`, `-Keyword`, `-Marker`, `-Verbose`, `-FailFast`, `-Dbg`

**Note:** Auto-detects project from full test path. Use `-Project` when providing relative paths or keyword-only searches.

---

## `test\cleanup.ps1`

Lists/deletes `.test_results` folders (containing timestamped test result directories) under each datrix project and `.generated/`.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\test\cleanup.ps1` | Show what would be deleted |
| **Delete** | `.\test\cleanup.ps1 -Force` | Delete after confirmation |
| **Trim old results** | `.\test\cleanup.ps1 -Force -Trim` | Keep 10 newest, delete older |
| **Custom base dir** | `.\test\cleanup.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Force`, `-Trim`, `-Dbg`

---

## `test\compare-tests.ps1`

Compares timestamped test runs inside one explicit `.test_results` folder. It does not scan multiple projects.

| Mode | Command | Description |
|------|---------|-------------|
| **Compare project runs** | `.\test\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results` | Compare unit/deploy runs for one project |
| **Write Markdown report** | `.\test\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results -Report D:\datrix\ecommerce-test-comparison.md` | Save report to a file |
| **Debug logging** | `.\test\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results -Dbg` | Enable debug output |

**Parameters:** `-TestResults` (positional, required; must be a `.test_results` folder), `-Report`, `-Dbg`

**Comparison behavior:** `unit-tests-*` folders are compared only with unit-test runs, and `deploy-test-*` folders only with deploy-test runs. When more than two timestamps exist, all runs are listed and the service-level delta compares the second-newest run to the newest run; the history column shows all runs.

---

## `test\mypy.ps1`

Runs mypy type checking for one or more Datrix projects. Accepts the same flags as `test.ps1` for command-line symmetry, but most test-selection flags (`-Unit`, `-Integration`, `-E2E`, `-Fast`, `-Slow`, `-Keyword`) are accepted for parity and silently ignored by the underlying mypy runner.

**A human-only tool, enforced.** No skill, hook, orchestrator, or other script runs it: its only caller is `affected-gate.ps1`'s opt-in `-Mypy` switch. The agent contract forbids agents to run any standalone type-checker (`CLAUDE.md`, "Running Python"), and that is now a harness block rather than prose -- `guard-forbidden-commands.py` refuses `mypy`/`dmypy`/`pyright`, the `python -m mypy` form, this wrapper, `library/mypy.py`, and `affected-gate.ps1 -Mypy` from any agent tool call. A person running it in his own terminal is not a tool call and is unaffected. For agents, the tests of the code they changed are the gate for type correctness; this wrapper exists so a person can run a full type-check on demand.

**The cache never lands in a package repo.** mypy writes `.mypy_cache/` into its working directory, which here is the package root, so the runner passes an explicit `--cache-dir D:\datrix\.tmp\mypy-cache\<project>`. Left at the default, one sweep of the installable packages buried ~51,400 cache files in 15 separate git repositories and failed `ignored-source-gate.ps1`. Run logs still go to `<project>/.test_results/mypy-results-<timestamp>.log`, which is the sanctioned in-repo location the test runner already owns.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\test\mypy.ps1 datrix-common` | Type-check one project |
| **Multiple projects** | `.\test\mypy.ps1 datrix-common datrix-language` | Type-check several |
| **All projects** | `.\test\mypy.ps1 -All` | All packages with pyproject.toml |
| **Specific file/dir** | `.\test\mypy.ps1 datrix-common -Specific "src/datrix_common/utils.py"` | Check one file or directory |
| **Verbose output** | `.\test\mypy.ps1 datrix-common -VerboseOutput` | Full mypy output |
| **No log save** | `.\test\mypy.ps1 datrix-common -NoSave` | Don't save output to log files |
| **Debug** | `.\test\mypy.ps1 datrix-common -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-VerboseOutput`, `-NoSave`, `-Specific <path>`, `-Dbg`

**The `datrix` showcase repo itself is a valid explicit project name** (e.g. `.\test\mypy.ps1 datrix -Specific "scripts/test/check-generated-file-ratchet.py"`) even though it is excluded from `-All`'s package sweep -- `datrix/pyproject.toml` carries its own `[tool.mypy]` (strict) section for its repo-level validation scripts, but is deliberately never auto-discovered by `Get-DatrixPackageNamesGlobWithPyProject`'s `datrix-*` glob (it is not an installable toolchain package). Always pass `-Specific` for `datrix` -- there is no `src/` layout to default to.

---

## Status Scripts

### `test\status-tests.ps1`

Reports test results from latest test logs for all datrix projects. Reads structured `index.json` when available (new directory format), falls back to regex-parsing flat log files.

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
| **One language only** | `.\test\status-deploy-tests.ps1 -L java` |
| **Markdown report** | `.\test\status-deploy-tests.ps1 -Report <path>` |
| **With debug** | `.\test\status-deploy-tests.ps1 -Dbg` |

**Parameters:** `-Report <path>`, `-Language` / `-L <lang>`, `-Dbg`

`-Language` restricts the report to `.generated\<language>` (any language directory
present in the tree). Omit it to report on every language.

### `test\status-unit-tests.ps1`

Reports run test results from `.generated/` tree.

| Mode | Command |
|------|---------|
| **Show status** | `.\test\status-unit-tests.ps1` |
| **One language only** | `.\test\status-unit-tests.ps1 -L python` |
| **With debug** | `.\test\status-unit-tests.ps1 -Dbg` |

**Parameters:** `-Language` / `-L <lang>`, `-Dbg`

`-Language` restricts the report to `.generated\<language>` (any language directory
present in the tree). Omit it to report on every language.

---

## Failure-Analysis Scripts (agent-oriented: minimal console, details to JSON)

These parse structured test-results run directories so AI agents read compact JSON instead of raw logs. Each prints a 1-2 line summary plus a `Details:` path; the full detail is in the JSON it writes.

### `test\collect-failure-data.ps1`

Builds `failure-data.json` inside a run directory: every error/failure cluster with its representative's traceback tail embedded, `codegen_hint`/`generated_file` when present, and (package runs only) a ready-to-run `test_command`. That command's shape follows the suite the package actually carries — a pytest package gets a `test-single.ps1` node-ID re-run, a Node package (`datrix-vscode`, which has no single-test runner) gets `test.ps1 <pkg> -Specific "<source .ts file>"`, and a package carrying no recognizable suite gets no `test_command` key at all rather than an invocation that cannot run. Supports all three index schemas: package (`structured_log_writer`), generated-project unit (`generated_test_log_writer`), and deploy-test (`deploy_test_log_writer` — deploy adds `failed_phase`; infra errors are keyed `phase#id` and may have `traceback_tail: null`).

| Mode | Command | Description |
|------|---------|-------------|
| **Run directory** | `.\test\collect-failure-data.ps1 "D:\datrix\datrix-common\.test_results\test-results-YYYYMMDD-HHMMSS"` | Parse an explicit run dir (or its `index.json` path) |
| **Latest run of a package** | `.\test\collect-failure-data.ps1 -Project datrix-codegen-aws` | Auto-locate the newest `test-results-*` run |
| **Longer tracebacks** | `.\test\collect-failure-data.ps1 -Project datrix-common -MaxLogLines 120` | Embed more tail lines per representative (default 60) |
| **Self-test only** | `.\test\collect-failure-data.ps1 -SelfTest` | Parse one fixture index per supported writer schema and check the re-run command emitted for each suite kind; skip the real run analysis |

**Parameters:** positional run-dir/`index.json` path OR `-Project <name>` (exactly one), `-MaxLogLines <n>`, `-SelfTest`, `-Dbg`

**Schema-shape self-test.** The three writers do not spell their cluster keys identically —
`structured_log_writer` and `deploy_test_log_writer` use `failure_ids`/`representative_failure_id`
inside `failure_clusters`, while `generated_test_log_writer` builds both of its cluster lists from
one `ErrorCluster` shape and therefore spells them `error_ids`/`representative_error_id` there too.
Test ids differ the same way: a pytest id carries a lowercase dotted module prefix that maps to a
source path, an xUnit id (`Namespace.Class::Method`) carries none, so the representative's `file` is
null and the locator is its `generated_file`. `-SelfTest` parses one minimal fixture index per shape
plus a deliberate unknown-spelling case that MUST be rejected (non-vacuity), so a writer that changes
its spelling fails here rather than at an agent's first read of a real run.

**Re-run-command shape self-test.** The same run also pins the `test_command` emitted for each suite
kind against a fixture package tree — pytest markers must yield the `test-single.ps1` form and Node
markers the `test.ps1 -Specific` form, each asserted to carry none of the other's markers, plus a
suite-less package that must yield no command at all. Handing a Node package the pytest invocation
is worse than emitting nothing: it reads as ready-to-run and cannot run.

**Output:** `{run-dir}\failure-data.json`. **Exit codes:** 0 = analysis completed (even all-green), 2 = usage / input not found / unrecognized schema / a failing `-SelfTest` case.

### `test\extract-warnings.ps1`

Parses the pytest `warnings summary` section of a run's `full.log` into deduplicated `warnings.json` (file, line, category, message, triggering code line, dedup count, per-category totals).

| Mode | Command |
|------|---------|
| **Run directory** | `.\test\extract-warnings.ps1 "D:\datrix\datrix-codegen-aws\.test_results\test-results-YYYYMMDD-HHMMSS"` |
| **index.json / full.log path** | `.\test\extract-warnings.ps1 "...\test-results-YYYYMMDD-HHMMSS\index.json"` |

**Parameters:** positional path (run dir, `index.json`, or `full.log`), `-Dbg`

**Output:** `{run-dir}\warnings.json` (empty `warnings` list when the run had no warnings section). **Exit codes:** 0 = done, 2 = usage error.

### `test\classify-run-delta.ps1`

Compares two runs of the same package and classifies the delta: `SUCCESS` (all previously-failing fixed, none new), `PARTIAL`, `NO_CHANGE`, or `REGRESSION` (new failures). Writes `run-delta.json` (with `now_passing` / `still_failing` / `new_failures` / cluster-level resolution lists) into the CURRENT run dir.

| Mode | Command |
|------|---------|
| **Named parameters** | `.\test\classify-run-delta.ps1 -Previous "{old-run-dir}" -Current "{new-run-dir}"` |
| **Positional** | `.\test\classify-run-delta.ps1 "{old-run-dir}" "{new-run-dir}"` |

**Parameters:** `-Previous`, `-Current` (run dirs or `index.json` paths; same project on both sides), `-Dbg`

**Exit codes:** 0 = SUCCESS, 1 = PARTIAL / NO_CHANGE / REGRESSION, 2 = usage error.

### `test\gate-verdict.ps1`

Aggregates the newest run of each requested package into a GREEN/RED gate verdict — one console line per package plus `OVERALL`. A package with no results, an in-progress/UNKNOWN result, or any failure is RED (fail-loud; never falsely green).

| Mode | Command |
|------|---------|
| **Named packages** | `.\test\gate-verdict.ps1 -Projects datrix-common,datrix-language` |
| **All testable packages** | `.\test\gate-verdict.ps1 -All` |
| **Custom output path** | `.\test\gate-verdict.ps1 -All -Output D:\datrix\.tmp\test\my-gate.json` |

**Parameters:** `-Projects <comma-separated>` OR `-All`, `-Output <path>`, `-Dbg`

**Output:** `D:\datrix\.tmp\test\gate-verdict.json` (schema 2: per-package counts + capped failing-test list). **Exit codes:** 0 = overall GREEN, 1 = overall RED, 2 = usage error.

**CARRIED verdict kind.** Rows have a third verdict, `CARRIED`, produced only through `evaluate_projects(carried=...)` by `affected-gate.ps1` (this CLI judges newest runs and never carries). A CARRIED row names a recorded green **full** run that stood in for a fresh one because its suite-input fingerprint still matches; it counts as green for `OVERALL` but is never rendered or serialized as `GREEN`. Every row carries two fields for it: `carried` (true only on a CARRIED row) and `fingerprint` (the fingerprint computed now that equals the run's recorded one; null otherwise). A CARRIED row's `run_dir`, `counts` and `age_minutes` are the carried run's own. The claim is re-checked against that run's `index.json` — `selection.kind` must be `full`, `result` `PASSED` with zero failed/errors, and `inputs.fingerprint` equal to the claimed one; anything else is `RED` with reason `CARRY_REJECTED: …`, never a fall-through to another run. Console line: `datrix-extensions: CARRIED 54 passed (run test-results-20260923-204821, age 3.2m, fingerprint 3c6f31f30e7e022b)`.

---

## Validation Scripts

### `test\type-mapping-completeness.ps1`

Two independent checks over the language type-mapping surfaces, both run on every invocation:

1. **Canonical-type completeness** — every canonical type in `TypeRegistry` has a mapping in
   each requested language's `TYPE_MAP` (`global_registry.unmapped_types`). Restricted by
   `-Languages` when given; defaults to every registered `datrix.languages` target (derived at
   runtime from the installed entry points — never a hardcoded literal). **SQL is not covered by
   this leg** — it is not a `datrix.languages` plugin and its `type_mappings` module does not
   register with `global_registry`.
2. **Extension-map completeness** (D3) — for every installed `datrix.extensions` pack, every
   registered language's `*_EXTENSION_MAPS` dict (`PYTHON_EXTENSION_MAPS`, `JAVA_EXTENSION_MAPS`,
   `TS_EXTENSION_MAPS`, `DOTNET_EXTENSION_MAPS`) **and SQL's** (`SQL_EXTENSION_MAPS`) must carry a
   key for that pack's name — an entry present but empty is correct for a pack contributing zero
   scalars. This leg is unconditional: `-Languages` never narrows it. SQL is checked here via its
   `datrix.generators` registration (`list_available_generators()`), not via `datrix.languages`.

**Built-in non-vacuity self-test, every invocation.** Before any real check is trusted, the script
feeds the extension-map comparator a synthetic surface that DOES carry a synthetic pack's key
(must report zero missing) and a synthetic surface that does NOT (must report exactly that pack
missing); a comparator that cannot detect the forced gap aborts (exit 2) before either real check
runs.

| Mode | Command | Description |
|------|---------|-------------|
| **Both checks, every registered language** | `.\test\type-mapping-completeness.ps1` | Canonical-type check over every registered language + extension-map check over every registered language and sql |
| **Restrict canonical-type check** | `.\test\type-mapping-completeness.ps1 -Languages python,typescript` | Canonical-type check limited to the named languages; extension-map check still covers everyone |
| **Debug** | `.\test\type-mapping-completeness.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\type-mapping-completeness.ps1 -SelfTest` | Run only the extension-map comparator's non-vacuity self-test; skip both real checks |

**Parameters:** `-Languages` (comma-separated subset of the REGISTERED `datrix.languages` set;
optional — omit for every registered language; restricts the canonical-type leg only), `-SelfTest`,
`-Dbg`

**Assertions:** canonical-type leg — `global_registry.unmapped_types(language)` is empty for every
requested language. Extension-map leg — `compare_extension_map_completeness` reports zero missing
packs for every surface (every registered language + sql).

**Exit codes:** 0 = both checks pass (or a successful `-SelfTest` run), 1 = either check found a
gap, 2 = the non-vacuity self-test failed, no languages are registered/requested, or a
discovery/import error occurred.

---

### `test\typescript-whole-system-gate.ps1`

Whole-system **TypeScript** generation gate: proves the whole-system generate path emits real TypeScript (not a hollow/failed run) and is byte-deterministic. Generates the language-neutral `examples/01-foundation` twice with `-Language typescript`, into two explicit `--output` dirs, and asserts realness + byte-stability. The target comes solely from the flag — Datrix has no language-specific examples, and a `language` key in a system `.dcfg` is rejected at load time. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\typescript-whole-system-gate.ps1` | Generate twice, assert realness + byte-stability |
| **Custom output root** | `.\test\typescript-whole-system-gate.ps1 -OutputRoot D:\datrix\.test-output\ts-gate` | Override run1/run2 location |
| **Debug** | `.\test\typescript-whole-system-gate.ps1 -Dbg` | Forward `-Dbg` to generate.ps1 |

**Parameters:** `-OutputRoot` (default: `d:/datrix/.test-output/ts-gate`), `-Dbg`/`-DebugLogging`

**Assertions:**
- **Realness (positive):** generated `*.ts` source count > 0 (the TypeScript language generator ran).
- **Realness (leak guard):** no `*.py` under any generated `src/` tree, and every `*.py` in the output lives only under `tests/` or `migration-tools/` — the two **language-agnostic** Python artifact classes emitted for every target (httpx HTTP-contract integration tests regenerated by datrix-codegen-python's `python_http_contract_overlay`; the live-schema exporter rendered by datrix-codegen-sql). Any other `*.py` is a language leak and fails the gate.
- **Byte-stability:** recursive sha256 diff of run1 vs run2, excluding non-source build/install artifacts `.datrix/`, `.ruff_cache/`, `.tsc_cache/`, `node_modules/`. Any content or file-set difference fails.

**Exit codes:** 0 = real + byte-stable TypeScript whole-system output, 1 = generation failed, realness violated, or byte drift detected.

---

### `test\java-generation-determinism-gate.ps1`

Java generation-pipeline determinism gate: the SAME source tree, generated N times in a row via the documented single-project `generate.ps1` path, must never produce two different outcomes (same failure mode every time, or a byte-identical success manifest every time). Each run is its own `generate.ps1` process (fresh `python.exe`, fresh `PYTHONHASHSEED`), so this also exercises hash-seed-driven set-iteration-order bugs a single long-lived process would never surface. Targets `examples/02-features/03-infrastructure-blocks/nosql/system.dtrx` — the example a java corpus generation sweep found producing three different outcomes (a struct-test planning failure, then two different `mvnw compile` failures) from the identical, unchanged-tree invocation. No before/after comparison of two code states can catch this class of bug, because it never runs the same code twice; this gate runs the SAME code N times and compares outcomes to each other. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (5 runs)** | `.\test\java-generation-determinism-gate.ps1` | Generate 5 times, assert identical outcomes |
| **Custom run count** | `.\test\java-generation-determinism-gate.ps1 -Runs 3` | Fewer/more repeated generations (must be >= 2) |
| **Custom output root** | `.\test\java-generation-determinism-gate.ps1 -OutputRoot D:\datrix\.test-output\java-determinism-gate` | Override run1..runN location |
| **Debug** | `.\test\java-generation-determinism-gate.ps1 -Dbg` | Forward `-Dbg` to generate.ps1 |

**Parameters:** `-OutputRoot` (default: `d:/datrix/.test-output/java-determinism-gate`), `-Runs` (default: 5, must be >= 2), `-Dbg`/`-DebugLogging`

**Assertions:**
- Every run's classification (SUCCESS vs FAILED) matches run 1's.
- A SUCCESS run's per-relative-path sha256 manifest of the generated source tree (excluding `.datrix/`, whose audit log / snapshot / manifest `generated_at` timestamp are expected to differ every invocation by design) matches run 1's manifest exactly.
- A FAILED run's generation-results log, normalized (run-specific `--output` directory replaced with a fixed placeholder; timestamp/log-path preamble lines stripped) and hashed, matches run 1's normalized fingerprint exactly.

**Exit codes:** 0 = all N runs produced the identical outcome, 1 = a classification or fingerprint mismatch was found (non-deterministic generation), non-zero PowerShell error = usage/environment error (e.g. venv activation failure, missing example).

---

### `test\ingress-migration-conformance-gate.ps1`

Declaration-driven service ingress migration conformance gate. Repo-level, independent proof that regenerating the framework's own showcase examples produces only the four intended DI-6 realized-exposure deltas. Regenerates three representative registered examples individually (`identity` for delta d, `shared-block` for delta a, `authentication` + `01-foundation` for delta c) via single-project explicit-output `generate.ps1` calls, separately runs the existing full-tree example generation gate (`run-complete.ps1 -All -Skip3 -Skip4`) over every registered example, proves at the source level that the webhook verification prelude is independent of `AuthMode`, and greps for the removed config keys. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (both languages)** | `.\test\ingress-migration-conformance-gate.ps1` | Full DI-6 conformance sweep, python + typescript |
| **Single language** | `.\test\ingress-migration-conformance-gate.ps1 -Languages python` | Faster iteration while debugging |
| **Custom output root** | `.\test\ingress-migration-conformance-gate.ps1 -OutputRoot D:\datrix\.test-output\ingress-gate` | Override scratch generation root |
| **Debug** | `.\test\ingress-migration-conformance-gate.ps1 -Dbg` | Forward `-Dbg` to generate.ps1/run-complete.ps1 |

**Parameters:** `-OutputRoot` (default: `D:\datrix\.test-output\ingress-gate`), `-Languages` (comma-separated, default: `python,typescript`), `-Dbg`/`-DebugLogging`

**Assertions:**
- **Step 0 (live counts):** re-verifies `rest_api` file count, `system.dcfg` gateway-declaration count, `auth(service` occurrence count, and that the sole `verify(` usage is paired with `auth(webhook)` (the webhook migration's precondition).
- **Delta (a):** shared-block's `publisher-service.dtrx` (all-`auth(service)` surface) derives `INTERNAL` — no gateway route, no bare all-interfaces port publish.
- **Delta (b):** documented, verified absence — no registered example reproduces the name-suppression fixture (owned by the docker/azure/aws package suites).
- **Delta (c):** a single-service example with a declared `gateway {}` (`authentication`) emits a non-empty `config/nginx/nginx.conf`; a single-service example with NO declared gateway (`01-foundation`) emits none.
- **Delta (d):** the shared webhook context builder, the python prelude builder and the typescript guard template each dispatch only on their verify-mode field and carry no `AuthMode` / `auth_contract.mode` / `access_level` reference, so the generated prelude is a pure function of the unchanged `verify(...)` contract; `identity` is also regenerated per language so the live tree is on disk for inspection (the repo keeps no stored output snapshot to diff against).
- **Step 3:** zero ING001/ING002/ING003 and webhook-invariant errors across the full-tree generation gate, both languages (known, tracked, out-of-scope failures — e.g. shared-block's pre-existing API003/XSV017 defect — are reported but not conflated with an ingress regression).
- **Step 4:** zero `publicIngress`/`platforms.azure.services` matches under `datrix/examples`.

**Exit codes:** 0 = every DI-6 delta class accounted for and the negative acceptance property holds, 1 = any finding (including known, out-of-scope pre-existing defects, reported distinctly) causes a non-zero ledger.

---

### `test\check-enum-value-literals.ps1`

**Hard-zero gate: no generator may branch on a user enum's member values.** AST-scans every `datrix-codegen-*`, `datrix-common` and `datrix-language` `src/` tree for two shapes: a member looked up by literal name (`.get_value("X")` / `.require_value("X")`), and a string literal tested against a collection of member names (`"X" in value_names`). A `.dtrx` enum's members are the declaring project's vocabulary — a generator reading one by literal turns somebody else's spelling into policy, so renaming a member silently changes behaviour and naming an unrelated enum the same way silently triggers it. Declared contracts (see `work { }`) reference the model instead. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

**There is no exemption file, on purpose.** A legitimate need to branch on a member value is a design defect, not an entry to record. The baseline is zero and only zero passes.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-enum-value-literals.ps1` | Scan every package, fail on any violation |
| **Self-test only** | `.\test\check-enum-value-literals.ps1 -SelfTest` | Prove the scanner detects both shapes; skip the real scan |
| **Show files** | `.\test\check-enum-value-literals.ps1 -ShowFiles` | Print each file as it is scanned |
| **Custom base dir** | `.\test\check-enum-value-literals.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-enum-value-literals.ps1 -Dbg` | Debug logging |

**Parameters:** `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** It plants one instance of each detected shape and requires both to be found, then requires clean source to report none — so a scanner that can only return zero fails here rather than being believed. A run that discovers no package source also fails rather than passing vacuously.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = a violation was found, 2 = usage error, no packages discovered, or the self-test failed.

---

### `test\check-handler-name-dedup.ps1`

**Hard-zero gate: no `datrix-codegen-*` package may de-duplicate a handler name.** AST-scans every `datrix-codegen-*` package's `src/` tree for the retired `while <name> in used: <name> = f"{base}{suffix}"; suffix += 1` shape over a derived REST handler / controller method name. Every handler name is derived ONCE, in the shared API-level derivation (`datrix_common.generation.api_helpers` — `compute_rest_api_handler_names` / `rest_api_handler_names_by_endpoint`), which refuses to hand two endpoints of one `rest_api` a single name: it raises, naming both routes. A package-local de-duplicator does the opposite — it renames one side of the collision (`getOrders` / `getOrders2`) while the browser client, the API test generator and every other language target keep calling that route by the un-numbered name, so the collision is hidden rather than resolved. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

**A match needs all three parts together**, which is what keeps the gate off the retired shape's legitimate neighbours: (1) the numeric-suffix allocation loop; (2) an **accumulating** container — named like a claim set (`used`, `used_names`, `seen`, `taken`, `claimed`, `existing`, …) or mutated by the enclosing function (`.add`/`.append`/`.update`/`.extend`/`|=`/item assignment) — which is what makes the rename order-dependent and invisible to other consumers; (3) a **handler-shaped subject** — a `handler`/`controller`/`endpoint`/`route`/`action` token in the module path, the enclosing function's name, or an identifier the loop touches. Part 2 clears deterministic shadow avoidance against a fixed set of other symbols (a serverless handler `def` renamed away from a service function's name); part 3 clears local-variable, generated-test-method and temp-file name allocation, which no second emitter consumes.

**There is no exemption file, on purpose.** A REST handler name that needs local de-duplication is a name that should have come from the shared table. The baseline is zero and only zero passes.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-handler-name-dedup.ps1` | Scan every `datrix-codegen-*` package, fail on any violation |
| **Self-test only** | `.\test\check-handler-name-dedup.ps1 -SelfTest` | Prove the scanner detects every retired form and clears every near-miss; skip the real scan |
| **Show files** | `.\test\check-handler-name-dedup.ps1 -ShowFiles` | Print each file as it is scanned |
| **Custom base dir** | `.\test\check-handler-name-dedup.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-handler-name-dedup.ps1 -Dbg` | Debug logging |

**Parameters:** `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** It plants each retired form (java's path-fold de-duplicator, java's nested-handler de-duplicator, .NET's nested-action de-duplicator whose function name says "method" rather than "handler" and is caught by the module path) and requires each to be detected, then plants each legitimate near-miss (serverless shadow avoidance, generated-test-method disambiguation, local-variable allocation) and requires each to be reported clean — so neither a scanner that can only return zero nor one that flags everything is believed. A run that discovers fewer than two `datrix-codegen-*` packages with a `src/` tree, or no Python source in them, fails rather than passing vacuously.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = a violation was found, 2 = usage error, too few packages discovered, or the self-test failed.

---

### `test\check-generated-file-ratchet.ps1`

GenDSL 2 Invariant I5 ratchet: AST-counts direct `GeneratedFile(...)` constructor calls per `datrix-*` package's `src/` tree and fails if any package's count exceeds its frozen baseline at `scripts/config/generated-file-ratchet.json`. Every emitted file should eventually be declared in genDSL rather than hand-constructed; this ratchet freezes the current count per package and only ever allows it to shrink as later migrations convert hand-coded construction into genDSL declarations. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), following the same AST-scan-and-ratchet shape as `dev\check-import-boundaries.ps1`'s I1/I6 ratchets.

| Mode | Command | Description |
|------|---------|-------------|
| **Run ratchet** | `.\test\check-generated-file-ratchet.ps1` | Scan all packages, fail on regressions |
| **Warning mode** | `.\test\check-generated-file-ratchet.ps1 -Warn` | Report regressions but exit 0 |
| **Show files** | `.\test\check-generated-file-ratchet.ps1 -ShowFiles` | Print each file being scanned |
| **Freeze/tighten baseline** | `.\test\check-generated-file-ratchet.ps1 -UpdateBaseline` | Recompute counts and write the baseline (bootstrap freeze if none exists yet; otherwise only accepts decreases) |
| **Self-test only** | `.\test\check-generated-file-ratchet.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite; skip the real package scan |
| **Custom base dir** | `.\test\check-generated-file-ratchet.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-generated-file-ratchet.ps1 -Dbg` | Debug logging |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-UpdateBaseline`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements, per the datrix showcase boundary) covers `count_generated_file_constructions`, `discover_packages`, `scan_package`, and `check_ratchet` edge cases -- including the adversarial "regression when above baseline" case, which must produce a message. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation and skips the real scan. `--harness-self-test` (no `.ps1` switch -- diagnostic only) registers one intentionally-failing dummy check to prove the `[OK]`/`[FAIL]` harness itself is not vacuous.

**Assertions:**
- Direct `GeneratedFile(...)` constructor calls (bare or module-qualified) are counted per package's `src/` tree; `GeneratedFile.from_content(...)` is never counted (a distinct call shape).
- `tests/` directories are never scanned (structural: only `src/` is walked).
- `datrix-codegen-common/src/datrix_codegen_common/gendsl/executor.py` is excluded (the declared-render path's own internals).
- A package absent from the baseline has an implicit baseline of 0.

**Exit codes:** 0 = every package's count is at or below its frozen baseline (or a successful `-UpdateBaseline` or `-SelfTest`), 1 = a package's count exceeds its frozen baseline (or `-SelfTest`/`--harness-self-test` reports a failing check), 2 = usage error, missing baseline, an attempted baseline increase over an existing baseline, or the automatic self-test step failing on a normal invocation.

---

### `test\check-docs-conformance.ps1`

Docs-conformance Invariant I5 gate: extracts repo-relative path references and Python module references from the curated 38-file architecture-doc set (each package's `docs/architecture.md` and/or `docs/architecture/` tree — `datrix-extensions` has neither and contributes zero) and fails if any reference does not resolve to a real file/directory/module in the tree, unless it is recorded in the committed exceptions baseline at `scripts/config/docs-conformance-exceptions.json` (a "what was removed" migration-history claim, a "must never exist" prohibition claim, or another confirmed-intentional non-existence). This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), following the same scan-and-baseline shape as `check-generated-file-ratchet.ps1`'s I5 ratchet, except the exceptions baseline is hand-edited and reviewed (no `-UpdateBaseline` flag — every entry needs a human-authored reason a script cannot synthesize).

`ARCHITECTURE_DOC_FILES` is a literal, reviewable constant in the script (never a directory glob) — "architecture docs" is a curated concept, and a new architecture doc added later is a deliberate, reviewed one-line addition to that constant. This v1 only checks path-reference candidates that are fully package-qualified (start with a known package name or `D:\datrix\`) and module-reference candidates that are fully import-qualified (start with a known Python import name) — a bare, package-relative shorthand span with no anchor at all is never a candidate (deliberate scope boundary, not a gap).

> **`ARCHITECTURE_DOC_FILES` is the one registry in the repo that does NOT self-update.** Everywhere else the package set is discovered from disk (`Get-DatrixDirectories`, `Get-DatrixPackages`, the metrics reports, `commit-and-push`), so a new package is picked up with no edit. This tuple is deliberately the exception — a curated list, reviewed by a human. Consequence: when a new `datrix-codegen-<lang>` package ships its own `docs/architecture.md`, that entry must be **added to the tuple by hand** (and the doc count in this section bumped), or the new package's architecture doc is silently never scanned by the gate. A package with no architecture doc yet contributes zero entries and is correctly absent — as `datrix-extensions` already is.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-docs-conformance.ps1` | Scan all 38 architecture docs, fail on unresolved references |
| **Warning mode** | `.\test\check-docs-conformance.ps1 -Warn` | Report unresolved references but exit 0 |
| **Show files** | `.\test\check-docs-conformance.ps1 -ShowFiles` | Print each architecture doc file being scanned |
| **Self-test only** | `.\test\check-docs-conformance.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite; skip the real docs scan |
| **Custom base dir** | `.\test\check-docs-conformance.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-docs-conformance.ps1 -Dbg` | Debug logging |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements, per the datrix showcase boundary) covers `extract_path_candidates`, `extract_module_candidates`, `resolve_path_candidate` (Tier 1 + Tier 2, including the adversarial ambiguous-Tier-2-match case, which must stay unresolved), `resolve_module_candidate`, `load_exceptions`, and `check_against_exceptions`. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation and skips the real scan. `--harness-self-test` (no `.ps1` switch -- diagnostic only) registers one intentionally-failing dummy check to prove the `[OK]`/`[FAIL]` harness itself is not vacuous.

**Assertions:**
- Every single-backtick inline code span in each of the 38 architecture docs is extracted as a path-reference or module-reference candidate per the fixed extraction rules (package/drive-prefixed for paths, import-name-prefixed dotted chains for modules); a span containing `...`, `<`/`>`, or `*` is rejected outright.
- A path candidate resolves via Tier 1 (exact path exists under the monorepo root; a trailing-slash candidate must be a directory) or Tier 2 (an unambiguous `src/`/`tests/`-relative suffix match — never attempted when the candidate already starts with `src`/`tests`, and never resolved when the suffix matches 2+ files).
- A module candidate resolves when any decreasing-length prefix of its segments after the import name matches a real `.py` file or package `__init__.py` (tolerating a trailing symbol/attribute/function name).
- A candidate unresolved by both tiers is checked against the exceptions baseline (span text -> reason); present spans never fail the gate, absent spans do.
- Every Markdown anchor link (`[text](<doc>.md#anchor)` or `[text](#anchor)`) in a curated doc names a heading that exists in the target doc, by the GitHub-flavoured slug the heading text produces (duplicates numbered); a missing target doc fails the same way. Reported with kind `anchor`, span `<target>#<anchor>`.
- Every `### Decision N:` heading in a curated doc carries a status from the closed vocabulary (`Adopted`, `Implemented`, `Stable`, `Approved — Implementation In Progress`); a `**Status:**` paragraph in the section, when present, opens with a status of the same class (`Adopted`/`Landed`/`Implemented`/`Stable` vs `Approved`); an in-progress decision must carry a `**Status:**` paragraph; and every `` `*.ps1` `` a decision section names exists under `datrix/scripts/test` or `datrix/scripts/dev`. Reported with kind `decision`. The self-test plants each disagreement and each accepted shape.

**Exit codes:** 0 = no unresolved references (or a successful `-Warn` or `-SelfTest` run), 1 = at least one unresolved, non-excepted reference found (or `-SelfTest`/`--harness-self-test` reports a failing check), 2 = usage error, missing exceptions baseline, a doc in `ARCHITECTURE_DOC_FILES` that no longer exists, or the automatic self-test step failing on a normal invocation.

---

### `test\instruction-surface-gate.ps1`

Instruction-surface gate: no agent-facing document may PRESCRIBE a whole-suite run — a whole-suite `test.ps1` form or any `affected-gate.ps1` sweep. `guard-full-suite-runs.py` blocks an agent from EXECUTING a whole-suite run, but a skill or rule doc can still tell an agent, in prose and command examples, to run one; nothing made that PRESCRIPTION visible until this gate. Scans `claude-config/.claude/CLAUDE.md`, `claude-config/.claude/rules/*.md`, and `claude-config/.claude/skills/**/*.md` (including `_shared/`) for every fenced code block and inline code span, walking fence/backtick delimiters directly (a real parser, never a line regex — a fenced block's contents are never re-scanned for inline backticks, and an inline span sharing a prose line is still found). This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

**Shares its classification with the runtime guard, never re-derives it.** Every code fragment found is handed to `_suite_invocation.py` (`claude-config/.claude/hooks/_suite_invocation.py`, loaded by path via `importlib.util.spec_from_file_location` — the same precedent `ignored-source-gate.ps1`'s `load_temp_dir_segment` uses to share `_repo_temp_dir_names.py` with its own hook) — the SAME module `guard-full-suite-runs.py` imports as a sibling, so the hook that BLOCKS a whole-suite run at execution time and the gate that COUNTS its prescription in prose can never disagree about what one looks like. A fragment classified whole-suite (bare package, several packages, `-All`, `-Rerun`, a tier switch with none of `-Specific`/`-Keyword`/`-Tag`, or any `affected-gate.ps1` invocation other than `-SelfTest`) is a hit unless an HTML comment `<!-- forbidden-example -->` sits on the same line, or the line immediately before (for a fenced block: the line before the opening fence).

A `-Tag` run and a `-ListTags` listing are never hits (targeted / runs nothing). A vacuous tail (the fragment is just the bare word `test.ps1` or `affected-gate.ps1`, naming the tool with no argument at all — e.g. "the `test.ps1` script") is never a hit either: a prescription to run a whole suite must name enough to actually run. A tail whose first character is not whitespace, a quote, or end-of-string (e.g. a `file.py:123` line citation immediately after the script name) is never a hit — a real command's next argument is always separated from the script name by whitespace or a closing quote.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\instruction-surface-gate.ps1` | Scan every agent-facing instruction document, fail on any un-exempted whole-suite form |
| **Self-test only** | `.\test\instruction-surface-gate.ps1 -SelfTest` | Run only the scanner's own self-test suite; skip the real census |
| **Debug** | `.\test\instruction-surface-gate.ps1 -Dbg` | Debug logging |

**Parameters:** `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest — real `tempfile.TemporaryDirectory()` fixtures, per the datrix showcase boundary) plants eight fixtures and requires each classification boundary to hold: a bare `test.ps1 {pkg}` form (1 hit), a `-Specific` form (0 hits), a bare form immediately preceded by `<!-- forbidden-example -->` (0 hits, 1 exempted), an `affected-gate.ps1 -Projects {pkg}` form (1 hit — a whole-suite sweep), a `-Tag` run plus an `-All -ListTags` listing (0 hits), an inline code span sharing a prose line (1 hit — proves the scanner is not fenced-block-only), a bare `test.ps1` mention with no argument at all (0 hits — a vacuous tail is not a prescription), and a `file.py:123`-shaped line citation immediately after the script name with no argument-separating whitespace (0 hits). This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 1); `-SelfTest` runs it in isolation and skips the real scan.

**Assertions:** zero un-exempted whole-suite `test.ps1` fragments across the scanned document set.

**Exit codes:** 0 = zero un-exempted whole-suite forms (or a successful `-SelfTest` run), 1 = at least one un-exempted whole-suite form found, or the self-test failed, 2 = usage error, or `_suite_invocation.py`/`_command_shape.py` could not be loaded.

---

### `test\check-observability-native-only.ps1`

Native-only observability providers conformance gate: scans every `datrix/examples/**/config/system.dcfg` (every declared profile, not just the default) for a portable observability provider (`prometheus`/`datadog` metrics, `jaeger`/`zipkin` tracing, `loki` logging, `grafana` visualization, `alertmanager` alerting) paired with a cloud deployment target (`provider = aws` or `azure`) in the same resolved profile -- a pairing the native-only platform-boundary validator rejects. Uses the real `datrix_common.config.unified_loader.load_system_config` + `datrix_common.config.dcfg.parser.parse_dcfg` resolution pipeline (never a hand-rolled regex scan of the DSL, which cannot follow profile inheritance correctly). Verified clean against the current example corpus (2026-07-18): every example's observability block sits on a LOCAL target. This is a repo-level validation **script** (per the datrix showcase boundary -- no pytest suite lives in datrix), following the same self-test-first shape as `check-docs-conformance.ps1`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-observability-native-only.ps1` | Scan every example/profile, fail on any cloud+portable pairing |
| **Warning mode** | `.\test\check-observability-native-only.ps1 -Warn` | Report violations but exit 0 |
| **Scratch examples root** | `.\test\check-observability-native-only.ps1 -ExamplesRoot D:\datrix\.tmp\obs-guard-check\examples` | Scan a hand-crafted examples tree instead of the real one |
| **Self-test only** | `.\test\check-observability-native-only.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite |
| **Show files** | `.\test\check-observability-native-only.ps1 -ShowFiles` | Print each `system.dcfg` being scanned |
| **Debug** | `.\test\check-observability-native-only.ps1 -Dbg` | Print the python invocation |

**Parameters:** `-Warn`, `-ExamplesRoot`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements, per the datrix showcase boundary) covers a deliberately-crafted cloud+portable-metrics violation (must be flagged), a clean LOCAL example with the same portable metrics provider (must NOT be flagged -- proves the guard checks the pairing, not the provider alone), and a clean cloud example using its platform-native metrics provider (must NOT be flagged -- proves the guard doesn't reject every cloud example). This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation and skips the real scan.

**Assertions:**
- Every profile of every `examples/**/config/system.dcfg` is resolved via the real `load_system_config` pipeline and checked -- not just the default profile.
- A configured portable-category provider value paired with a resolved `deployment.provider` of `aws` or `azure` is a violation; `local` is never a violation target.
- A `logging` block with `provider = None` (stdout-only) is never flagged, even on a cloud target.

**Exit codes:** 0 = no violations found (or a successful `-Warn` or `-SelfTest` run), 1 = at least one violation found (or `-SelfTest` reports a failing check), 2 = usage error, missing examples root, or the automatic self-test step failing on a normal invocation.

---

### `test\emitted-escape-integrity-gate.ps1`

Escaped-escape gate for **Python-emitting** templates. Jinja copies template text through verbatim, so a doubled backslash before `n`/`t`/`r` in a `*.py.j2` template reaches the emitted Python source still doubled — an escaped BACKSLASH rather than the escape that was meant — and the generated program builds a string carrying two literal characters where a line break belonged. Nothing downstream notices: the emitted Python compiles, the function writing the artifact returns the right count, and any validator that accepts comments passes. Found in production as a gateway trusted-peer fragment whose whole body landed on one physical line behind a leading `#`, so every directive in it was read as part of that comment and the proxy trusted nobody — through a green smoke gate and a successful deploy. Scope is deliberately templates that emit **Python**: a doubled backslash is ordinary and correct in shell-, TypeScript- and regex-emitting templates. The package set is walked from disk, so a new `datrix-codegen-<lang>` package is covered with no edit. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\emitted-escape-integrity-gate.ps1` | Scan every `*.py.j2` template under every package's `src/` |
| **Show files** | `.\test\emitted-escape-integrity-gate.ps1 -ShowFiles` | Print each template as it is read |
| **Custom base dir** | `.\test\emitted-escape-integrity-gate.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Self-test only** | `.\test\emitted-escape-integrity-gate.ps1 -SelfTest` | Run only the detector's non-vacuity self-test; skip the real scan |

**Parameters:** `-BaseDir` (default: `D:/datrix`), `-ShowFiles`, `-SelfTest`

**Self-test runs automatically, every invocation.** The run length IS the rule — one backslash is the correct escape, two are the defect, four are a deliberate deeper escape — so the self-test covers all three and requires the detector to flag exactly the middle one. A detector that cannot tell them apart would either miss the defect or flag correct code until someone exempted it away. Self-test failure aborts before the real scan (exit 2).

**Assertions:**
- No `*.py.j2` template carries a run of exactly two backslashes before `n`, `t`, or `r`, outside the reviewed exemptions.
- Discovering zero templates is a failure, not a clean result (the scan would pass vacuously).
- Every exemption in `scripts/config/emitted-escape-exemptions.json` still matches a live line; one that matches nothing fails the gate rather than lingering.
- Every baseline entry names a file, the exact matched line, and a reason.

**Exit codes:** 0 = clean, 1 = an escaped escape was found or an exemption matches nothing, 2 = usage error, unreadable/self-inconsistent exemptions baseline, no templates discovered, or a failing self-test.

---

### `test\test-specific-selection-gate.ps1`

**The repo's proof that `test.ps1 <package> -Specific <file>` really runs THAT file.** A `-Specific` run
that prints `[PASSED]` while its own `index.json` / JUnit XML describe a **different** file's tests is a
silent false green — the caller "proves" a fix that never ran. That was a real, observed defect:
`TeeLogger` named its run directory `test-results-<YYYYMMDD-HHMMSS>` (second granularity) and created it
with `mkdir(exist_ok=True)`, so two `test.ps1` invocations against one package that started in the same
second **shared one run directory** and overwrote each other's `junit-*.xml` and `index.json` — each still
printing its own correct exit code. Repo-level validation **script**, not a pytest suite (per the datrix
showcase boundary).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\test-specific-selection-gate.ps1` | Default package/file pair (~2 min) |
| **Different package** | `.\test\test-specific-selection-gate.ps1 -Package datrix-common -FileA "tests/unit/datrix_model/test_seal.py" -FileB "tests/unit/datrix_model/test_traits.py"` | Exercise another package |
| **Debug** | `.\test\test-specific-selection-gate.ps1 -Dbg` | Print the python invocation |

**Parameters:** `-Package` (default: `datrix-codegen-python`), `-FileA` / `-FileB` (package-relative test
files; must be two *different* files — the default pair is the one from the original report), `-Dbg`

**Assertions (4 steps):**
- **Non-vacuity (runs first).** The comparator is fed a deliberately **wrong-file** run directory — a
  synthetic JUnit XML naming another file's tests — and must reject it; it is also fed a correct run and a
  zero-testcase run, which it must accept and reject respectively. A comparator that cannot detect the
  forced mismatch fails the gate before any real result is trusted.
- **Positive.** A real `-Specific <FileA>` run's own artifacts (the run directory the runner *printed* —
  never the newest directory on disk) name tests from `FileA` and nothing else.
- **Run-directory exclusivity (deterministic).** `LogConfig.timestamp_format` is pinned to a literal so
  every racer computes the **same** preferred directory name — a guaranteed collision, not a hoped-for one.
  8 sequential racers prove the name is never reused; 8 concurrent racers prove the claim is atomic. This
  is the root-cause invariant and it fails 8/8 against the old `mkdir(exist_ok=True)`.
- **Concurrency (end-to-end).** Two concurrent `-Specific` runs against the same package but different
  files must land in distinct run directories, each naming only its own file.

**The gate judges SELECTION, not test health:** a `-Specific` run of a file whose tests fail still passes
the gate, as long as the file that ran is the file that was asked for.

---

### `test\run-log-exclusivity-gate.ps1`

**The repo's proof that two concurrent runs never share one log file.** Same defect class as the gate
above, one surface over: `generate.ps1` named its log `generate-results-<YYYYMMDD-HHMMSS>-<language>.log`
and wrote the header with a truncating write, so two runs started together **for two different config
profiles** computed one name — the second truncated the first's log and both appended into it, each
pointing its caller at a log describing the other run's generation. Adding the profile as a third segment
would only move the collision to two runs of one profile, exactly as adding the language segment left the
profile case open, so uniqueness comes from *claiming* the name (`common/DatrixRunLog.psm1`,
`FileMode.CreateNew`). Pure PowerShell, no venv, ~2 s.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\run-log-exclusivity-gate.ps1` | 8 racers (default) |
| **More racers** | `.\test\run-log-exclusivity-gate.ps1 -Racers 32` | Widen the forced collision (2–64) |

**Parameters:** `-Racers` (default: `8`, range 2–64)

**Assertions (5 steps):**
- **Non-vacuity (runs first).** The distinct-count comparator is fed names composed the way the defect
  composed them (one pinned timestamp, one label set) and must see **1** name; fed genuinely different
  label sets it must see all of them. A comparator that cannot see the forced collision fails the gate
  before any real result is trusted.
- **Sequential exclusivity.** N claims on a **pinned** base name yield N distinct files that all exist —
  a name is never reused.
- **Concurrent exclusivity.** The same N claims made simultaneously yield N distinct files — the claim is
  atomic. This is the step that fails against any name-only scheme.
- **Label containment.** A label carrying `..`, a separator, a drive letter, or a wildcard cannot steer the
  log out of its results directory.
- **Wiring.** `generate.ps1`'s own **syntax tree** must call `New-DatrixRunLogFile` and must contain no
  inline interpolated `generate-results-…` name. Without this the gate would prove a library nobody calls.

**Exit codes:** 0 = `-Specific` selects only the requested file and the check is non-vacuous, 1 = wrong-file
selection, shared run directory, or a vacuous comparator, 2 = usage error (`test.ps1` or the named test
files not found).

---

### `test\supported-domain-parity-gate.ps1`

Two checks, in order, both against a live-computed universe never a fixed count quoted here (the universe grows as domains are added — run the gate for its live output):

1. **Domain-universe closure.** Before checking stances, computes the union of every registered language's COMPILED GenDSL IR domain ids (`get_definitions(<lang>)`, read directly — independent of any supported/unsupported stance a plugin later commits) and asserts it equals `datrix_codegen_common.parity.domain_registry.SHARED_CONTEXT_TYPES.keys()` exactly. A domain id some language's compiled IR declares but the registry omits fails naming the declaring language(s); a registry id no registered language's compiled IR declares fails as a dead entry (dead surfaces are deleted, never deprecated in place). Zero tolerance, no exemption file — this check short-circuits the gate (exit 1) before the stance-completeness check runs, since a wrong universe makes that check meaningless.
2. **Per-language stance completeness.** EVERY registered `datrix.languages` plugin must declare a stance — `supported` or `unsupported(reason)` — for every id in the closed universe, and no stance for an id outside it. Derives its target LANGUAGE set from `importlib.metadata.entry_points(group="datrix.languages")` at runtime — never a hardcoded language literal — so a future `datrix-codegen-<lang>` package is covered automatically with no edit to this gate. This is a completeness check, never an agreement check: a per-language `supported`/`unsupported(reason)` split is the designed state — most `unsupported` stances are permanent "realized elsewhere on this target" facts (e.g. a domain folded into another domain, or architecturally inapplicable to that target's runtime), not capability gaps awaiting work. A language with no stance for a universe id, or a stance for an id outside the universe, is a fail-loud `STANCE COMPLETENESS VIOLATION`.

On success, the gate prints every registered language's full stance table (one row per universe id) plus a divergence report for every id whose stance is not unanimous across languages — including unanimous `unsupported` — quoting each unsupported language's declared reason verbatim. Divergence-with-a-reason is the designed per-target-realization state; the report is diagnostic and never itself a failure condition.

**The MariaDB engine boundary needs no special-case code** — it is an engine choice inside the `rdbms`/migration domains, not a withheld domain, so it never shows up as a domain-id-level diff at all (this script compares at `domain_id` grain, coarser than per-engine).

**Built-in non-vacuity self-test, every invocation.** Before any real comparison is trusted, the script runs two self-tests: one feeds the domain-universe closure comparator a synthetic matching registry/compiled-IR pair (must report zero divergence), a synthetic compiled id absent from the registry (must be reported, naming the declaring language), and a synthetic registry id no synthetic language declares (must be reported as a dead entry); the other feeds the stance-completeness comparator a complete synthetic stance table (must report zero findings), a synthetic language missing one universe id's stance (must be reported, naming that language and id), and a synthetic language declaring a stance for an out-of-universe id (must be reported, naming that language and id). Either self-test failing aborts the gate (exit 2) before any real comparison runs. Fails loud (exit 2) if fewer than 2 languages are registered — a cross-language comparison over 0 or 1 language is vacuous.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\supported-domain-parity-gate.ps1` | Check domain-universe closure and every registered language's stance completeness |
| **Debug** | `.\test\supported-domain-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\supported-domain-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = the domain-universe closure holds and every registered language's stance table is complete over the full universe, 1 = a domain-universe closure violation was found (checked first) or a stance-completeness violation was found for at least one language, 2 = a non-vacuity self-test failed or fewer than 2 languages are registered.

---

### `test\behaviour-parity-gate.ps1`

**Replaces the retired name-keyed drift report on the language axis.** AST-walks every
registered target package's `src/` tree and groups functions into **roles** — a *signature
role* (shared-typed parameter/return annotations from `datrix_common`/`datrix_codegen_common`)
or, for functions with no shared-typed parameter, a *normalized-name role* (bare name with each
language's own declared `name_tokens` stripped) — so a language token inside a name can never
hide a parallel implementation. Each role's members are compared by **behaviour skeleton**
(`if`/`for`/`while`/comprehension/`return`/`raise` structure, `try`/`except`/`with` structure,
and parameter arity, model-rooted predicates and calls preserved, every other literal collapsed)
rather than by verbatim text, and classified `identical`, `same-behaviour` (skeletons and arity
equal, bodies differ), or `divergent`. A per-target difference in behaviour is a defect with N
copies, never a choice; only rendering differs per target. **Arity is role-level:** a parameter
name ANY member of a role drops as language-private plumbing is dropped for every member sharing
that name, so a language whose own file-scope subclass happens to live inside the shared layer
does not count a parameter its sibling languages drop.

**Two hard-zero buckets, one shape-exempt, one declared-hole:**
- `identical` / `same-behaviour` fail unless every member is a **pre-binding adapter** (a single
  `return` of a call into `datrix_codegen_common`, recognized by AST shape only — no written
  exemption list).
- `divergent` is judged **without a reference language**: the role's member packages are
  partitioned into **skeleton groups** (packages whose contributed skeleton sets are equal share
  a group); every package that declares the construct unsupported on one of three surfaces — its
  `DomainDeclaration.status == "unsupported"` for the role's resolved domain, the domain in its
  `on_demand_domains`, or (for `@emit_adapter`-marked members) every emit-table row's builtin
  group having an `unsupported` `builtin_group_stances` entry — is set aside; the role passes
  iff at most one group remains, and otherwise fails with one reason naming every remaining
  group (e.g. `members split into 2 skeleton groups: {java, python} vs {dotnet}; no member
  declares the construct unsupported`) — the gate cannot know which group is right, so it names
  all of them. A role every member of which declares the construct unsupported passes and is
  still reported. An `undomained` role admits only the builtin-group surface. A role the gate
  cannot classify (unparseable member, unresolvable annotation) is reported as a **failure naming
  the member** — never skipped.
- The `identical`/`same-behaviour` shape exemption also covers a **rendering leaf**: a body with
  no branch/loop/`try`/`with`/comprehension/`raise`, no attribute chain rooted at `self`, a
  shared-typed or unannotated parameter, or a derived root sourced from one of those (a chain
  rooted at a language-private parameter, or at a derived root sourced only from such reads, is
  exempt — it is never a model root by the same rule the arity count already applies), and every
  call resolving to the shared codegen layer or the standard library — reported
  `rendering-leaf-exempt` beside `adapter-exempt`.

**Scope is migration-only.** While `datrix/scripts/config/behaviour-parity-scope.json` exists,
only the domains it lists (plus the literal `undomained` if listed) can fail the gate; every
other role is reported but never fails. `-Scope` overrides the file for one run. When the file
is absent, every domain is in scope (hard zero). The file only grows, never shrinks, and is
deleted once every domain is in scope.
The same file's `buckets` list independently gates every role of a named verdict across every
domain regardless of `domains`; it too only grows and accepts only the three verdict names.
A role fails when EITHER half admits it — a scoped bucket is never narrowed by an empty or
unrelated `domains` list, and vice versa. `-Buckets` overrides the file's `buckets` list for
one run the same way `-Scope` overrides `domains`.

**Non-vacuity is enforced on every run.** A synthetic five-bucket tree (one identical role, one
same-behaviour role, one divergent role, one role split only by a language token, one role
unified only by shared-typed signature) must land in exactly its bucket, a single-target tree
must be refused, a two-group divergent role must fail naming both groups and pass once the odd
group's package declares the construct unsupported, and the bucket labels printed must be
exactly `identical` / `same-behaviour` / `divergent`.

**The platform axis (`-Axis platforms`) is report-only and never fails** — the platform packages
realize different infrastructure by design.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\behaviour-parity-gate.ps1` | Language axis, default (empty or file) scope |
| **Scoped** | `.\test\behaviour-parity-gate.ps1 -Scope queue,cache` | Fail only roles in these domains |
| **Bucket-gated** | `.\test\behaviour-parity-gate.ps1 -Buckets identical` | Fail every role in these verdict buckets (identical, same-behaviour, divergent) across every domain, regardless of -Scope |
| **Platform axis** | `.\test\behaviour-parity-gate.ps1 -Axis platforms` | Report only, always exits 0 |
| **Debug** | `.\test\behaviour-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\behaviour-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test |

**Parameters:** `-Axis <languages|platforms>` (default: languages), `-Scope <id,...>`, `-Buckets <id,...>`, `-Dbg`, `-SelfTest`

**Exit codes:** 0 = no failing role in scope (or a successful `-SelfTest`, or `-Axis platforms`),
1 = ≥1 failing role in scope, 2 = usage/discovery/parse error or the self-test failed.

---

### `test\dependency-declaration-ratchet-gate.ps1`

Dependency-declaration-only-path ratchet (W4 / declarations-are-the-only-emission-path enforcement): a per-language CENSUS of every dependency-**SET** decision site in a registered language package that decides dependency package NAMES outside that package's own `generation/dependency_tables.py` table -- the completeness proof for the declared-table migration: a language's migration is done when this scan reports ZERO out-of-table sites for that package, never when a hand-written list is exhausted. Target derivation is pure runtime discovery via the installed `datrix.languages` entry points -- never a hardcoded language list -- so a fifth `datrix-codegen-<lang>` package is covered automatically with no edit here. A registered language with no `defaults.yaml` at all declares an empty dependency-catalog universe, which is a legitimate zero-site result, not an error.

**The counted unit is a decision SITE, not a bare catalog-name-shaped literal anywhere in the tree.** An earlier version of this scanner flagged any string literal equal to a registered catalog package name, anywhere under `src/` and `templates/`; that over-matched by roughly two orders of magnitude (a cache-ENGINE identifier constant, an import-deduplication helper's module-name constants, and a code template's own `import <pkg>` statement all happen to share a spelling with a real package name without ever deciding a manifest's dependency set) and could never structurally reach zero for a migrated language. Two structural detection passes, neither a text regex over raw source:
- **Python source.** AST-walks every `.py` file under the language's `src/` tree for string-literal `ast.Constant` nodes whose value is a member of that language's registered `DependencyCatalog` package universe (read from the language's own `defaults.yaml`) -- but ONLY when the literal sits inside (a) a `get_dependencies`/`get_npm_dependencies`/`get_nuget_dependencies`/`_collect_*_deps`-shaped function at any nesting depth, or (b) a module-TOP-LEVEL (never class- or function-nested) assignment shaped the same way (e.g. `ENGINE_PACKAGE_NAMES`, `EMAIL_COORDINATES`). Both shapes are recognized by a documented whole-snake_case-token naming vocabulary (`_DEPENDENCY_DECISION_NAME_TOKENS` in the runner module: `dependency`/`dependencies`/`deps`/`package`/`packages`/`coordinate`/`coordinates`), matched as whole tokens, never a substring search or a hardcoded function-name allowlist.
- **Jinja templates.** Parses every `.j2` file under the language's `templates/` tree into its Jinja AST and walks `nodes.Const` literal nodes inside `{{ }}`/`{% %}` expressions (e.g. a `v['pkg']` version-lookup in a manifest template) for the same catalog-membership match -- the structural analogue of the Python pass's `ast.Constant`. Raw `TemplateData` (a template's literal rendered-output text between tags) is deliberately NOT scanned by containment: it degrades to a text search over a template's entire output, including plain generated code and even doc comments, which is not a dependency-set decision.

This is a naming-shape heuristic, not an exhaustive semantic analysis: under-reporting a genuine decision site named entirely outside the token vocabulary is a known, accepted, documented limitation (extend the vocabulary in the runner module if one is found), preferred over a hardcoded per-function allowlist that would drift silently out of sync with the code it polices.

**This is a REPORT with a decrease-only out-of-table-count baseline, not a check that identifies WHICH package a site decides to require** -- only WHETHER a site decides one at all, outside the one place it is allowed to. A single conceptual site (e.g. the same literal appearing as both a dict key and a sibling function argument on one line) collapses to one `(file, line, literal)` entry, never double-counted.

**A small, reviewed, coordinate-pinned exemption list** (`_KNOWN_NON_JINJA_TEMPLATES` in the runner module) skips the Jinja parse attempt for `.j2`-suffixed files that are not actually Jinja source -- at authoring time this is exactly one file, a dormant static-Python legacy template kept intentionally unrendered by an unrelated, already-settled hardening decision. Every OTHER `.j2` file that fails to parse still fails the scan loud (a genuine template syntax error is a scan error, never a silently skipped file); a template that parses but references an undefined Jinja global is unaffected (`Environment().parse()` only needs syntactic validity, not a rendering context).

**Built-in non-vacuity self-test, every invocation.** Before any real scan is trusted, the script builds a synthetic two-language package tree under a temp directory and proves: it finds exactly the two planted out-of-table sites; a non-qualifying decoy referencing the same planted literal (mirroring the real `resolve_*_engine`/`SUPPORTED_*_ENGINES` false-positive shape) adds no second site -- the narrowing itself; moving one planted literal into a synthetic `generation/dependency_tables.py` drops the combined count by exactly one; a synthetic Jinja template's planted literal is detected by the template pass independently of the Python-source pass; the LIVE scan (real tree, not synthetic) finds a described, currently-real out-of-table instance AND no longer reports three described, currently-real sites the earlier, over-broad matcher wrongly counted; and the minimum-language guard refuses a single-language set with exit code 2, never a silent pass. Fails loud (exit 2) if fewer than two languages are registered -- a per-language census over fewer than two languages is vacuous.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the report** | `.\test\dependency-declaration-ratchet-gate.ps1` | Full scan over every registered language, checked against the ratchet baseline |
| **Debug** | `.\test\dependency-declaration-ratchet-gate.ps1 -Dbg` | Debug logging (also lists every out-of-table site found) |
| **Self-test only** | `.\test\dependency-declaration-ratchet-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Freeze/tighten baseline** | `.\test\dependency-declaration-ratchet-gate.ps1 -UpdateBaseline` | Write the live out-of-table count as the new baseline |

**Parameters:** `-Dbg`, `-SelfTest`, `-UpdateBaseline`

**Baseline:** `scripts/config/dependency-declaration-ratchet-baseline.json` -- a decrease-only ratchet on the out-of-table site count, summed across every registered language (a live count HIGHER than the recorded value fails; a decrease never fails). `-UpdateBaseline` is the only writer; do not hand-guess the number.

**Exit codes:** 0 = the report ran and the out-of-table count is at or below the baseline (or a successful `-SelfTest`/`-UpdateBaseline`), 1 = the out-of-table count exceeds the baseline, 2 = the non-vacuity self-test failed, fewer than 2 languages are registered, or a discovery/parse error occurred.

---

### `test\shared-builder-reachability-gate.ps1`

Shared-builder reachability gate: every module-level `build_*` function declared in `datrix_codegen_common`'s `algorithms/` and `context_models/` modules must have at least one production caller outside its own defining module, across the defining package itself, every registered language package, and `datrix-cli`. A shared context builder that is written, exported and unit-tested but never called looks complete by every signal except the one that matters — it never executes on a real generation run — and that shape recurs as machinery gets hoisted into the shared layer for several languages to share, because every other gate asks whether the code is CORRECT, never whether it RUNS. Whole-tree AST import/call-graph resolution, never text matching: it follows aliased imports (`import X as Y`, `from X import Y as Z`), attribute calls (`module.build_x(...)`), and package `__init__` re-exports (bounded chase, so a cyclic re-export cannot loop). It also counts a **thin delegation** as live — a wrapper whose entire body is one context construction delegating to a callee some module OUTSIDE the defining package binds, and whose constructed type another production module builds — which is what keeps the registered test-axis domains' `build_<kind>_test_context` wrappers from reading as dead when the production path builds the identical value generically inside `TestGeneratorOrchestrator`. A builder that branches, walks the model, logs, or returns `None` has more than one statement and is never a thin delegation, whatever types it touches. **Hard zero: no exemption file, no pinned baseline** — a baseline on a gate whose entire job is "notice code nobody wired in" would exempt exactly the defect class it exists to catch. Language package set from the installed `datrix.languages` entry points at runtime, never a literal list; the gate refuses to run against fewer than two languages rather than passing vacuously. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix, and a unit test importing several generator packages is the cross-package coupling `check-import-boundaries.ps1` forbids).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\shared-builder-reachability-gate.ps1` | Census the real installed package tree |
| **Debug** | `.\test\shared-builder-reachability-gate.ps1 -Dbg` | Debug logging (names each self-test check as it passes) |
| **Self-test only** | `.\test\shared-builder-reachability-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |
| **Census** | `.\test\shared-builder-reachability-gate.ps1 -Census` | Print every builder with its calling packages, every live thin delegation with the delegate and context type it resolved through, and every dead builder; exit 0 |

**Parameters:** `-Dbg`, `-SelfTest`, `-Census`

**Assertions:**
- Zero `build_*` definitions under the scanned subpackages have neither a resolved external caller nor a live thin delegation.
- **Correctness floors (over-reporting is as much a failure as under-reporting):** five named genuinely-wired builders are never flagged dead; `build_api_context`'s resolved callers span several language packages (cross-package resolution); `extract_max_length` resolves through its aliased same-named private wrappers (alias resolution); and every registered test-axis wrapper is live through its OWN `plan_<kind>_tests` delegate and constructs `TestPlanContext` — a rule folding every wrapper onto one delegate would pass a bare "something was rescued" check while proving nothing. A floor whose expected caller package is not installed is a loud configuration error (exit 2), never a silent skip.
- Non-vacuity self-test (every invocation, before any real census): a planted orphan `build_*` is flagged by name and clears once a real cross-module caller is wired; a caller reached ONLY through an aliased private wrapper is still resolved (the shape no text search can see); a thin wrapper over a production-bound plan is recognized as live with its delegate and context type recorded; a **multi-statement** builder touching the same production-bound plan and constructing the same production-built context type is STILL dead (the half that matters most — a delegation rule that rescued it would have quietly disabled the whole gate); and a thin wrapper whose delegate nothing outside the defining package binds is still dead.

**Exit codes:** 0 = every shared builder is reachable and every floor holds (or a successful `-SelfTest` / `-Census`), 1 = a dead builder or a violated correctness floor, 2 = the self-test failed, a scanned package could not be located, or fewer than two languages are registered.

---

### `test\migration-upgrade-op-family-gate.ps1`

Migration upgrade-op family gate: the cross-package half of the upgrade-op duplication census. Six `_build_upgrade_op_for_*` symbols exist once per migration target (python's Alembic migration generator, dotnet's FluentMigrator ops); the census read both bodies of each and concluded they are genuinely divergent, so **both private copies must survive** — a later "cleanup" deleting one would be deleting a target's real behaviour. `_build_upgrade_op_for_field_added` additionally carried a behaviour gap that is now CLOSED (dotnet emitted no backfill default, so a non-nullable `FIELD_ADDED` the shared change policy classifies *safe* rendered a migration that failed at apply time on any populated table); the gate holds the default-bearing `FluentMigratorColumn` field that closes it. One genuinely shared fact WAS hoisted: both targets reassembled the `INDEX_ADDED` JSON detail into its `SnapshotIndex` with byte-identical semantics and error text, so that parse now lives once in `datrix_codegen_common.algorithms.migration_upgrade_op_index`, each target calls it the exact number of times its own paths need, and neither may redefine it. Structural resolution only, never a text match. The two languages are named (a fact about which targets carry this family, not a claim about which targets exist) but their packages resolve through the installed `datrix.languages` entry points, so a named language that is not installed fails loud instead of letting its half pass vacuously. Repo-level validation **script** — a unit test importing two generator packages to compare their bodies is the shape the repo boundary forbids outright; the shared parser's own input/output behaviour stays as a unit test in `datrix-codegen-common`, which owns the function.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\migration-upgrade-op-family-gate.ps1` | Run every cross-package check in this family |
| **Debug** | `.\test\migration-upgrade-op-family-gate.ps1 -Dbg` | Debug logging (names each self-test check as it passes) |
| **Self-test only** | `.\test\migration-upgrade-op-family-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Each of the six divergent symbols is still defined exactly once per target.
- `FluentMigratorColumn` declares a default-bearing annotated field.
- Each target has exactly the pinned number of resolved call sites for `parse_index_added_detail` (a count, not a `>= 1`: a path silently losing its call is the regression this pins), and neither target defines `parse_index_added_detail` or the retired `_index_from_index_added_detail`.
- Non-vacuity self-test (every invocation): the resolver finds a planted direct call, follows a `from … import … as …` alias, and finds a module-qualified `alias.symbol(...)` call; and it does NOT count a same-suffix private wrapper (`_parse_index_added_detail`) or a bare docstring/string mention — both false-positive shapes this chain has been bitten by. The definition scan is proven in both directions too: it finds a planted definition and invents none.

**Exit codes:** 0 = every check holds (or a successful `-SelfTest`), 1 = at least one violation, 2 = the self-test failed, a named language is not registered/installable, or the classification file is missing/malformed.

---

### `test\observability-axis-parity-gate.ps1`

Cross-target observability-AXIS parity gate: proves every registered language agrees with the platform axis about which observability categories a language may realize. Exists because two generation-breaking defects shipped with every per-package conformance suite green — a language declaring it realized providers in a category only the PLATFORM provisions (so the same config generated on one language and failed generation on another), and the language-axis validator policing a platform-only category (so a provider the resolved platform natively realizes and actually provisions was rejected for every project on that language). Both are **cross-target** consistency defects, which per-package conformance cannot detect by construction: each package validates its own declaration in isolation, so all of them stay internally green while disagreeing about the same portable field. Target sets come from the installed `datrix.languages` / `datrix.platforms` entry points at runtime — never a hardcoded language or provider literal — so a new package is covered with no edit here. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\observability-axis-parity-gate.ps1` | Both legs, every registered language × platform |
| **Debug** | `.\test\observability-axis-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\observability-axis-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- **Leg 1 (declaration identity).** Every registered language declares exactly the empty set for every category in `PLATFORM_ONLY_OBSERVABILITY_CATEGORIES` — a non-empty claim is how the same config generates on one language and fails generation on another.
- **Leg 2 (validator agreement).** For each in-scope category, **every** provider at least one registered platform declares native must validate cleanly against **every** registered language. All providers are checked, not a representative: the original defect was one specific provider being rejected, which a single-representative check misses whenever another sorts first.

**Leg 2's scope is derived from the declarations, never from `PLATFORM_ONLY_OBSERVABILITY_CATEGORIES`** — it is the set of categories some platform realizes and **no** language realizes. Scoping it by that constant would make the gate blind to the exact defect the constant can have: dropping a category from it would silently drop the category from the check too, so reintroducing the original rejection defect passes unnoticed. This was not theoretical — the first revision of this gate did scope leg 2 by the constant, and a mutation test proved it passed green with the real defect planted.

**Non-vacuity self-test runs as step 1 of every invocation** (self-test failure aborts before any real comparison, exit 2). Leg 1's comparator must detect a synthetic language claiming a platform-only provider and must not fire on a clean one. Leg 2's check must still observe the validator **reject** an unrealized provider in a language-realizable category — otherwise a neutered validator would make leg 2's clean result vacuous.

**Exit codes:** 0 = both legs hold, 1 = an axis violation was found, 2 = the non-vacuity self-test failed, or too few registered targets (no language, no platform, or no category in leg 2's derived scope) for a non-vacuous comparison.

---

### `test\manifest-import-parity-gate.ps1`

Manifest / import parity gate: for every `datrix-*` package at the workspace root carrying a `pyproject.toml`, the `datrix-*` distributions its `[project] dependencies` declare must equal the `datrix_*` import roots its `src/` tree actually imports (mapped by the `_` → `-` spelling every package uses). `imported − declared` is an undeclared dependency; `declared − imported` is a dead declaration; a runtime requirement carrying a test-only extra (`[testkit]`, `[dev]`, `[testing]`) drags a test surface into production. All three are violations, and the gate is a **hard zero** with no baseline — there is no legitimate steady state in which a manifest disagrees with the import set. Exists because the shared editable venv makes every package importable from every other, so a manifest can lie in either direction with every suite green (a package documented as fenced out of `datrix-codegen-common` imported it from twelve production modules; a platform package ran on an undeclared dependency; three language packages carried a dead dependency; one pulled `[testkit]` into production). `TYPE_CHECKING`-only imports count: a type-checking install needs the package too. The package set is discovered from disk, never a hardcoded list. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\manifest-import-parity-gate.ps1` | Compare every `datrix-*` package's manifest against its `src/` imports |
| **Debug** | `.\test\manifest-import-parity-gate.ps1 -Dbg` | Debug logging (prints each package's declared and imported sets) |
| **Self-test only** | `.\test\manifest-import-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- For every discovered package, `imported − declared = ∅` and `declared − imported = ∅` over Datrix distributions, and no `[project] dependencies` entry naming a Datrix distribution carries a test-only extra. An import satisfied only by one of the package's **own** non-dev extras (for example `datrix-codegen-common`'s `testkit/` subtree importing `datrix-language`, declared by its `[testkit]` extra) is a declared optional dependency: logged, never a violation. A `dev`/`testing` extra never satisfies a `src/` import.
- Non-vacuity self-test (every invocation): a synthetic dirty package yields exactly its five planted violations (one plain undeclared import, one `TYPE_CHECKING`-only undeclared import, one import declared only by a `dev` extra, one dead declaration, one test-only extra) while its import declared by a non-dev extra is not reported; a synthetic clean package yields none; a workspace with fewer than two packages is refused; and the **live** scan sees every package registering `datrix.languages` import `datrix-codegen-common` — a real edge, so the scanner is proven against the tree it guards, not only against fixtures.

**Exit codes:** 0 = every manifest agrees with its imports (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two packages were discovered, or a manifest/module could not be parsed.

---

### `test\third-party-dependency-parity-gate.ps1`

Third-party dependency parity gate: for every `datrix-*` package with a `src/` tree, the **third-party** distributions its `[project] dependencies` declare must equal the third-party distributions its `src/` tree imports (`ast`, nested imports included, mapped to distributions through the installed metadata via `importlib.metadata.packages_distributions`). `imported − declared` is an undeclared dependency that works here only because something else installed it into the shared venv; `declared − imported` is a dead declaration. Extras other than `dev` are optional runtime surfaces (a shipped `testing` helper subpackage, an `lsp` server) that may satisfy a `src/` import; the `dev` extra never does. A root several distributions provide (`ruamel`) is satisfied by any declared candidate; a root no installed distribution provides is itself a violation. A distribution the package **invokes as a subprocess** rather than imports is a reviewed executable exemption in `datrix/scripts/config/third-party-dependency-exemptions.json` (package + distribution + reason; a stale entry fails the gate) — a distribution merely used by the projects the package generates is never exempted. The sibling `manifest-import-parity-gate.ps1` holds the same invariant for the Datrix distributions. Exists because four packages imported a password hasher no framework manifest declared (present only because generated customer projects installed into the venv required it), five packages declared a template engine only a sixth (undeclared) imported, and one generator declared the web framework and ORM of the projects it generates. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\third-party-dependency-parity-gate.ps1` | Compare every `datrix-*` manifest's third-party dependencies against its `src/` imports |
| **Self-test only** | `.\test\third-party-dependency-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |
| **Show files** | `.\test\third-party-dependency-parity-gate.ps1 -ShowFiles` | Print each package's declared set as it is scanned |
| **Debug** | `.\test\third-party-dependency-parity-gate.ps1 -Dbg` | Print the python invocation |

**Parameters:** `-BaseDir <path>`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Assertions:**
- For every discovered package, `imported − declared = ∅` and `declared − imported = ∅` over third-party distributions, where `declared` is `[project] dependencies` plus every non-`dev` extra and a dead declaration is excused only by a reviewed executable exemption.
- Non-vacuity self-test (every invocation): a planted dirty package yields exactly its four violations (an undeclared import, a `dev`-extra-only import, an import no distribution provides, a dead declaration) while its non-`dev`-extra import, its ambiguous root satisfied by one declared candidate, and its exempted executable are accepted and its stale exemption is left unused; a planted clean package yields none; a workspace with fewer than two packages is refused; and the **live** scan sees at least one real package both declare and import the same distribution.

**Exit codes:** 0 = every manifest agrees with its imports (or a successful `-SelfTest`), 1 = a violation or a stale exemption was found, 2 = the self-test failed, fewer than two packages were discovered, or a manifest/exemption file could not be parsed.

---

### `test\app-probe-path-literal-gate.ps1`

Application probe-path literal gate: no platform package may hardcode a route a registered language declares as its readiness or liveness probe. The route a traffic-routing probe consults (Compose `healthcheck`, ECS / App Runner health check, ALB / NLB target-group health check, Front Door origin probe, App Service health monitor) is a route the LANGUAGE's generated application mounts, declared on `LanguageRuntimeSpec.readiness_probe_path()` / `app_service_liveness_probe_path()`; every platform reads it from the resolved plugin. Platform packages are discovered from disk (every `datrix-*/pyproject.toml` registering `datrix.platforms`); the declared routes come from the installed `datrix.languages` plugins; each platform `src/` tree is scanned for Python string constants (`ast`, docstrings excluded) and quoted `.j2` literals (comment lines excluded) equal to a declared route. Exists because a shared `"/ready"` constant was once consumed identically by every platform while one registered language never mounted `/ready`, so its containers were probed at a 404 on three platforms and never became healthy. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\app-probe-path-literal-gate.ps1` | Scan every platform package, fail on any unexempted probe-route literal |
| **Self-test only** | `.\test\app-probe-path-literal-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Show files** | `.\test\app-probe-path-literal-gate.ps1 -ShowFiles` | Print each file as it is scanned |
| **Debug** | `.\test\app-probe-path-literal-gate.ps1 -Dbg` | Print the python invocation |

**Parameters:** `-BaseDir <path>`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Assertions:**
- Every literal hit is either absent or covered by a reviewed entry in `datrix/scripts/config/app-probe-path-exemptions.json` (file + exact snippet + written reason). An exemption is legitimate only for a literal that is NOT an application probe target (an infrastructure container's own probe, a gateway framework-path list); an application probe is never exempted. A stale entry whose snippet no longer matches a hit fails the gate.
- Non-vacuity self-test (every invocation): a planted platform package yields exactly its code-line hits (a docstring and a template comment carrying the same route are NOT reported), a clean planted package yields none, a workspace with fewer than two platform packages or fewer than two registered languages is refused, and the **live** scan of the language packages' own `src/` trees finds every declared route — so the matcher is proven against the real literals the languages mount, not only against fixtures.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = an unexempted hit or a stale exemption was found, 2 = the self-test failed, too few packages/languages were discovered, or a manifest/exemption file could not be parsed.

---

### `test\zero-environment-runtime-gate.ps1`

Zero-environment runtime census gate: every registered language is held to the `zero_environment_runtime` posture it declares on its `LanguageCapabilityDeclaration`. The zero-environment architecture (every deployment-static value baked as a literal constant at generation time; the running service consults no environment variable) is a portable decision whose realization is per language, so each language plugin declares whether it realizes the contract, the regular expressions that spell an environment read in its own templates, and — when unrealized — a written reason. The gate censuses every `.j2` template under each registered language package's `src/` tree against that language's own idioms. A language declaring the contract **realized** may carry environment reads only as reviewed exemptions with a written reason in `scripts/config/zero-environment-runtime-baseline.json` (an unlisted read and a stale entry are both violations); a language declaring it **unrealized** carries a decrease-only `pinned_count` that may never rise; a registered language that declares nothing fails, named. Language set from the installed `datrix.languages` entry points; idioms from each language's declaration — never a table in the script. Test-harness templates count too (a harness that reads the environment is still emitted into the generated project); a realized language lists them as exemptions with that reason. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\zero-environment-runtime-gate.ps1` | Census every registered language against its declared posture and the baseline |
| **Debug** | `.\test\zero-environment-runtime-gate.ps1 -Dbg` | Debug logging (lists every environment-reading template) |
| **Self-test only** | `.\test\zero-environment-runtime-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |
| **Re-pin counts** | `.\test\zero-environment-runtime-gate.ps1 -UpdateBaseline` | Re-pin every unrealized language's count to its live census (the only writer of `pinned_count`; exemption lists are hand-authored and untouched) |

**Parameters:** `-Dbg`, `-SelfTest`, `-UpdateBaseline`

**Assertions:**
- Realized language: `reads − exemptions = ∅` and `exemptions − reads = ∅`; every exemption carries a non-empty reason.
- Unrealized language: `len(reads) ≤ pinned_count`; a count below the pin is reported with the re-pin hint, never silently accepted as the new floor.
- Undeclared language (`zero_environment_runtime is None`): a violation naming the language.
- Non-vacuity self-test (every invocation): a synthetic template tree yields exactly the planted read (the clean template and a non-`.j2` file are not counted); the comparator reports exactly one problem for a missing exemption, a stale exemption, a count above the pin, and a missing pin, and none for an exact match or a count at/below the pin; a reasonless exemption is rejected; an unrealized declaration without a reason and a declaration with no idiom are rejected at construction; the **live** census finds a known real read (`python: templates/api/identity.py.j2`); a single-language set is refused.

**Exit codes:** 0 = every language matches its declaration and baseline (or a successful `-SelfTest` / `-UpdateBaseline`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the baseline is malformed.

---

### `test\framework-header-parity-gate.ps1`

Framework header parity gate: every registered language spells the framework-minted HTTP headers from datrix-common's one registry (`datrix_common.generation.http_headers` — the trusted-caller token, the delegated-user envelope, the three rate-limit response headers, the inbound webhook secret, the outbound webhook delivery headers) and realizes every header family or declares the hole with a reason on its `LanguageCapabilityDeclaration.unrealized_framework_headers`. The gate censuses every `.py` and `.j2` source under each registered language package's `src/` tree for `X-`-prefixed header tokens and registry-constant references. **Spelling:** a header under a framework prefix (`X-Datrix-`, `X-RateLimit-`, `X-Webhook-`) is an exact registered name (case-insensitively — Node lowercases header names) or a reviewed, counted entry in `scripts/config/framework-header-exemptions.json`; a retired name (`X-Internal-Token`) is a violation with no exemption path. **Realization:** a family is realized when the exact name is spelled or its registry constant is referenced from python; otherwise it must be declared unrealized with a reason. A family that is neither fails naming the language; one that is both is a stale declaration and fails; a family no language realizes is a dead registry entry and fails; an unused exemption is stale and fails. Language set from the installed `datrix.languages` entry points; registry and declarations read from the packages — never a table in the script. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\framework-header-parity-gate.ps1` | Census every registered language against the registry, its declaration and the exemption file; prints the family × language realized/declared/MISSING table |
| **Debug** | `.\test\framework-header-parity-gate.ps1 -Dbg` | Debug logging (per-language spelling and constant-reference counts) |
| **Self-test only** | `.\test\framework-header-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Spelling: `framework-prefixed spellings − registered names − exemptions = ∅`; `retired spellings = ∅`; `exemptions − live spellings = ∅` (no stale entry); every entry carries package, header, a registered family and a non-empty reason.
- Realization, per language and family: exactly one of `realized` / `declared unrealized (non-empty reason)`; a declared family must be registered.
- Registry: every family is realized by at least one language.
- Non-vacuity self-test (every invocation): a planted source tree yields exactly its two template spellings plus one python constant reference (a Markdown file and a `__pycache__` entry are not counted); the comparator reports exactly one problem for a retired spelling, an unregistered framework-prefixed spelling, a stale exemption, an undeclared hole, a reasonless hole, a stale declaration, an unknown declared family and a family nobody realizes, and none for a clean pair, an exempted spelling, a non-framework `X-` header, a declared hole, or a constant-realized family; the exemption parser rejects a miscount, an unknown family, a non-framework header and a reasonless entry; the **live** census finds the caller-token header on at least two languages; a single-language set is refused.

**Exit codes:** 0 = every language passes both rules (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the exemption file is missing/malformed/miscounted.

---

### `test\problem-type-parity-gate.ps1`

Problem-type parity gate: every registered language answers errors with RFC 7807 `type` URNs from datrix-common's one registry (`datrix_common.generation.problem_types` — `urn:datrix:error:<slug>`; a declared DSL exception derives its slug from its class name through the shared exception-declaration algorithm, a framework error uses a registered family) and realizes every framework family or declares the hole with a reason on its `LanguageCapabilityDeclaration.unrealized_problem_types`. The gate censuses every `.py` and `.j2` source under each registered language package's `src/` tree for `urn:datrix:error:` literals. **Spelling:** every literal slug is a registered family; a private slug has no exemption path (register it or spell the registered one). The bare prefix, a composition site for runtime-built URNs, is not a spelling. **Realization:** a family is realized when its URN is spelled; otherwise it must be declared unrealized with a reason. Neither fails naming the language; both is a stale declaration and fails; a family no language spells is a dead registry entry and fails. Language set from the installed `datrix.languages` entry points; registry and declarations read from the packages — never a table in the script. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\problem-type-parity-gate.ps1` | Census every registered language against the registry and its declaration; prints the family × language realized/declared/MISSING table |
| **Debug** | `.\test\problem-type-parity-gate.ps1 -Dbg` | Debug logging (per-language spelling counts) |
| **Self-test only** | `.\test\problem-type-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Spelling: `literal slugs − registered families = ∅`.
- Realization, per language and family: exactly one of `spelled` / `declared unrealized (non-empty reason)`; a declared family must be registered.
- Registry: every family is spelled by at least one language.
- Non-vacuity self-test (every invocation): a planted source tree yields exactly its two literal slugs (the bare prefix, a Markdown file and a `__pycache__` entry are not counted); the comparator reports exactly one problem for an unregistered slug, an undeclared hole, a reasonless hole, a stale declaration, an unknown declared family and a family nobody spells, and none for a clean pair or a declared hole; the **live** census finds the `internal` type on at least two languages; a single-language set is refused.

**Exit codes:** 0 = every language passes both rules (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed or fewer than two languages are registered.

---

### `test\artifact-role-parity-gate.ps1`

Cross-language artifact-role parity gate (D7) -- the G-A closure: detects a language silently emitting nothing for a construct another language realizes, without generating anything and without storing anything. It reads the generation pipeline's own per-target manifests (`.datrix/manifests/<target>.json`: the files each target wrote, plus a `generated_at` stamp) from the example trees `generate.ps1` writes under `<workspace>/.generated/<language>/<runtime>/<provider>/<example>/`. **There is no committed baseline and no bless step** -- see `datrix/docs/architecture/generated-output-stability.md`. For every `(example, runtime, provider)` generated in >= 2 registered languages, classifies each language's paths by domain role via that language's own derived `DomainDeclaration.structural_pattern` set (the same fnmatch globs the domain self-consistency gate uses) and asserts the role set is identical across those languages, EXCLUDING two cases the gate resolves structurally rather than through the exemption file. First, any domain the "missing" language declares globally `unsupported` -- a declared absence explained once at the language level, read directly off the declaration, never a per-example fact. Second, any domain whose `structural_pattern` matches nothing anywhere in that language's ENTIRE generated footprint (corpus-vacuous): if no example exercises the construct, its absence from one example is not drift. Both rules are consulted BEFORE the exemption file, so neither needs an exemption entry -- but the second is no longer silent: every corpus-vacuous `(language, domain)` must carry a typed, counted record in `scripts/config/corpus-vacuity-records.json` saying why nothing exercises it, since a generator no example reaches has no end-to-end signal at all. Paths matching no pattern are reported in an "unclassified" bucket but never compared -- template-level naming legitimately differs by language; the role SET is the contract.

**The gate is exactly as current as the local corpus, and refuses a partial one.** It prints every language's oldest and newest `generated_at` stamp, and exits 2 before comparing anything when any registered language has a registered example with no generated tree and no entry in `scripts/config/parity-known-nongenerating.json` -- naming every missing pair and the command that fills it (`generate.ps1 -All -L <language>`, once per registered language; Jon runs this, it is blocked for agents). A parked pair that DOES have a generated tree is a stale park entry and also fails: the recorded defect is fixed, delete the entry.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\artifact-role-parity-gate.ps1` | Compare role sets for every `(example, runtime, provider)` generated in >= 2 languages under `<workspace>/.generated` |
| **Explicit output base** | `.\test\artifact-role-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated` | Same, reading a named `generate.ps1` output base |
| **Debug** | `.\test\artifact-role-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\artifact-role-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |
| **Corpus-vacuity census** | `.\test\artifact-role-parity-gate.ps1 -Census` | Print every `(language, domain)` the generated corpus exercises nowhere, with its reviewed status; exit 0 (exit 2 on an incomplete corpus) |

**Parameters:** `-GeneratedRoot` (default: `<workspace>/.generated`), `-Dbg`, `-SelfTest`, `-Census`

**Assertions:**
- Every registered language's corpus is complete: each `system.dtrx` under `datrix/examples/` has a generated tree (a directory carrying `.datrix/manifests/*.json`) or a park entry; no parked pair has a tree.
- Every `(example, runtime, provider)` generated in >= 2 registered languages is compared.
- A domain role present (>= 1 matching path) in one language's generated tree for an example and absent from another language's tree for the SAME `(example, runtime, provider)` is a violation, UNLESS the missing language declares that domain globally `unsupported` (`_is_declared_unsupported`, skipped directly), OR declares it emitted on demand on its `LanguageCapabilityDeclaration.on_demand_domains` (it emits the domain only when the DSL invokes a triggering construct, where another language emits baseline scaffolding regardless -- dotnet's `Support/*.cs` helpers, python/java/dotnet's service-level `fn` file, python/typescript/java's `exceptions { }`-gated errors folder; skipped directly), OR the domain's pattern matches nothing across that language's entire generated footprint (`_is_corpus_vacuous_for_language`, skipped directly), OR a reviewed entry exists in `scripts/config/artifact-role-exemptions.json` -- the last being reserved for a genuinely example-specific hole; the file is absent when there is none, which is the normal state.
- `load_exemptions` refuses (raises `ValueError`, exit 2) an exemption entry naming a `(domain, language)` pair that language declares `unsupported` or on-demand -- such an entry would duplicate a declared absence the gate already reads directly; delete it instead of keeping it. A declared on-demand id that is not a shared universe domain is refused by name.
- **Corpus vacuity is skipped but never silent.** `check_corpus_vacuity_records` censuses EVERY registered language against EVERY domain it declares `supported` (not just the pairs the multi-language groups happen to exercise) and holds each corpus-vacuous `(language, domain)` to a reviewed record in `scripts/config/corpus-vacuity-records.json`. The comparison runs in both directions: a censused pair with no record fails (exit 1), and a record whose pair is no longer vacuous fails as stale (exit 1). Each record carries one of three statuses, which are never interchangeable because each carries a different remedy -- `unreachable-by-design` (no example can produce a matching file at all, whatever it declares or targets), `cloud-platform-only` (only an example resolving `deployment.provider` to a cloud provider could, and the corpus has none), `unexercised` (an ordinary local/docker example could and none declares the construct). `load_corpus_vacuity_records` refuses (exit 2) a missing/malformed file, a status outside those three, or a duplicated `(language, domain)`.
- Non-vacuity self-test (every invocation): a synthetic matching role-set pair reports zero divergence; a synthetic forced-mismatch pair reports exactly the planted gap; a synthetic manifest/declaration pair proves `classify_paths` buckets matched vs. unclassified paths correctly; `_is_declared_unsupported` correctly distinguishes a declared-unsupported domain, a declared-supported domain, and an undeclared domain id; `_is_corpus_vacuous_for_language` is proven against a synthetic footprint (never touching a real generated tree); the corpus reader is proven against a synthetic `.generated` layout under a PID-scoped scratch root (two targets' manifests union into one sorted path list with the newest stamp, a directory without pipeline manifests is not a tree, a single-language tree forms no comparison group, and the completeness check names a missing pair and a stale park entry); `_reject_exemptions_for_unsupported_domains` correctly rejects a synthetic entry duplicating a declared-unsupported domain; and `compare_vacuity_records` reports nothing for an agreeing census/record pair, reports a censused pair carrying no record, and reports a record whose pair is no longer censused -- with `_parse_vacuity_record` accepting each declared status and refusing an undeclared one.

**Exit codes:** 0 = every comparable example's role sets agree modulo declared-unsupported skips, recorded corpus-vacuous skips and reviewed exemptions (or a successful `-SelfTest` / `-Census`), 1 = an un-exempted role drift was found over a domain the missing language declares `supported` and whose pattern is non-vacuous corpus-wide, or a corpus-vacuous `(language, domain)` carries no reviewed record (or a record carries no corpus-vacuous pair), 2 = the self-test failed, the generated corpus is incomplete for some registered language (or a park entry is stale), zero groups are generated in >= 2 languages, or the exemption / corpus-vacuity-record / park file is missing/malformed (or, for exemptions, contains an entry duplicating a declared-unsupported domain).

---

### `test\example-registry-gate.ps1`

Example-universe consistency **and layout** gate (D9): every `system.dtrx` under `datrix/examples/` must appear in >= 1 named test set of `scripts/config/test-projects.json`, or carry a reviewed entry in `scripts/config/test-set-exclusions.json`. An unregistered example is never built by `generate.ps1 -All`/`run-complete.ps1 -All`, which select their corpus FROM `test-projects.json`'s test sets -- this is exactly how the `config-store` and `replayable-ingestion` whole-example parked defects (tracked in `parity-known-nongenerating.json`) went unnoticed for a full generation cycle before this gate landed.

The gate also enforces the examples tree's layout contract, since an example's identity IS its directory (`example_id`, its parity-baseline key and its `test-projects.json` path are all derived from the path its `system.dtrx` sits under): no example may live inside another example, and no `.dtrx`/`.dcfg` may belong to two examples or to none.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\example-registry-gate.ps1` | Compare disk examples against test-projects.json + test-set-exclusions.json, and check the examples tree's layout |
| **Debug** | `.\test\example-registry-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\example-registry-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Every `system.dtrx` under `datrix/examples/` has an id reachable from >= 1 `testSets` entry, or a `test-set-exclusions.json` entry.
- An exclusion naming an example with no `system.dtrx` on disk is a stale-exclusion violation.
- An example both excluded AND registered in some test set is a redundant-exclusion violation.
- An example directory inside another example directory is a nested-example violation -- the host's whole-tree operations would silently absorb the guest.
- A `.dtrx`/`.dcfg` contained in more than one example directory is a shared-file violation; one contained in no example directory is an unowned-file violation (a leftover nothing can parse).
- Non-vacuity self-test (every invocation, no file I/O): synthetic ids and paths prove both pure comparators detect each of the six violation classes and report a clean state as clean.

**Exit codes:** 0 = registry and layout both consistent (or a successful `-SelfTest`), 1 = at least one violation, 2 = the self-test failed, zero examples exist on disk, or a config file is missing/malformed/miscounted.

---

### `test\example-secret-seed-gate.ps1`

Example secret-seed gate: every example's deploy test can start its stack. A handle a service
declares in its `secrets { }` table is mounted into the container as a file, and the generated
deployment script refuses to start while that file is absent, writing nothing in its place; on
a local secret profile the generator writes the file only from the handle's `localDefault`. The
corpus is deploy-tested on the `test` profile by an unattended harness, so for every example,
on that profile, every `required = true` operator-provisioned handle must carry a `localDefault`
-- or no full-corpus run can ever bring the example up. A handle the profile does not consume
(a live-model API key on a profile that binds `replay`) is dropped from that profile with
`replace secrets { ... }`, never seeded with a fake value.

Resolves each example's service `.dcfg` files (kind detected by parsing, so identity/system
configs are skipped) through `datrix_common.config.unified_loader.load_service_config` on the
`test` profile -- the same resolution the pipeline applies -- and never parses a `.dtrx`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\example-secret-seed-gate.ps1` | Check every example's resolved `test`-profile secret tables |
| **Debug** | `.\test\example-secret-seed-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\example-secret-seed-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- For every `system.dtrx` under `datrix/examples/` and every service-kind `.dcfg` under its `config/`, the `test`-profile secret table has no handle that is `required = true`, `provisioningAuthority = "operator"` and without `localDefault`.
- Non-vacuity self-test (every invocation, no file I/O): a synthetic table with seeded, unseeded, optional and Datrix-owned handles must report exactly the unseeded ones, and an empty table must report nothing.

**Exit codes:** 0 = every handle seeded (or a successful `-SelfTest`), 1 = at least one unseeded handle, 2 = the self-test failed, zero examples or zero service configs exist on disk, or a config fails to parse or resolve.

---

### `test\block-realization-parity-gate.ps1`

Cross-platform capability-declaration parity gate (D1): the platform-axis counterpart of
`supported-domain-parity-gate.ps1`. Every installed `datrix.platforms` plugin declares a
`PlatformCapabilityDeclaration` — block realizations, secret backends, observability providers,
deployment runtimes, identity providers/features, and roughly a dozen scalar/mapping capability
flags. This gate computes the union of every capability coordinate any installed platform
declares, across seven surfaces (block-realization cells, secret backends, native observability
providers per category, deployment runtimes, identity `(provider_type, feature)` cells, every
remaining optional scalar/mapping field, and `unrealizable_surfaces`), and fails loud if another
installed platform has made no decision at all about a coordinate — unless the gap carries a
reviewed entry in `datrix/scripts/config/platform-capability-holes.json`.

Derives its target platform set from `importlib.metadata.entry_points(group="datrix.platforms")`
at runtime — never a hardcoded `aws`/`azure`/`docker`/`local` literal.

**Built-in non-vacuity self-test, every invocation.** Feeds the comparator a synthetic matching
declaration pair (must report zero gaps) and a synthetic pair with one planted missing union cell
(must report exactly that gap). Fails loud (exit 2) if fewer than 2 platforms are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\block-realization-parity-gate.ps1` | Compare every registered platform's declared capability coordinates |
| **Debug** | `.\test\block-realization-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\block-realization-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every union coordinate is declared or exempted, 1 = at least one unexempted
gap was found, 2 = the non-vacuity self-test failed or fewer than 2 platforms are registered.

---

### `test\model-realization-parity-gate.ps1`

Model-realization capability-declaration parity gate (Decision 46 invariant 6): every installed
`datrix.platforms` plugin declares a well-formed `model_realizations` mapping on its
`PlatformCapabilityDeclaration` — one `ModelRealization` per model provider (API family) the
platform realizes, each cell's `flavors` drawn from the closed placement domain
`container | external | managed | direct`. The field is REQUIRED with no default: a platform
realizing zero providers must still declare an explicit empty mapping, so a missing declaration
is a construction error (reported naming the platform, never a raw traceback), not a silently
absent capability. Scoped to that single field — it never compares provider sets across
platforms (a platform realizing zero providers is conforming); the cross-platform union
comparison over every OTHER capability surface is `block-realization-parity-gate.ps1`'s job.

Derives its target platform set from `importlib.metadata.entry_points(group="datrix.platforms")`
at runtime — never a hardcoded `aws`/`azure`/`docker`/`local` literal.

**Built-in non-vacuity self-test, every invocation.** Feeds the comparator a synthetic matching
declaration pair (must report zero violations) and a synthetic pair with one planted
out-of-domain flavor cell (must report exactly one violation, naming the offending platform and
flavor). Fails loud (exit 2) if fewer than 2 platforms are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\model-realization-parity-gate.ps1` | Check every registered platform's `model_realizations` declaration |
| **Debug** | `.\test\model-realization-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\model-realization-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every registered platform declares a well-formed `model_realizations`
mapping, 1 = at least one violation (an unconstructible declaration or an out-of-domain
flavor), 2 = the non-vacuity self-test failed or fewer than 2 platforms are registered.

---

### `test\pooled-cache-realization-gate.ps1`

Pooled-cache member-slice realization gate: for every registered `datrix.languages` /
`datrix.platforms` target, asserts that a pooled cache member's declared slice
(`PooledMember.slice_index`, `datrix_codegen_common.pooling.contract`) actually reaches that
target's own emitted-output-facing source — not merely that the shared pooling pre-pass computed
it. **Detection is STATIC**: the gate AST-parses each target package's own `src/` tree (never a
substring/regex scan, never `generate.ps1`) for a function that both reads a `.slice_index`
attribute AND is call-reachable from elsewhere in that same tree — declared AND consumed, not dead
code. A target that does not yet realize the slice must carry a typed exemption (axis + target +
reason) in `datrix/scripts/config/pooled-cache-realization-exemptions.json` — a target quietly losing its realization
(a regression) fails the gate the same way a target that never had one does; a target that starts
realizing while its exemption is still present (a stale exemption) also fails.

Derives its target sets from
`importlib.metadata.entry_points(group="datrix.languages" | "datrix.platforms")` at runtime —
never a hardcoded `python`/`typescript`/`java`/`dotnet` or `aws`/`azure`/`docker` literal — so a
future `datrix-codegen-<x>` package is covered automatically with no edit here. Every registered
entry-point name is checked independently (a platform name backed by a shared package, e.g.
`local` with `docker` or `azure-vm` with `azure`, still gets its own exemption entry).

**Built-in non-vacuity self-test, every invocation.** Proves, against synthetic source trees it
has never seen, that a declared-and-reachable `.slice_index` consumer classifies realized and a
declared-but-dead (never called) one classifies NOT realized — the exact regression shape a
realization task could introduce. Also exercises the gate's own vacuity guard for real (via a
`target_names` override, the same code path a live run takes) against a synthetic single-target
axis. Fails loud (exit 2) if fewer than 2 targets are registered on an axis being checked.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate (both axes)** | `.\test\pooled-cache-realization-gate.ps1` | Check every registered language AND platform target |
| **Single axis** | `.\test\pooled-cache-realization-gate.ps1 -Axis platforms` | Check only the platforms axis (or `-Axis languages`) |
| **Debug** | `.\test\pooled-cache-realization-gate.ps1 -Dbg` | Debug logging (also lists each target's declared-and-reachable consumer sites) |
| **Self-test only** | `.\test\pooled-cache-realization-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |

**Parameters:** `-Axis <languages\|platforms>` (default: both axes), `-Dbg`, `-SelfTest`

**Exemptions:** `scripts/config/pooled-cache-realization-exemptions.json` — one entry per
currently-unrealized target (`{axis, target, reason}`). There is no `-UpdateBaseline`: a
realization change removes its own entry, never a generic freeze command.

**Exit codes:** 0 = every registered target realizes the slice or carries a reviewed exemption
(and no exemption is stale), 1 = at least one unexempted gap or stale exemption was found, 2 = the
non-vacuity self-test failed or fewer than 2 targets are registered on an axis being checked.

---

### `test\documentation-realization-parity-gate.ps1`

Documentation-realization parity gate (Decision 39 I2/I6). For every registered `datrix.languages`
target, generates one small fixture project — via the real
`datrix_cli.pipeline.generation.GenerationPipeline` (the exact code path `datrix generate`/
`generate.ps1` runs, `ValidationLevel.FAST` so post-generation `dotnet build`/`mvnw compile` are
skipped — see below), never a hand-built test context — whose DSL documents an endpoint, an entity,
a field, an enum value, a struct field and a function, each with a published (`///`) comment and an
adjacent source-channel (`//`) comment. Asserts, by parsing the generated artifacts **structurally**
(Python's real `ast` + `tokenize` — a call-keyword `summary`/`description` string constant, or a
class/function/async-function docstring via `ast.get_docstring`, the landing site for a construct
with no decorator surface; a hand-rolled bracket/string-literal-aware lexer for TypeScript/Java that
either finds a decorator anchor outside any string/comment span and bracket-depth-tracks to its
matching close, or reads a `/** ... */` JSDoc/Javadoc doc-comment block — the no-decorator-surface
landing site, distinguished structurally from a plain `/* ... */` block comment by its `/**` opener,
exactly as `///` is distinguished from `//`; real XML parsing — `xml.etree.ElementTree` — of C#'s
grouped `///` doc-comment blocks, pulling `<summary>`/`<remarks>`/`<param>` element text — `<param>`'s
`name` attribute attributes a struct field's doc to the right record component — never a
line-oriented regex over a whole file), that the published text reaches that target's declared
published surface and the source text reaches its source surface and never the published one.

**Asserts over generated artifacts, not a running/building service.** This sandbox has zero NuGet
connectivity (dotnet) and an incompatible default JDK release (java `mvnw compile`), so generation
runs with `ValidationLevel.FAST` — `fix_imports` + `format_files` run, but `validate_files` (where
those two toolchains would otherwise be invoked) is skipped. **Two** language packages prove a real
end-to-end document in their own suites: python against a real FastAPI router's `.openapi()`, and
typescript against a real `tsc` + `SwaggerModule.createDocument()` run over an npm-installed
dependency set. java and dotnet do **not** — their suites assert over the generated artifacts
(springdoc reads the emitted annotations at request time, and no `.xml` doc file can be compiled
here), the same rung of the ladder this gate stands on. So this gate is the repo-level cross-target
census, and for java/dotnet the artifact assertion is the strongest proof this environment supports.

Derives its target set from `importlib.metadata.entry_points(group="datrix.languages")` at
runtime — never a hardcoded python/typescript/java/dotnet literal.

**Built-in non-vacuity self-test, every invocation.** Confirms every marker text is actually present
in the fixture DSL itself, then proves each structural extractor (Python ast/tokenize including
docstring detection, the C-family decorator-anchor lexer, the C-family `/** ... */` doc-block reader
— including a negative proof that a plain `/* ... */` block comment is never mistaken for one — the
dotnet XML-doc parser including `<param>`) finds a known-present published/source text in a synthetic
snippet it has never seen and never leaks a source comment into the published set. Fails loud
(exit 2) if fewer than 2 languages are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\documentation-realization-parity-gate.ps1` | Check every registered language target |
| **Debug** | `.\test\documentation-realization-parity-gate.ps1 -Dbg` | Debug logging (also logs each target's discovered published-string set and the fixture's `files_written` count) |
| **Self-test only** | `.\test\documentation-realization-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skips fixture generation entirely |
| **Re-pin coverage** | `.\test\documentation-realization-parity-gate.ps1 -UpdateCoverageBaseline` | Re-freeze the decrease-only coverage-hole baseline to this run's measured counts (the only writer; refuses to write when any target failed generation) |

**Parameters:** `-Dbg`, `-SelfTest`, `-UpdateCoverageBaseline`

**Coverage census (Decision 39 invariant 1):** the same run re-parses the fixture with the shipped
capture pipeline, collects every comment run ATTACHED to a node, and counts how many reach no
generated artifact at all on each target. Comparison is marker- and whitespace-normalized (a
formatter rewrapping a comment across lines is not lost documentation) and paragraph-by-paragraph
(the summary/description split puts one run's paragraphs in two different fields). Counts are held
by `scripts/config/documentation-coverage-baseline.json`; a target whose hole count rises above its
pinned value fails the gate. Attachment itself is policed separately, and at zero, by
`datrix-language`'s own produced-minus-consumed census.

**Exemptions:** `scripts/config/documentation-realization-exemptions.json` — one entry per
currently-unrealized `(target, construct_kind, surface)` cell (`{target, construct_kind, surface,
reason}`). A realization change removes its own entry; a STALE exemption
(the artifact now carries the text but the entry is still present) also fails the gate, naming the
entry to remove.

**Output:** `D:\datrix\.tmp\documentation-realization-parity-gate-report.json` (per-target census:
checked/populated/exempted/unexempted holes, the coverage block with each target's attached/reached/
hole counts and the anchors of any holes, plus generation failures if any) on every run, pass or
fail. The fixture project and its per-target generated output tree live under
`D:\datrix\.tmp\documentation-realization-parity-gate\` (fixture/, generated/&lt;target&gt;/).

**Exit codes:** 0 = every registered target's every `(construct_kind, surface)` cell is populated or
carries a reviewed, non-stale exemption AND no target's coverage holes exceed its pinned baseline,
1 = at least one unexempted hole, a stale exemption, a coverage regression, a generation failure, or
an exemption-file count mismatch, 2 = the non-vacuity self-test failed or fewer than 2 languages are
registered.

---

### `test\builtin-claims-parity-gate.ps1`

Cross-language builtin-claims parity gate (D2). Reads every registered `datrix.languages`
plugin's `LanguageCapabilityDeclaration.builtin_group_stances` and checks two surfaces, neither
with a reviewed-gap path (a divergence is always a real defect):

1. **Stance key-set identity** — every language declares a stance for exactly the same set of
   `BuiltinGroup` names. A non-vacuity proof: per-language completeness is already enforced at
   each language's own plugin import; this repo-level check exists to catch a future decoupling.
2. **Per-group stance-vs-mapper coherence** — every group has a declared stance, and every group
   a language declares `supported` has every one of its `BUILTIN_REGISTRY` rows actually mapped
   by that language's profile. Re-derives, as an independent backstop, the same judgment
   `register_builtin_capability` enforces at each language's own plugin import.

A `supported` stance is fully mapped by construction, so there is no "mapped by some languages,
not all" state left to catalogue as a reviewed exception — unlike the hand-typed claimed-group
set plus per-method reviewed-gap design this gate replaced, this one has no such config file.

Derives its target language set from `importlib.metadata.entry_points(group="datrix.languages")`
at runtime — never a hardcoded `python`/`typescript`/`dotnet`/`java` literal.

**Built-in non-vacuity self-test, every invocation.** Feeds both comparators a synthetic matching
pair (must report zero divergence) and a synthetic forced-mismatch pair (must report the planted
gap), using real `BuiltinGroup`/`BUILTIN_REGISTRY` data for surface 2. Fails loud (exit 2) if
fewer than 2 languages are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\builtin-claims-parity-gate.ps1` | Compare every registered language's stance key sets and stance-vs-mapper coherence |
| **Debug** | `.\test\builtin-claims-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\builtin-claims-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = stance key sets identical and every `supported` group is fully mapped, 1 = a
stance key-set divergence or an unmapped row in a `supported` group was found, 2 = the
non-vacuity self-test failed or fewer than 2 languages are registered.

---

### `test\wire-shape-round-trip-gate.ps1`

Wire-shape round-trip gate. Generates BOTH a backend service and a browser client for the adopted
ecommerce fixture application (`datrix/examples/03-domains/ecommerce/`), boots the backend with
`docker compose up -d --build --wait`, invokes every generated client method against it through a
Node harness that executes the emitted client classes **as shipped** (real TypeScript compilation,
real framework dependency injection, real `fetch`-backed HTTP), and compares every response body
against the interface the client generator emitted for it. This is the only check that exercises the
emitted client against a *running* backend rather than reasoning about either artifact in isolation —
the one that catches a response field transcribed in the wrong case, or a query parameter cased
against the wrong rule, at the source.

It is a repo-level script and not a renderer-package pytest suite because it asserts on the COMBINED
output of two generator packages — a backend language package's service and the browser-client
renderer's tree — which `.claude/rules/repo-boundaries.md` forbids inside any single package.

Derives its BACKEND target set from `importlib.metadata.entry_points(group="datrix.languages")` at
runtime — never a hardcoded language literal. A backend that fails to generate or boot is reported as
SKIPPED by name with its reason, and an emitted client target the gate has no harness for is reported
the same way; the target set is never narrowed in silence. The browser-facing base URL is read from
the generated `docker-compose.yml` (the service on the front-end network that publishes a host port,
whose live host port is then resolved with `docker compose port`) — no port or URL is assumed, and an
unresolvable one fails loud naming the compose file. Requires a running Docker daemon plus `node`/`npm`
on PATH; the pinned harness toolchain installs once into `D:\datrix\.tmp\wire-shape-round-trip\`.

Before building anything it runs five pre-flight comparisons over the emitted artifacts, so a boot
that cannot succeed says why in seconds instead of after an image build: the Host header the gate
will dial against the trusted hosts every emitted service will accept; the container names the
compose file fixes against the names the Docker daemon already holds; the host ports it fixes as
literals against the ports already bound; the compose variables that declare themselves required
against the ones `.env.example` supplies (each remaining one is given a freshly generated value,
reported by name); and the provisioned JWT signing key against the JWKS documents the stack's own
identity providers will verify against. A name or port conflict is reported with the container that
holds it — both are machine-global namespaces, so the holder is the actionable half. Where the
compose file draws the browser-facing host port from an environment substitution, the gate reserves
a free port for it rather than taking the template default, so a busy port is not reported as a
generator defect.

**The Host header is a seam, not a constant.** Every emitted service installs trusted-host
enforcement over the author-declared `httpSecurity.allowedHosts`, and the emitted gateway forwards
the client's Host verbatim to the upstream service *and* to the JWT auth subrequest — so one name
has to satisfy every service at once. The gate intersects the trusted-host lists of every service in
the fixture's *resolved* configuration (the language-neutral producer each backend transcribes into
its own emitted service), narrows that to the names this machine resolves to loopback, and dials one
of those. An empty intersection fails the gate before anything is generated, naming every declared
list and what each candidate resolved to. It is never closed by widening `allowedHosts`, which is a
trust boundary of the application under test.

**Authenticated routes are called authenticated.** The gate signs a short-lived bearer token with
the stack's **own provisioned private key** — the one the compose file mounts as the framework's
`jwt_private_key` secret — after proving that key's public half is in the JWKS an emitted identity
provider will fetch, and stamps the issuer, key id, algorithm and roles that provider's plan entry
and surfaces require. A real Angular interceptor attaches it, so the emitted client classes run
exactly as shipped and no auth check anywhere is bypassed, stubbed or relaxed. An absent provisioned
key, an absent provider plan, or no provider whose JWKS holds that key **fails the gate** rather
than falling back to unauthenticated calls, which would report every authenticated route as
unexercised and check nothing. A route that answers 401/403 with a valid token is still reported
UNEXERCISED, with its status — that is the application's own authorization decision.

**Requests are paced to the emitted rate limit, never around it.** The generated gateway declares
one address-keyed zone shared by every route (`rate=100r/m`, `burst=10`), so firing the whole route
manifest at once lets eleven requests through and answers the rest 429. The harness paces at one
request per 700 ms, honours the `Retry-After` the gateway sends on a 429, and retries within a
bounded, run-wide wait budget; only when that budget is spent is a route reported UNEXERCISED, with
the reason. The emitted limit itself is untouched.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\wire-shape-round-trip-gate.ps1` | Generate, boot, call, and compare for every registered backend language |
| **Debug** | `.\test\wire-shape-round-trip-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\wire-shape-round-trip-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real generate-boot-call-compare run |
| **Reuse the generated tree** | `.\test\wire-shape-round-trip-gate.ps1 -ReuseGenerated` | Boot and exercise the tree a previous run already generated, skipping generation |

**Parameters:** `-Dbg`, `-SelfTest`, `-ReuseGenerated`

`-ReuseGenerated` exists for the gate's own negative proof: plant a mis-cased property into an
emitted response interface and the gate must catch it, which a fresh generation would overwrite
before the first request. It fails loud when no previously generated tree is present.

**Two self-tests run automatically, every invocation, before anything is generated.** The first is a
diagnostic-durability check: every configured log stream is asked to encode a character outside the
console code page, because a stream that refuses one DROPS the whole record — and the records this
gate writes quote build transcripts and container logs it did not author, so a backend's SKIPPED
reason can vanish and look exactly like a backend with nothing to say. A stream left on `strict`
fails the gate in milliseconds instead of eating a diagnostic an hour in.

The second drives the SHARED response-shape comparator —
the same function the live path calls, not a copy — over synthetic payloads seven times. Three prove
it catches what it must: a matching synthetic interface (must report parsed), one whose single
property has been re-spelled in a different case (must report unparsed, naming that property), and one
declaring the wrong value kind for a nested property (must report unparsed, naming that property).
Severing the comparator turns `-SelfTest` red.

Four more prove it does not OVER-trigger, each paired with a negative leg so the permissive half
cannot pass by switching comparison off:

- an object under a field declared `unknown` parses (that is the generator's marker for a DSL `JSON`
  value, which constrains nothing) — while a mis-cased sibling field beside it still fails;
- a JSON `null` body parses against a `void` declaration (what the generator emits for `-> Void`) —
  while an interface declaring a required property still rejects `null`.

Both over-triggers were live: `NonNullable<unknown>` is `{}`, not `unknown`, so descending into a
correct `pagination: unknown` reported all six of its inner keys as undeclared properties; and
`null extends void` is false, so two correct `-> Void` routes were reported as mismatches. Neither
could ever have been fixed generator-side.

A route the backend answers with a non-2xx status is reported as **UNEXERCISED**, by name and with the
status, rather than as a mismatch: the generated interface describes the success body only (error
responses are deliberately untyped in this design), so an error body is a route the gate could not
exercise, not a shape disagreement. A method declaring `Observable<unknown>` is reported as **UNTYPED**
the same way. Both counts are printed on every run, and a run in which *nothing* could be compared
fails rather than passing vacuously.

**Exit codes:** 0 = every response that carried a typed success body parsed against its generated
interface, for at least one backend that booted; 1 = a wire-shape mismatch, a declared route with no
reachable client method, a method whose emitted shape could not be read or whose response type could
not be resolved, an argument no value could be constructed for, an emitted client tree that does not
compile, a client method issuing a route the generated manifest does not declare, an emitted client
target the gate cannot drive at all, or a run in which nothing at all could be compared; 2 = either
self-test failed (diagnostic durability or comparator non-vacuity), no `datrix.languages` targets are
registered, no host every emitted service trusts reaches this machine's loopback, or every registered
backend failed before a single route could be called.

---

### `test\body-wire-naming-conformance-gate.ps1`

Cross-language response-body wire-naming conformance gate. Generates the real CQRS example project
(`datrix/examples/02-features/03-infrastructure-blocks/cqrs/`) once per registered
`datrix.languages` plugin and proves every emitted response-body schema serializes under ONE
declared rule -- camelCase wire keys -- by reading each language's OWN generated response classes'
EFFECTIVE wire names, never the mere presence of a wire-renaming mechanism (a template with no
alias generator but single-word fields, e.g. `problem_details.py.j2`, is not a divergence -- its
effective wire name is unchanged either way).

A language whose response surface genuinely diverges declares it via a reviewed entry
in `datrix/scripts/config/body-wire-naming-exemptions.json` (`{language, schema_kind, template,
reason}`).

Derives its target language set from `importlib.metadata.entry_points(group="datrix.languages")`
at runtime -- never a hardcoded `python`/`typescript`/`dotnet`/`java` literal.

**Built-in non-vacuity self-test, every invocation.** Proves the comparator flags a genuinely
divergent field, does not flag a genuinely conformant one, does not flag a single-word field with
no wire-renaming mechanism (the real `problem_details.py.j2` shape), correctly suppresses a
divergence covered by a real exemption entry, and reads the EFFECTIVE serialization wire name
(never an `alias`-only read) against a real Pydantic model whose field carries only
`Field(serialization_alias=...)`. Fails loud (exit 2) if fewer than 2 languages are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\body-wire-naming-conformance-gate.ps1` | Generate the CQRS example for every registered language and compare effective wire names |
| **Debug** | `.\test\body-wire-naming-conformance-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\body-wire-naming-conformance-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip real generation |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every registered language's response bodies serialize camelCase (or every
divergence is exempted), 1 = an unexempted divergence was found (or a registered language has no
implemented extractor), 2 = the non-vacuity self-test failed or fewer than 2 languages are
registered.

---

### `test\enum-classifier-conformance-gate.ps1`

Cross-target enum-classifier conformance gate (D11, G10). Proves every registered
`datrix.languages` plugin that emits enum types realizes `equalsKeyword`/`containsKeyword`
identically for a fixture keyword-bearing enum: a hit returns the correct member, a miss without
fallback raises the language's declared unrecognized-value exception (`LanguageProfile.errors`)
with a message naming only the enum type (no input/keyword disclosure), and a miss with fallback
returns the fallback. These classifiers are deliberately NOT `BUILTIN_REGISTRY` entries (the
registry is keyed by fixed category names and a user enum is never one of those categories), so
this gate is the coverage the closed registry would otherwise provide.

Derives its target language set from `importlib.metadata.entry_points(group="datrix.languages")`
at runtime, then narrows to enum-emitting languages from each plugin's own registered `"enum"`
sub-generator domain — never a hardcoded `python`/`typescript`/`dotnet`/`java` literal.

**Built-in non-vacuity self-test, every invocation.** Feeds the comparator a synthetic
fully-conformant pair (must report zero violations) and a synthetic partially-broken pair (must
report exactly the broken language). Fails loud (exit 2) if fewer than 2 enum-emitting languages
are registered.

A known, reviewed gap is a typed entry in
`datrix/scripts/config/enum-classifier-conformance-exemptions.json` (`{language, reason}`) —
never silence.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\enum-classifier-conformance-gate.ps1` | Compare every registered enum-emitting language's classifier conformance |
| **Debug** | `.\test\enum-classifier-conformance-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\enum-classifier-conformance-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every enum-emitting registered language is fully conformant or has a valid
exemption, 1 = an unexempted conformance gap was found, 2 = the non-vacuity self-test failed or
fewer than 2 enum-emitting languages are registered.

---

### `test\gendsl-corpus-resolution-gate.ps1`

GenDSL D1/I1 corpus proof: eager builder/call-expression reference resolution runs at
`@generator_definition` registration time (`datrix_codegen_common.gendsl.resolver`). Importing
each discovered target's genDSL definitions module IS the assertion: a bad reference raises
`GenDSLReferenceResolutionError` at import time.

**Target set is derived, never hardcoded.** The module list comes from
`datrix_codegen_common.gendsl.target_registry.target_kind_map()` +
`definition_modules_for()`, folded from `datrix.gendsl_generator_targets` entry-point discovery --
every target, including aws/azure/docker, self-registers its definition modules there (platform
KIND classification separately derives from `datrix.platforms` membership). A future
`datrix-codegen-<x>` package that registers either entry-point group is swept automatically, with
no edit to this gate.

This gate previously lived as a pytest test inside `datrix-codegen-common`
(`tests/integration/gendsl/test_resolution_corpus.py`) that imported every concrete target package
directly — a `datrix_codegen_common`-must-not-import-concrete-target-packages boundary violation
**and** a cross-package test (prohibited everywhere in the repo, not only in the showcase package).
The proof is inherently repo-level, so it moved here (deleting the pytest test) rather than
allowlisting the violation — the allowlist is terminal-empty (Invariant I7) and adding an entry
would be a regression.

**Each target's module is imported in its own dedicated subprocess** — never in this process — so
no single process ever holds more than one generator package's genDSL modules loaded at once (a
registration from one package's earlier import could otherwise silently satisfy a reference the
next package's own corpus does not actually resolve on its own).

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\gendsl-corpus-resolution-gate.ps1` | Import every discovered target's genDSL definitions, fail on any unresolved reference |
| **Debug** | `.\test\gendsl-corpus-resolution-gate.ps1 -Dbg` | Debug logging (also prints the discovered module list and count) |

**Parameters:** `-Dbg`

**Exit codes:** 0 = every discovered target's genDSL corpus resolved at import, 1 = at least one
target failed to resolve or import.

---

### `test\toolchain-free-suites-gate.ps1`

**The repo's proof that no framework test suite compiles or executes generated output.** A `datrix-*/tests/` suite exists to prove that DATRIX FUNCTIONALITY works -- that the generator emits the right thing. Whether the emitted output then compiles and runs in its target language belongs to the generated tier: the generated project's own unit tests, and the deploy tests.

**Why it is a gate and not a convention:** a framework suite that shells out to a language toolchain has to install one, so its result stops depending only on the code under test. That was real, not theoretical -- a cold Maven Central jar fetch with no timeout wedged one package's suite at 99% for an hour with no error text, and the same suite runs in under a minute with the compile legs gone.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\toolchain-free-suites-gate.ps1` | Scan every `datrix-*` package suite |
| **One suite** | `.\test\toolchain-free-suites-gate.ps1 -Suites D:/datrix/datrix-codegen-java/tests` | Scan one or more comma-separated `tests/` directories |
| **Self-test** | `.\test\toolchain-free-suites-gate.ps1 -SelfTest` | Prove the detector is non-vacuous, skip the real scan |

**Parameters:** `-Suites <path[,path...]>`, `-SelfTest`

**Fails on:**
- A toolchain subprocess: `javac`, `java`, `mvn`/`mvnw`, `gradle`, `dotnet`, `tsc`/`tsx`, `npm`/`npx`, `node`, `docker`, `az`, `aws`, `gcloud`, `kubectl`, `terraform`, `bicep` -- whether named as a literal or resolved through a helper.
- In-process execution of generated source: `exec(compile(...))`, `runpy.run_path`/`run_module`, `importlib`'s `spec_from_file_location`/`exec_module`.

**Never fails on:**
- Linters over generated TEXT (`ruff`, `black`, `isort`, `mypy`) -- reading is not executing.
- Subprocess runs of datrix itself (`sys.executable -m datrix_cli`, the import-boundary probes) -- that is framework functionality, not generated output.
- Loading a sibling `test_*.py` for a shared harness -- that is this suite's own code.

**Assertions:** the non-vacuity self-test runs before every real scan (a planted `javac` call and a planted `exec(compile(...))` must both be caught; an allowed `ruff` call and an allowed `sys.executable -m datrix_cli` must both pass), so a green result can never mean the detector was broken.

**Exit codes:** 0 = no suite compiles or executes generated output, 1 = at least one violation, or the self-test failed.

---

### `test\standing-conformance-gate.ps1`

Standing conformance-spec corpus gate (D10): runs every committed `conformance_gate.py` spec under `scripts/config/conformance-specs/` (top-level `*.json` files only -- fixture subdirectories such as `_fixtures/` are never swept). Each spec's own self-test runs first, exactly as `conformance_gate.py`'s single-spec CLI already guarantees on every invocation.

**Policy this gate exists to serve:** a design-acceptance NEGATIVE check ("the old state is gone on every surface") that outlives its landing must either become a real test in the owning package (preferred, per the prefer-a-test-over-a-scratch-script rule), or a committed spec here -- never a one-off run nobody re-executes. When a change's acceptance proof is "the old construct no longer exists anywhere" and that proof cannot naturally live as a package test, add a spec JSON here.

**Writing a spec:**
- **Paths are relative to the spec file.** `conformance_gate.py` accepts absolute paths too (fine for a one-off hand-run spec), but a *committed* spec bakes one machine's checkout location into the repo, and the runner hard-fails exit 2 on a missing directory -- so an absolute path does not degrade elsewhere, it simply cannot run. This gate checks the whole corpus for rooted paths **before running any spec** and aborts with exit 2 naming the offenders. From `scripts/config/conformance-specs/`: `../../../examples` (datrix examples), `../../library/test` (script library), `../../../../<package>/src` (a sibling package).
- **Negative-control fixtures live under `_fixtures/`** -- per-spec in `_fixtures/<spec-stem>/negative-control/`, or `_fixtures/_shared/<name>/` when several specs police the same retired surface (the four config-block dead-surface specs share one `system.dcfg` control this way). A `must_not_contain` whose pattern is absent from the control tree too fails as VACUOUS, so the fixture must keep containing the forbidden pattern forever -- never "fix" it to match the real code. A control tree is scanned with the **assertion's own glob**, so the fixture's filenames must satisfy that glob (a spec globbing `secret_backend.py` needs a control root holding a file by that name).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\standing-conformance-gate.ps1` | Run every committed spec |
| **Debug** | `.\test\standing-conformance-gate.ps1 -Dbg` | Debug logging, forwarded per-spec |

**Parameters:** `-Dbg`

**Assertions:**
- Every `*.json` file directly under `scripts/config/conformance-specs/` is a spec, run via `conformance_gate.py --spec <file>` (its own built-in self-test runs first, per-spec, aborting that spec with exit 2 before any real result is trusted).
- Seed spec `gendsl-corpus-no-hand-authored-module-tuple.json`: `gendsl_corpus_resolution.py` contains none of the seven retired hand-authored genDSL definitions-module literal strings, proven non-vacuous by a dedicated negative-control fixture under `scripts/config/conformance-specs/_fixtures/` that intentionally still contains them.

**Exit codes:** 0 = every spec passed, 1 = at least one spec's assertions failed, 2 = the spec directory is missing/empty, a committed spec addresses its trees by absolute path, or any individual spec's own self-test failed (that spec's run aborts before its real assertions are evaluated).

---

### `test\review-library-gate.ps1`

Absorbs the valuable coverage of 5 orphaned pytest files that used to live under
`scripts/library/review/tests/` (`test_review_schema.py`, `test_canonical_modules_cache.py`,
`test_escalation.py`, `test_model_parsing.py`, `test_orchestrator_core.py`) — the `datrix`
showcase repo hosts no pytest suite of any kind, so those files were never executed by any
runner. Re-expresses each file's distinct behavioral classes as plain-Python `assert`-based
checks (no pytest, no mocks/fakes) against `scripts/library/review/{review_schema,
canonical_modules, escalation, review}.py`: `Finding`/`ReviewResult` construction and
serialization round-trips, canonical-module package discovery/scanning/digest-building/cache
validity/prompt formatting, `should_escalate_to_tier2` across every escalation mode and
threshold combination, `extract_json_from_response`/`parse_model_response` JSON-extraction
strategies (fences, brace-matching, `<think>` tag stripping, largest-review-JSON selection), and
the orchestrator core (`resolve_task_context`, `discover_phase_tasks`, `dict_to_review_result`,
`build_reviewer_prompt`). Repo-level validation **script**, not a pytest suite (per the datrix
showcase boundary).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\review-library-gate.ps1` | Run all 48 absorbed checks |
| **Harness self-test** | `.\test\review-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\review-library-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** 48 named checks covering `review_schema.py`, `canonical_modules.py`,
`escalation.py`, and `review.py`'s JSON-extraction and orchestrator-core functions. Several are
inherently adversarial (corrupt/malformed JSON → invalid or `None`, non-review JSON rejected,
garbage → `None`, unknown escalation mode never escalates), which already demonstrates
discriminating power; `-HarnessSelfTest` additionally proves the pass/fail harness itself is not
vacuous by registering one deliberately-failing dummy check and confirming it is reported
`[FAIL]` with a nonzero exit.

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage error.

---

### `test\test-tooling-parsing-gate.ps1`

Absorbs the valuable coverage of 2 orphaned pytest files that used to live under
`scripts/library/test/tests/` (`test_compare_tests.py`, `test_status_tests_index.py`) — the
`datrix` showcase repo hosts no pytest suite of any kind, so those files were never executed by
any runner. Re-expresses each file's distinct behavioral classes as plain-Python `assert`-based
checks (no pytest, no mocks/fakes) against `scripts/library/test/compare_tests.py` and
`scripts/library/test/status_tests.py`: `find_runs`/`build_service_comparisons`/`parse_unit_run`
(direct-child-only `unit-tests-*`/`deploy-test-*` run discovery excluding nested/archived dirs,
service change classification e.g. REGRESSED with OK/FAIL history, the flat-log fallback parser
for `unit-tests-summary.log`, and unit-vs-deploy runs discovered and compared as separate
populations), and `TestResult`/`_format_result_row`/`_read_index_json`/`find_latest_log_file`/
`parse_pytest_summary`/`parse_timestamp_from_log_file` (structured `index.json` parsing including
the INCOMPLETE-falls-back-to-`full.log` signal, `index.json`-preferred-over-`full.log` discovery,
directory-name timestamp parsing, and the in-progress xdist `[ NN%]` progress-percent extraction
case). It additionally covers `scripts/library/test/run_complete.py`'s Java generated-project
handling — `_find_java_service_dirs`/`_is_java_project` service detection (Maven modules with
`src/test/java`, with the project-level `deployment-tests` module excluded because deploy tests
run in Step 4) and `_merge_surefire_reports`/`_count_junit_testcases`, including the adversarial
cases where a build never reached surefire and so must NOT read as a clean run. Repo-level
validation **script**, not a pytest suite (per the datrix showcase boundary).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\test-tooling-parsing-gate.ps1` | Run all 45 absorbed checks |
| **Harness self-test** | `.\test\test-tooling-parsing-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\test-tooling-parsing-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** 45 named checks covering `compare_tests.py`, `status_tests.py`, and
`run_complete.py`'s Java project detection / surefire report merging. Several are
inherently adversarial (nested/archived run dirs excluded from discovery, corrupt JSON → `None`,
INCOMPLETE result → `None`/fallback, missing `counts` → `None`), which already demonstrates
discriminating power; `-HarnessSelfTest` additionally proves the pass/fail harness itself is not
vacuous by registering one deliberately-failing dummy check and confirming it is reported
`[FAIL]` with a nonzero exit.

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage error.

---

### `test\shared-library-gate.ps1`

Absorbs the valuable coverage of 8 orphaned pytest files that used to live under
`scripts/library/shared/tests/` (`test_structured_log_writer.py`, `test_test_runner_junit.py`,
`test_codegen_hint_mapper.py`, `test_deploy_test_aggregate_writer.py`,
`test_generated_test_log_writer.py`, `test_aggregate_test_writer.py`,
`test_deploy_test_log_writer.py`, and 3 of the 8 test classes in `test_logging_utils_dirs.py`) —
the `datrix` showcase repo hosts no pytest suite of any kind, so those files were never executed
by any runner. Re-expresses each file's distinct behavioral classes as plain-Python `assert`-based
checks (no pytest, no mocks/fakes, real `tempfile.TemporaryDirectory()` fixtures) against
`scripts/library/shared/{structured_log_writer, test_runner, codegen_hint_mapper,
deploy_test_aggregate_writer, generated_test_log_writer, aggregate_test_writer,
deploy_test_log_writer, logging_utils}.py`: JUnit XML / Jest JSON parsing and clustering by
normalized error pattern, source-location fallback chains (project frame → test frame →
conftest-as-test → stdlib-only/no-traceback → `unknown:0`), codegen-hint path mapping,
cross-project cluster correlation (including representative-project count/alphabetical
tie-breaking and suite-failure clusters as a separate cluster type from error/failure clusters),
deploy-test phase detection from both human-readable (`=== Docker Build ===`) and structured
(`docker_build_started`/`docker_build_failed exit_code=1`) log markers — including the regression
where a Docker-unavailable-with-no-markers or fully empty deploy dir must resolve to FAILED at
docker-build with every phase SKIPPED, never silently PASSED, and the one where a lifecycle
failure's message must be the failed command's captured output (the record body under the
runner's `<label> output:` header, bounded, with a legacy line-per-record log unchanged), never
the header line or its timestamp — transient-vs-logic failure
classification, `failures.json` read as the ENVELOPE the generated runners write (its `failures`
entries decide the phase result — a green run whose envelope carries an empty list must not read as
FAILED), per-service counts derived from each runner's own suite totals rather than from a tally of
the failure list (a partly-green run reports its real `passed`, and a JUnit `<error>` case lands in
`errors` instead of being folded into `failed`), and `TeeLogger`/`cleanup_old_logs` log-content and
directory-cleanup behavior.
`test_runner.py` and `logging_utils.py` are used READ-ONLY (imported and called, never edited);
the directory-creation/uniqueness classes of `test_logging_utils_dirs.py`
(`TestTeeLoggerDirectoryCreation`, `TestRunDirProperty`, `TestContextManager`) are deliberately
NOT re-covered here because `test-specific-selection-gate.ps1`'s `run_dir_exclusivity_check`
already exercises the same `TeeLogger`/`LogConfig` directory-claiming mechanism far more
rigorously (8 sequential + 8 concurrent racers). Repo-level validation **script**, not a pytest
suite (per the datrix showcase boundary).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\shared-library-gate.ps1` | Run all 69 checks |
| **Harness self-test** | `.\test\shared-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\shared-library-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** 69 named checks covering `structured_log_writer.py`, `test_runner.py`,
`suite_stamp.py`, `node_test_runner.py`'s stamp, `codegen_hint_mapper.py`,
`deploy_test_aggregate_writer.py`, `generated_test_log_writer.py`,
`aggregate_test_writer.py`, `deploy_test_log_writer.py`, and `logging_utils.py`'s log-content and
cleanup functions. Ten cover the suite-input stamp, none of them running pytest. One imports each
stamp-path library module (`test.suite_inputs`, `test.affected_set`, `test.affected_gate`,
`test.gate_verdict`, `shared.suite_stamp`, `shared.test_runner`, `shared.node_test_runner`,
`shared.structured_log_writer`) FIRST in a fresh interpreter, after proving on a planted cycle that
the probe sees an order-dependent import cycle. Of the rest: the runner
plugin is loaded by its own `-p` argv pair only when asked; the selection classifier records only
an unnarrowed run as `full`; index.json v2 writes `selection`/`inputs` as given and never `inputs`
on an INCOMPLETE run; the record names the merge reads are compared in code against the runner
plugin that writes them; over real git repositories, a complete record set is stamped with exactly
the cone's trees plus its ignored, foreign and executable inputs, while a missing, unaccounted,
mislabelled or unreadable record, a phase that did not complete, or a cone tree edited mid-run
each refuse the stamp; and the Node runner's stamp names exactly the executables it launched over
the real `datrix-vscode` cone, which holds its cross-ecosystem dependency `datrix-language`, and
its `installed` component covers the package's installed Node dependencies. Seven cover the
serial-phase decision over real record files, read the way the runner reads them: workers that
deselected serial items run the phase (with or without a marker/keyword filter); every worker
deselecting 0 skips it with `phases.Serial` = `skipped (0 serial items)` (but a filter keeps it);
no records, a controller-listed worker with no record, an unrecorded run and a parallel phase that
did not complete all run it and none is a runner error; disagreeing counts, a malformed count and a
record the controller did not list are runner errors that still run the phase; index.json writes a
skipped phase as its reason string (rendered as no status, never OK) and a runner error makes an
otherwise-green run FAILED under `runner_errors`; a full run whose serial phase was skipped is
stamped from the workers' records alone; and the unstamped run's recorder environment passes the
runner plugin's own validation. One of them pins the parallel phase's distribution mode to `-n auto --dist
loadgroup` (and the serial phase to neither flag): `loadgroup` is the only xdist mode that honours
an `xdist_group` mark, and both `datrix-codegen-typescript` and `datrix-codegen-angular` pool their
`npm_tsc` tests through such marks — a downgrade to plain `--dist load` would silently un-bound
both pools without failing anything else. Several checks are inherently adversarial
(corrupt/truncated/empty JUnit XML →
INCOMPLETE, missing/corrupt per-project `index.json` skipped without error, a
Docker-unavailable-with-no-markers or fully empty deploy dir → FAILED never PASSED,
`add_project_results` raising `FileNotFoundError`/`JSONDecodeError` on bad input), which already
demonstrates discriminating power; `-HarnessSelfTest` additionally proves the pass/fail harness
itself is not vacuous by registering one deliberately-failing dummy check and confirming it is
reported `[FAIL]` with a nonzero exit.

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage error.

---

### `test\customer-domain-isolation-gate.ps1`

**The repo's proof that no customer/project domain language lives in a framework repo.** Scans the git-TRACKED content of every framework repo in the workspace (`datrix` plus every `datrix-*` clone, discovered from disk) against the hashed customer-term corpus at `scripts/config/customer-term-hashes.json`. The rule ("no customer name, no customer-specific service names, no terms from a customer's business domain in framework code, docs, tests, or examples") was prose only until this gate: customer cloud-resource names and paths into a customer checkout reached committed files through Claude Code permission entries, and a customer deployment target reached a hook's docstring example. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

**The corpus stores digests, not terms.** A plaintext denylist naming the customer would itself be the violation it polices. Only SHA-256 digests of lowercased terms are committed, so the term never exists in any repo, while the check still travels with the checkout and enforces on every machine — an out-of-repo term file would silently not exist on a second machine, which is exactly the failure mode a guard must not have. Register a term with `-AddTerm`; the plaintext is hashed and discarded.

**Reported excerpts are redacted.** The matched token is masked as `<customer-term>`; the file and line are what a fix needs. Echoing the term back invites an agent into copying it onward — into a summary, a task file, or a commit message — re-committing the leak while reporting it.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\customer-domain-isolation-gate.ps1` | Scan every tracked file in every framework repo |
| **One repo** | `.\test\customer-domain-isolation-gate.ps1 -Repo datrix` | Scan only the named repo(s) |
| **Pending changes only** | `.\test\customer-domain-isolation-gate.ps1 -PendingOnly` | Scan only what a `git add -A` would stage |
| **Register a term** | `.\test\customer-domain-isolation-gate.ps1 -AddTerm acmecorp -Hint "customer project"` | Append the term's digest to the corpus and exit |
| **Debug** | `.\test\customer-domain-isolation-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-Repo <name[,name...]>`, `-PendingOnly`, `-AddTerm <term>`, `-Hint <text>` (default: `customer project`), `-Dbg`

**Self-test runs automatically, every invocation.** Before any real scan, the scanner is fed four synthetic occurrence shapes it must detect (hyphenated resource name, path segment, camelCase identifier, upper-case identifier), two clean strings it must NOT flag, a redaction check (the reported excerpt must not contain the term), and an empty-corpus check (must report nothing). A detector that stopped detecting reports a clean tree, which is indistinguishable from a clean tree — so a self-test failure aborts before any result is trusted.

**Matching shape:** content is split into alphanumeric tokens, each token is additionally camel-split, and every piece of at least `min_token_length` (default 5) characters is lowercased and hashed. That covers `<term>-system-kv-dev`, `//d/g/<Term>/**`, `<term>_rg`, and `<term>Backend`. It does NOT match a term glued to another word with neither separator nor case boundary (`<term>dev`) — a hash denylist cannot substring-search without the plaintext it deliberately does not hold; register such a variant as its own term.

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over every dirty repo's pending changes before it generates a message or stages anything, and refuses the whole run on a violation (`-SkipCustomerDomainCheck` overrides, loudly). This gate is the tracked-tree counterpart: it also catches what is already committed.

**Exit codes:** 0 = no violations (or zero terms registered, reported as `NOT ENFORCED`), 1 = at least one violation or a failing self-test, 2 = usage error or a missing/malformed corpus.

---

### `test\ignored-source-gate.ps1`

**The repo's proof that no `.gitignore` rule is silently deleting a publishable file.** For the `datrix` showcase repo and every `datrix-*` clone in the workspace (discovered from disk at runtime — a new package is covered with no edit to the gate), it computes the set difference between the working tree and what a `git add -A` would stage. Every element of that difference must be a reviewed, scoped entry in `scripts/config/ignored-source-exemptions.json`; anything else is a source file that exists locally and will not survive a clone. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), and the gate's own self-test is its coverage.

**Why it exists.** A package carried the stock Python `.gitignore`'s **unanchored** `MANIFEST` line — intended for setuptools' root `MANIFEST` file. Git matches an unanchored pattern at *any depth*, and `core.ignorecase=true` on this platform makes the match case-insensitive, so it also matched a `templates/manifest/` directory and swallowed both Jinja2 templates inside. Nothing was visible locally: the files were on disk, every test passed, the emitted output compiled. The loss appears only after a clone or a wheel install, as a package that cannot generate — and by then the templates are gone from history. It was found by hand, by comparing a file count against a `git add -A --dry-run` count. This gate is that comparison, living in code.

**Git is the oracle.** Ignore matching is never re-implemented. `git ls-files -o -i --exclude-standard` produces the difference at *file* granularity (directories are not collapsed), and `git check-ignore -v` names the `.gitignore` file, line number, and pattern responsible for each element. Anchoring, negation (`!`), nested `.gitignore` files, `.git/info/exclude`, global excludes and `core.ignorecase` interact in ways a hand-rolled matcher gets wrong — and a wrong matcher returns a confident "clean" that will be believed, which is how the original defect survived. A path git refuses to stage but attributes to no rule is reported with a placeholder rule and fails the gate; it can never match an exemption.

**Every finding names the rule, not just the file.** Output is grouped as `<gitignore>:<line>: <pattern> -- shadows N publishable file(s)`, then the paths. Reporting only the file leaves the fix a hunt through several hundred `.gitignore` lines.

**Exemptions are scoped, and the scope is load-bearing.** Each entry excuses **one** rule (identified by the `.gitignore` file plus the pattern text git reports) over **one** path scope, and carries a written reason. An entry for the root `build/` tree does not excuse the same unanchored `build/` rule swallowing a `templates/build/` directory full of source — that is the same defect wearing a different name, and the self-test proves the scope rejects it. `repos` is a list of repo names or `["*"]` for every framework repo; `path_glob` is segment-aware (`**/` spans whole segments, `**` spans the remainder, `*`/`?` stay inside one segment). `pinned_count` is enforced against `len(exemptions)`, so an entry cannot be added or removed without the reviewed number moving in the same change.

**A stray temp directory is a different finding with a different fix.** Temp, scratch and test-output directories never belong inside a package repo (`guard-repo-temp-dirs.py` refuses to create one; the workspace-level `D:\datrix\.tmp`, `.scripts`, `.test-output` are where they go). One that exists anyway — left by a run before the hook, or by a tool that defaulted its output path — is full of `.py`/`.java`/`.sql` files that an ignore backstop hides, and to a scan that only knows "ignored, unexempted" it looks like hundreds of thousands of shadowed source files whose fix is to edit the ignore line or add an exemption; both are wrong. The gate classifies such paths by the **same name list the hook enforces** (`claude-config/.claude/hooks/_repo_temp_dir_names.py` — one definition, two enforcement points; the gate refuses to run if it cannot load it rather than keep a copy) and reports each directory **once**, as a `WARNING` carrying the file count and the `Remove-Item` command. It never appears in the shadowed-source report, it can never be exempted, and it does not fail the gate: the contents are already unpublishable, and the gate's verdict is about what a clone would lose. `commit-and-push.ps1` prints the same warning and proceeds.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\ignored-source-gate.ps1` | Scan every framework repo in the workspace |
| **One repo** | `.\test\ignored-source-gate.ps1 -Repo datrix-language` | Scan only the named repo(s) |
| **Several repos** | `.\test\ignored-source-gate.ps1 -Repo datrix-language,datrix-vscode` | Scan the named repos only |
| **Self-test only** | `.\test\ignored-source-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Show exemptions** | `.\test\ignored-source-gate.ps1 -ShowExempt` | Print every reviewed entry with its written reason, then scan |
| **Debug** | `.\test\ignored-source-gate.ps1 -Dbg` | DEBUG logging; print the python invocation before running |

**Parameters:** `-Repo <name[,name...]>`, `-SelfTest`, `-ShowExempt`, `-Dbg`

**Self-test runs automatically, every invocation.** Before any real scan, real `git init` repos are created in a temp directory and the scanner must reach the correct verdict on each planted path — a scan that can only return zero is not evidence, which is precisely how the original defect survived. It asserts:

- an unanchored `MANIFEST` rule shadowing `src/pkg/templates/MANIFEST/entry.j2` is **detected**, and blamed on the right `.gitignore` **file, line number and pattern**;
- that finding is **not** excused by any entry in the real exemption file;
- a planted publishable file (`src/pkg/keep.py`) is **not** reported;
- a `__pycache__/` file and a root `build/` file **are** excused by their real entries, while the same `build/` rule shadowing `src/pkg/templates/build/template.j2` is **not** — proving the path scope is load-bearing;
- an empty exemption set excuses nothing (the exemption matcher is not vacuously true);
- two files planted in different subtrees of a `.test-output/` directory fold into **one** stray-temp-directory finding with a count of 2 and a delete command, appear in **no** shadowed-source finding, and do not swallow the `MANIFEST` finding beside them — which also proves the hook's shared name list still names `.test-output`;
- git's own semantics are honoured: a `!`-re-included path is not reported, and a lowercase `manifest` directory under an uppercase `MANIFEST` rule is detected **iff** `core.ignorecase` is true in that repo;
- the scope glob is segment-aware across nine positive and negative cases.

A self-test failure aborts before any real result is trusted (exit 1).

**Unused exemption entries are reported, never failed.** An entry covers output a tool writes only once it has run (a coverage report, an `npm install`), so its absence on a clean checkout is normal and is not evidence the entry is stale.

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over every dirty repo before it generates a message or stages anything, and refuses the whole run on a violation (`-SkipIgnoredSourceCheck` overrides, loudly); a scanner that fails its own self-test aborts the run rather than returning a verdict nobody can trust. That is the seam this defect is actually about — `git add -A` is where the file is or is not published. This gate is the whole-workspace counterpart: it also covers repos the current run is not committing.

**Exit codes:** 0 = every unstaged working-tree path is a reviewed exemption, 1 = at least one publishable file is shadowed or the self-test failed, 2 = usage error (unknown `-Repo` name, no framework repo found) or a missing/malformed/miscounted exemption file.

---

### `test\polystring-case-roundtrip-gate.ps1`

**The repo's proof that no name goes `str()` → `to_*_case()`.** Every identifier the generator re-cases — an entity, service, block, field, queue or shared-container name, `QualifiedNode.name`, `qualified_name` — is a `PolyString`: a `str` subclass that split its words **once** and exposes `.snake`, `.camel`, `.pascal`, `.kebab`, `.screaming_snake` and `.simple`. The case functions in `datrix_common.utils.text` are for text that is *not* already a name object. For the `datrix` showcase repo and every `datrix-*` clone (discovered from disk at runtime), the gate parses every publishable `.py` file with `ast` and fails on any case-function call — by canonical name, import alias, or module attribute — whose argument is one of four shapes:

| Kind | Shape | Fix |
|------|-------|-----|
| `str-wrapped` | `to_X_case(str(E))` | read `E.X`; if `E` is genuinely plain text, drop the `str()` — case functions accept any `str`, PolyString included |
| `str-bound` | `to_X_case(NAME)` where `NAME = str(E)` is bound in the same function/module scope | read `E.X` off the original name object |
| `nested` | `to_X_case(to_Y_case(E))` | the outer call alone is equivalent; a derived name is `PolyString.compose(...).X` |
| `simple-name` | `to_X_case(extract_simple_name(E))` | `E.simple.X` |

**Held at a hard zero with no exemption file.** No shape above has a legitimate instance: a case function never needs a `str()` around its argument, and a nested call never needs its inner one. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), and the gate's own self-test is its coverage.

**Why it exists.** The round trip is not merely wasteful (it recomputes the word split the name already paid for): it hides from the next reader that the value was a name, so they treat it as text too, and the pattern spread to several hundred sites across the language and platform packages before anything refused it. A Semgrep rule (`redundant-case-conversion`) named the shape but ran only on demand, as a WARNING — an advisory nobody has to read is the same as no rule.

**What it cannot see.** `to_snake_case(node.name)` — a PolyString passed straight to a case function — is the same waste without the `str()`, but whether `.name` is a PolyString or an `Enum` member's plain-`str` `.name` is a type fact, and no type checker runs in this repo. That shape is left to review.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\polystring-case-roundtrip-gate.ps1` | Scan every publishable `.py` file in every framework repo |
| **One repo** | `.\test\polystring-case-roundtrip-gate.ps1 -Repo datrix-codegen-aws` | Scan only the named repo(s) |
| **Pending changes only** | `.\test\polystring-case-roundtrip-gate.ps1 -PendingOnly` | Scan only what a `git add -A` would stage (the commit-path form) |
| **Self-test only** | `.\test\polystring-case-roundtrip-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Debug** | `.\test\polystring-case-roundtrip-gate.ps1 -Dbg` | DEBUG logging; print the python invocation before running |

**Parameters:** `-Repo <name[,name...]>`, `-SelfTest`, `-PendingOnly`, `-Dbg`

**Self-test runs automatically, every invocation.** A planted module carrying one instance of every kind and every callee spelling (canonical, `as` alias, `text.to_snake_case` attribute, function-level import) plus a nested function must yield exactly the expected `(line, kind, function)` triples — so the scope barrier is proven, not assumed; a clean module (reading `.snake`, casing a value that was never `str()`-wrapped, `str()` applied *after* the case call, `PolyString.compose`) must yield zero; and an unparseable module must refuse (exit 2) rather than report clean. A self-test failure aborts before any real result is trusted (exit 1).

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over the pending files of every dirty repo before it generates a message or stages anything, and refuses the whole run on a hit (`-SkipPolyStringCaseCheck` overrides, loudly). This gate is the whole-workspace counterpart: it also covers repos the current run is not committing.

**Exit codes:** 0 = zero round trips in every scanned file, 1 = at least one round trip or the self-test failed, 2 = usage error (unknown `-Repo` name, no framework repo found) or a scanned file that could not be parsed.

---

### `test\design-task-reference-gate.ps1`

**The repo's proof that no committed artifact cites a design document or a task file.** `design/` and `.tasks/` are gitignored and are developed on more than one machine, so their numbering collides: two different `044-*` documents can exist, and after a clone neither is present. A reference to one from anything committed is a dangling pointer — it resolves to nothing, or to a different artifact elsewhere. The gate scans the committed trees for the SHAPE of such a reference and fails on any hit. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

**Roots are derived from disk, never hand-authored.** Every `datrix*` directory contributes its `src`, `tests`, `docs` and `scripts` subtrees (the `datrix` showcase repo contributes `scripts`, `docs`, `examples` instead — it has no `src`), so a new package is scanned the day it appears. The gitignored orchestration trees themselves (`.tasks/`, `.bugs/`, `design/`) plus build noise are skipped: design and task files referencing **each other** is allowed and expected.

**Four reference shapes are matched, over all of `.py .ps1 .json .md .j2 .ts .mts .cts .js .mjs .cjs .cs .java .toml .yaml .yml .dtrx`** (spelled here with `N`/`M` placeholders so this page is not itself a hit): a task-file id (`task-NN-MM`, the prose `task NN-MM`, and the three-digit `task-NN-MMM`, case-insensitively), a design path (`design/NNN-slug`), a design number (`design NNN`, `design-NNN`, `design doc NNN` — the word `doc` is optional), and a phase directory (`.tasks/phase-NN`). A **bare** `Phase NN` is deliberately NOT matched: the committed architecture docs use it as product vocabulary for delivery waves, self-contained text rather than a pointer into a gitignored tree.

**The terminal state is zero.** There is no baseline and no count to ratchet down. `ALLOWLIST` in `scripts/library/test/design_task_references.py` is the only escape hatch and is for files that document the ID *format* itself (the task-ID parser, the review runner's usage examples, this gate's own patterns) — never for a file that merely happens to carry a reference.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\design-task-reference-gate.ps1` | Scan every committed tree in the workspace |
| **One tree** | `.\test\design-task-reference-gate.ps1 -Roots D:/datrix/datrix/scripts/config` | Scan only the named directories |
| **Several trees** | `.\test\design-task-reference-gate.ps1 -Roots D:/datrix/datrix-common/src,D:/datrix/datrix-common/docs` | Comma-separated roots |
| **Self-test only** | `.\test\design-task-reference-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |

**Parameters:** `-Roots <dir[,dir...]>` (default: every committed tree), `-SelfTest`

**Self-test runs automatically, every invocation.** One line per reference shape is planted in a temp directory and every one must be flagged; a clean file must produce zero; and a bare `### Phase 01 capabilities` heading must NOT be flagged. A scan that silently matches nothing returns a confident "clean" that will be believed — which is exactly how two holes in this gate let whole phases' worth of references through: matching only the hyphenated `task-NN-MM` form missed the prose `task NN-MM` an agent actually writes, and requiring the literal word `doc` missed the bare `design NNN` entirely.

**Exit codes:** 0 = no references found (or a successful `-SelfTest`), 1 = at least one reference found or the self-test failed.

---

### `test\import-name-existence-gate.ps1`

**The repo's proof that no `from <datrix module> import <name>` names something that does not exist.** A half-completed rename leaves a module importing one name and defining another. At runtime that announces itself — the first test to touch the module raises `ImportError`. Inside `if TYPE_CHECKING:` it announces nothing, ever: the block never executes, every package still imports cleanly, and this repo runs no standalone type-checker by policy (`CLAUDE.md`, "Running Python"), so every annotation written against the dead name is silently meaningless. Three half-completed renames landed in one phase and all three were found by accident. This gate looks for them on purpose. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

**Resolution, three routes, in order.** (1) A module-level binding in the target module's own source, by AST — `def`/`class`/assignment/import alias, including inside its own top-level `if`/`try`/`with` and its own `TYPE_CHECKING` block, so this gate is never stricter than a type checker. (2) A **submodule** of the target — `from datrix_cli.commands import lsp` imports a module, not an attribute; skipping this step is what made a first attempt report 102 findings of which 100 were not defects. (3) A runtime attribute, by importing the module — reached only for names routes 1 and 2 miss, covering `from x import *` re-exports and module-level `__getattr__`. An import that raises is reported with its exception text, never treated as resolved.

**Roots are derived from disk.** Every `datrix*` package repo contributes its `src/` and `tests/` trees; the `datrix` showcase repo contributes `scripts/`. Relative imports are resolved, and a package's `__init__.py` is resolved as its own package (one dot there means THIS package, not the parent). Relative imports in `tests/`/`scripts/` trees, which have no unambiguous dotted name, are counted and reported rather than silently dropped.

**Deliberate negative-existence assertions are excluded and counted.** An import inside `pytest.raises(ImportError)` / `pytest.raises(ModuleNotFoundError)` or a `try/except ImportError`, written to prove a deleted symbol is really gone, is not a defect. A `raises` naming some other exception tolerates nothing, and the import inside it is still checked.

**The terminal state is zero.** No baseline, no ratchet, no allowlist. A name resolving by none of the three routes is a defect in the importing module — fix the import or the definition.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\import-name-existence-gate.ps1` | Scan every datrix package tree |
| **One tree** | `.\test\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src` | Scan only the named directories |
| **Several trees** | `.\test\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src,D:/datrix/datrix-codegen-common/src` | Comma-separated roots |
| **Self-test only** | `.\test\import-name-existence-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |

**Parameters:** `-Roots <dir[,dir...]>` (default: every datrix package tree), `-SelfTest`

**Self-test runs automatically, every invocation.** A synthetic package is built in a temp directory carrying four dead names that MUST be reported (two under `if TYPE_CHECKING:`, one behind a package-relative import, one inside a non-import `raises`) and five shapes that must NOT be: a submodule import, a name re-exported only inside the target module's own `TYPE_CHECKING` block, a single-dot import in a package `__init__.py`, the same statement in a sibling module, and an import written to fail under `pytest.raises(ImportError)`. In-scope and TYPE_CHECKING counts are asserted too, so a walker that stops seeing a shape fails here rather than reporting a confident clean.

**Exit codes:** 0 = every import name resolves (or a successful `-SelfTest`), 1 = at least one dead name found or the self-test failed, 2 = no datrix `src/` tree found to resolve against.

---

### `test\affected-set.ps1`

Derives the reverse-dependency closure of every `datrix-*` package from actual imports (never a hand-maintained table). Discovers packages from disk by `pyproject.toml` presence, builds the import graph from each package's `src/`, `tests/`, and root-level `conftest.py` (the file class that hides test-time-only edges like datrix-common's consumption of datrix-language/datrix-cli) unioned with declared `pyproject.toml` dependencies, and computes each requested package's transitive reverse closure -- the packages whose code may consume a change. It answers "which packages might this change reach"; an agent then confirms each by surface and runs the changed behaviour's feature tags there (`test.ps1 <pkgs> -Tag <tag>`), never their whole suites. `affected-gate.ps1` (human-only) consumes this module directly. This is a repo-level validation **script** (per the datrix showcase boundary -- no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **One package's closure** | `.\test\affected-set.ps1 -Projects datrix-language` | Print datrix-language's reverse closure |
| **Several packages** | `.\test\affected-set.ps1 -Projects datrix-language,datrix-cli` | Print each package's own closure |
| **Every package** | `.\test\affected-set.ps1 -All` | Print every discovered package's closure |
| **Custom output path** | `.\test\affected-set.ps1 -All -Output D:\datrix\.tmp\test\my-closure.json` | Override the JSON output path |
| **Self-test only** | `.\test\affected-set.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite; skip the real derivation |
| **Debug** | `.\test\affected-set.ps1 -Projects datrix-common -Dbg` | Debug logging |

**Parameters:** `-Projects <comma-separated>` OR `-All`, `-Output <path>`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements, per the datrix showcase boundary) covers `discover_packages`, the root-conftest-only import edge (must be detected when the conftest scan is enabled, and adversarially proven ABSENT when it is disabled), BOM-prefixed source files, a cyclic/self-referential edge (must terminate, not hang), the non-vacuity guard (`check_closure_not_smaller_than_declared`), and unreadable/corrupt `pyproject.toml` input. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real derivation, exit 1); `-SelfTest` runs it in isolation and skips the real derivation.

**Assertions:**
- Package discovery is by `pyproject.toml` presence under a `datrix-*`-prefixed directory name -- never a hardcoded list or count.
- An import edge from a package's root-level `conftest.py` (outside both `src/` and `tests/`) is detected exactly as an import from `src/` or `tests/` would be.
- The full (import+declared) reverse closure of every package is never a strict subset of its declared-pyproject-deps-only closure; a violation fails the run loud (exit 1), never silently.

**Exit codes:** 0 = derivation completed (or a successful `-SelfTest` run), 1 = the non-vacuity self-check failed (or `-SelfTest` reports a failing check), 2 = usage error or unreadable input (corrupt/unreadable `pyproject.toml` or source file, unknown `-Projects` name, no `datrix-*` packages found).

---

### `test\affected-gate.ps1`

**A human-only tool, enforced.** It runs whole package suites, and no agent — subagent or main session, in any skill, gate, or phase — ever runs a whole suite: `guard-full-suite-runs.py` refuses every invocation from an agent tool call except `-SelfTest` (which launches no suite), with no override. Agents verify a change with `test.ps1 -Specific` / `-Tag` (see `test\test.ps1` above). Jon runs this in his own terminal, where no hook applies.

Runs the affected set of Datrix package suites concurrently and returns one GREEN/RED verdict. The affected set is the changed packages (`-Projects`) plus the consumers the change reaches (`-Consumers`), established per "Which packages a change reaches" in `.claude/skills/_shared/verification-strategy.md` — importing a changed package does not make a package affected. Unless `-All`, one of `-Consumers` / `-NoConsumers` is required; without either the gate stops with a usage error listing the packages that import the changed ones. Every such importer not named is printed as `Excluded (…): …` and recorded as `excluded` in `affected-gate.json` and the completion row. The gate schedules `test.ps1 <pkg>` child processes longest-first under a `PYTEST_XDIST_AUTO_NUM_WORKERS` budget so concurrently running children never oversubscribe the machine, and aggregates the final verdict by reusing `gate-verdict.ps1`'s own per-project evaluation -- never reimplementing `index.json` parsing. This is a repo-level validation **script** (per the datrix showcase boundary -- no pytest suite lives in datrix). It only SCHEDULES existing runners; it never duplicates `test.ps1`'s or `gate-verdict.ps1`'s own logic.

| Mode | Command | Description |
|------|---------|-------------|
| **Changed + reached consumers** | `.\test\affected-gate.ps1 -Projects datrix-codegen-common -Consumers datrix-codegen-python,datrix-cli` | Run the changed package and the consumers the change reaches; every other importer is excluded |
| **No consumers** | `.\test\affected-gate.ps1 -Projects datrix-codegen-java -NoConsumers` | Run only the changed package(s); every importer is excluded |
| **Everything** | `.\test\affected-gate.ps1 -All` | Run every discovered package concurrently |
| **Cap concurrency** | `.\test\affected-gate.ps1 -Projects datrix-cli -NoConsumers -MaxConcurrent 2` | At most 2 children at once; each keeps its proportional worker allotment |
| **Uniform workers** | `.\test\affected-gate.ps1 -Projects datrix-cli -NoConsumers -WorkersPerChild 4` | Every child gets 4 workers instead of its proportional share |
| **With mypy** | `.\test\affected-gate.ps1 -Projects datrix-common -Consumers datrix-cli -Mypy` | Also type-check the changed packages, same budget. **Human-only** -- `guard-forbidden-commands.py` refuses this switch from an agent tool call |
| **Force past an in-progress run** | `.\test\affected-gate.ps1 -Projects datrix-cli -NoConsumers -Force` | Start even if a requested package's newest run looks in-progress |
| **No carry** | `.\test\affected-gate.ps1 -Projects datrix-common -Consumers datrix-cli -NoCarry` | Run every named package even when its recorded green run still matches (flakiness hunts, a scheduled full sweep) |
| **Self-test only** | `.\test\affected-gate.ps1 -SelfTest` | Run only the scheduler's own edge-case self-test suite |
| **Debug** | `.\test\affected-gate.ps1 -Projects datrix-cli -NoConsumers -Dbg` | Debug logging |

**Parameters:** `-Projects <comma-separated>` with `-Consumers <comma-separated>` or `-NoConsumers`, OR `-All`, `-MaxConcurrent <n>` (optional cap on concurrently running children, >= 1; default none), `-WorkersPerChild <n>` (uniform override, 1..logical cores; default the proportional allotment below), `-Mypy` (runs `-MaxConcurrent` mypy children at once, or one per logical core without it), `-Force`, `-NoCarry`, `-Output <path>`, `-SelfTest`, `-Dbg`

**Worker allotment (proportional share).** Only the packages that did not carry are scheduled, and only they share the cores. Each one's CPU demand `c` is its newest **full** run's `test_time_seconds` (per-test time summed across xdist workers, roughly workers × wall — not `duration_seconds`); a run whose `selection.kind` is not `full`, a run recording no `selection` (older runs of both kinds carry none, so one cannot be told from a targeted subset), an unreadable run, and a full run that recorded no value are passed over, and with no usable full run the package's `src/` line count stands in. With `n` logical cores and `L = Σc / n` computed once over the scheduled set, a package gets `w = clamp(ceil(c / L), 2, n)` workers as its `PYTEST_XDIST_AUTO_NUM_WORKERS` (on a machine with fewer than 2 cores, the core count). Children start longest-first — by the newest full run's `duration_seconds`, same run selection and fallback — and the next one starts only while the running children's allotments plus its own fit in `n` (and, under `-MaxConcurrent`, fewer than the cap are running); `simulate_schedule` applies the identical rule. `-MaxConcurrent` is a cap, never a divisor of the cores: `-MaxConcurrent 1` runs the packages one at a time, each with its own allotment. `-WorkersPerChild` replaces the allotment with one uniform count; a value above the core count is a usage error, since one child alone would exceed the budget.

**Carry (default on).** Before any child is launched, each affected package's **newest full run** (`selection.kind == "full"`; targeted runs are skipped over, never consulted) is checked. It is **CARRIED** — no `test.ps1` child is launched, and that run stands in — only when it is schema 2, `result` `PASSED` with zero failed/errors, not `INCOMPLETE`, younger than the 24 h carry window (a named constant in `suite_inputs.py`, not a flag), and its recorded `inputs.fingerprint` equals the fingerprint recomputed now over the same components (cone trees, installed set, interpreter, and the foreign / ignored-in-cone / executable paths that run itself observed). Every unknown **runs** the package instead: no full run, RED, INCOMPLETE, over-age or future-dated, no `selection`/`inputs` (a run that predates stamps), a malformed stamp or a different algorithm, a newer run whose `index.json` cannot be read, or any error while computing a digest. The gate prints one line per package — `datrix-x: CARRIED run=<dir> fingerprint=<hex>` or `datrix-x: running -- <reason>`, e.g. `datrix-common tree changed; foreign tree datrix/examples changed`. The workspace's cones are derived once per invocation, and only when some package reaches the fingerprint comparison.

**`affected-gate.json` rows** are `gate-verdict.ps1` rows (including its `CARRIED` verdict, `carried` and `fingerprint` fields — see that section) plus two carry fields: `carry_reason` (why the package ran instead of carrying; null on a CARRIED row; `carry disabled (-NoCarry)` under `-NoCarry`) and `diff_components` (every fingerprint component that no longer matched, e.g. `["datrix-common tree changed"]`; empty when the refusal came before any component was compared). A CARRIED row: `verdict: "CARRIED"`, `carried: true`, `run_dir` (the carried run), `age_minutes`, `fingerprint`, the run's own `counts`. CARRIED counts as green for `OVERALL`.

**One install check per gate.** After its usage checks and before the carry decision, every non-`-SelfTest` invocation runs `Ensure-DatrixVenv` then `Ensure-DatrixPackagesInstalled -SkipIfInstalled` once, dot-sourcing the same `scripts/common/venv.ps1` `test.ps1` uses (so the carry fingerprint's installed-distributions component is computed over the venv exactly as the children will find it — the check runs even when every package then carries). Every child is launched with `DATRIX_PACKAGES_ENSURED=1` and skips its own check. With `DATRIX_VENV_VERBOSE=1` set, the check's `All packages are importable and up-to-date, skipping reinstall (SkipIfInstalled mode)` line appears exactly once, before the first child, and each child prints `Package install check skipped: the caller already ran it (DATRIX_PACKAGES_ENSURED=1)` instead (these are console lines relayed from the child's stdout; a child's `full.log` is written by the Python runner and never carries `test.ps1`'s own output). A failing check launches no child: the gate exits 1 with `overall` `INSTALL_CHECK_FAILED`.

**Completion row.** Every non-`-SelfTest` invocation appends exactly one row to `D:\datrix\.tmp\full-suite-audit.jsonl` — the same log `guard-full-suite-runs.py` appends its allow/block decision rows to — after aggregation (or on a usage error, a failed install check, a failed self-test, or an interrupt): `{"ts": <int epoch seconds>, "source": "affected-gate", "changed": [...], "consumers": [...], "excluded": [...], "ran": [...], "carried": [...], "wall_seconds": {"<pkg>": <s>}, "overall": "GREEN"|"RED"|"USAGE_ERROR"|"INSTALL_CHECK_FAILED"|"SELF_TEST_FAILED"|"ABORTED"}`. `ts` has the guard rows' type (integer epoch seconds); `source` tells the two writers apart. The gate prints `Completion row: overall=… ran=[…] carried=[…] excluded=[…] -> <path>` as its last line. `affected-gate.json` carries the same `excluded` list at its top level.

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures, real git repositories, and `assert` statements, per the datrix showcase boundary) covers the scheduler: on a fixed table of measured per-package CPU seconds, the simulated schedule never has more allotted workers active than cores at any instant (for 1, 2, 8, 12 and 32 cores, and it fills all 12 on the table's own machine), the allotment matches concrete expected worker counts (including the clamps and one `L` for every package), the simulated makespan lies between the CPU lower bound `Σc / n` and 1.25 × it, and no worse than the retired fixed-slot policy (4 slots x floor(n/4) workers) on the same table, `-WorkersPerChild` is a uniform override refused outside `1..cores`, an allotment above the core count is refused, `-MaxConcurrent 1` runs sequentially and `-MaxConcurrent 2`/`3` bound the number of running children; longest-first ordering and the CPU demand read the newest full run (never a newer targeted, selection-less or unreadable run) with the LOC fallback; then same-package double-request rejection, consumer selection (a named consumer runs, every other importer is excluded, a consumer outside the import closure is honoured, and neither/both of `-Consumers`/`-NoConsumers` or a changed package named as a consumer is a usage error), a child that dies without producing an `index.json` forcing RED (never a stale GREEN), and carry: every refusal above forces a run; identical inputs carry and launch no child; `-NoCarry` runs a carriable package; newer targeted runs (RED or GREEN) never hide an older carriable full run; a one-byte change in each of the seven fingerprint components (a cone tree file, an ignored-in-cone file, a foreign tree, an observed executable, the installed set, the interpreter string, the algorithm) runs the package with exactly that component in `diff_components`; `affected-gate.json` rows for a carried and a ran package; `gate_verdict` rejecting a carry claim the run does not support; the completion row sharing the guard's `ts` type (read from the guard's own source) while being told apart by `source`; and install-once: every child's environment carries `DATRIX_PACKAGES_ENSURED=1`, `test.ps1`'s one install call sits inside the guard reading that flag (proven on the real `test.ps1`, with the guard finder shown to reject an unguarded call), `test_project.py` reads the same name, the install check is called exactly once — from `_run`, after the in-progress refusal and before carry and scheduling, never on `-SelfTest` — and real PowerShell processes over planted `venv.ps1` modules show a passing check calls `-SkipIfInstalled` while a failing install, a throwing venv activation and a missing module each raise. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before real scheduling, exit 1); `-SelfTest` runs it in isolation and writes no completion row.

**Assertions:**
- At no point do concurrently-running children's declared `PYTEST_XDIST_AUTO_NUM_WORKERS` values sum above the logical core count.
- The scheduler never launches two live children for the same package.
- A package whose newest run directory has no/INCOMPLETE `index.json` (a run in progress) is refused unless `-Force`.
- A child that exits without naming a run directory of its own is reported RED with reason `CHILD_PRODUCED_NO_RUN`, never silently defaulting to whatever stale prior result exists.
- Every other package is judged on **the run directory its child attributed to itself** — the absolute `index.json` path in the `Details:` line `test.ps1` prints under its own `[PASSED]`/`[FAILED]` block, relayed through the child's stdout and pinned through `gate_verdict.evaluate_projects(pinned_runs=...)`. The newest run directory under `.test_results` is never consulted, neither at child exit nor at verdict time: `test.ps1` holds the workspace package lock only through its install phase, so a targeted `-Specific` run from another session can land a newer directory before **or** after the child exits, and a newest-run lookup then replaces a RED whole-suite result with an unrelated GREEN subset — a 59-test targeted run once stood in for a 5,950-test RED suite this way (the gate printed `OVERALL: GREEN` with exit 0), and later a 7-test targeted run landed mid-suite and stood in for a child that had exited 1 with two failures. A pinned run with no results file is RED with reason `PINNED_RUN_HAS_NO_RESULTS`; it never falls through to the newest run.
- A CARRIED package's `test.ps1` child is never launched (the decision is made before scheduling, not after), and its row is pinned to exactly the full run whose fingerprint matched.

**Exit codes:** 0 = overall GREEN (or a successful `-SelfTest` run), 1 = overall RED, a failed install check, or `-SelfTest` reporting a failing check, 2 = usage error (bad `-MaxConcurrent`/`-WorkersPerChild`, unknown/duplicate package name, both `-Projects` and `-All` given, neither or both of `-Consumers`/`-NoConsumers` given without `-All`, either given with `-All`, a changed package named in `-Consumers`).

---
