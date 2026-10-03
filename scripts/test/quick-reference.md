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
| **Feature tag** | `.\test\test.ps1 datrix-codegen-python datrix-codegen-typescript -Tag gateway` | Only the tests carrying the tag, in every named package — how a change's behaviour is verified across the packages it reaches |
| **Several tags** | `.\test\test.ps1 datrix-common -Tag config-resolution,secrets` | A test runs when it carries ANY named tag |
| **List tags** | `.\test\test.ps1 datrix-codegen-python -ListTags` | Every tag with its test count, and the untagged tests; runs nothing; exit 1 while any test is untagged or a module fails to collect |
| **List tags (scoped)** | `.\test\test.ps1 datrix-common -ListTags -Specific "tests/unit/config"` | Listing over the named files/directories only |
| **Verbose output** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -VerboseOutput` | Verbose pytest output (Jon; agents never pass it) |
| **No log save** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -NoSave` | Don't save output to log files (Jon; agents never pass it) |
| **Debug logging** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -Dbg` | Enable DEBUG level |
| **Coverage** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -Coverage` | Generate coverage report |

Whole-suite modes (Jon only): a bare package (`.\test\test.ps1` + package names), a folder path, `-All`, `-Rerun` (re-run projects whose latest log reports failures), and the tier switches `-Unit` / `-Integration` / `-E2E` / `-Fast` (excludes slow) / `-Slow`.

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rerun`, `-Coverage`, `-VerboseOutput`, `-NoSave`, `-NoAutoInstall`, `-Unit`, `-Integration`, `-E2E`, `-Fast`, `-Slow` (mutually exclusive), `-Specific <path[,path...]>` (comma-separated files/node-IDs run in one pytest session), `-Keyword <expr>`, `-Tag <tag[,tag...]>` (feature tags; a test runs when it carries any of them), `-ListTags` (list tags, run nothing; with `-Specific`, scoped), `-Dbg`

**Feature tags.** Every test carries one or more feature tags (pytest `tag` marker; Node `#tag` token in a test or `describe()` name). They are declared by `datrix_common.testing.feature_tags`, a `pytest11` plugin every session in the venv loads; `test.ps1` runs every session with `--datrix-require-tags`, so an untagged test fails at setup (an untagged Node test fails the run). `-Tag` fails a package in which no test carries a named tag (a misspelling never shrinks a run silently), refuses a selection that keeps every test of a package's whole test tree (the full suite in disguise), and cannot be combined with `-Keyword` on a Node suite. Both refusals are decided **before any test phase starts**: a pytest package's `-Tag` run first does one collection-only pass in a single process over the run's own targets, and a refused selection exits 4 with the plugin's message and no run directory — never discovered inside every xdist worker after each has collected the whole tree. A tier name (`unit`, `slow`, `serial`, …) is never a tag. Rules and vocabulary: `datrix-common/docs/contributing/test-guidelines/feature-tags.md`. A run's `index.json` records `selection.tags`.

**Log output:** Unless `-NoSave` is used, `test.ps1` creates one timestamped log folder for each project it runs under that project's `.test_results` directory. AI agents do not need to capture full console output; read the final console lines to find the saved log folder, then inspect the files in that folder.

