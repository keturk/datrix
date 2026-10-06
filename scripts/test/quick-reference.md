# Quick Reference — Testing Scripts

The test runner, status and failure analysis, and the gates that hold the test tooling itself.
Cross-target and repository gates are in [../gates/README.md](../gates/README.md).

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
| **No failure digest** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -NoDigest` | Skip the failure digest printed under the summary |

Whole-suite modes (Jon only): a bare package (`.\test\test.ps1` + package names), a folder path, `-All`, `-Rerun` (re-run projects whose latest log reports failures), and the tier switches `-Unit` / `-Integration` / `-E2E` / `-Fast` (excludes slow) / `-Slow`.

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rerun`, `-Coverage`, `-VerboseOutput`, `-NoSave`, `-NoAutoInstall`, `-Unit`, `-Integration`, `-E2E`, `-Fast`, `-Slow` (mutually exclusive), `-Specific <path[,path...]>` (comma-separated files/node-IDs run in one pytest session), `-Keyword <expr>`, `-Tag <tag[,tag...]>` (feature tags; a test runs when it carries any of them), `-ListTags` (list tags, run nothing; with `-Specific`, scoped), `-NoDigest` (print no failure digest), `-Dbg`

The runner is `datrix_scripts.test_project` (in `common/lib/`), run as a module.

**Failure digest.** After the summary table, every failed package whose run was saved gets a short digest from `common/lib/datrix_scripts/run_digest.py`, also written to `digest.txt` in the run directory. It lists the run's failure groups (the `collect-failure-data.ps1` families, labelled `E1..` for errors and `F1..` for failures) with count, pattern, source location and a re-run command. It also says what changed since the newest earlier run of the package with the same `selection` (new failing tests, still failing, fixed — `classify-run-delta.ps1`'s counts; each group is marked `[new]` or `[seen before]`). From a resident local model it adds a one-paragraph hint per group (first 5) and, when there are several groups, one reading of which share a cause and which to fix first. Model text is labelled with its model and is a lead to confirm, never a finding. Every prompt goes through the customer-term filter, and nothing is sent without the corpus. Only resident models are used (no cold load), with a 60 s request timeout. When no model answers, one `Model: no hint (...)` line says why and the digest carries the deterministic part alone. A digest that cannot be written prints `No failure digest for <package> ...` and never changes the exit code. The run also gains `failure-data.json` and, when an earlier comparable run exists, `run-delta.json`. About 15 s on a three-group run. The `digest-red-test-run.py` hook asks no model for a run that has `digest.txt`, because its console output already carries the digest.

**Feature tags.** Every test carries one or more feature tags (pytest `tag` marker; Node `#tag` token in a test or `describe()` name). They are declared by `datrix_common.testing.feature_tags`, a `pytest11` plugin every session in the venv loads; `test.ps1` runs every session with `--datrix-require-tags`, so an untagged test fails at setup (an untagged Node test fails the run). `-Tag` fails a package in which no test carries a named tag (a misspelling never shrinks a run silently), refuses a selection that keeps every test of a package's whole test tree (the full suite in disguise), and cannot be combined with `-Keyword` on a Node suite. Both refusals are decided **before any test phase starts**: a pytest package's `-Tag` run first does one collection-only pass in a single process over the run's own targets, and a refused selection exits 4 with the plugin's message and no run directory — never discovered inside every xdist worker after each has collected the whole tree. A tier name (`unit`, `slow`, `serial`, …) is never a tag. Rules and vocabulary: `datrix-common/docs/contributing/test-guidelines/feature-tags.md`. A run's `index.json` records `selection.tags`.

**Log output:** Unless `-NoSave` is used, `test.ps1` creates one timestamped log folder for each project it runs under that project's `.test_results` directory. AI agents do not need to capture full console output; read the final console lines to find the saved log folder, then inspect the files in that folder.

**Selection and suite-input stamp (`index.json` `schema_version: 2`):** every saved run records `selection` — `{"kind": "full"}` for a bare `test.ps1 <package>`, otherwise `{"kind": "targeted", "specific", "keyword", "tier", "marker", "tags"}` for `-Specific`/`-Keyword`/`-Tag`/any tier switch. Only a full run whose every phase completed records `inputs` (the suite-input fingerprint over the package's cone, installed set, interpreter, and observed foreign paths and executables); a targeted run never has an `inputs` key, so it can never stand in for a full one. A full run loads `datrix_scripts.runner_plugin` (`-p`) in every phase and also leaves `observed-*.json` / `deselected-*.json` / `timings-*.json` / `workers-controller.json` records and a merged `timings.json`; any other saved run loads it in its parallel phase only and is never stamped. **The serial phase runs only when needed:** when every parallel worker's `deselected-<worker>.json` says it deselected 0 items (so no collected test is `serial`), the serial phase is skipped — `full.log` says `Phase 2: serial tests SKIPPED -- …` and `index.json` records `"phases": {"Serial": "skipped (0 serial items)"}` with no `junit-serial.xml`. It runs on any missing evidence (`-NoSave`, a worker the controller listed with no record, a parallel phase that did not complete), under a marker or keyword filter (`-Unit`/`-Fast`/`-Keyword`/…; `-Specific` is not a filter), and when workers deselected items. Workers disagreeing on the count, or an unreadable record, is a runner error: the serial phase runs and the run is FAILED with the reason in `index.json` `runner_errors`. When a full run cannot be stamped (a phase did not complete, a session's records are missing, or a cone tree changed while it ran), `full.log` says why and `index.json` has `selection` but no `inputs`. Field reference: [README.md](README.md#package-run-indexjson-schema-version-2).

**Never run two `test.ps1` invocations at once — batch the projects into ONE call instead.** `-Projects` is variadic and iterates sequentially, so `test.ps1 a b c` is the supported way to cover several packages. Before running anything, `test.ps1` calls `Ensure-DatrixPackagesInstalled`, which takes a **workspace-wide exclusive package lock** (`scripts/common/venv.ps1`, 120s acquisition timeout) shared with `generate.ps1` — it guards the install/repair phase against concurrent writers of the one shared venv. A second concurrent invocation therefore blocks for up to two minutes and then dies with `Could not acquire package lock - another process may be installing packages`, having run **no** tests. The one sanctioned concurrency is `affected-gate.ps1` (Jon's tool — agents never run it), and it does not contend here: it runs that install check **once**, before any child, and launches every `test.ps1` child with `DATRIX_PACKAGES_ENSURED=1`, which makes `test.ps1` skip its own check (with `DATRIX_VENV_VERBOSE=1` it prints `Package install check skipped: the caller already ran it` instead). `test.ps1` restores its caller's value of that variable on exit, so a run started in your own shell never leaves it set for the next direct run — a direct `test.ps1` always performs its own check.

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

**Steps:** Step 1 (syntax checker, `scan\syntax-checker.ps1`) → Step 2 (code generation) → Step 3 (unit tests) → Step 4 (deployment tests: spec + integration). Step 5 is deprecated (merged into Step 4).

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

**Parameters:** `-ExamplePath` (positional 0), `-OutputPath` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (python\|typescript, **mandatory**), `-Platform`/`-P` (output-path runtime segment, default: docker-compose; provider segment comes from each project's `config/system.dcfg`), `-Hosting`/`-H`, `-TestSet` (default: all), `-Rerun`, `-VerboseOutput`, `-SkipVenv`, `-Skip1`, `-Skip2`, `-Skip3`, `-Skip4`, `-Skip5` (deprecated), `-FreshBuild`, `-Dbg`/`-DebugLogging`, `-LlmSummary`, `-LlmLimit` (default: 12), `-LocalMachines` (default: the list in `common/lib/datrix_scripts/local_llm.py`), `-LlmModel` (default: any model already in memory), `-LlmTimeout` (default: 180), `-LlmNumPredict` (default: 4096), `-LlmTemperature` (default: 0.1)

**Note:** Deploy tests (Step 4) use Docker cache by default for faster builds and better network resilience. Use `-FreshBuild` to force `--no-cache` for maximum validation confidence. `-Skip5` is accepted but deprecated (Step 5 merged into Step 4).

**LLM advisory summary:** Pass `-LlmSummary` to print a post-run advisory summary generated by a local model against the aggregate result indexes. The model is whichever server `common/lib/datrix_scripts/local_llm.py` finds first on the local machines (Ollama, vLLM or llama-server), failing over to the next. All `-Llm*` and `-LocalMachines` parameters only take effect when `-LlmSummary` is set.

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

**A human-only tool, enforced.** No skill, hook, orchestrator, or other script runs it: its only caller is `affected-gate.ps1`'s opt-in `-Mypy` switch. The agent contract forbids agents to run any standalone type-checker (`CLAUDE.md`, "Running Python"), and that is now a harness block rather than prose -- `guard-forbidden-commands.py` refuses `mypy`/`dmypy`/`pyright`, the `python -m mypy` form, this wrapper, `test/lib/mypy_check.py`, and `affected-gate.ps1 -Mypy` from any agent tool call. A person running it in his own terminal is not a tool call and is unaffected. For agents, the tests of the code they changed are the gate for type correctness; this wrapper exists so a person can run a full type-check on demand.

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

**The `datrix` showcase repo itself is a valid explicit project name** (e.g. `.\test\mypy.ps1 datrix -Specific "scripts/gates/ratchet/lib/check_generated_file_ratchet.py"`) even though it is excluded from `-All`'s package sweep -- `datrix/pyproject.toml` carries its own `[tool.mypy]` (strict) section for its repo-level validation scripts, but is deliberately never auto-discovered by `Get-DatrixPackageNamesGlobWithPyProject`'s `datrix-*` glob (it is not an installable toolchain package). Always pass `-Specific` for `datrix` -- there is no `src/` layout to default to.

---

## Status Scripts

### `test\status-tests.ps1`

Reports test results from latest test logs for all datrix projects. Reads structured `index.json` when available (new directory format), falls back to regex-parsing flat log files. Runs `datrix_scripts.status_tests` as a module.

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

Builds `failure-data.json` inside a run directory: every error/failure cluster with its representative's traceback tail embedded, `codegen_hint`/`generated_file` when present, and (package runs only) a ready-to-run `test_command`. That command's shape follows the suite the package actually carries — a pytest package gets a `test-single.ps1` node-ID re-run, a Node package (`datrix-vscode`, which has no single-test runner) gets `test.ps1 <pkg> -Specific "<source .ts file>"`, and a package carrying no recognizable suite gets no `test_command` key at all rather than an invocation that cannot run. Supports all three index schemas: package (`structured_log_writer`), generated-project unit (`generated_test_log_writer`), and deploy-test (`deploy_test_log_writer` — deploy adds `failed_phase`; infra errors are keyed `phase#id` and may have `traceback_tail: null`). Runs `datrix_scripts.collect_failure_data` as a module.

**Kept small without losing anything (bundle schema 2).** Clusters sharing one `(kind, pattern)` form a **family** (`families[]`, and `family_id` on each cluster): only the family's first cluster embeds `traceback_tail`, the others carry `traceback_tail_in_cluster: <id>` and keep their own `log_file`. An `error_message` over 20 lines or 2000 characters is cut, marked `error_message_truncated: true`, and ends `[message cut: ...]` — the whole message is in that entry's `log_file`. On an 18-failure datrix-common run this took the bundle from 136 KB to 74 KB (five "drifted" clusters became one family; one 36 KB baseline diff was cut).

**Advisory hints.** The first `-LlmHintLimit` families (default 5, errors first) get a `hint` from a local model server found by `common/lib/datrix_scripts/local_llm.py`: the model is given the message, the traceback and the source around the traceback's in-workspace frames, and answers with a probable defect site, cause and first check. `hint.source` names the server and model, or says `unavailable` (no server answered, or no customer-term corpus) or `skipped` (past the limit / `-NoLlmHints`). Every prompt line carrying a registered customer term is withheld before it is sent (the filter `local_reading` applies), and without the corpus no hint is requested. A hint is a hypothesis to verify in the code, never a root cause. Adds seconds, not minutes (9 s for 5 hints on the run above).

| Mode | Command | Description |
|------|---------|-------------|
| **Run directory** | `.\test\collect-failure-data.ps1 "D:\datrix\datrix-common\.test_results\test-results-YYYYMMDD-HHMMSS"` | Parse an explicit run dir (or its `index.json` path) |
| **Latest run of a package** | `.\test\collect-failure-data.ps1 -Project datrix-codegen-aws` | Auto-locate the newest `test-results-*` run |
| **Longer tracebacks** | `.\test\collect-failure-data.ps1 -Project datrix-common -MaxLogLines 120` | Embed more tail lines per representative (default 60) |
| **No hints** | `.\test\collect-failure-data.ps1 -Project datrix-common -NoLlmHints` | Families and message caps only; no local-model call |
| **Self-test only** | `.\test\collect-failure-data.ps1 -SelfTest` | Parse one fixture index per supported writer schema and check the re-run command emitted for each suite kind; skip the real run analysis |

**Parameters:** positional run-dir/`index.json` path OR `-Project <name>` (exactly one), `-MaxLogLines <n>`, `-NoLlmHints`, `-LlmHintLimit <n>` (default 5; 0 = none), `-LocalMachines <hosts>` (default: the list in `common/lib/datrix_scripts/local_llm.py`), `-LlmModel <models>` (default: any model in memory), `-LlmTimeout <seconds>` (default 120), `-SelfTest`, `-Dbg`

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

Compares two runs of the same package and classifies the delta: `SUCCESS` (all previously-failing fixed, none new), `PARTIAL`, `NO_CHANGE`, or `REGRESSION` (new failures). Writes `run-delta.json` (with `now_passing` / `still_failing` / `new_failures` / cluster-level resolution lists) into the CURRENT run dir. Runs `datrix_scripts.classify_run_delta` as a module.

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

## Affected Packages

### `test\affected-set.ps1`

Derives the reverse-dependency closure of every `datrix-*` package from actual imports (never a hand-maintained table). Discovers packages from disk by `pyproject.toml` presence, builds the import graph from each package's `src/`, `tests/`, and root-level `conftest.py` (the file class that hides test-time-only edges like datrix-common's consumption of datrix-language/datrix-cli) unioned with declared `pyproject.toml` dependencies, and computes each requested package's transitive reverse closure -- the packages whose code may consume a change. It answers "which packages might this change reach"; an agent then confirms each by surface and runs the changed behaviour's feature tags there (`test.ps1 <pkgs> -Tag <tag>`), never their whole suites. `affected-gate.ps1` (human-only) consumes this module directly. Runs `datrix_scripts.affected_set` as a module.

| Mode | Command | Description |
|------|---------|-------------|
| **One package's closure** | `.\test\affected-set.ps1 -Projects datrix-language` | Print datrix-language's reverse closure |
| **Several packages** | `.\test\affected-set.ps1 -Projects datrix-language,datrix-cli` | Print each package's own closure |
| **Every package** | `.\test\affected-set.ps1 -All` | Print every discovered package's closure |
| **Custom output path** | `.\test\affected-set.ps1 -All -Output D:\datrix\.tmp\test\my-closure.json` | Override the JSON output path |
| **Self-test only** | `.\test\affected-set.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite; skip the real derivation |
| **Debug** | `.\test\affected-set.ps1 -Projects datrix-common -Dbg` | Debug logging |

**Parameters:** `-Projects <comma-separated>` OR `-All`, `-Output <path>`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements) covers `discover_packages`, the root-conftest-only import edge (must be detected when the conftest scan is enabled, and adversarially proven ABSENT when it is disabled), BOM-prefixed source files, a cyclic/self-referential edge (must terminate, not hang), the non-vacuity guard (`check_closure_not_smaller_than_declared`), and unreadable/corrupt `pyproject.toml` input. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real derivation, exit 1); `-SelfTest` runs it in isolation and skips the real derivation.

**Assertions:**
- Package discovery is by `pyproject.toml` presence under a `datrix-*`-prefixed directory name -- never a hardcoded list or count.
- An import edge from a package's root-level `conftest.py` (outside both `src/` and `tests/`) is detected exactly as an import from `src/` or `tests/` would be.
- The full (import+declared) reverse closure of every package is never a strict subset of its declared-pyproject-deps-only closure; a violation fails the run loud (exit 1), never silently.

**Exit codes:** 0 = derivation completed (or a successful `-SelfTest` run), 1 = the non-vacuity self-check failed (or `-SelfTest` reports a failing check), 2 = usage error or unreadable input (corrupt/unreadable `pyproject.toml` or source file, unknown `-Projects` name, no `datrix-*` packages found).

### `test\affected-gate.ps1`

**A human-only tool, enforced.** It runs whole package suites, and no agent — subagent or main session, in any skill, gate, or phase — ever runs a whole suite: `guard-full-suite-runs.py` refuses every invocation from an agent tool call except `-SelfTest` (which launches no suite), with no override. Agents verify a change with `test.ps1 -Specific` / `-Tag` (see `test\test.ps1` above). Jon runs this in his own terminal, where no hook applies.

Runs the affected set of Datrix package suites concurrently and returns one GREEN/RED verdict. The affected set is the changed packages (`-Projects`) plus the consumers the change reaches (`-Consumers`), established per "Which packages a change reaches" in `.claude/skills/_shared/verification-strategy.md` — importing a changed package does not make a package affected. Unless `-All`, one of `-Consumers` / `-NoConsumers` is required; without either the gate stops with a usage error listing the packages that import the changed ones. Every such importer not named is printed as `Excluded (…): …` and recorded as `excluded` in `affected-gate.json` and the completion row. The gate schedules `test.ps1 <pkg>` child processes longest-first under a `PYTEST_XDIST_AUTO_NUM_WORKERS` budget so concurrently running children never oversubscribe the machine, and aggregates the final verdict by reusing `gate-verdict.ps1`'s own per-project evaluation -- never reimplementing `index.json` parsing. It only SCHEDULES existing runners; it never duplicates `test.ps1`'s or `gate-verdict.ps1`'s own logic.

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

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures, real git repositories, and `assert` statements) covers the scheduler: on a fixed table of measured per-package CPU seconds, the simulated schedule never has more allotted workers active than cores at any instant (for 1, 2, 8, 12 and 32 cores, and it fills all 12 on the table's own machine), the allotment matches concrete expected worker counts (including the clamps and one `L` for every package), the simulated makespan lies between the CPU lower bound `Σc / n` and 1.25 × it, and no worse than the retired fixed-slot policy (4 slots x floor(n/4) workers) on the same table, `-WorkersPerChild` is a uniform override refused outside `1..cores`, an allotment above the core count is refused, `-MaxConcurrent 1` runs sequentially and `-MaxConcurrent 2`/`3` bound the number of running children; longest-first ordering and the CPU demand read the newest full run (never a newer targeted, selection-less or unreadable run) with the LOC fallback; then same-package double-request rejection, consumer selection (a named consumer runs, every other importer is excluded, a consumer outside the import closure is honoured, and neither/both of `-Consumers`/`-NoConsumers` or a changed package named as a consumer is a usage error), a child that dies without producing an `index.json` forcing RED (never a stale GREEN), and carry: every refusal above forces a run; identical inputs carry and launch no child; `-NoCarry` runs a carriable package; newer targeted runs (RED or GREEN) never hide an older carriable full run; a one-byte change in each of the seven fingerprint components (a cone tree file, an ignored-in-cone file, a foreign tree, an observed executable, the installed set, the interpreter string, the algorithm) runs the package with exactly that component in `diff_components`; `affected-gate.json` rows for a carried and a ran package; `gate_verdict` rejecting a carry claim the run does not support; the completion row sharing the guard's `ts` type (read from the guard's own source) while being told apart by `source`; and install-once: every child's environment carries `DATRIX_PACKAGES_ENSURED=1`, `test.ps1`'s one install call sits inside the guard reading that flag (proven on the real `test.ps1`, with the guard finder shown to reject an unguarded call), `datrix_scripts.test_project` reads the same name, the install check is called exactly once — from `_run`, after the in-progress refusal and before carry and scheduling, never on `-SelfTest` — and real PowerShell processes over planted `venv.ps1` modules show a passing check calls `-SkipIfInstalled` while a failing install, a throwing venv activation and a missing module each raise. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before real scheduling, exit 1); `-SelfTest` runs it in isolation and writes no completion row.

**Assertions:**
- At no point do concurrently-running children's declared `PYTEST_XDIST_AUTO_NUM_WORKERS` values sum above the logical core count.
- The scheduler never launches two live children for the same package.
- A package whose newest run directory has no/INCOMPLETE `index.json` (a run in progress) is refused unless `-Force`.
- A child that exits without naming a run directory of its own is reported RED with reason `CHILD_PRODUCED_NO_RUN`, never silently defaulting to whatever stale prior result exists.
- Every other package is judged on **the run directory its child attributed to itself** — the absolute `index.json` path in the `Details:` line `test.ps1` prints under its own `[PASSED]`/`[FAILED]` block, relayed through the child's stdout and pinned through `gate_verdict.evaluate_projects(pinned_runs=...)`. The newest run directory under `.test_results` is never consulted, neither at child exit nor at verdict time: `test.ps1` holds the workspace package lock only through its install phase, so a targeted `-Specific` run from another session can land a newer directory before **or** after the child exits, and a newest-run lookup then replaces a RED whole-suite result with an unrelated GREEN subset — a 59-test targeted run once stood in for a 5,950-test RED suite this way (the gate printed `OVERALL: GREEN` with exit 0), and later a 7-test targeted run landed mid-suite and stood in for a child that had exited 1 with two failures. A pinned run with no results file is RED with reason `PINNED_RUN_HAS_NO_RESULTS`; it never falls through to the newest run.
- A CARRIED package's `test.ps1` child is never launched (the decision is made before scheduling, not after), and its row is pinned to exactly the full run whose fingerprint matched.

**Exit codes:** 0 = overall GREEN (or a successful `-SelfTest` run), 1 = overall RED, a failed install check, or `-SelfTest` reporting a failing check, 2 = usage error (bad `-MaxConcurrent`/`-WorkersPerChild`, unknown/duplicate package name, both `-Projects` and `-All` given, neither or both of `-Consumers`/`-NoConsumers` given without `-All`, either given with `-All`, a changed package named in `-Consumers`).

---

## Test-Tooling Gates

Plain-Python gates over the test tooling and the scripts tree itself. Repo-level validation
**scripts**, not pytest suites (the datrix showcase repo hosts none).

### `test\shared-library-gate.ps1`

Behaviour checks for the shared scripts package (`common/lib/datrix_scripts/`) and the layout of the
scripts tree, as plain-Python checks (no pytest, no mocks/fakes, real `tempfile.TemporaryDirectory()`
fixtures). They cover:

- the structured-output writers (`structured_log_writer`, `generated_test_log_writer`,
  `deploy_test_log_writer`, `aggregate_test_writer`, `deploy_test_aggregate_writer`): JUnit XML / Jest
  JSON parsing and clustering by normalized error pattern, source-location fallback chains (project
  frame → test frame → conftest-as-test → stdlib-only/no-traceback → `unknown:0`), cross-project
  cluster correlation (representative-project count/alphabetical tie-breaking; suite-failure
  clusters as their own cluster type), deploy-test phase detection from human-readable and structured
  log markers (a Docker-unavailable-with-no-markers or fully empty deploy dir resolves to FAILED at
  docker-build with every phase SKIPPED, never PASSED; a lifecycle failure's message is the failed
  command's captured output), transient-vs-logic failure classification, `failures.json` read as the
  envelope the generated runners write, and per-service counts from each runner's own suite totals
- `codegen_hint_mapper` path mapping; `logging_utils`' log-content and cleanup functions
  (directory-claiming is covered more rigorously by `test-specific-selection-gate.ps1`)
- the test runner (`test_runner`, `node_test_runner`, `suite_stamp`, `suite_inputs`): the
  `-Tag` pre-flight refusing an unknown or whole-tree tag selection before any phase, the parallel
  phase's `-n auto --dist loadgroup` distribution (the only xdist mode that honours `xdist_group`),
  the selection classifier, the suite-input stamp over real git repositories, the serial-phase
  decision over real record files, and each stamp-path module importing first in a fresh interpreter
  (after proving on a planted cycle that the probe sees an order-dependent import cycle)
- `local_llm` (discovery, candidate order, request shapes, readiness, failover, the no-server
  outcome) against real HTTP servers on loopback, and `llm_code_fix` (code-answer parsing; a ruff
  verification that cannot run fails closed)
- **the scripts tree** (`-Only check_scripts_tree`): no retired central `library` folder; every Python file in
  `<folder>/lib/`, `gates/<family>/lib/` or the shared package; no flat `lib/` module named like a
  stdlib or installed module (it would shadow it from `sys.path[0]`); every import resolvable (a
  shared module as `datrix_scripts.<name>`, a flat `lib/` file's siblings by bare name, never a bare
  sibling import from inside the shared package, which runs as `-m`); every script a wrapper runs
  (`Join-Path $scriptDir|$commonDir "…"`, `-m datrix_scripts.<module>`) present; and every script
  path a doc, skill, hook, config or package file in any framework repo names present. Each check
  first proves on a planted fixture that it reports the defect it exists for, and the wrapper and
  reference scans also require a floor of matches, so a matcher that stopped matching fails rather
  than reporting clean.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\shared-library-gate.ps1` | Run every check |
| **One area** | `.\test\shared-library-gate.ps1 -Only check_scripts_tree` | Run only checks whose name starts with the prefix |
| **Harness self-test** | `.\test\shared-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\shared-library-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Only <prefix>`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage error.

### `test\runner-plugin-gate.ps1`

Behaviour checks for the test runner's pytest plugin (`datrix_scripts.runner_plugin`). Every check
spawns a real, separate pytest process (`python -m pytest -p datrix_scripts.runner_plugin ...`)
against a temporary fixture suite and inspects the record files it writes: records never leak file
contents, environment values or CLI arguments; they hold exactly the observed/deselected/timings
facts the session produced, with paths confined to the workspace and transient paths excluded; a
missing or malformed required environment variable is a usage error that names it and leaves no
record; records are named for their worker (`main`, or the real `PYTEST_XDIST_WORKER` id under a
distributed `-n` run, with the controller's `observed-controller.json` / `workers-controller.json`
naming every worker); an existing record file is never overwritten.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\runner-plugin-gate.ps1` | Run every check |
| **Harness self-test** | `.\test\runner-plugin-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure |
| **Debug** | `.\test\runner-plugin-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed.

### `test\test-tooling-parsing-gate.ps1`

Plain-Python checks (no pytest, no mocks/fakes) of how the test tooling reads run results:
`test/lib/compare_tests.py`'s `find_runs`/`build_service_comparisons`/`parse_unit_run`
(direct-child-only `unit-tests-*`/`deploy-test-*` run discovery excluding nested/archived dirs,
service change classification e.g. REGRESSED with OK/FAIL history, the flat-log fallback parser for
`unit-tests-summary.log`, and unit-vs-deploy runs discovered and compared as separate populations),
`datrix_scripts.status_tests`' `TestResult`/`_format_result_row`/`_read_index_json`/
`find_latest_log_file`/`parse_pytest_summary`/`parse_timestamp_from_log_file` (structured
`index.json` parsing including the INCOMPLETE-falls-back-to-`full.log` signal,
`index.json`-preferred-over-`full.log` discovery, directory-name timestamp parsing, and the
in-progress xdist `[ NN%]` progress-percent extraction case), `run_complete.py`'s summary-line
statistics and generated-project metadata derivation, the structured-output writers, and the Node
test runner.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\test-tooling-parsing-gate.ps1` | Run every check |
| **Harness self-test** | `.\test\test-tooling-parsing-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\test-tooling-parsing-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** several checks are inherently adversarial (nested/archived run dirs excluded from discovery, corrupt JSON → `None`, INCOMPLETE result → `None`/fallback, missing `counts` → `None`), which already demonstrates discriminating power; `-HarnessSelfTest` additionally proves the pass/fail harness itself is not vacuous by registering one deliberately-failing dummy check and confirming it is reported `[FAIL]` with a nonzero exit.

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage error.

### `test\test-specific-selection-gate.ps1`

**The repo's proof that `test.ps1 <package> -Specific <file>` really runs THAT file.** A `-Specific` run
that prints `[PASSED]` while its own `index.json` / JUnit XML describe a **different** file's tests is a
silent false green — the caller "proves" a fix that never ran. That was a real, observed defect:
`TeeLogger` named its run directory `test-results-<YYYYMMDD-HHMMSS>` (second granularity) and created it
with `mkdir(exist_ok=True)`, so two `test.ps1` invocations against one package that started in the same
second **shared one run directory** and overwrote each other's `junit-*.xml` and `index.json` — each still
printing its own correct exit code.

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

**Exit codes:** 0 = `-Specific` selects only the requested file and the check is non-vacuous, 1 = wrong-file
selection, shared run directory, or a vacuous comparator, 2 = usage error (`test.ps1` or the named test
files not found).

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

**Exit codes:** 0 = every step held, 1 = a shared or reused log name, an escaped label, unwired
`generate.ps1`, or a vacuous comparator, 2 = `common/DatrixRunLog.psm1` or `dev/generate.ps1` not found.

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