**Selection and suite-input stamp (`index.json` `schema_version: 2`):** every saved run records `selection` — `{"kind": "full"}` for a bare `test.ps1 <package>`, otherwise `{"kind": "targeted", "specific", "keyword", "tier", "marker", "tags"}` for `-Specific`/`-Keyword`/`-Tag`/any tier switch. Only a full run whose every phase completed records `inputs` (the suite-input fingerprint over the package's cone, installed set, interpreter, and observed foreign paths and executables); a targeted run never has an `inputs` key, so it can never stand in for a full one. A full run loads `test.runner_plugin` (`-p`) in every phase and also leaves `observed-*.json` / `deselected-*.json` / `timings-*.json` / `workers-controller.json` records and a merged `timings.json`; any other saved run loads it in its parallel phase only and is never stamped. **The serial phase runs only when needed:** when every parallel worker's `deselected-<worker>.json` says it deselected 0 items (so no collected test is `serial`), the serial phase is skipped — `full.log` says `Phase 2: serial tests SKIPPED -- …` and `index.json` records `"phases": {"Serial": "skipped (0 serial items)"}` with no `junit-serial.xml`. It runs on any missing evidence (`-NoSave`, a worker the controller listed with no record, a parallel phase that did not complete), under a marker or keyword filter (`-Unit`/`-Fast`/`-Keyword`/…; `-Specific` is not a filter), and when workers deselected items. Workers disagreeing on the count, or an unreadable record, is a runner error: the serial phase runs and the run is FAILED with the reason in `index.json` `runner_errors`. When a full run cannot be stamped (a phase did not complete, a session's records are missing, or a cone tree changed while it ran), `full.log` says why and `index.json` has `selection` but no `inputs`. Field reference: [README.md](README.md#package-run-indexjson-schema-version-2).

**Never run two `test.ps1` invocations at once — batch the projects into ONE call instead.** `-Projects` is variadic and iterates sequentially, so `test.ps1 a b c` is the supported way to cover several packages. Before running anything, `test.ps1` calls `Ensure-DatrixPackagesInstalled`, which takes a **workspace-wide exclusive package lock** (`scripts/common/venv.ps1:1547`, 120s acquisition timeout) shared with `generate.ps1` — it guards the install/repair phase against concurrent writers of the one shared venv. A second concurrent invocation therefore blocks for up to two minutes and then dies with `Could not acquire package lock - another process may be installing packages`, having run **no** tests. The one sanctioned concurrency is `affected-gate.ps1` (Jon's tool — agents never run it), and it does not contend here: it runs that install check **once**, before any child, and launches every `test.ps1` child with `DATRIX_PACKAGES_ENSURED=1`, which makes `test.ps1` skip its own check (with `DATRIX_VENV_VERBOSE=1` it prints `Package install check skipped: the caller already ran it` instead). `test.ps1` restores its caller's value of that variable on exit, so a run started in your own shell never leaves it set for the next direct run — a direct `test.ps1` always performs its own check.

Two consequences worth knowing before you parallelize anything:

- **Concurrency here buys nothing and costs a lot.** The runs serialize on the lock whatever you do, and the loser fails outright rather than queueing. A sweep launched as N parallel invocations finishes later than the same sweep as one invocation, and reports failures that are pure contention.
- **Contention also breaks `npm`-dependent suites in a way that looks like a real defect.** Integration tests that shell out to `npm install` (`datrix-codegen-typescript`) run under a fixed subprocess timeout and contend for CPU and npm's own cache locks. Oversubscribe the machine and they hit that timeout and report as **errors on setup**, indistinguishable at a glance from a genuine failure. `datrix-codegen-typescript` bounds this deliberately: a `pytest_collection_modifyitems` hook in its `tests/conftest.py` pools every `@pytest.mark.npm_tsc` item into one of `DATRIX_TS_NPM_TSC_POOLS` (default 4) `xdist_group`s keyed by the test's file, and the runner's parallel phase distributes with `--dist loadgroup`, so at most that many npm/tsc chains run at once per session (the runner iterates packages sequentially, so that is the bound in practice). Set `DATRIX_TS_NPM_TSC_POOLS=1` to serialize them completely on a busy machine. Other packages do not bound this at all. If a run shows `npm install ... timed out` or a package-lock error, re-run the affected files on a quiet machine before believing the result — and treat the counts, not the exit code, as the signal.

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

**Parameters:** `-ExamplePath` (positional 0), `-OutputPath` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (python\|typescript, **mandatory**), `-Platform`/`-P` (output-path runtime segment, default: docker-compose; provider segment comes from each project's `config/system.dcfg`), `-Hosting`/`-H`, `-TestSet` (default: all), `-Rerun`, `-VerboseOutput`, `-SkipVenv`, `-Skip1`, `-Skip2`, `-Skip3`, `-Skip4`, `-Skip5` (deprecated), `-FreshBuild`, `-Dbg`/`-DebugLogging`, `-LlmSummary`, `-LlmLimit` (default: 12), `-LocalMachines` (default: the list in `library/shared/local_llm.py`), `-LlmModel` (default: any model already in memory), `-LlmTimeout` (default: 180), `-LlmNumPredict` (default: 4096), `-LlmTemperature` (default: 0.1)

**Note:** Deploy tests (Step 4) use Docker cache by default for faster builds and better network resilience. Use `-FreshBuild` to force `--no-cache` for maximum validation confidence. `-Skip5` is accepted but deprecated (Step 5 merged into Step 4).

**LLM advisory summary:** Pass `-LlmSummary` to print a post-run advisory summary generated by a local model against the aggregate result indexes. The model is whichever server `library/shared/local_llm.py` finds first on the local machines (Ollama, vLLM or llama-server), failing over to the next. All `-Llm*` and `-LocalMachines` parameters only take effect when `-LlmSummary` is set.

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
| **One language only** | `.\test\status-deploy-tests.ps1 -L typescript` |
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

**Kept small without losing anything (bundle schema 2).** Clusters sharing one `(kind, pattern)` form a **family** (`families[]`, and `family_id` on each cluster): only the family's first cluster embeds `traceback_tail`, the others carry `traceback_tail_in_cluster: <id>` and keep their own `log_file`. An `error_message` over 20 lines or 2000 characters is cut, marked `error_message_truncated: true`, and ends `[message cut: ...]` — the whole message is in that entry's `log_file`. On an 18-failure datrix-common run this took the bundle from 136 KB to 74 KB (five "drifted" clusters became one family; one 36 KB baseline diff was cut).

**Advisory hints.** The first `-LlmHintLimit` families (default 5, errors first) get a `hint` from a local model server found by `library/shared/local_llm.py`: the model is given the message, the traceback and the source around the traceback's in-workspace frames, and answers with a probable defect site, cause and first check. `hint.source` names the server and model, or says `unavailable` (no server answered) or `skipped` (past the limit / `-NoLlmHints`). A hint is a hypothesis to verify in the code, never a root cause. Adds seconds, not minutes (9 s for 5 hints on the run above).

| Mode | Command | Description |
|------|---------|-------------|
| **Run directory** | `.\test\collect-failure-data.ps1 "D:\datrix\datrix-common\.test_results\test-results-YYYYMMDD-HHMMSS"` | Parse an explicit run dir (or its `index.json` path) |
| **Latest run of a package** | `.\test\collect-failure-data.ps1 -Project datrix-codegen-aws` | Auto-locate the newest `test-results-*` run |
| **Longer tracebacks** | `.\test\collect-failure-data.ps1 -Project datrix-common -MaxLogLines 120` | Embed more tail lines per representative (default 60) |
| **No hints** | `.\test\collect-failure-data.ps1 -Project datrix-common -NoLlmHints` | Families and message caps only; no local-model call |
| **Self-test only** | `.\test\collect-failure-data.ps1 -SelfTest` | Parse one fixture index per supported writer schema and check the re-run command emitted for each suite kind; skip the real run analysis |

**Parameters:** positional run-dir/`index.json` path OR `-Project <name>` (exactly one), `-MaxLogLines <n>`, `-NoLlmHints`, `-LlmHintLimit <n>` (default 5; 0 = none), `-LocalMachines <hosts>` (default: the list in `library/shared/local_llm.py`), `-LlmModel <models>` (default: any model in memory), `-LlmTimeout <seconds>` (default 120), `-SelfTest`, `-Dbg`

**Schema-shape self-test.** The three writers do not spell their cluster keys identically —
`structured_log_writer` and `deploy_test_log_writer` use `failure_ids`/`representative_failure_id`
inside `failure_clusters`, while `generated_test_log_writer` builds both of its cluster lists from
one `ErrorCluster` shape and therefore spells them `error_ids`/`representative_error_id` there too.
Test ids differ the same way: a pytest id carries a lowercase dotted module prefix that maps to a
source path, a non-python id (`Class::method`) carries none, so the representative's `file` is
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
2. **Extension-map completeness** — for every installed `datrix.extensions` pack, every
   registered language's `*_EXTENSION_MAPS` dict (`PYTHON_EXTENSION_MAPS`, `TS_EXTENSION_MAPS`,
   ...) **and SQL's** (`SQL_EXTENSION_MAPS`) must carry a
   key for that pack's name — an entry present but empty is correct for a pack contributing zero
   scalars. This leg is unconditional: `-Languages` never narrows it. SQL's map is a shared SQL
   fact in the codegen kernel (`datrix_codegen_kernel.sql_facts.type_mappings`), read directly,
   not via `datrix.languages`.

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

### `test\generation-determinism-gate.ps1`

Generation-pipeline determinism gate for one registered language: the SAME source tree, generated N times in a row via the documented single-project `generate.ps1` path, must never produce two different outcomes (same failure mode every time, or a byte-identical success manifest every time). Each run is its own `generate.ps1` process (fresh `python.exe`, fresh `PYTHONHASHSEED`), so this also exercises hash-seed-driven set-iteration-order bugs a single long-lived process would never surface. Targets `examples/02-features/03-infrastructure-blocks/nosql/system.dtrx` — the example a corpus generation sweep once found producing three different outcomes (a struct-test planning failure, then two different compile failures) from the identical, unchanged-tree invocation. No before/after comparison of two code states can catch this class of bug, because it never runs the same code twice; this gate runs the SAME code N times and compares outcomes to each other. `-Language` is required — the gate never assumes which languages are installed. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (5 runs)** | `.\test\generation-determinism-gate.ps1 -Language python` | Generate 5 times for one language, assert identical outcomes |
| **Custom run count** | `.\test\generation-determinism-gate.ps1 -Language typescript -Runs 3` | Fewer/more repeated generations (must be >= 2) |
| **Custom output root** | `.\test\generation-determinism-gate.ps1 -Language python -OutputRoot D:\datrix\.test-output\generation-determinism-gate\python` | Override run1..runN location |
| **Debug** | `.\test\generation-determinism-gate.ps1 -Language python -Dbg` | Forward `-Dbg` to generate.ps1 |

**Parameters:** `-Language` (required; a registered `datrix.languages` name), `-OutputRoot` (default: `d:/datrix/.test-output/generation-determinism-gate/<Language>`), `-Runs` (default: 5, must be >= 2), `-Dbg`/`-DebugLogging`

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

### `test\check-cross-package-fixture-reads.ps1`

**D14 gate: no package's tests resolve a path inside another package's `tests/` directory.** AST-scans every `.py` file under every discovered `datrix*` package's `tests/` tree and statically evaluates the pathlib expressions test fixtures use to locate `.dtrx`/`.dcfg`/`.json` files (`Path(__file__)`, `.resolve()`, `.parent`/`.parents[N]`, `/` joins against literals or previously-resolved names, including `from tests.<module> import NAME` — always the same package's own `tests/` namespace). Reports two things: (a) a resolved directory constant that points inside ANOTHER package's own `tests/` tree — the D14 violation itself, regardless of whether the file it names still exists there; (b) a statically-resolved fixture path that does not exist on disk (skipping any path a test explicitly asserts is absent, e.g. `assert not X.exists()`). This is the exact shape that turned datrix-common commit `0badd1c`'s fixture cleanup into a red `datrix-codegen-typescript` suite: `COMMON_FIXTURES_DIR / "system-with-jobs.dtrx"` pointed at a file datrix-common's own tests no longer read. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

**A fixture read by one package lives in that package's own `tests/fixtures/`. A fixture read by several packages lives in `datrix-testing` as shared package data** (`datrix_testing.shared_fixtures`), reached through a function or constant — never a relative path into another package's `tests/` tree.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-cross-package-fixture-reads.ps1` | Scan every package, fail on any cross-package reference or missing fixture |
| **Self-test only** | `.\test\check-cross-package-fixture-reads.ps1 -SelfTest` | Prove the scanner detects both defect shapes (including the exact two-step, cross-module incident chain) and clears the clean case; skip the real scan |
| **Show files** | `.\test\check-cross-package-fixture-reads.ps1 -ShowFiles` | Print each file as it is scanned |
| **Custom base dir** | `.\test\check-cross-package-fixture-reads.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-cross-package-fixture-reads.ps1 -Dbg` | Debug logging |

**Parameters:** `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** It plants a cross-package directory constant and a missing-fixture reference (both must be found) alongside a clean, own-package, existing-file case (must not be found), then separately plants the real incident's exact shape (a two-step `_MONOREPO_ROOT` / `COMMON_FIXTURES_DIR` chain, imported cross-module via `from tests.conftest import ...`, joined against `"system-with-jobs.dtrx"`) and requires both halves caught — so the self-test stays meaningful even after the real incident is fixed and no longer visible in the live workspace.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = a cross-package reference or missing fixture was found, 2 = usage error, no packages discovered, or the self-test failed.

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

**Hard-zero gate: no `datrix-codegen-*` package may de-duplicate a handler name.** AST-scans every `datrix-codegen-*` package's `src/` tree for the retired `while <name> in used: <name> = f"{base}{suffix}"; suffix += 1` shape over a derived REST handler / controller method name. Every handler name is derived ONCE, in the shared API-level derivation (`datrix_codegen_kernel.generation.api_helpers` — `compute_rest_api_handler_names` / `rest_api_handler_names_by_endpoint`), which refuses to hand two endpoints of one `rest_api` a single name: it raises, naming both routes. A package-local de-duplicator does the opposite — it renames one side of the collision (`getOrders` / `getOrders2`) while the browser client, the API test generator and every other language target keep calling that route by the un-numbered name, so the collision is hidden rather than resolved. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

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

**Self-test runs automatically, every invocation.** It plants each retired form (a path-fold de-duplicator, a nested-handler de-duplicator, and a nested-action de-duplicator whose function name says "method" rather than "handler" and is caught by the module path) and requires each to be detected, then plants each legitimate near-miss (serverless shadow avoidance, generated-test-method disambiguation, local-variable allocation) and requires each to be reported clean — so neither a scanner that can only return zero nor one that flags everything is believed. A run that discovers fewer than two `datrix-codegen-*` packages with a `src/` tree, or no Python source in them, fails rather than passing vacuously.

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
- `datrix-codegen-kernel/src/datrix_codegen_kernel/gendsl/executor.py` is excluded (the declared-render path's own internals).
- A package absent from the baseline has an implicit baseline of 0.

**Exit codes:** 0 = every package's count is at or below its frozen baseline (or a successful `-UpdateBaseline` or `-SelfTest`), 1 = a package's count exceeds its frozen baseline (or `-SelfTest`/`--harness-self-test` reports a failing check), 2 = usage error, missing baseline, an attempted baseline increase over an existing baseline, or the automatic self-test step failing on a normal invocation.

---

### `test\check-docs-conformance.ps1`

Docs-conformance Invariant I5 gate: extracts repo-relative path references and Python module references from the curated 38-file architecture-doc set (each package's `docs/architecture.md` and/or `docs/architecture/` tree — `datrix-extensions` has neither and contributes zero) and fails if any reference does not resolve to a real file/directory/module in the tree, unless it is recorded in the committed exceptions baseline at `scripts/config/docs-conformance-exceptions.json` (a "what was removed" migration-history claim, a "must never exist" prohibition claim, or another confirmed-intentional non-existence). This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), following the same scan-and-baseline shape as `check-generated-file-ratchet.ps1`'s I5 ratchet, except the exceptions baseline is hand-edited and reviewed (no `-UpdateBaseline` flag — every entry needs a human-authored reason a script cannot synthesize).

`ARCHITECTURE_DOC_FILES` is a literal, reviewable constant in the script (never a directory glob) — "architecture docs" is a curated concept, and a new architecture doc added later is a deliberate, reviewed one-line addition to that constant. This v1 only checks path-reference candidates that are fully package-qualified (start with a known package name or `D:\datrix\`) and module-reference candidates that are fully import-qualified (start with a known Python import name) — a bare, package-relative shorthand span with no anchor at all is never a candidate (deliberate scope boundary, not a gap).

> **`ARCHITECTURE_DOC_FILES` is the one registry in the repo that does NOT self-update.** Everywhere else the package set is discovered from disk (`Get-DatrixDirectories`, `Get-DatrixPackages`, the metrics reports, `commit-and-push`), so a new package is picked up with no edit. This tuple is deliberately the exception — a curated list, reviewed by a human. Consequence: when a new `datrix-codegen-<lang>` package ships its own `docs/architecture.md`, that entry must be **added to the tuple by hand** (and the doc count in this section bumped), or the new package's architecture doc is silently never scanned by the gate. A package with no architecture doc yet contributes zero entries and is correctly absent — as `datrix-extensions` already is.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-docs-conformance.ps1` | Scan every architecture doc and API/reference doc, fail on unresolved references |
| **Warning mode** | `.\test\check-docs-conformance.ps1 -Warn` | Report unresolved references but exit 0 |
| **Show files** | `.\test\check-docs-conformance.ps1 -ShowFiles` | Print each doc file being scanned |
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

1. **Domain-universe closure.** Before checking declarations, computes the union of every registered language's COMPILED GenDSL IR domain ids (`get_definitions(<lang>)`, read directly — independent of any declaration a plugin later commits) and asserts it equals `datrix_codegen_common.parity.domain_registry.SHARED_CONTEXT_TYPES.keys()` exactly. A domain id some language's compiled IR declares but the registry omits fails naming the declaring language(s); a registry id no registered language's compiled IR declares fails as a dead entry (dead surfaces are deleted, never deprecated in place). Zero tolerance, no exemption file — this check short-circuits the gate (exit 1) before the declaration-presence check runs, since a wrong universe makes that check meaningless.
2. **Per-language declaration presence.** EVERY registered `datrix.languages` plugin must declare every STRUCTURAL domain id (`datrix_codegen_kernel.parity.domain_ids.STRUCTURAL_DOMAIN_IDS`) and nothing outside the full registration universe (`SHARED_CONTEXT_TYPES`). `discovery` and `resilience` keep their GenDSL registration but carry no structural-pattern obligation: no language is required to declare either, and a language that does is not reported out-of-universe. The gate reads only membership (`domain_id in plugin.domain_declarations`) and a declaration's `structural_pattern`. A structural id a language does not declare, or an out-of-universe declaration, is a fail-loud `DECLARATION PRESENCE VIOLATION` naming the language and the id; a domain a language does not realize is accounted for only by that language's own `domain:<id>` gap row (logged as a `TRACKED GAP` line; a row for a declared domain (stale) or for a non-structural id (unknown) fails the gate). Derives its target LANGUAGE set from `importlib.metadata.entry_points(group="datrix.languages")` at runtime — never a hardcoded language literal — so a future `datrix-codegen-<lang>` package is covered automatically with no edit to this gate. This is a presence check, never an agreement check: languages may emit a domain to different globs.

On success, the gate prints, for every STRUCTURAL domain id, each registered language's declared `structural_pattern` (or `no structural pattern`) as `DECLARATION: <lang>.<id> = ...`, then a divergence block listing the languages that declare a structural id with no structural pattern or do not declare it. `discovery`/`resilience` appear nowhere in the report. The report is diagnostic and never itself a failure condition.

**The MariaDB engine boundary needs no special-case code** — it is an engine choice inside the `rdbms`/migration domains, not a withheld domain, so it never shows up as a domain-id-level diff at all (this script compares at `domain_id` grain, coarser than per-engine).

**Built-in non-vacuity self-test, every invocation.** Before any real comparison is trusted, the script runs two self-tests: one feeds the domain-universe closure comparator a synthetic matching registry/compiled-IR pair (must report zero divergence), a synthetic compiled id absent from the registry (must be reported, naming the declaring language), and a synthetic registry id no synthetic language declares (must be reported as a dead entry); the other feeds the declaration-presence comparator a complete synthetic declaration table over the structural ids (must report zero findings), a synthetic language omitting one structural id (must be reported, naming that language and id), a synthetic language declaring an out-of-universe id (must be reported, naming that language and id), and a synthetic language declaring the non-structural id (must be neither reported nor required). Either self-test failing aborts the gate (exit 2) before any real comparison runs. Fails loud (exit 2) if fewer than 2 languages are registered — a cross-language comparison over 0 or 1 language is vacuous.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\supported-domain-parity-gate.ps1` | Check domain-universe closure and every registered language's declaration presence |
| **Debug** | `.\test\supported-domain-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\supported-domain-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = the domain-universe closure holds and every registered language declares every structural domain id, 1 = a domain-universe closure violation was found (checked first) or a declaration-presence violation was found for at least one language, 2 = a non-vacuity self-test failed or fewer than 2 languages are registered.

---

### `test\behaviour-parity-gate.ps1`

**Replaces the retired name-keyed drift report on the language axis.** AST-walks the `src/`
tree of every package implementing each registered target -- the package registering its
entry point plus every `<backend>-core` distribution it requires, derived from the installed
requirements (`datrix_testing.target_distributions`), never a hand list -- and groups functions into **roles** — a *signature
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

**Two buckets that fail by shape, one that fails by skeleton groups:**
- `identical` / `same-behaviour` fail unless every member is a **pre-binding adapter** (a single
  `return` of a call into `datrix_codegen_common`, recognized by AST shape only — no written
  exemption list).
- `divergent` is judged **without a reference language**: the role's member packages are
  partitioned into **skeleton groups** (packages whose contributed skeleton sets are equal share
  a group); the role passes iff at most one group remains, and otherwise fails with one reason
  naming every remaining group (e.g. `members split into 2 skeleton groups: {python} vs
  {typescript}; no member declares domain 'x' on-demand`) — the gate cannot know which group is
  right, so it names all of them. The one package set aside is a package whose
  `LanguageCapabilityDeclaration.on_demand_domains` names the role's domain (that language emits
  the domain's artifacts only when the DSL triggers them). No domain stance, builtin-group
  stance, capability declaration or `capability_gaps` row sets a package aside, so a capability a
  target does not realize leaves its roles failing and counted. An `undomained` role admits no
  set-aside. A role the gate cannot classify (unparseable member, unresolvable annotation) is
  reported as a **failure naming the member** — never skipped.
- The `identical`/`same-behaviour` shape exemption also covers a **rendering leaf**: a body with
  no branch/loop/`try`/`with`/comprehension/`raise`, no attribute chain rooted at `self`, a
  shared-typed or unannotated parameter, or a derived root sourced from one of those (a chain
  rooted at a language-private parameter, or at a derived root sourced only from such reads, is
  exempt — it is never a model root by the same rule the arity count already applies), and every
  call resolving to the shared codegen layer or the standard library — reported
  `rendering-leaf-exempt` beside `adapter-exempt`.

**Every role is in scope; the verdict is a pinned, two-directional failing-role count.** No
file, flag or domain id narrows the measured population: every bucket, every domain, and every
role the domain ladder resolves to `undomained` is evaluated and counted. The gate compares the
number of failing roles with `[languages].failing_roles` in
`datrix/scripts/config/behaviour-parity-baseline.toml` and exits 0 only on an exact match. More
failing roles than the pin fails (a regression); FEWER failing roles than the pin fails too,
unless the pin is lowered in the same change (an improvement must be banked — no other ratchet in
this repo fails on an unpinned decrease). The failure message names the direction, the delta and
the live split. The `[languages.buckets]` counts split the failing roles by verdict
(`identical`/`same_behaviour`/`divergent`); they are diagnostic — a stale split logs a WARNING and
never moves the exit code. The loader refuses a missing, unreadable or malformed file, an
unrecognized top-level section or key (naming the file and the key), and a non-integer or
negative count. Seed or lower a pin from the gate's own `BEHAVIOUR-PARITY GATE: N role(s) FAIL
(...)` line (`-Dbg` also lists every role), never from a document. The platform axis has no
section.

**`-Scope` / `-Buckets` are report filters only.** They choose which role lines the report
prints (a role prints when its domain and its verdict satisfy every filter given), print a
`BEHAVIOUR-PARITY REPORT FILTER` line, and never change the failing-role count, the ratchet
comparison or the exit code. An unknown id is a usage error naming the valid options, and both
are refused on a `--report-only` run.

**Non-vacuity is enforced on every run.** A synthetic five-bucket tree (one identical role, one
same-behaviour role, one divergent role, one role split only by a language token, one role
unified only by shared-typed signature) must land in exactly its bucket, a single-target tree
must be refused, a two-group divergent role must fail naming both groups and pass only once the
odd group's package declares the role's domain on-demand, a divergent role whose package would
once have been declared unsupported (or whose member is an `@emit_adapter` over an unsupported
builtin group) must still fail, the module's own AST must import, name and read none of the
retired declaration types, an `undomained` failing role must be counted by the failing-role count
and the ratchet, a live count above the pin and a live count below it must each fail while an
exact match passes, the baseline loader must refuse an unrecognized key naming the file, a report
filter must change the printed lines and not the verdict, and the bucket labels printed must be
exactly `identical` / `same-behaviour` / `divergent`. A fixture language split into a backend
and a core must resolve both packages under one label, a function planted only in the core must
be compared as that language's member, and the core must never land in the "other package" set
whose bare names exclude name roles (fed as one, the role is excluded). The fingerprint pass's own non-vacuity is
checked the same way: a renamed cross-language pair must be reported, and a covered pair (same
name in both packages), an under-size pair, a no-model-attribute-read pair, and a pair of renamed
copies inside one package must not.

**The platform axis (`-Axis platforms`) gates against its own `[platforms]` pin** in
`behaviour-parity-baseline.toml`, exactly like the language axis. Before the signature and
normalized-name keys it tries a COORDINATE role key: the block type a platform's own
`RealizationTable` (`load_realization_table`) registers a function as `plan_builder` for (flavor
builders of one block type fold into one role; a builder bound to several block types keeps the name
key; a bound method or one-delegate closure adapter resolves to the function holding the behaviour).
A platform whose tables cannot be located or imported fails the run (exit 2) rather than falling
back to name keys. The self-test asserts a floor of live coordinate roles spanning at least two
platform packages.

**Fingerprint pass (report-only, `-Fingerprint`).** The role/name grouping above only compares
functions that already share a signature or normalized-name role; a parallel implementation each
language wrote under an unrelated name, with no shared return type, lands in a single-package
role and is never compared. `-Fingerprint` adds a second, independent pass over exactly those
uncovered functions — members of a role with fewer than 2 distinct member packages, minus
pre-binding adapters and rendering leaves — grouping them across packages by a **behaviour
fingerprint**: the function's control shape (the ordered statement heads a skeleton renders —
`if`/`for`/`return`/… — with every predicate, chain and operand dropped) paired with the set of
model attribute names it reads (every `.attr` access rooted at a parameter or a derived root,
never through `self` and never through a plain local). A skeleton under
`FINGERPRINT_MIN_SKELETON_LINES` (6) lines, or a function reading no model attribute, is never a
candidate. A surviving cross-package group is judged by the same `identical` / `same-behaviour` /
`divergent` verdict rules a name/signature role uses — no second classifier — and labelled
`match` (every member's skeleton text equal) or `near-match` (same shape and attributes, at least
one member's skeleton text differs). The pass never reaches the exit code, the baseline, or the
report filters; it becomes gated only once its first measurement is worked down.

| Mode | Command | Description |
|------|---------|-------------|
| **Fingerprint pass** | `.\test\behaviour-parity-gate.ps1 -Fingerprint` | Also report cross-package skeleton-fingerprint groups among functions no role covers (report-only; exit code unchanged) |

**The language axis also covers every `transpiler_profile`-bearing frontend-client renderer.**
Beside every `datrix.languages` package, the language axis compares every registered
`datrix.generators` package whose native generator class declares a non-`None`
`transpiler_profile` on its `PluginDescriptor` (angular/flutter once their own tasks land
— none do yet, so today's scan is unaffected). Its name-token vocabulary comes from its
`ClientTargetCapabilityDeclaration.name_tokens`, resolved only after no `datrix.languages`
plugin answers to the same name — never guessed from the bare registered name alone. The
`.ps1` wrapper and its flags are unchanged; only the underlying `--axis languages` scan widens.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\behaviour-parity-gate.ps1` | Language axis: the failing-role count against its pinned baseline, in both directions |
| **List every role** | `.\test\behaviour-parity-gate.ps1 -Dbg` | Debug logging; also prints every passing role (failing roles always print) |
| **Filter by domain** | `.\test\behaviour-parity-gate.ps1 -Dbg -Scope queue,cache` | Print only these domains' role lines (add `undomained` to see those); never changes the exit code |
| **Filter by bucket** | `.\test\behaviour-parity-gate.ps1 -Dbg -Buckets identical` | Print only these verdict buckets' role lines (identical, same-behaviour, divergent); never changes the exit code |
| **Platform axis** | `.\test\behaviour-parity-gate.ps1 -Axis platforms` | Failing-role count against the `[platforms]` pin, both directions; exit 0 on exact match, 1 otherwise |
| **Self-test only** | `.\test\behaviour-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test |

**Parameters:** `-Axis <languages|platforms>` (default: languages), `-Scope <id,...>`, `-Buckets <id,...>`, `-Dbg`, `-SelfTest`, `-Fingerprint`

**Exit codes:** 0 = the failing-role count equals its pin (or a successful `-SelfTest`),
1 = the count differs from its pin (above it: a regression; below it: an improvement whose pin was not lowered in the same change),
2 = usage/discovery/parse error, an unreadable or malformed baseline, or the self-test failed.

---

### `test\shared-home-body-gate.ps1`

A function with a shared home has exactly one definition. The homes are `datrix-common`,
`datrix-codegen-kernel` and `datrix-codegen-common`; a private copy elsewhere is usually a renamed
one, so this gate compares **normalized bodies**, not names or text (the sibling hoist tests prove a
copy is gone by name; Pylint's similar-lines check is textual and misses a renamed copy).

**What a hit is.** The gate AST-walks every public function of the three homes (no segment of the
qualified name starts with `_`) and every function, public or private, of every discovered
`datrix-*` package's `src/` tree. A function qualifies at **8 lines and 40 AST nodes** (measured on
the docstring-free body; the floor removes Protocol `...` stubs and one-line accessors). Its body is
normalized: the function's own name, decorators, annotations and docstring are dropped; every
parameter and locally bound name becomes a positional token; every constant collapses to its type
name; **attribute names, keyword-argument names and non-local call targets are kept**, so two
functions that read different attributes or call different functions never compare equal. A function
in package P is a hit when its normalized body equals a public home function's in a package other
than P. The rule is symmetric across homes: when two public home functions in different home
packages are duplicates, both are hits (deleting one clears both); equal bodies inside the same
package are not hits.

**The verdict is a decrease-only per-package count** pinned in
`datrix/scripts/config/shared-home-body-baseline.toml`: `[[baseline]]` entries with exactly the keys
`package` (import name), `count`, `seed` and `reason`. A live count above its `count` fails; a
decrease passes and logs the command to lower the pin. A package with no entry is pinned at 0.
`seed` is the first measurement and never changes (the closing check proves each package's count
strictly below its seed). The loader refuses a missing or malformed file, an unrecognized key, a
duplicate package, a negative or non-integer count, `count > seed` and an empty `reason`.

**Self-test, run first on every invocation.** On a fixture tree under `D:\datrix\.tmp`: a planted
renamed copy raises its package's count by exactly 1 and the ratchet message names the package, the
live count and the pin; reverting clears it; docstring-only and constant-only differences are hits;
attribute-name and call-target differences are not; a below-floor pair and a copy of a private home
function are not; same-package equal bodies are not hits and a cross-home pair counts symmetrically;
the ratchet verdicts (above, below, no entry, unknown package); the baseline round trip (seed,
load, lower, refuse a rise, refuse each malformed form); and an unparseable source file fails the
scan naming the file. Run `-Symbol <name>` over the real tree to confirm a known real renamed copy is
found.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\shared-home-body-gate.ps1` | Per-package duplicate count against the decrease-only pin; exit 0 when no package exceeds its pin |
| **List every hit** | `.\test\shared-home-body-gate.ps1 -Hits` | Print every `SHARED-HOME BODY HIT:` line (copy location and name == home location and name) |
| **Check named copies** | `.\test\shared-home-body-gate.ps1 -Symbol event_for_replay_plan,_iter_calls` | Print only the hit lines whose copy has one of these bare names; `0 hit line(s) shown` proves a removed copy is gone. A report filter only |
| **Seed / lower the pin** | `.\test\shared-home-body-gate.ps1 -UpdateBaseline` | Seed the baseline when the file does not exist (`count = seed = measured`); otherwise lower every `count` to the live value, keeping `seed` and `reason`. Refuses (exit 1, file untouched) when any count would rise |
| **Debug logging** | `.\test\shared-home-body-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\shared-home-body-gate.ps1 -SelfTest` | Run only the plant / observe / revert self-test |

**Parameters:** `-Hits`, `-Symbol <name,...>`, `-UpdateBaseline`, `-Dbg`, `-SelfTest`

**Exit codes:** 0 = no package exceeds its pin (or a successful `-SelfTest` / `-UpdateBaseline`),
1 = a package's count is above its pin, or `-UpdateBaseline` was refused because a count would rise,
2 = the self-test failed, the baseline is unreadable or malformed, a source file cannot be parsed,
or a home package is missing from disk.

---

### `test\dependency-declaration-ratchet-gate.ps1`

Dependency-declaration-only-path ratchet (W4 / declarations-are-the-only-emission-path enforcement): a per-language CENSUS of every dependency-**SET** decision site in a registered language that decides dependency package NAMES outside that language's own `generation/dependency_tables.py` table -- the completeness proof for the declared-table migration: a language's migration is done when this scan reports ZERO out-of-table sites for that language, never when a hand-written list is exhausted. Target derivation is pure runtime discovery via the installed `datrix.languages` entry points -- never a hardcoded language list -- so a fifth `datrix-codegen-<lang>` package is covered automatically with no edit here. **A language is every package implementing it:** the backend registering its entry point plus each `<backend>-core` distribution the backend requires (derived from the installed requirements by `datrix_testing.target_distributions`); every package's `src/` and `templates/` trees are scanned, against the UNION of their `defaults.yaml` catalogs, so a decision site that moved into a core (which ships no catalog of its own) is still matched against the backend's. A registered language with no `defaults.yaml` at all declares an empty dependency-catalog universe, which is a legitimate zero-site result, not an error.

**The counted unit is a decision SITE, not a bare catalog-name-shaped literal anywhere in the tree.** An earlier version of this scanner flagged any string literal equal to a registered catalog package name, anywhere under `src/` and `templates/`; that over-matched by roughly two orders of magnitude (a cache-ENGINE identifier constant, an import-deduplication helper's module-name constants, and a code template's own `import <pkg>` statement all happen to share a spelling with a real package name without ever deciding a manifest's dependency set) and could never structurally reach zero for a migrated language. Two structural detection passes, neither a text regex over raw source:
- **Python source.** AST-walks every `.py` file under the language's `src/` tree for string-literal `ast.Constant` nodes whose value is a member of that language's registered `DependencyCatalog` package universe (read from the language's own `defaults.yaml`) -- but ONLY when the literal sits inside (a) a `get_dependencies`/`get_npm_dependencies`/`get_nuget_dependencies`/`_collect_*_deps`-shaped function at any nesting depth, or (b) a module-TOP-LEVEL (never class- or function-nested) assignment shaped the same way (e.g. `ENGINE_PACKAGE_NAMES`, `EMAIL_COORDINATES`). Both shapes are recognized by a documented whole-snake_case-token naming vocabulary (`_DEPENDENCY_DECISION_NAME_TOKENS` in the runner module: `dependency`/`dependencies`/`deps`/`package`/`packages`/`coordinate`/`coordinates`), matched as whole tokens, never a substring search or a hardcoded function-name allowlist.
- **Jinja templates.** Parses every `.j2` file under the language's `templates/` tree into its Jinja AST and takes the `nodes.Const` literals that DECIDE a dependency -- a version-map subscript key (the `'pkg'` of `v['pkg']`), the needle of a membership test against a decision-named collection (`'pkg' in deps`), or a literal assigned to a decision-named variable (`{% set npm_deps = [...] %}`) -- for the same catalog-membership match: the structural analogue of the Python pass's decision-span gating. A literal in any other expression position decides nothing and is not counted (a controller template's `qp.pipe == 'uuid'` compares a query parameter's pipe kind that happens to spell a package name). Raw `TemplateData` (a template's literal rendered-output text between tags) is deliberately NOT scanned by containment: it degrades to a text search over a template's entire output, including plain generated code and even doc comments, which is not a dependency-set decision.

This is a naming-shape heuristic, not an exhaustive semantic analysis: under-reporting a genuine decision site named entirely outside the token vocabulary is a known, accepted, documented limitation (extend the vocabulary in the runner module if one is found), preferred over a hardcoded per-function allowlist that would drift silently out of sync with the code it polices.

**This is a REPORT with a decrease-only out-of-table-count baseline, not a check that identifies WHICH package a site decides to require** -- only WHETHER a site decides one at all, outside the one place it is allowed to. A single conceptual site (e.g. the same literal appearing as both a dict key and a sibling function argument on one line) collapses to one `(file, line, literal)` entry, never double-counted.

**A small, reviewed, coordinate-pinned exemption list** (`_KNOWN_NON_JINJA_TEMPLATES` in the runner module) skips the Jinja parse attempt for `.j2`-suffixed files that are not actually Jinja source -- at authoring time this is exactly one file, a dormant static-Python legacy template kept intentionally unrendered by an unrelated, already-settled hardening decision. Every OTHER `.j2` file that fails to parse still fails the scan loud (a genuine template syntax error is a scan error, never a silently skipped file); a template that parses but references an undefined Jinja global is unaffected (`Environment().parse()` only needs syntactic validity, not a rendering context).

**Built-in non-vacuity self-test, every invocation.** Before any real scan is trusted, the script builds a synthetic two-language package tree under a temp directory and proves: it finds exactly the two planted out-of-table sites; a non-qualifying decoy referencing the same planted literal (mirroring the real `resolve_*_engine`/`SUPPORTED_*_ENGINES` false-positive shape) adds no second site -- the narrowing itself; moving one planted literal into a synthetic `generation/dependency_tables.py` drops the combined count by exactly one; a synthetic Jinja template's planted literal is detected by the template pass independently of the Python-source pass; the template pass counts a membership test against a decision-named collection and a decision-named `set`, and not an equality test against an unrelated attribute spelling the same name; a fixture language split into a backend and a core has a decision site planted in the core found against the backend's catalog, and missed by a backend-only scan; against the LIVE tree (not synthetic), every registered language's catalog contains every package its declared table names, a real declared name planted into a decision site is reported against that live catalog, and the scan no longer reports three described, currently-real sites the earlier, over-broad matcher wrongly counted; and the minimum-language guard refuses a single-language set with exit code 2, never a silent pass. Fails loud (exit 2) if fewer than two languages are registered -- a per-language census over fewer than two languages is vacuous.

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

Migration upgrade-op family gate: the cross-package half of the upgrade-op duplication census. Six `_build_upgrade_op_for_*` symbols exist once per migration target that carries the family (today python's Alembic migration generator); the census read their bodies and concluded they are genuinely target-specific, so **every private copy must survive** — a later "cleanup" deleting one would be deleting a target's real behaviour. One genuinely shared fact WAS hoisted: the targets reassembled the `INDEX_ADDED` JSON detail into its `SnapshotIndex` with byte-identical semantics and error text, so that parse now lives once in `datrix_codegen_common.algorithms.migration_upgrade_op_index`, each target calls it the exact number of times its own paths need, and none may redefine it. Structural resolution only, never a text match. The languages are named (a fact about which targets carry this family, not a claim about which targets exist) but their packages resolve through the installed `datrix.languages` entry points, so a named language that is not installed fails loud instead of letting its part pass vacuously. Repo-level validation **script** — a unit test importing several generator packages to compare their bodies is the shape the repo boundary forbids outright; the shared parser's own input/output behaviour stays as a unit test in `datrix-codegen-common`, which owns the function.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\migration-upgrade-op-family-gate.ps1` | Run every cross-package check in this family |
| **Debug** | `.\test\migration-upgrade-op-family-gate.ps1 -Dbg` | Debug logging (names each self-test check as it passes) |
| **Self-test only** | `.\test\migration-upgrade-op-family-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Each of the six target-specific symbols is still defined exactly once per target.
- Each target has exactly the pinned number of resolved call sites for `parse_index_added_detail` (a count, not a `>= 1`: a path silently losing its call is the regression this pins), and no target defines `parse_index_added_detail` or the retired `_index_from_index_added_detail`.
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

Zero-environment runtime census gate: every registered language is obligated to bake deployment-static values at generation time (the running service consults no environment variable). Each language plugin states, on its `LanguageCapabilityDeclaration.zero_environment_runtime`, the regular expressions that spell an environment read in its own templates. The gate censuses every `.j2` template under the `src/` tree of every package implementing each registered language (its backend plus each language core the backend requires) against those idioms, and holds each language to the rule the KIND of its entry in `scripts/config/zero-environment-runtime-baseline.json` selects — never a field on the declaration, a reason or a gap row:
- `reviewed_exemptions`: every template that reads the environment is listed with a written reason, as a justification of that specific read (python's reads are per-read reviewed exemptions). An unlisted read and a stale entry are both violations. A language with NO entry is held to this kind with an empty list, so adding a language needs no edit here.
- `pinned_count`: a decrease-only count of environment-reading templates, for a language that delivers runtime facts through the environment by design (typescript). It may fall and may never rise.

A registered language that states no idioms fails, named; a baseline entry naming an unregistered language is stale and fails. Language set from the installed `datrix.languages` entry points; idioms from each language's declaration — never a table in the script. Test-harness templates count too (a harness that reads the environment is still emitted into the generated project). Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\zero-environment-runtime-gate.ps1` | Census every registered language against its baseline entry |
| **Debug** | `.\test\zero-environment-runtime-gate.ps1 -Dbg` | Debug logging (lists every environment-reading template) |
| **Self-test only** | `.\test\zero-environment-runtime-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |
| **Lower pins** | `.\test\zero-environment-runtime-gate.ps1 -UpdateBaseline` | Lower every `pinned_count` entry to its live census (the only writer of `pinned_count`; it refuses to raise one; `reviewed_exemptions` entries are hand-authored and untouched) |

**Parameters:** `-Dbg`, `-SelfTest`, `-UpdateBaseline`

**Assertions:**
- `reviewed_exemptions` kind (or no entry): `reads − exemptions = ∅` and `exemptions − reads = ∅`; every exemption carries a non-empty reason.
- `pinned_count` kind: `len(reads) ≤ pinned_count`; a count below the pin is logged with the lower-the-pin hint, never silently accepted as the new floor.
- Every entry's `kind` is one of the two values and carries exactly its own payload key; a missing or unknown kind, a `pinned_count` entry carrying `exemptions` (or the reverse), an entry lacking its payload, or an extra key is rejected.
- Non-vacuity self-test (every invocation): a synthetic template tree yields exactly the planted read (the clean template and a non-`.j2` file are not counted); the comparator reports exactly one problem for a missing exemption, a stale exemption, a count above the pin, and no entry with a read, and none for an exact match, a count at/below the pin, or no entry with no read; the same one-read census passes against a `pinned_count` entry of 1 and fails against an empty `reviewed_exemptions` entry (the entry kind alone selects the branch); a reasonless exemption is rejected; every `entry_kind` rejection above; `-UpdateBaseline`'s writer lowers a pin, refuses to raise one and carries exemption entries through unchanged; a baseline entry naming an unregistered language is one stale-entry problem; a fixture language split into a backend and a core has a read planted in the core censused (a backend-only census misses it) and one relative template path carried by both packages refused; the **live** census finds a known real read (`python: templates/api/identity.py.j2`); a single-language set is refused.

**Exit codes:** 0 = every language matches its baseline entry (or a successful `-SelfTest` / `-UpdateBaseline`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the baseline is malformed.

---

### `test\framework-header-parity-gate.ps1`

Framework header parity gate: every registered language spells the framework-minted HTTP headers from datrix-codegen-common's one registry (`datrix_codegen_common.generation.http_headers` — the trusted-caller token, the three rate-limit response headers, the inbound webhook secret, the outbound webhook delivery headers) and realizes every header family. The gate censuses every `.py` and `.j2` source under the `src/` tree of every package implementing each registered language (its backend plus each language core the backend requires) for `X-`-prefixed header tokens and registry-constant references; a spelling records the package it lives in, which is what an exemption keys on. **Spelling:** a header under a framework prefix (`X-Datrix-`, `X-RateLimit-`, `X-Webhook-`) is an exact registered name (case-insensitively — Node lowercases header names) or a reviewed, counted entry in `scripts/config/framework-header-exemptions.json`; a retired name (`X-Internal-Token`, `X-Datrix-Delegated-User`) is a violation with no exemption path. **Realization:** every registered language realizes every registered family (the exact name spelled, or its registry constant referenced from python); a family a language does not realize fails naming the language and the family, and no declaration can excuse it; a family no language realizes is a dead registry entry and fails; an unused exemption is stale and fails. Hard zero: any problem exits non-zero and there is no baseline file. Language set from the installed `datrix.languages` entry points; registry read from the packages — never a table in the script. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\framework-header-parity-gate.ps1` | Census every registered language against the registry and the exemption file; prints the family × language realized/MISSING table |
| **Debug** | `.\test\framework-header-parity-gate.ps1 -Dbg` | Debug logging (per-language spelling and constant-reference counts) |
| **Self-test only** | `.\test\framework-header-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Spelling: `framework-prefixed spellings − registered names − exemptions = ∅`; `retired spellings = ∅`; `exemptions − live spellings = ∅` (no stale entry); every entry carries package, header, a registered family and a non-empty reason.
- Realization, per language: `registered families − realized families = ∅`.
- Registry: every family is realized by at least one language.
- Non-vacuity self-test (every invocation): a planted source tree yields exactly its two template spellings plus one python constant reference (a Markdown file and a `__pycache__` entry are not counted); the comparator reports exactly one problem for a retired spelling, an unregistered framework-prefixed spelling, a stale exemption and an unrealized family (it takes no declaration input that could excuse one), one dead-contract problem for a family nobody realizes, and none for a clean pair, an exempted spelling, a non-framework `X-` header, or a constant-realized family; the exemption parser rejects a miscount, an unknown family, a non-framework header and a reasonless entry; a fixture language split into a backend and a core has a header and a registry constant planted only in the core realized for the language and keyed on the core package; the **live** census finds the caller-token header on at least two languages; a single-language set is refused.

**Exit codes:** 0 = every language passes both rules (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the exemption file is missing/malformed/miscounted.

---

### `test\web-security-header-parity-gate.ps1`

Web security header parity gate: every registered platform realizing `static_web_hosting` (docker/local's loopback nginx static site, AWS's CloudFront response-headers policy, Azure's Static Web Apps `staticwebapp.config.json`) emits the ONE declared security-header set from datrix-common's one builder (`datrix_codegen_kernel.platform.web_security_headers.build_web_security_headers` — Content-Security-Policy, Strict-Transport-Security, X-Content-Type-Options, Referrer-Policy, Permissions-Policy). None of the three platforms spells a header name literally in its own source — each threads the shared builder's `WebSecurityHeaderSet.as_header_dict()` straight into its own rendering primitive — so this gate DRIVES each platform's real generation composition for one shared fixture (app, web target, environment) rather than censusing source text, then parses the EMITTED artifact structurally (nginx `add_header` directives at server level, the CloudFront response-headers policy's CDK IR, the parsed `staticwebapp.config.json`). **Realization:** every header family the platform's own topology expects (read from `PlatformCapabilityDeclaration.static_web_hosting.origin` — a loopback platform correctly omits Strict-Transport-Security, never a per-platform declared hole) must be realized in the emitted artifact; there is no exemption path for this gate — a platform realizing `static_web_hosting` must realize its full topology-appropriate set, always. **CSP safety:** no emitted Content-Security-Policy value contains `unsafe-inline` or `unsafe-eval`, checked independently of family completeness. Every registered platform serves static web hosting and is censused; a platform whose declaration carries no `static_web_hosting.origin` (or whose folded names disagree on origin) is a defect that fails the run with exit 2, never skipped. Platform set from the installed `datrix.platforms` entry points; the declared header set read from datrix-common — never a table in the script. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\web-security-header-parity-gate.ps1` | Drive every realizing platform's real generation composition for the shared fixture; prints the family × platform realized/n-a/MISSING table |
| **Debug** | `.\test\web-security-header-parity-gate.ps1 -Dbg` | Debug logging (per-platform census detail) |
| **Self-test only** | `.\test\web-security-header-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Realization, per realizing platform and family: every family in that platform's own topology-derived expected set (`_topology_families`, keyed by `static_web_hosting.origin`) is realized in the emitted artifact; a realized family outside the declared vocabulary is also a violation.
- CSP safety: no censused `Content-Security-Policy` value contains `unsafe-inline` or `unsafe-eval`, regardless of family completeness.
- Registry: every declared family is realized by at least one registered platform.
- Non-vacuity self-test (every invocation): two fully realizing planted platforms report no problem; a platform missing an expected family is exactly one problem naming the platform and family; a loopback platform legitimately omitting Strict-Transport-Security is NOT a violation, and its verdict records the topology-narrowed expected set; a realized header outside the declared vocabulary is exactly one problem; a planted `unsafe-inline`/`unsafe-eval` CSP sample is exactly one problem independent of family completeness; a family nobody realizes anywhere is reported as a dead contract; platform-origin resolution is proven directly (one name, two agreeing names, two disagreeing names raising, a name declaring no origin raising); a single-platform set is refused; the **live** scan drives every real registered platform's generation composition, finds every declared family realized somewhere, and passes `evaluate()` with zero violations.

**Exit codes:** 0 = every realizing platform passes both rules (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two platforms are registered, a platform has no census driver, or a platform declares no / a disagreeing static-hosting origin.

---

### `test\problem-type-parity-gate.ps1`

Problem-type parity gate: every registered language answers errors with RFC 7807 `type` URNs from datrix-common's one registry (`datrix_common.datrix_model.problem_types` — `urn:datrix:error:<slug>`; a declared DSL exception derives its slug from its class name through the shared exception-declaration algorithm, a framework error uses a registered family) and is obligated to every framework family. The gate censuses every `.py` and `.j2` source under the `src/` tree of every package implementing each registered language (its backend plus each language core the backend requires) for **registry references**, never URN literals: `PROBLEM_<FAMILY>` in a template, `problem_type_for("<family>")` in Python, or a template naming `GENERIC_PROBLEM_FAMILY_BY_STATUS` (which realizes every generic family it carries). **Spelling:** any `urn:datrix:error:<slug>` literal in a language package is a hard problem with no exemption path — the registry renders every URN, and a literal is a second vocabulary. **Realization:** every registered language is obligated to reference every registered family. A (language, family) cell a language does not reference is an *unspelled cell*, printed on every run as `PINNED GAP language=<l> family=<f>` and counted against that language's pin in `scripts/config/problem-type-parity-baseline.toml` (`[languages]` table, `<language> = <count>`; a language absent from the table is pinned at zero; the loader refuses an unrecognized key, a negative count or a bool). A count above the pin fails (`EXCEED`: spell the family, never raise the pin); a count below the pin fails (`BELOW`: lower the pin in the same change); a pin naming an unregistered language is stale. The pin is seeded from a live run and lowered by hand; no script writes it. A family no language spells is a dead registry entry and fails outright, and is never pinned. Language set from the installed `datrix.languages` entry points; registry read from the packages — never a table in the script. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\problem-type-parity-gate.ps1` | Census every registered language against the registry and its pin; prints the family × language realized/MISSING table and every `PINNED GAP` cell |
| **Debug** | `.\test\problem-type-parity-gate.ps1 -Dbg` | Debug logging (per-language spelling counts) |
| **Self-test only** | `.\test\problem-type-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Spelling: `literal slugs − registered families = ∅`.
- Realization, per language: `len(unspelled families) == pin` (exact match; the pin defaults to zero for a language absent from the baseline).
- Registry: every family is spelled by at least one language.
- Non-vacuity self-test (every invocation): a planted source tree yields exactly its two literal slugs (the bare prefix, a Markdown file and a `__pycache__` entry are not counted); the comparator reports a language spelling only some families as exactly one unspelled cell and zero hard problems, and exactly one hard problem for a private slug and for a family nobody spells; the pin check is clean on an exact match, one `EXCEED` above the pin, one `BELOW` (saying to lower the pin) under it, `EXCEED` against the implicit zero for an unpinned language with one unspelled family, and one stale-pin problem for a pin naming an unregistered language; the baseline loader accepts a well-formed file and rejects an unrecognized key, a missing `[languages]` table, a negative count, a bool, a non-integer, invalid TOML and a missing file; a fixture language split into a backend and a core has a URN planted only in the core censused against the core package (a backend-only census misses it); the **live** census finds the `internal` type on at least two languages; a single-language set is refused.

**Exit codes:** 0 = every language's unspelled-cell count equals its pin and no hard problem was found (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the baseline is missing/malformed.

---

### `test\field-error-path-parity-gate.ps1`

Field-error-path parity gate: every registered language spells a `request-validation` problem body's `errors[].field` with the ONE shape `datrix_common.datrix_model.problem_types.FIELD_ERROR_PATH_RULE` defines (a dot-separated wire-name path relative to the request body root, no leading `body` segment, `[n]` for array elements). Hard zero: every registered language is obligated to realize the rule and no declaration excuses one. Unlike the problem-type/framework-header registries this is not a family table — there is exactly one rule. Realization is a runtime BEHAVIOUR rather than a literal wire string, so there is no single cross-language regex: the gate censuses, across every package implementing each registered language (its backend plus each language core the backend requires), that language's own construction technique — python's real, callable `format_field_error_path` mapping function (found by definition, then EXECUTED against the rule's own canonical worked example so the produced string is real, not guessed), and typescript's recursive `joinPath` builder (found by its two required construction lines — bracket-indexed, dot-joined). Python's `classify_request_validation` is executed too, against a located fixture (a missing path parameter, a wrongly typed query value, an unknown body field): a path or query entry landing in the wrong `location`, `field` or `code` is a divergence recorded at the classifier. A language with no known technique censuses to zero sites. **Realization:** the language's census produces the canonical path for the shared fixture; a language that does not fails naming the language; a found but divergent construction (a literal `body` prefix, or an index not spelled `[n]`) fails naming the found and expected spelling. Language set from the installed `datrix.languages` entry points — never a table in the script. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\field-error-path-parity-gate.ps1` | Census every registered language's construction technique against the canonical rule; prints the language realized/MISSING table |
| **Debug** | `.\test\field-error-path-parity-gate.ps1 -Dbg` | Debug logging (per-language site counts) |
| **Self-test only** | `.\test\field-error-path-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Realization, per language: the census produces the canonical path; an empty census is a failure.
- Non-vacuity self-test (every invocation): a planted correct python formatter's real execution produces the canonical path, a planted divergent one surfaces its actual wrong output; a planted correct typescript builder censuses as canonical, one missing the `[n]`-index construction censuses as divergent; a language with no known detector censuses to zero sites; a fixture language split into a backend and a core has a realization planted only in the core censused against the core package; the comparator reports exactly one problem for a divergent spelling and for a language that realizes nothing (it takes no declaration input that could excuse one), and none for two languages spelling the canonical path; the **live** census finds at least one registered language realizing the rule; a single-language set is refused.

**Exit codes:** 0 = every language realizes the rule (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed or fewer than two languages are registered.

---

### `test\artifact-role-parity-gate.ps1`

Artifact-role parity gate, cross-language and cross-provider: detects a language (or a provider) silently emitting nothing for a construct another language (or provider) realizes, without generating anything and without storing anything. It reads the generation pipeline's own per-target manifests (`.datrix/manifests/<target>.json`: the files each target wrote, plus a `generated_at` stamp) from the example trees `generate.ps1` writes under `<workspace>/.generated/<language>/<runtime>/<provider>/<example>/`. **There is no committed baseline and no bless step** -- see `datrix/docs/architecture/generated-output-stability.md`.

**Language axis.** For every `(example, runtime, provider)` generated in >= 2 registered languages, each language's paths are classified by domain role via that language's own derived `DomainDeclaration.structural_pattern` set (a domain is realized exactly when its declaration carries a pattern), and the role set must be identical across those languages. A missing role is a failure. EXACTLY TWO skips exist, both resolved structurally before the exemption file and neither reading a declaration's absence: (1) the missing language emits the domain only on demand (`LanguageCapabilityDeclaration.on_demand_domains`, declared once with its trigger), and (2) the domain's own pattern matches nothing anywhere in that language's ENTIRE generated footprint (corpus-vacuous). The second is never silent: every corpus-vacuous `(language, domain)` must carry a typed, counted record in `scripts/config/corpus-vacuity-records.json` saying why nothing exercises it. A language that realizes a domain by NO structural pattern is never excused: the gap is tracked once, as a `capability_gaps` row on its own capability declaration and counted by the capability-gap ledger gate, and this gate reports the missing role regardless of whether a row exists. A reviewed entry in `scripts/config/artifact-role-exemptions.json` (absent when there is none, the normal state) excuses a role the language realizes by a pattern whose tree for ONE example has no matching file. Paths matching no pattern are reported in an "unclassified" bucket but never compared -- template-level naming legitimately differs by language; the role SET is the contract.

**Provider axis.** The same comparison then runs for a fixed language: for every `(language, example, runtime)` generated under >= 2 providers, each provider's role set must be identical. A role present under one provider and absent under another is reported as `ARTIFACT-ROLE CROSS-PROVIDER DRIFT`, naming the language, example, runtime, the provider missing the role and the providers that have it. The same two skips apply; the per-example exemption file never does (it has no provider coordinate). Below two providers there is nothing to compare, so a single-provider corpus yields no provider-axis comparison (a no-op, not an error); the self-test is what proves the axis live.

**The gate is exactly as current as the local corpus, and refuses an incomplete one.** It prints every language's oldest and newest `generated_at` stamp, and exits 2 before comparing anything when any registered language has a registered example with no generated tree and no entry in `scripts/config/parity-known-nongenerating.json` -- naming every missing pair and the command that fills it (`generate.ps1 -All -L <language>`, once per registered language; Jon runs this, it is blocked for agents). A parked pair that DOES have a generated tree is a stale park entry and also fails: the recorded defect is fixed, delete the entry.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\artifact-role-parity-gate.ps1` | Compare role sets for every `(example, runtime, provider)` generated in >= 2 languages, and for every `(language, example, runtime)` generated under >= 2 providers, under `<workspace>/.generated` |
| **Explicit output base** | `.\test\artifact-role-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated` | Same, reading a named `generate.ps1` output base |
| **Debug** | `.\test\artifact-role-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\artifact-role-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test (one `[OK]` line per proven case); skip the real comparison |
| **Corpus-vacuity census** | `.\test\artifact-role-parity-gate.ps1 -Census` | Print every `(language, domain)` the generated corpus exercises nowhere, with its reviewed status; exit 0 (exit 2 on an incomplete corpus) |

**Parameters:** `-GeneratedRoot` (default: `<workspace>/.generated`), `-Dbg`, `-SelfTest`, `-Census`

**Assertions:**
- Every registered language's corpus is complete: each `system.dtrx` under `datrix/examples/` has a generated tree (a directory carrying `.datrix/manifests/*.json`) or a park entry; no parked pair has a tree.
- Every `(example, runtime, provider)` generated in >= 2 registered languages is compared, and every `(language, example, runtime)` generated under >= 2 providers is compared.
- A domain role present (>= 1 matching path) in one language's generated tree for an example and absent from another language's tree for the SAME `(example, runtime, provider)` is a violation, UNLESS the missing language emits it on demand (`LanguageCapabilityDeclaration.on_demand_domains`: it emits the domain only when the DSL invokes a triggering construct, where another language emits baseline scaffolding regardless -- e.g. a service-level `fn` file or an `exceptions { }`-gated errors folder; skipped directly), OR the domain's pattern matches nothing across that language's entire generated footprint (`_is_corpus_vacuous_for_language`, skipped directly), OR a reviewed entry exists in `scripts/config/artifact-role-exemptions.json` -- the last being reserved for a genuinely example-specific hole; the file is absent when there is none, which is the normal state. A language holding no declaration for the domain is not excused.
- A role present under one provider and absent under another, for the same language, example and runtime, is a violation under the same two skips; the exemption file is never consulted on this axis.
- `load_exemptions` refuses (raises `ValueError`, exit 2) an exemption entry naming a `(domain, language)` pair the language realizes by no structural pattern, or emits on demand -- an exemption is an example-specific hole, never a language-level absence. A declared on-demand id that is not a shared universe domain is refused by name. A structural domain a language neither realizes nor tracks with a `domain:<id>` `capability_gaps` row makes the declaration derivation raise (exit 2), naming the fix.
- **Corpus vacuity is skipped but never silent.** `check_corpus_vacuity_records` censuses EVERY registered language against EVERY domain it realizes by a pattern (not just the pairs the multi-language groups happen to exercise) and holds each corpus-vacuous `(language, domain)` to a reviewed record in `scripts/config/corpus-vacuity-records.json`. The comparison runs in both directions: a censused pair with no record fails (exit 1), and a record whose pair is no longer vacuous fails as stale (exit 1). Each record carries one of three statuses, which are never interchangeable because each carries a different remedy -- `unreachable-by-design` (no example can produce a matching file at all, whatever it declares or targets), `cloud-platform-only` (only an example resolving `deployment.provider` to a cloud provider could, and the corpus has none), `unexercised` (an ordinary local/docker example could and none declares the construct). `load_corpus_vacuity_records` refuses (exit 2) a missing/malformed file, a status outside those three, or a duplicated `(language, domain)`.
- Non-vacuity self-test (every invocation, one `[OK]` line per case): the language-axis comparator detects a forced mismatch and reports nothing for a matching pair; `classify_paths` buckets matched vs. unclassified paths, ignores a package-init marker and credits the most specific pattern; `unexcused_missing_domains` fails a missing role for a language with no declaration and excuses it only through on-demand membership, a zero-match footprint, or a matching exemption; the exemption guard rejects an entry for an unrealized domain (message free of stance wording), still rejects an on-demand duplicate and accepts an entry for a realized domain; `_is_corpus_vacuous_for_language` is proven against a synthetic footprint (never touching a real generated tree); the corpus reader and the provider axis are proven against synthetic `.generated` layouts under a PID-scoped scratch root (corpus reader: two targets' manifests union into one sorted path list with the newest stamp, a directory without pipeline manifests is not a tree, a single-language tree forms no comparison group, and the completeness check names a missing pair and a stale park entry; provider axis: only >= 2-provider groups compared, other languages/examples/runtimes ignored, a planted role reported against exactly the provider lacking it on a line naming both providers, identical sets and a single provider report nothing, on-demand and vacuity excuses honored); and `compare_vacuity_records` reports nothing for an agreeing census/record pair, reports a censused pair carrying no record, and reports a record whose pair is no longer censused -- with `_parse_vacuity_record` accepting each declared status and refusing an undeclared one.

**Exit codes:** 0 = every comparable group's role sets agree on both axes modulo on-demand skips, recorded corpus-vacuous skips and reviewed exemptions (or a successful `-SelfTest` / `-Census`), 1 = an un-excused role difference on the language or provider axis, or a corpus-vacuous `(language, domain)` carries no reviewed record (or a record carries no corpus-vacuous pair), 2 = the self-test failed, the generated corpus is incomplete for some registered language (or a park entry is stale), zero groups are generated in >= 2 languages, a declaration could not be derived (a structural domain neither realized nor tracked by a `capability_gaps` row), or the exemption / corpus-vacuity-record / park file is missing/malformed (or, for exemptions, names a domain the language realizes by no pattern or emits on demand).

---

### `test\generated-suite-parity-gate.ps1`

Cross-language generated-suite parity gate: every registered language's generated project carries its own emitted test suite, and the suites must agree. For every `(example, runtime, provider)` unit-tested in >= 2 registered languages under `<workspace>/.generated/<language>/<runtime>/<provider>/<example>/`, it compares the structured result index `run-complete.ps1` already wrote for each language's latest unit-test run (`<project>/.test_results/unit-tests-<stamp>/index.json`, written by `shared/generated_test_log_writer.py`, whose `tests` list names every executed test as `{service, test, outcome}`). **Generates NOTHING and runs NOTHING** -- it reads existing index files only; there is no committed baseline. A test is identified by its service and the framework-reported full test name (pytest `classname::name`, Jest `fullName`) exactly as the index records it, so two languages agree on a test only when they emit the same name for it. Three divergences are reported, each its own category: a **role gap** (a test present in one language's suite and absent from another's), a **behaviour gap** (a test present in several languages' suites that passes in one and fails or errors in another), and a **skip gap** (a test one language skips and another runs -- a skip is neither a pass nor a fail, so it is never folded into the other two; a test every language skips is no divergence). The pass/fail comparison runs over the languages a test is present in, so a role gap never hides a behaviour gap. Only unit-test runs are compared: a deploy-test index records the docker lifecycle phases of a live stack, not a flat per-test suite.

**The gate is exactly as current as the local corpus, and refuses incomplete evidence.** It prints every language's oldest and newest index timestamp and exits 2 before comparing anything when: fewer than two languages are registered; a registered language has no unit-tests index for an example another language has one for and the pair has no entry in `scripts/config/parity-known-nongenerating.json` (naming every missing pair and the command that fills it, `run-complete.ps1 -All -L <language> -Skip4`; Jon runs this, the gate never runs a suite itself); an index predates per-test records (no `tests` list); a service's per-test records do not equal its `passed + failed + errors + skipped` counts (it reported totals only, or no test report at all); a service reports a spec file that never ran (`suite_failures > 0`); two tests share one identity; an outcome falls outside `passed/failed/error/skipped`; an index belongs to another language or example than the tree it sits in; or the newest `unit-tests-*` run directory holds no `index.json` (an older run is never substituted for it). A missing index is never read as "zero tests, therefore zero gap".

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\generated-suite-parity-gate.ps1` | Compare the unit-test suites of every `(example, runtime, provider)` unit-tested in >= 2 languages under `<workspace>/.generated` |
| **Explicit output base** | `.\test\generated-suite-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated` | Same, reading a named `generate.ps1` output base |
| **Longer listing** | `.\test\generated-suite-parity-gate.ps1 -ListLimit 50` | List up to 50 gaps per (example group, kind) before summarizing the rest (default 10) |
| **Debug** | `.\test\generated-suite-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\generated-suite-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-GeneratedRoot` (default: `<workspace>/.generated`), `-ListLimit` (default: 10), `-Dbg`, `-SelfTest`

**Assertions:**
- Every `(example, runtime, provider)` unit-tested in >= 2 registered languages is compared; the language set comes from the installed `datrix.languages` entry points, never a list in the script.
- A test present in one language's index and absent from another's is a role gap; present in several with a pass in one and a fail/error in another is a behaviour gap; skipped in one and run in another is a skip gap.
- Non-vacuity self-test (every invocation, 11 `[OK]` lines): a planted role gap, a planted behaviour gap and a planted skip divergence are each reported as exactly that gap; a matching pair reports none; a fail against an error is no gap; fewer than two registered languages is refused (the real entry point and the comparator); every outcome the index writer records is classified; indices written by the real writer (pytest JUnit and Jest JSON) are read, grouped and compared; an incomplete corpus is refused naming the pair while a parked pair is not missing; each unusable-index shape above is refused with its reason; the newest run is read and a newest run with no index is refused; and the entry point exits 0 for agreeing suites, 1 for each gap kind (named in the report, bounded by `-ListLimit`) and 2 over an empty corpus.

**Exit codes:** 0 = every comparable group's suites agree (or a successful `-SelfTest`), 1 = a role, behaviour or skip gap was found, 2 = the self-test failed, fewer than two languages are registered, the corpus is incomplete, an index is unusable, or no group is unit-tested in >= 2 languages.

---

### `test\example-registry-gate.ps1`

Example-universe consistency **and layout** gate: every `system.dtrx` under `datrix/examples/` must appear in >= 1 named test set of `scripts/config/test-projects.json`, or carry a reviewed entry in `scripts/config/test-set-exclusions.json`. An unregistered example is never built by `generate.ps1 -All`/`run-complete.ps1 -All`, which select their corpus FROM `test-projects.json`'s test sets -- this is exactly how the `config-store` and `replayable-ingestion` whole-example parked defects (tracked in `parity-known-nongenerating.json`) went unnoticed for a full generation cycle before this gate landed.

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

Cross-platform capability parity gate: the platform-axis counterpart of
`supported-domain-parity-gate.ps1`. It compares CAPABILITIES, never implementations. A platform that
lacks one flavor, vendor product or provider another platform has is not a gap; a capability a platform
realizes by no implementation is recorded as a `<kind>:<id>` row in that platform's own
`capability_gaps`. A row accounts for the violation here and suppresses nothing in any other gate.
There is no exemption file.

Declarations are read through one extractor (presence only) and compared as plain facts. Seven surfaces:
1. block types: every block type any platform realizes by at least one flavor is realized by at least one
   flavor on every platform (`block_type:<id>` row).
2. observability categories: at least one native provider per category any platform realizes
   (`observability_category:<id>` row).
3. supported runtimes: a floor of at least one runtime (no row kind).
4. identity features: offered through at least one provider on every platform (`identity_feature:<id>` row).
5. static web hosting: each platform's origin equals its OWN edge (`domain` when the edge binds custom
   domains, `loopback_port` otherwise).
6. custom-domain surfaces: an edge-binding platform carries both `gateway` and `web`, any other carries neither.
7. model realizations: at least one provider with a flavor cell.

Retired surfaces: secret backends and deployable constructs (construction-time floors, product vocabulary),
the set-shaped optional fields (each platform's own vocabulary) and the presence-shaped optional fields
(per-platform topology facts). A field partition guard still forces every declaration field, required or
optional, into a named bucket. Derives platforms from
`importlib.metadata.entry_points(group="datrix.platforms")`; the self-test plants facts every run; exit 2 if
fewer than 2 platforms are registered or a live surface unions over nothing.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\block-realization-parity-gate.ps1` | Compare every registered platform's capabilities |
| **Debug** | `.\test\block-realization-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\block-realization-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every capability realized or accounted for, 1 = at least one violation, 2 = self-test or
partition guard failed, fewer than 2 platforms, or a vacuous live surface.

---

### `test\capability-gap-ledger-gate.ps1`

Capability gap ledger gate. Every target package carries its own gaps as `capability_gaps` rows on its own capability declaration; the declarations ARE the ledger (no separate file). The gate censuses those rows from the live declarations of every registered language, client target and platform, prints the row count, enforces a decrease-only two-directional pin on the total and per-target split (`scripts/config/capability-gap-baseline.toml`), and fails a surface that EVERY distinct implementation of an axis carries a row for (a defect in the shared layer, never a per-target gap: a builtin group obligated on the wrong axis, a config surface with no consumer, or an obligation that should not exist). A row suppresses nothing in any other gate; this gate only counts and bounds the ledger.

The pin fails in both directions: live above a pin (a gap was added), live below a pin (rows removed without lowering the pin in the same change), and a row on a target absent from the pin (pinned at zero). The baseline's `total` must equal the sum of its per-target counts.

Derives its target sets from the installed `datrix.languages`, `datrix.generators` (client targets) and `datrix.platforms` entry points at runtime -- never a hardcoded target literal. Registered names sharing one on-disk package fold into one implementation, so the floor and the shared-layer comparison count distinct implementations.

**Built-in non-vacuity self-test, every invocation.** Plants an over-count, an under-count, a per-target split skew, an unpinned row, a synthetic 2-target axis sharing a surface, folded-implementation cases, the two-implementation floor, malformed baselines and a clean matching case. Fails loud (exit 2) if an axis has fewer than 2 distinct implementations or the baseline is unreadable.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\capability-gap-ledger-gate.ps1` | Census every registered target's gap rows and apply the pin and the shared-layer check |
| **Debug** | `.\test\capability-gap-ledger-gate.ps1 -Dbg` | Print every censused row (target, surface, detail) and the total |
| **Self-test only** | `.\test\capability-gap-ledger-gate.ps1 -SelfTest` | Run only the non-vacuity self-test |
| **Alternate pin** | `.\test\capability-gap-ledger-gate.ps1 -BaselinePath <file.toml>` | Compare against another baseline file (proves a raised or lowered pin fails) |

**Parameters:** `-Dbg`, `-SelfTest`, `-BaselinePath`

**Exit codes:** 0 = ledger equals the pin and no surface is carried by every implementation, 1 = a ratchet violation (either direction) or a shared-layer defect, 2 = self-test failed, fewer than 2 distinct implementations on an axis, or the baseline is unreadable or invalid.

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
(`PooledMember.slice_index`, `datrix_codegen_kernel.pooling.contract`) actually reaches that
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
never a hardcoded language-name or `aws`/`azure`/`docker` literal — so a
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
`generate.ps1` runs, `ValidationLevel.FAST` so each language's post-generation toolchain build is
skipped — see below), never a hand-built test context — whose DSL documents an endpoint, an entity,
a field, an enum value, a struct field and a function, each with a published (`///`) comment and an
adjacent source-channel (`//`) comment. Asserts, by parsing the generated artifacts **structurally**
(Python's real `ast` + `tokenize` — a call-keyword `summary`/`description` string constant, or a
class/function/async-function docstring via `ast.get_docstring`, the landing site for a construct
with no decorator surface; a hand-rolled bracket/string-literal-aware lexer for C-family targets such
as TypeScript that either finds a decorator anchor outside any string/comment span and
bracket-depth-tracks to its matching close, or reads a `/** ... */` JSDoc doc-comment block — the
no-decorator-surface landing site, distinguished structurally from a plain `/* ... */` block comment
by its `/**` opener — never a line-oriented regex over a whole file), that the published text reaches
that target's declared published surface and the source text reaches its source surface and never
the published one. The gate is a hard zero: every registered target realizes every
(construct kind, surface) cell, and an unpopulated cell is a hole that fails the gate naming the
target, construct kind and surface. There is no exemption mechanism of any kind.

**Asserts over generated artifacts, not a running/building service.** Generation runs with
`ValidationLevel.FAST` — `fix_imports` + `format_files` run, but `validate_files` (where a language's
toolchain build would otherwise be invoked) is skipped, because the property under test is where the
text lands, not whether the toolchain builds. Each language package proves a real end-to-end
document in its own suite: python against a real FastAPI router's `.openapi()`, and typescript
against a real `tsc` + `SwaggerModule.createDocument()` run over an npm-installed dependency set.
This gate is the repo-level cross-target census.

Derives its target set from `importlib.metadata.entry_points(group="datrix.languages")` at
runtime — never a hardcoded language-name literal.

**Built-in non-vacuity self-test, every invocation.** Confirms every marker text is actually present
in the fixture DSL itself, then proves each structural extractor (Python ast/tokenize including
docstring detection, the C-family decorator-anchor lexer, the C-family `/** ... */` doc-block reader
— including a negative proof that a plain `/* ... */` block comment is never mistaken for one) finds
a known-present published/source text in a synthetic snippet it has never seen and never leaks a
source comment into the published set. A planted unpopulated cell is proven to fail the gate, with
no input that excuses it. Fails loud
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

**Output:** `D:\datrix\.tmp\documentation-realization-parity-gate-report.json` (per-target census:
checked/populated/holes, the list of holes, the coverage block with each target's attached/reached/
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

Cross-language builtin-claims parity gate. Reads every registered `datrix.languages` plugin's
`LanguageCapabilityDeclaration.realized_builtin_groups` and `capability_gaps` and checks two surfaces,
neither with a reviewed-gap path (a divergence is always a real defect):

1. **Claim accounting** — a language's realized set names only real `BuiltinGroup` members; every group it is
   obligated to realize (derived from the group's own axis through `obligated_groups`) is realized or carried
   as a `builtin_group:<id>` gap row; a group both realized and rowed is a stale row. Each tracked gap row is
   logged on a live run.
2. **Realized-group mapping coherence** — every `BUILTIN_REGISTRY` row whose group the language realizes is
   mapped by its profile, whether or not the language carries a gap row. Re-derives, as an independent
   backstop, the judgment `register_builtin_capability` enforces at plugin import.

Language set from the installed `datrix.languages` entry points. Built-in non-vacuity self-test every
invocation: planted frozensets (a clean language, an unknown realized name, an unaccounted obligated group, a
rowed obligated group, a stale row, an unmapped key of a realized group, an extra client-axis group). Exit 2
if fewer than 2 languages are registered.

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

**Response-body transform census.** The comparison above reads the emitted response classes, so a
transform applied after serialization (a global interceptor, a response-model setting that changes
field names) is invisible to it. Each registered language declares the regular expressions that
spell such a transform in its framework
(`LanguageCapabilityDeclaration.response_body_transform_idioms`, required and non-empty); the gate
greps the same generated tree for them. Every hit must be a typed `transform_exemptions` entry in
`body-wire-naming-exemptions.json` (`{language, path_suffix, matched_text, reason}`) -- the
TypeScript `MetricsInterceptor` registration (`APP_INTERCEPTOR` in `src/app.module.ts`), which never
touches the body, is the one entry. An unexempted hit, an exemption that matches nothing, and a
language with no declaration each fail by name.

Derives its target language set from `importlib.metadata.entry_points(group="datrix.languages")`
at runtime -- never a hardcoded language-name literal.

**Built-in non-vacuity self-test, every invocation.** Plants a `useGlobalInterceptors(` hit in a
scratch tree and requires the transform census to report it at its coordinates (and to honour an
exemption, flag a stale one, ignore a clean file and refuse an undeclared language). Proves the comparator flags a genuinely
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
divergence is exempted) and no unreviewed response-body transform exists, 1 = an unexempted
divergence or transform was found (or a registered language has no implemented extractor), 2 = the
non-vacuity self-test failed or fewer than 2 languages are registered.

---

### `test\enum-classifier-conformance-gate.ps1`

Cross-target enum-classifier conformance gate. Proves every registered
`datrix.languages` plugin that emits enum types realizes `equalsKeyword`/`containsKeyword`
identically for a fixture keyword-bearing enum: a hit returns the correct member, a miss without
fallback raises the language's declared unrecognized-value exception (`LanguageProfile.errors`)
with a message naming only the enum type (no input/keyword disclosure), and a miss with fallback
returns the fallback. These classifiers are deliberately NOT `BUILTIN_REGISTRY` entries (the
registry is keyed by fixed category names and a user enum is never one of those categories), so
this gate is the coverage the closed registry would otherwise provide.

Derives its target language set from `importlib.metadata.entry_points(group="datrix.languages")`
at runtime, then narrows to enum-emitting languages from each plugin's own registered `"enum"`
sub-generator domain — never a hardcoded language-name literal.

**Built-in non-vacuity self-test, every invocation.** Feeds the comparator a synthetic
fully-conformant pair (must report zero violations) and a synthetic partially-broken pair (must
report exactly the broken language), and the verdict over each result passes the first pair and
fails the second with no exemption input. Fails loud (exit 2) if fewer than 2 enum-emitting
languages are registered.

The gate is a hard zero: every enum-emitting registered language must be fully conformant. A
language that is not fails the gate naming the missing classifier behaviour, and no exemption of
any kind exists.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\enum-classifier-conformance-gate.ps1` | Compare every registered enum-emitting language's classifier conformance |
| **Debug** | `.\test\enum-classifier-conformance-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\enum-classifier-conformance-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every enum-emitting registered language is fully conformant, 1 = a
conformance gap was found, 2 = the non-vacuity self-test failed or fewer than 2 enum-emitting
languages are registered.

---

### `test\gendsl-corpus-resolution-gate.ps1`

GenDSL D1/I1 corpus proof: eager builder/call-expression reference resolution runs at
`@generator_definition` registration time (`datrix_codegen_kernel.gendsl.resolver`). Importing
each discovered target's genDSL definitions module IS the assertion: a bad reference raises
`GenDSLReferenceResolutionError` at import time.

**Target set is derived, never hardcoded.** The module list comes from
`datrix_codegen_kernel.gendsl.target_registry.target_kind_map()` +
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
| **Run gate** | `.\test\toolchain-free-suites-gate.ps1` | Scan every `datrix-*` package suite, every shape |
| **One suite** | `.\test\toolchain-free-suites-gate.ps1 -Suites D:/datrix/datrix-codegen-typescript/tests` | Scan one or more comma-separated `tests/` directories |
| **New shapes only** | `.\test\toolchain-free-suites-gate.ps1 -Shapes suite-in-suite-pytest,suite-in-suite-script` | Enforce only the two suite-in-suite shapes at hard zero, independent of the pre-existing `in-process-execution`/`toolchain-subprocess` counts |
| **Self-test** | `.\test\toolchain-free-suites-gate.ps1 -SelfTest` | Prove the detector is non-vacuous, skip the real scan |

**Parameters:** `-Suites <path[,path...]>`, `-Shapes <kind[,kind...]>`, `-SelfTest`

**Fails on:**
- A toolchain subprocess: `javac`, `java`, `mvn`/`mvnw`, `gradle`, `dotnet`, `tsc`/`tsx`, `npm`/`npx`, `node`, `docker`, `az`, `aws`, `gcloud`, `kubectl`, `terraform`, `bicep` -- whether named as a literal or resolved through a helper.
- In-process execution of generated source: `exec(compile(...))`, `runpy.run_path`/`run_module`, `importlib`'s `spec_from_file_location`/`exec_module`.
- **`suite-in-suite-pytest`** -- a `subprocess` call spawning a nested pytest session against a repo test path: `pytest`/`py.test` as argv[0], or the `[sys.executable, "-m", "pytest", ...]` module form.
- **`suite-in-suite-script`** -- a `subprocess` call naming any script under `datrix/scripts/` (directly, or via `powershell -File`), whether the path is one joined literal or assembled from separate `Path(...) / "datrix" / "scripts" / ... / "x.ps1"` segments (still Call-node-local -- no cross-statement variable tracing).

**Never fails on:**
- Linters over generated TEXT (`ruff`, `black`, `isort`, `mypy`) -- reading is not executing.
- Subprocess runs of datrix itself (`sys.executable -m datrix_cli`, the import-boundary probes) -- that is framework functionality, not generated output.
- Loading a sibling `test_*.py` for a shared harness -- that is this suite's own code.
- A `pytester`-based synthetic suite (a test function taking a `pytester` fixture parameter, or a direct `pytester.runpytest*(...)` attribute call) -- pytest's own plugin, launching a nested run against a SYNTHETIC tree in a tmp dir, never against this repo's own production tests. E.g. `datrix-testing/tests/unit/test_xdist_pooling.py`'s `pytester.runpytest_subprocess(...)`.

**No baseline or exemption file for either new shape** -- unlike the slow-test ratchet, both `suite-in-suite-pytest` and `suite-in-suite-script` are hard zero; `-Shapes` scopes which kinds a run enforces, it does not exempt individual sites.

**Assertions:** the non-vacuity self-test runs before every real scan (a planted `javac` call, a planted `exec(compile(...))`, a planted nested-pytest subprocess, and a planted repo-script subprocess must all be caught; an allowed `ruff` call, an allowed `sys.executable -m datrix_cli`, a `pytester`-fixture test, and a `pytester.runpytest(...)` call must all pass), so a green result can never mean the detector was broken.

**Exit codes:** 0 = no violation of the requested shape(s), 1 = at least one violation, or the self-test failed.

---

### `test\slow-test-ratchet-gate.ps1`

**The repo's decrease-only ceiling on test wall time.** Reads the newest FULL run's merged
`timings.json` (written by `test.runner_plugin`, merged by the shared test
runner) for every testable package -- discovered the same way `test.ps1`/`status-tests.ps1` do,
never a hardcoded list -- and fails on:

- **A call ceiling:** any test whose call-phase duration exceeds 30.0s (strict -- 30.0s itself is
  not an offender, 30.1s is).
- **A fixture-replication ceiling:** any session/package/module-scoped fixture set up on more than
  one DISTINCT xdist worker (keyed by the recorded worker id, never by occurrence count -- a
  module-scoped fixture set up twice on the SAME worker is not replication) with a setup duration
  exceeding 5.0s on at least one of those workers (strict -- 5.0s itself is not an offender, 5.1s
  is).

...unless the offending id is listed in `datrix/scripts/config/slow-test-baseline.json` with a
`class` (one of `matrix-in-one-test`, `session-fixture-per-worker`, `whole-corpus-scan`,
`toolchain-compile`) and a written `reason`. A Node package (`datrix-vscode`) carries no
runner_plugin/timings.json -- its merged JUnit XML's own per-`<testcase>` `time` attribute is the
only call-duration signal, so it has no fixture dimension at all.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\slow-test-ratchet-gate.ps1` | Check every package's newest full run against the baseline |
| **Self-test** | `.\test\slow-test-ratchet-gate.ps1 -SelfTest` | Prove the detector is non-vacuous, skip the real scan |
| **Seed the baseline** | `.\test\slow-test-ratchet-gate.ps1 -Seed` | Write the baseline from the current offenders (placeholder `class`/`reason` -- hand-edit every entry before commit) |

**Parameters:** `-SelfTest`, `-Seed`, `-Dbg`

**Decrease-only, enforced in every mode against git, not just the working-tree file.** Both check
mode and `-Seed` compare against the baseline **as committed at HEAD** in the `datrix` package's
own git repository (`git -C <repo> show HEAD:scripts/config/slow-test-baseline.json`), never
merely against the file on disk: a key may never be added and a `seconds` value may never
increase relative to what HEAD carries. A path absent at HEAD reads as an empty baseline (first
seed, allowed). Any other git failure fails closed (exit 2) -- decrease-only cannot be verified
without a trustworthy committed reference.

**A stale entry fails the gate.** A baseline entry that no longer measures as an offender must be
REMOVED, never left as harmless cover -- except a `toolchain-compile` entry, which this gate never
drives to zero and is permanently exempt from the staleness check. A baseline entry whose `class`
or `reason` still carries the `-Seed` placeholder (`REPLACE-WITH-REAL-CLASS`/
`REPLACE-WITH-REAL-REASON`) is rejected outright (exit 2) -- it was never hand-classified.

**Fails closed on missing data.** A package with no v2 full run (`index.json` `schema_version >= 2`
and `selection.kind == "full"`) recorded at all -- including a Node package whose `.test_results`
exists but never produced a usable full run -- is reported under `missing_full_run` rather than
silently passing.

**Exit codes:** 0 = no un-baselined offender and no stale entry, 1 = an offender, a stale entry, a
missing full run, or a working-tree baseline that grew relative to HEAD, 2 = an invalid baseline,
an untrusted git read, or `-Seed` would grow the baseline committed at HEAD.

---

### `test\standing-conformance-gate.ps1`

Standing conformance-spec corpus gate: runs every committed `conformance_gate.py` spec under `scripts/config/conformance-specs/` (top-level `*.json` files only -- fixture subdirectories such as `_fixtures/` are never swept). Each spec's own self-test runs first, exactly as `conformance_gate.py`'s single-spec CLI already guarantees on every invocation.

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

### `test\code-index-gate.ps1`

Behaviour checks for the code index (`scripts/library/code_index`) and its entry points (`dev/code-index.ps1`, the MCP server `library/dev/code_index_mcp.py`, and the logic-map consumers). Each check builds a real workspace of git repositories in a temporary directory and runs the real index over it. The checks cover:

- extraction: definitions, imports and references, a file with a syntax error, and wrapped `@rule` lines
- the file set: git visibility and config excludes
- incremental refresh: a touched-but-unchanged file is not re-parsed, and deleted files leave the index
- references resolved through aliases, re-exports and module imports
- the method-reference caveat
- the logic-map rewrite happening only when markers change
- search and canonical topic matching
- model summaries against a real loopback model server, the summarize lock (exclusive, stale locks taken over), and the background summarize run (started only when modules are pending and no run holds the lock, by the CLI and by the MCP server when its refresh changes files)
- the MCP protocol, in-process and as a subprocess whose stdout must carry only protocol
- the code scan's additions (`dev/code-scan.ps1`): index verdicts for dead-code findings (dead, test-only, refuted by another file's use, unmatched), names used through strings and templates, and changed-package selection

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\code-index-gate.ps1` | Run every check |
| **One area** | `.\test\code-index-gate.ps1 -Only check_references` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\test\code-index-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

---

### `test\task-orientation-gate.ps1`

Behaviour checks for task orientation and citation validation (`scripts/library/tasks/task_orientation.py`, `task_citations.py`, `validate_task.py`, wrapped by `tasks/validate-task.ps1`). Each check builds a real workspace in a temporary directory (framework repositories with real Python, task files under `.tasks/phase-NN`) and runs the real code index over it; explanations are answered by a real model server on loopback, never the network's. The checks cover:

- the `## Orientation` block read by the one task parser (`parse_task_file`), and prose lines that exclude code fences
- every malformed entry rejected with what to write instead; every question that asks where something is defined or who calls it rejected (a local model invents those answers; `symbol` / `refs` answer them exactly)
- the resolver: facts exact from the index, a stale entry called out as a stale premise, an explanation marked as a lead, no model server leaving the facts intact
- the citation checker: missing file / line past the end / backwards range are errors; an abbreviated path, a relative path or bare file name that several repositories carry, and a file another task of the phase creates are not errors; a name written beside a citation that is nowhere near its lines is a warning; names elsewhere in the sentence, language names and code fences are ignored
- the validator end to end (`--phase`, `--require-orientation`) and its exit codes

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\task-orientation-gate.ps1` | Run every check |
| **One area** | `.\test\task-orientation-gate.ps1 -Only check_citations` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\test\task-orientation-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

---

### `test\local-llm-gate.ps1`

Behaviour checks for the local-model reading tools: the reading layer (`library/shared/local_reading.py`) and the MCP server built on it (`library/dev/local_llm_mcp.py`). Each check builds a real workspace in a temporary directory (two framework repositories, a customer-style repository beside them, `.tmp` and `.test-output`) and answers through a real OpenAI-compatible server on loopback whose answers depend on the prompt. It never contacts the network's model servers, and it records requests in a temporary usage log, never the machine's own. The checks cover:

- scope: framework repositories and `.test-output` are read; another repository, `.tmp`, `..` escapes, `.git` internals and paths outside the workspace are refused; a glob reaching out of scope is refused whole; at most 40 files per call
- chunking: every chunk opens with its file's header and keeps original line numbers; a long file is split at line boundaries
- log reduction: a large log is cut to the lines around error markers, or to its end when it has none
- answering: one request for one chunk; one request per chunk plus a merge for more; a citation of an unsent file or line is called out (for a log, only citations of the log itself are checked)
- the MCP server: tool listing, an answer, an out-of-scope refusal, bad arguments, no model server reported as a tool error, the usage log entry under `mcp:<tool>`, and stdout carrying only protocol

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\local-llm-gate.ps1` | Run every check |
| **One area** | `.\test\local-llm-gate.ps1 -Only check_scope` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\test\local-llm-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

---

### `test\ineedtoknow-gate.ps1`

Behaviour checks for `dev\ineedtoknow.ps1` (`library/knowledge/*`, `library/dev/ineedtoknow_cli.py`). Each check builds a real workspace in a temporary directory (framework repositories plus a customer-style repository), uses real SQLite files, and answers through a real OpenAI-compatible server on loopback. It never contacts the network's model servers and never touches the machine's own knowledge base. The checks cover:

- chunking: a chunk's body equals the document's own lines `line_start`..`line_end`; a `#` line inside a code fence is not a heading; a long section splits into bounded chunks that keep every line
- sync: docs are added, updated by content hash and removed; a customer repository never enters the knowledge base
- lookup: a question is answered only by a chunk covering most of its significant words (camelCase identifiers match their words); unrelated and stopword-only questions find nothing
- the committed text copy: a learned file round-trips and a hand-edited id, a missing front matter, a bad source hash or an empty answer is refused; a second machine converges from the files alone, a rebuild restores them, and deleting a file drops the answer
- expiry: an answer whose cited file changed is not returned, not imported by another machine, never deleted by a sync, and deleted by `-Prune`
- gathering: the model is sent the closest chunks with their real line numbers and no customer text; an answer is stored only when grounded (no citation, a citation of an unsent file or line, quoted code that was not sent, and "nothing relevant" are each rejected and write nothing); no model server raises `LocalLlmUnavailable`

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\ineedtoknow-gate.ps1` | Run every check |
| **One area** | `.\test\ineedtoknow-gate.ps1 -Only check_gather` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\test\ineedtoknow-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

---

### `test\pre-review-gate.ps1`

Behaviour checks for the first-pass pre-review (`scripts/library/git/pre_review.py`, wrapped by `git/pre-review.ps1`), over real git repositories in a temporary directory. It covers:

- the diff parser
- every definite rule firing on added lines only, with planted old violations as the non-vacuity control and Protocol/ABC declarations exempt
- pending changes read from git (untracked files included, ignored files excluded)
- model findings dropped unless high-confidence, on an added line, and quoting that line
- the model review staying advisory and off test files, against a real loopback model server

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\pre-review-gate.ps1` | Run every check |
| **One area** | `.\test\pre-review-gate.ps1 -Only check_model` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\test\pre-review-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

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
case). Repo-level validation **script**, not a pytest suite (per the datrix showcase boundary).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\test-tooling-parsing-gate.ps1` | Run all 39 absorbed checks |
| **Harness self-test** | `.\test\test-tooling-parsing-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\test-tooling-parsing-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** 39 named checks covering `compare_tests.py`, `status_tests.py`,
`run_complete.py`'s generated-project metadata derivation, the structured-output writers, and the
Node test runner. Several are
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
rigorously (8 sequential + 8 concurrent racers). It also covers `shared/local_llm.py` — model
server discovery, candidate order, request shapes, readiness, failover to the next server, and the
no-server outcome — against real HTTP servers it starts on loopback, and `shared/llm_code_fix.py`
(code-answer parsing; a ruff verification that cannot run fails closed). Repo-level validation
**script**, not a pytest suite (per the datrix showcase boundary).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\shared-library-gate.ps1` | Run every check |
| **One module** | `.\test\shared-library-gate.ps1 -Only check_local_llm` | Run only checks whose name starts with the prefix |
| **Harness self-test** | `.\test\shared-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\shared-library-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Only <prefix>`, `-Dbg`

**Assertions:** 72 named checks covering `structured_log_writer.py`, `test_runner.py` (including
the `-Tag` pre-flight that refuses an unknown or whole-tree tag selection before any phase),
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
an `xdist_group` mark, and `datrix-codegen-typescript` pools its `npm_tsc` tests through such
marks — a downgrade to plain `--dist load` would silently un-bound that pool without failing
anything else. Several checks are inherently adversarial
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

**The repo's proof that no `.gitignore` rule is silently deleting a publishable file.** For the `datrix` showcase repo and every `datrix-*` clone in the workspace (discovered from disk at runtime — a new package is covered with no edit to the gate), it computes the set difference between the working tree and what a `git add -A` would stage. Every element of that difference must be a reviewed, scoped entry in `scripts/config/ignored-source-exemptions.json`; anything else is a source file that exists locally and will not survive a clone. An entry names the ignore rule by its pattern text and by a segment-aware glob over the repo-relative path of the `.gitignore` file git blames (a literal path matches only that file; `examples/**/generated/**/.gitignore` matches the nested files a generator writes into each emitted project), and scopes the paths it excuses with `path_glob`. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), and the gate's own self-test is its coverage.

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

**Four reference shapes are matched, over all of `.py .ps1 .json .md .j2 .ts .mts .cts .js .mjs .cjs .cs .java .toml .yaml .yml .dtrx`** (spelled here with `N`/`M` placeholders so this page is not itself a hit): a task-file id (`task-NN-MM`, the prose `task NN-MM`, and the three-digit `task-NN-MMM`, case-insensitively), a design path (`design/NNN-slug`), a design number (`design NNN`, `design-NNN`, `design doc NNN` — the word `doc` is optional), and a phase directory (`.tasks/phase-NN`). Each line is also matched joined to the next with that line's comment leader (`#`, `//`, ` * `, `--`) removed, because a wrapped comment splits a reference across the break (`(design` / `# NNN section …`) and a line-at-a-time match sees neither half; a hit is reported at the line it starts on. A **bare** `Phase NN` is deliberately NOT matched: the committed architecture docs use it as product vocabulary for delivery waves, self-contained text rather than a pointer into a gitignored tree.

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
| **No consumers** | `.\test\affected-gate.ps1 -Projects datrix-codegen-typescript -NoConsumers` | Run only the changed package(s); every importer is excluded |
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
