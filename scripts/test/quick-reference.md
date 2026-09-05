# Quick Reference — Testing Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `test\test.ps1`

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
| **Several test files (one session)** | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py,tests/unit/test_bar.py"` | Comma-separated files/node-IDs run in ONE pytest session — always batch a targeted set this way instead of one invocation per file (commas inside parametrized IDs `[1,2]` are literal) |
| **Keyword filter** | `.\test\test.ps1 datrix-common -Keyword "test_parse"` | Match by keyword (-k) |
| **Verbose output** | `.\test\test.ps1 datrix-common -VerboseOutput` | Verbose pytest output |
| **No log save** | `.\test\test.ps1 datrix-common -NoSave` | Don't save output to log files |
| **Debug logging** | `.\test\test.ps1 datrix-common -Dbg` | Enable DEBUG level |
| **Rerun failed** | `.\test\test.ps1 -Rerun` | Re-run only projects whose latest test log reports failures |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rerun`, `-Coverage`, `-VerboseOutput`, `-NoSave`, `-NoAutoInstall`, `-Unit`, `-Integration`, `-E2E`, `-Fast`, `-Slow` (mutually exclusive), `-Specific <path[,path...]>` (comma-separated files/node-IDs run in one pytest session), `-Keyword <expr>`, `-Dbg`

**Log output:** Unless `-NoSave` is used, `test.ps1` creates one timestamped log folder for each project it runs under that project's `.test_results` directory. AI agents do not need to capture full console output; read the final console lines to find the saved log folder, then inspect the files in that folder.

**Never run two `test.ps1` invocations at once — batch the projects into ONE call instead.** `-Projects` is variadic and iterates sequentially, so `test.ps1 a b c` is the supported way to cover several packages. Before running anything, `test.ps1` calls `Ensure-DatrixPackagesInstalled`, which takes a **workspace-wide exclusive package lock** (`scripts/common/venv.ps1:1547`, 120s acquisition timeout) shared with `generate.ps1` — it guards the install/repair phase against concurrent writers of the one shared venv. A second concurrent invocation therefore blocks for up to two minutes and then dies with `Could not acquire package lock - another process may be installing packages`, having run **no** tests.

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
| `-Fast` | Excludes slow-marked tests; a Node suite marks none, so the whole suite runs (stated on stdout) |
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

**A human-only tool, enforced.** No skill, hook, orchestrator, or other script runs it: its only caller is `affected-gate.ps1`'s opt-in `-Mypy` switch. The agent contract forbids agents to run any standalone type-checker (`CLAUDE.md`, "Running Python"), and that is now a harness block rather than prose -- `guard-forbidden-commands.py` refuses `mypy`/`dmypy`/`pyright`, the `python -m mypy` form, this wrapper, `library/mypy.py`, and `affected-gate.ps1 -Mypy` from any agent tool call. A person running it in his own terminal is not a tool call and is unaffected. The package test suites are the declared gate for type correctness; this wrapper exists so a person can run a full type-check on demand.

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

**Output:** `D:\datrix\.tmp\test\gate-verdict.json` (per-package counts + capped failing-test list). **Exit codes:** 0 = overall GREEN, 1 = overall RED, 2 = usage error.

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

### `test\reference-example-parity-gate.ps1`

**The repo's proof that generated output does not change unintentionally.** For ONE reference
example (`PARITY_EXAMPLE_RELPATH` in `scripts/library/test/reference_example_parity.py`), runs
the **real generation pipeline**
(`datrix_cli.pipeline.generation.GenerationPipeline` — the same code path `generate.ps1` runs,
with the same `PipelineConfig` defaults: profile `test`, `format_output=True`,
`validation_level=STANDARD`) and compares a per-file sha256 manifest of the **whole generated
output tree** against the stored baseline in
`datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256`. Any changed byte in any
generated file, and any file that appears or disappears, fails the gate.

**One example, not the corpus.** `datrix/examples/` covers DSL features; this gate detects
drift, and drift in a shared template surfaces in the FIRST example that renders it — so
sweeping all of them bought redundancy rather than coverage, at one full pipeline run per
example per language. It also made blessing unusable: whole-tree manifests written at example
granularity meant an intentional one-line change could not be blessed without also blessing
every unrelated pending delta in the same tree. The corpus example must generate in EVERY
registered language, which is a real constraint — most examples do not.

Repo-level validation **script**, not a pytest suite (per the datrix showcase boundary), and
`datrix_codegen_common` may not import `datrix_cli`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\reference-example-parity-gate.ps1` | Check the corpus example, once per registered language |
| **Another example** | `.\test\reference-example-parity-gate.ps1 -Example "02-features/01-core-data-modeling/identity"` | Check any example by name, corpus member or not |
| **Debug** | `.\test\reference-example-parity-gate.ps1 -Dbg` | DEBUG logging (very verbose: every pipeline stage) |

**Parameters:** `-Example` (path relative to `datrix/examples/`, optional — default is the corpus
example; an explicit value may name ANY example), `-Dbg`

**Sweeps the registered language set.** The target generation language is a real CLI input
(`datrix generate --language`, forwarded by `generate.ps1`/`generate.py`) rather than a
`config/system.dcfg` field, so every example is genuinely generatable in every registered
`datrix.languages` target. Each selected example is generated and checked once **per registered
language** (derived at runtime from the installed `datrix.languages` entry points — never a
hardcoded `python`/`typescript` literal), against that language's own
`<example_id>/<language>.sha256` baseline. A missing baseline for a swept `(example, language)`
pair is reported loudly as a failure — never silently skipped. Narrowing the EXAMPLE corpus
never narrows the LANGUAGE sweep: a new `datrix-codegen-<lang>` package is picked up with no
edit here. Bless new `(example, language)` baselines with `regen-parity-baselines.ps1`.

**Non-vacuity is enforced on every run.** Before trusting any comparison, the gate copies a real
generated tree, mutates one byte of one file, and requires that the comparison reports exactly
that path as CHANGED with a rendered unified diff. If the comparator cannot detect a real change,
the gate fails regardless of how the examples compare.

**Reading a failure.** The report names **every** changed / added / removed path (not "the first
divergent file") and, when a local baseline cache from the last bless is present under
`.test-output/parity-baseline-cache/`, renders a real **unified diff** of each changed file. The
freshly generated tree is left under `.test-output/parity-current/<example_id>/`.

**Known non-generating examples** live in `scripts/config/parity-known-nongenerating.json` with a
pinned `expected_count`, and are reported loudly on every run — never silently skipped.

**A parked pair is never just skipped — check mode attempts generation for it.** The recorded
reason for a parked, baseline-less `(example, language)` pair can go stale (the underlying defect
gets fixed by unrelated work, and nothing announces it). Every check run generates each parked
pair into its own scratch tree (never the bless cache, so a failed probe never pollutes the diff
cache real blessed generations populate) and branches on the outcome: if generation now
**succeeds**, the gate FAILS with `PARKED PAIR NOW GENERATES — remove its entry from
parity-known-nongenerating.json, decrement expected_count, and bless with
regen-parity-baselines.ps1`; if it still fails, the outcome stays `skip`, reported with the
recorded reason plus the fresh error's first line (so a stale recorded reason is visible without
becoming a hard failure).

**Blessed-coverage ratchet.** Every check run also compares the live count of `.sha256` files under `scripts/config/parity-baselines/` against the pinned value in `scripts/config/parity-blessed-count.json`; a live count LOWER than the pinned value fails the gate (a baseline was deleted without a park entry). Growth never fails. `regen-parity-baselines.ps1` is the only writer of the pinned value.

**Exit codes:** 0 = every example matches its baseline and the comparator is non-vacuous,
1 = drift / missing baseline / generation failure / self-test failure, 2 = usage or config error.

---

### `test\regen-parity-baselines.ps1`

**The single re-bless command** for the reference-example parity gate. Regenerates the stored
baselines by running the same real pipeline **once per registered `datrix.languages` target**
(never a hardcoded `python`/`typescript` literal) and writing a per-file sha256 manifest to
`datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256`. This is the **only**
sanctioned baseline writer — the gate never writes baselines (no auto-heal). Run it deliberately,
**after** you have explained the change.

| Mode | Command | Description |
|------|---------|-------------|
| **Re-bless the corpus** | `.\test\regen-parity-baselines.ps1` | The normal case: the corpus example, once per registered language |
| **Re-bless another example** | `.\test\regen-parity-baselines.ps1 -Example "02-features/01-core-data-modeling/identity"` | Bless any example by name, corpus member or not |
| **Debug** | `.\test\regen-parity-baselines.ps1 -Dbg` | Debug logging |

**Parameters:** `-Example` (path relative to `datrix/examples/`, optional — default is the corpus
example; an explicit value may name ANY example), `-Dbg`

**Why the explicit `-Example` still reaches beyond the corpus:** other repo gates bless a
specific example's baseline as their own byte-level proof — `ingress-migration-conformance-gate.ps1`
does exactly this for the identity example — and narrowing the gate's default corpus must not
take that capability away. The full generated tree of each blessed example is kept under
`.test-output/parity-baseline-cache/` so a later failing gate can show a real unified diff.

**Note:** an example that cannot generate is never blessed — the run fails and names it. Always
review the resulting baseline diff before committing: **an unexpected baseline change is a
generator regression, not a baseline update.**

**Also updates the blessed-coverage ratchet** (`scripts/config/parity-blessed-count.json`) in the same operation as any successful bless — the check gate's proof that coverage can never silently regress.

**Exit codes:** 0 = all selected baselines written, 1 = an example failed to generate, 2 = usage
or config error.

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

Java generation-pipeline determinism gate: the SAME source tree, generated N times in a row via the documented single-project `generate.ps1` path, must never produce two different outcomes (same failure mode every time, or a byte-identical success manifest every time). Each run is its own `generate.ps1` process (fresh `python.exe`, fresh `PYTHONHASHSEED`), so this also exercises hash-seed-driven set-iteration-order bugs a single long-lived process would never surface. Targets `examples/02-features/03-infrastructure-blocks/nosql/system.dtrx` — the example a java parity bless sweep found producing three different outcomes (a struct-test planning failure, then two different `mvnw compile` failures) from the identical, unchanged-tree invocation. Unlike `dev\byte-identity-generate.ps1` (diffs a "before" code state against the current tree — proves a CODE CHANGE is output-neutral), this gate runs the SAME code N times and compares outcomes to each other, so it catches non-determinism a before/after diff cannot. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

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

Declaration-driven service ingress migration conformance gate. Repo-level, independent proof that regenerating the framework's own showcase examples produces only the four intended DI-6 realized-exposure deltas. Regenerates three representative registered examples individually (`identity` for delta d, `shared-block` for delta a, `authentication` + `01-foundation` for delta c) via single-project explicit-output `generate.ps1` calls, separately runs the existing full-tree example generation gate (`run-complete.ps1 -All -Skip3 -Skip4`) over every registered example, diffs the `identity` parity baseline via `regen-parity-baselines.ps1`, and greps for the removed config keys. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (both languages)** | `.\test\ingress-migration-conformance-gate.ps1` | Full DI-6 conformance sweep, python + typescript |
| **Single language** | `.\test\ingress-migration-conformance-gate.ps1 -Languages python` | Faster iteration while debugging |
| **Custom output root** | `.\test\ingress-migration-conformance-gate.ps1 -OutputRoot D:\datrix\.test-output\ingress-gate` | Override scratch generation root |
| **Debug** | `.\test\ingress-migration-conformance-gate.ps1 -Dbg` | Forward `-Dbg` to generate.ps1/run-complete.ps1/regen-parity-baselines.ps1 |

**Parameters:** `-OutputRoot` (default: `D:\datrix\.test-output\ingress-gate`), `-Languages` (comma-separated, default: `python,typescript`), `-Dbg`/`-DebugLogging`

**Assertions:**
- **Step 0 (live counts):** re-verifies `rest_api` file count, `system.dcfg` gateway-declaration count, `auth(service` occurrence count, and that the sole `verify(` usage is paired with `auth(webhook)` (the webhook migration's precondition).
- **Delta (a):** shared-block's `publisher-service.dtrx` (all-`auth(service)` surface) derives `INTERNAL` — no gateway route, no bare all-interfaces port publish.
- **Delta (b):** documented, verified absence — no registered example reproduces the name-suppression fixture (owned by the docker/azure/aws package suites).
- **Delta (c):** a single-service example with a declared `gateway {}` (`authentication`) emits a non-empty `config/nginx/nginx.conf`; a single-service example with NO declared gateway (`01-foundation`) emits none.
- **Delta (d):** the `identity` parity baseline diff (via `regen-parity-baselines.ps1`) contains only mode-literal-class changes, justified by a direct read of the verification-prelude generator code (provably independent of `AuthMode`).
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
- The baseline's `expected_count` equals its entry count, and every entry names a file, the exact matched line, and a reason.

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

### `test\parallel-implementation-drift-gate.ps1`

Parallel-implementation drift REPORT (D10.1): a strictly weaker, more general instrument than the exact-duplicate scan `duplicate.ps1` runs (Decision 34 Invariant 1). That scan proves a completed hoist *stayed* hoisted, but its sensitivity to finding the *next* hoist candidate falls to zero the moment two copies diverge even slightly. This report instead AST-walks every registered `datrix.languages` package's `src/` tree for module-level and class-method function declarations, groups them by bare name, and reports every name declared in **>= 2 registered language packages and in ZERO other `datrix-*` package** (the "nowhere else" half of its own definition — a name also hoisted to `datrix-codegen-common` or appearing in any other package is excluded as already-consolidated). Each qualifying name is classified **identical** (every declaration's source text, decorators included, is byte-for-byte equal) or **drifted** (at least one differs) — a pure binary verdict, never a fuzzy similarity score. Target derivation and the "everywhere else" package set are BOTH pure runtime/filesystem discovery — never a hardcoded language or package list — so a fifth `datrix-codegen-<lang>` package (or any new `datrix-*` package) is picked up automatically with no edit here.

**This is a REPORT with a decrease-only DRIFTED-count baseline, not a pass/fail gate on individual names.** A name-keyed check cannot distinguish an intentional per-language emission difference (e.g. a `_render_endpoint_handler` method that must legitimately differ per target language) from a genuine unreconciled divergence, and a gate that cannot make that distinction gets turned off. Classifying which drifted groups are legitimate vs. which need reconciling is a separate, human-reviewed pass over this report's output.

**Built-in non-vacuity self-test, every invocation.** Before any real scan is trusted, the script builds synthetic two/three-language package trees under a temp directory and proves: an identical pair reports one "identical" group; a one-token mutation flips it to "drifted"; a third, never-hardcoded synthetic language is picked up with no code change; a name also present in a synthetic "other" package tree is excluded even though >= 2 language packages define it; and the CLI-facing minimum-target guard refuses a single-language map. Fails loud (exit 2) if fewer than 2 languages are registered — a parallel-implementation comparison over < 2 targets is vacuous.

**Two axes, one scanner, two independent baselines.** `-Axis languages` (the default) compares the registered `datrix.languages` packages; `-Axis platforms` compares the registered `datrix.platforms` packages. The axes never share a ratchet. **The comparison unit is the PACKAGE, not the registered name** — five platform names resolve to three packages today (`azure`/`azure-vm` both live in `datrix_codegen_azure`, `docker`/`local` both in `datrix_codegen_docker`), and folding them is what stops the scan comparing a package's src tree against itself and reporting every function in it as a parallel implementation of itself. Names sharing a package are folded into one entry labelled with both (e.g. `azure+azure-vm`); on the 1:1 language axis the fold is a no-op. "Everywhere else" is axis-relative: on the platform axis the language packages are part of the exclusion set and vice versa.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the report** | `.\test\parallel-implementation-drift-gate.ps1` | Full scan over every registered language, checked against the language baseline |
| **Platform axis** | `.\test\parallel-implementation-drift-gate.ps1 -Axis platforms` | Same scan over every registered platform package, checked against the platform baseline |
| **Debug** | `.\test\parallel-implementation-drift-gate.ps1 -Dbg` | Debug logging (also lists every "identical" group) |
| **Self-test only** | `.\test\parallel-implementation-drift-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Freeze/tighten baseline** | `.\test\parallel-implementation-drift-gate.ps1 -UpdateBaseline` | Write the live DRIFTED-group count as that axis's new baseline |

**Parameters:** `-Axis <languages\|platforms>` (default: languages), `-Dbg`, `-SelfTest`, `-UpdateBaseline`

**Baselines:** `scripts/config/parallel-implementation-drift-baseline.json` (languages) and `scripts/config/platform-implementation-drift-baseline.json` (platforms) — each a decrease-only ratchet on that axis's DRIFTED-group count (a live count HIGHER than the recorded value fails; a decrease never fails). `-UpdateBaseline` is the only writer, and writes only the axis it was invoked with.

**Self-test additions for the two-axis form:** beyond the five original assertions, every run also proves that two names sharing one package fold into a single labelled entry, that an axis whose every name shares one package is refused as vacuous even with two registered names, and that the entry-point module root this scanner resolves packages by equals the resolved plugin class's module root for every registered language — the substitution that lets the platform axis avoid constructing a plugin that needs generation context is therefore re-proven on every run rather than assumed once.

**Exit codes:** 0 = the report ran and the drifted count is at or below the baseline (or a successful `-SelfTest`/`-UpdateBaseline`), 1 = the drifted count exceeds the baseline, 2 = the non-vacuity self-test failed, fewer than 2 languages are registered, or a discovery/parse error occurred.

**Terminal floor as of Decision 44, language axis:** the live `drifted_count` reads **561**, not
the design's originally-stated 190 — the 190 figure was a design-time miscalculation, retracted
once the collapse work that would have reached it was actually attempted and measured against
live source, before the true number was known. `parallel-implementation-drift-classification.json`
holds exactly 561 entries, matching the live count as the classification gate requires. Of those,
529 carry `mechanism: "none"` (the audited irreducible core) and 32 still carry a named mechanism
with no disposition recorded yet — 16 `signature-alignment`, 13 `shared-predicate-hoist`,
1 `rename`, 1 `capability-gap-defect`, 1 `shared-raise-site`. Further decrease below 561 requires a
real hoist (deleting per-language duplication), not a relabel; it is not a target this phase or its
successors chase by default without a new decision identifying a genuinely new collapsibility
mechanism.

**This is a design-expectation miss, not a bookkeeping gap.** The remaining-mechanism collapse work
read every language's live source for each mechanism's population before dispositioning it, per its
own read-before-folding rule, and found most of that population was mislabeled: a real
signature-only or vocabulary-spelling difference that the design's arithmetic assumed, versus a
genuine per-language *decision* (a different produced shape, a different downstream API, a
capability gap, orchestration over already-distinct helpers) that no listed mechanism collapses
without dropping or inventing behaviour. This entry applies the verdicts that work already reached
in its own completion notes but had not yet written into the classification file: 131 entries
relabeled `mechanism: "none"` with a reason distinct from each entry's own legitimacy reason (69
from the two signature-alignment mechanism passes, 42 from the shared-vocabulary pass
at zero collapses, 16 from the shared-predicate-hoist task, 20 from the shared-jinja-macro task at
zero collapses — plus the 4 already-collapsed entries those same tasks' own hoists had already
removed from the live file before this task ran, confirmed absent here rather than double-counted).
**A reclassification is a label change, never a decrement** — `drifted_count` did not move as a
result of this task's edits, and did not move (confirmed by a live gate run before and after).

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

### `test\collapsibility-classification-gate.ps1`

Collapsibility-classification enforcement gate (W1): asserts that every name the parallel-implementation drift scanner (`parallel-implementation-drift-gate.ps1`) reports DRIFTED, on either axis, carries a schema-valid `collapsibility` field in that axis's classification file. Two strictness levels: entry count == live drifted count and every entry carries `status` are HARD checks; every entry carrying a closed-vocabulary `collapsibility.mechanism`, and every `mechanism: "none"` entry carrying a `collapsibility.reason` distinct from its legitimacy `reason`, is a decrease-only ratchet on the unclassified-collapsibility count.

**A classification file's absence is a HARD FAILURE, not a skip, for any axis declared in `EXPECTED_CLASSIFIED_AXES`** (`collapsibility_classification.py` -- currently both `languages` and `platforms`). This is declared, not inferred: an axis outside that set with no classification file yet is still skipped (logged, never failed), but an axis inside it whose file is absent -- including one that existed and was deleted -- fails loud with a four-part message. This is what stops the enforcement from being silenced simply by removing its own input file; adding a new axis's classification file must add it to `EXPECTED_CLASSIFIED_AXES` in the same change.

**Built-in plant/observe/revert non-vacuity self-test, every invocation.** Before any real check is trusted, the script plants a short classification file (missing an entry, missing a status), a classification entry missing `collapsibility` entirely, and a `mechanism: "none"` entry whose reason duplicates its legitimacy reason -- proves each is flagged with the exact expected count delta -- then reverts each and proves the count clears. It also proves the expected-axes branch both ways, against a synthetic expected-axes set disjoint from the real one: an axis NOT in the (synthetic) expected set with a missing file is skipped, and an axis IN it with a missing file is a hard `missing_expected_classification_file` violation.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\collapsibility-classification-gate.ps1` | Check the language-axis classification file |
| **Platform axis** | `.\test\collapsibility-classification-gate.ps1 -Axis platforms` | Check the platform-axis classification file |
| **Debug** | `.\test\collapsibility-classification-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\collapsibility-classification-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |
| **Freeze/tighten baseline** | `.\test\collapsibility-classification-gate.ps1 -UpdateBaseline` | Write the live unclassified-collapsibility count as that axis's new baseline |

**Parameters:** `-Axis <languages\|platforms>` (default: languages), `-Dbg`, `-SelfTest`, `-UpdateBaseline`

**Baselines:** `scripts/config/collapsibility-unclassified-baseline.json` (languages) and `scripts/config/platform-collapsibility-unclassified-baseline.json` (platforms) -- each a decrease-only ratchet on that axis's unclassified-collapsibility count, distinct from `parallel-implementation-drift-baseline.json`'s `drifted_count` ratchet. `-UpdateBaseline` is the only writer, and writes only the invoked axis.

**Exit codes:** 0 = the gate ran and all hard checks + the ratchet hold (or a successful `-SelfTest`/`-UpdateBaseline`), 1 = a hard violation or a ratchet regression, 2 = the non-vacuity self-test failed or a discovery/parse error occurred.

**By-mechanism worklist query.** The gate above only asserts every drifted name carries a schema-valid `collapsibility` field; it does not itself answer "how much target-dependent code is left, and what would remove it." That question is answered by grouping either classification file's entries by `collapsibility.mechanism` -- a query, not a fresh investigation, because the mechanism is already recorded on every entry:

```
D:\datrix\.venv\Scripts\python.exe -c "
import json, collections, pathlib
for label, fname in (('languages', 'parallel-implementation-drift-classification.json'), ('platforms', 'platform-implementation-drift-classification.json')):
    p = pathlib.Path('d:/datrix/datrix/scripts/config') / fname
    cls = json.loads(p.read_text(encoding='utf-8'))['classifications']
    by_mech = collections.defaultdict(list)
    for name, entry in cls.items():
        mech = entry.get('collapsibility', {}).get('mechanism', '<unset>')
        by_mech[mech].append(name)
    print(f'--- {label} ---')
    for mech, names in sorted(by_mech.items(), key=lambda kv: -len(kv[1])):
        print(f'{mech}: {len(names)}')
"
```

Swap in only one axis's path (drop the `for` loop) to work a single axis. Never commit the printed worklist anywhere -- it is meant to be run ad hoc against whichever classification file is current, not baked into a static file that goes stale the moment either file's `collapsibility.mechanism` values change.

---

### `test\classification-reason-symbol-existence-gate.ps1`

Classification-reason symbol-existence gate: asserts that every code symbol and `file.py:NN` citation appearing in any `reason` or `collapsibility.reason` in either drift-classification file resolves to something that exists, on that axis. `collapsibility-classification-gate.ps1` only checks that the `collapsibility` FIELD is schema-valid -- it never reads what the prose actually SAYS. A classification entry can be schema-valid and still cite a function, class, constant, or attribute that was since deleted, renamed, or never existed the way the prose claims; the schema-validity gate cannot see that, because the schema stays valid regardless of what the prose contains. This gate is the accuracy layer for that gap.

**Candidate extraction is a naming-shape heuristic over backtick-quoted spans** (`` `([A-Za-z_][A-Za-z0-9_.]*(?::\d+)?)` `` in the runner module), never a full-text scan: an exotic reference phrased outside a backtick-quoted, identifier- or `file.py:NN`-shaped span is under-reported, never flagged -- an accepted, documented trade-off, preferred over a hardcoded per-entry allowlist of "known dead but fine" symbols that would drift silently out of sync with the file it polices. A small closed vocabulary of schema/prose words (`_SCHEMA_PROSE_VOCABULARY`: `status`, `reason`, `mechanism`, `collapsibility`, `intentional`, `tracked`, `none`, `classifications`) is excluded from candidates even though it matches the identifier shape. A backtick span that does not open with an identifier character (e.g. `` `.maven_coordinates` ``) never matches the extraction regex at all -- it is simply never produced as a candidate, not filtered out afterward. This module also never parses negation: a citation inside a sentence asserting the symbol's ABSENCE ("X no longer defines `Y`") is extracted and, if dead, reported exactly the same as any other citation -- erring toward flagging is the safe failure direction for a check that exists to catch prose describing dead code.

**Resolution searches three surfaces, all scoped to the axis's own target package `src/` trees (never the whole monorepo):** real Python identifiers declared or used anywhere in those trees (an AST walk); string-literal content parsed from those same `.py` files (`ast.Constant` string values, word-boundary matched, never a bare substring); and raw text of every `.j2` Jinja template under those trees (also word-boundary matched). The latter two surfaces exist because many citations name a construct in the GENERATED target language or a third-party API a language's generator emits (a C# `using` statement, EF Core's `FirstOrDefaultAsync`, SQLAlchemy's `_sa_instance_state`) -- Datrix's own Python source never declares those as one of its own functions/classes/attributes; they exist only inside the f-string/template fragments that build the emitted code. Word-boundary matching (never `in`) is what keeps this sound: a substring check would false-resolve a dead name that merely appears as part of a longer identifier (e.g. `_CACHE_CLIENT_PACKAGE` inside an unrelated `_MY_CACHE_CLIENT_PACKAGE_V2`).

**A DOTTED candidate (`ClassName.attribute`) is resolved more strictly when its base segment names a real class found in the tree**: the attribute must be one that class ITSELF defines (a class-body field) or assigns (an `<something>.attribute = ...` anywhere in the class's own body) -- never merely "some attribute somewhere in the codebase". This is what catches the real defect class this gate exists for: a reason once cited `RemoteConfigBackendSpec.maven_coordinates` even though `RemoteConfigBackendSpec`'s own docstring states Maven coordinates are NOT part of its spec -- the class existing must not launder a nonexistent attribute cited on it. A dotted candidate whose base does NOT name a recognized class (e.g. `this.field`, a generated TypeScript/C# receiver reference, not a Datrix class) falls back to the same broad per-segment resolution a bare identifier gets.

**Built-in plant/observe/revert non-vacuity self-test, every invocation.** Before any real check is trusted, the script proves: extraction excludes schema vocabulary, never produces a dot-prefixed span as a candidate, and still extracts a citation from inside a negation sentence; a planted dead symbol does not resolve against a synthetic package tree while a genuinely present one does; a synthetic class with one declared attribute and one deliberately undeclared attribute resolves the former and rejects the latter (the `RemoteConfigBackendSpec` shape); `file.py:NN` resolution behaves for an in-range line, an out-of-range line, and a nonexistent file; and a known-present REAL symbol (`scan_axis`, this module's own function) resolves against this module's own directory while a value that is never written as one literal string anywhere in that directory does not -- proving the scan finds a real, currently-live symbol via the exact resolver the real gate uses, not only a synthetic fixture.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\classification-reason-symbol-existence-gate.ps1` | Check the language-axis classification file |
| **Platform axis** | `.\test\classification-reason-symbol-existence-gate.ps1 -Axis platforms` | Check the platform-axis classification file |
| **Debug** | `.\test\classification-reason-symbol-existence-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\classification-reason-symbol-existence-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |

**Parameters:** `-Axis <languages\|platforms>` (default: languages), `-Dbg`, `-SelfTest`

**Assertions:** every backtick-quoted, identifier- or `file.py:NN`-shaped candidate extracted from every classification entry's `reason` and `collapsibility.reason`, on the invoked axis, resolves against that axis's own registered package `src/` trees.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = at least one dead-symbol reference found, 2 = the non-vacuity self-test failed or a discovery/parse error occurred.

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

Migration upgrade-op family gate: the cross-package half of the upgrade-op duplication census. Six `_build_upgrade_op_for_*` symbols exist once per migration target (python's Alembic migration generator, dotnet's FluentMigrator ops); the census read both bodies of each and concluded they are genuinely divergent, so each carries `collapsibility.mechanism: "none"` in `scripts/config/parallel-implementation-drift-classification.json` and **both private copies must survive** — a later "cleanup" deleting one would be deleting a target's real behaviour. The `_build_upgrade_op_for_field_added` entry additionally recorded a behaviour gap that is now CLOSED (dotnet emitted no backfill default, so a non-nullable `FIELD_ADDED` the shared change policy classifies *safe* rendered a migration that failed at apply time on any populated table); the gate holds both halves of that — the entry's `intentional` status, and the default-bearing `FluentMigratorColumn` field that earns it, since `tracked` is what an entry says while a gap is open. One genuinely shared fact WAS hoisted: both targets reassembled the `INDEX_ADDED` JSON detail into its `SnapshotIndex` with byte-identical semantics and error text, so that parse now lives once in `datrix_codegen_common.algorithms.migration_upgrade_op_index`, each target calls it the exact number of times its own paths need, and neither may redefine it. Structural resolution only, never a text match. The two languages are named (a fact about which targets carry this family, not a claim about which targets exist) but their packages resolve through the installed `datrix.languages` entry points, so a named language that is not installed fails loud instead of letting its half pass vacuously. Repo-level validation **script** — a unit test importing two generator packages to compare their bodies is the shape the repo boundary forbids outright; the shared parser's own input/output behaviour stays as a unit test in `datrix-codegen-common`, which owns the function.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\migration-upgrade-op-family-gate.ps1` | Run every cross-package check in this family |
| **Debug** | `.\test\migration-upgrade-op-family-gate.ps1 -Dbg` | Debug logging (names each self-test check as it passes) |
| **Self-test only** | `.\test\migration-upgrade-op-family-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Each of the six reclassified symbols keeps a classification entry with `collapsibility.mechanism == "none"` whose collapsibility reason is not a verbatim repeat of its legitimacy reason (an entry repeating one string has answered only one of the two questions).
- Each of the six is still defined exactly once per target.
- `_build_upgrade_op_for_field_added` carries `status: intentional`, and `FluentMigratorColumn` declares a default-bearing annotated field.
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

Third-party dependency parity gate: for every `datrix-*` package with a `src/` tree, the **third-party** distributions its `[project] dependencies` declare must equal the third-party distributions its `src/` tree imports (`ast`, nested imports included, mapped to distributions through the installed metadata via `importlib.metadata.packages_distributions`). `imported − declared` is an undeclared dependency that works here only because something else installed it into the shared venv; `declared − imported` is a dead declaration. Extras other than `dev` are optional runtime surfaces (a shipped `testing` helper subpackage, an `lsp` server) that may satisfy a `src/` import; the `dev` extra never does. A root several distributions provide (`ruamel`) is satisfied by any declared candidate; a root no installed distribution provides is itself a violation. A distribution the package **invokes as a subprocess** rather than imports is a reviewed executable exemption in `datrix/scripts/config/third-party-dependency-exemptions.json` (package + distribution + reason, `expected_count` pinned; a stale entry fails the gate) — a distribution merely used by the projects the package generates is never exempted. The sibling `manifest-import-parity-gate.ps1` holds the same invariant for the Datrix distributions. Exists because four packages imported a password hasher no framework manifest declared (present only because generated customer projects installed into the venv required it), five packages declared a template engine only a sixth (undeclared) imported, and one generator declared the web framework and ORM of the projects it generates. Repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

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
- Every literal hit is either absent or covered by a reviewed entry in `datrix/scripts/config/app-probe-path-exemptions.json` (file + exact snippet + written reason; `expected_count` pinned to the entry count). An exemption is legitimate only for a literal that is NOT an application probe target (an infrastructure container's own probe, a gateway framework-path list); an application probe is never exempted. A stale entry whose snippet no longer matches a hit fails the gate.
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
- Spelling: `framework-prefixed spellings − registered names − exemptions = ∅`; `retired spellings = ∅`; `exemptions − live spellings = ∅` (no stale entry); `expected_count` equals the entry count and every entry carries package, header, a registered family and a non-empty reason.
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

Cross-language artifact-role parity gate (D7) -- the G-A closure: detects a language silently emitting nothing for a construct another language realizes, without generating anything. For every example with >= 2 blessed language baselines under `scripts/config/parity-baselines/`, classifies each blessed manifest's paths by domain role via that language's own derived `DomainDeclaration.structural_pattern` set (the same fnmatch globs the domain self-consistency gate uses) and asserts the role set is identical across the example's blessed languages, EXCLUDING two cases the gate resolves structurally rather than through the exemption file. First, any domain the "missing" language declares globally `unsupported` -- a declared absence explained once at the language level, read directly off the declaration, never a per-example fact. Second, any domain whose `structural_pattern` matches nothing anywhere in that language's ENTIRE blessed footprint (corpus-vacuous): if no example exercises the construct, its absence from one example is not drift. Both rules are consulted BEFORE the exemption file, so neither needs an exemption entry -- but the second is no longer silent: every corpus-vacuous `(language, domain)` must carry a typed, counted record in `scripts/config/corpus-vacuity-records.json` saying why nothing exercises it, since a generator no example reaches has no end-to-end signal at all. Paths matching no pattern are reported in an "unclassified" bucket but never compared -- template-level naming legitimately differs by language; the role SET is the contract. Replaces nothing: `reference-example-parity-gate.ps1` still pins byte-level CONTENT per pair; this gate pins cross-language PRESENCE. Its coverage grows automatically as later phases bless more of the `(example, language)` matrix -- no code change needed here when that happens.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\artifact-role-parity-gate.ps1` | Compare role sets for every example with >= 2 blessed language baselines |
| **Debug** | `.\test\artifact-role-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\artifact-role-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |
| **Corpus-vacuity census** | `.\test\artifact-role-parity-gate.ps1 -Census` | Print every `(language, domain)` the blessed corpus exercises nowhere, with its reviewed status; exit 0 |

**Parameters:** `-Dbg`, `-SelfTest`, `-Census`

**Assertions:**
- Every example directory under `scripts/config/parity-baselines/` with >= 2 registered-language `.sha256` manifests is compared.
- A domain role present (>= 1 matching path) in one blessed language's manifest for an example and absent from another blessed language's manifest for the SAME example is a violation, UNLESS the missing language declares that domain globally `unsupported` (`_is_declared_unsupported`, skipped directly), OR the domain's pattern matches nothing across that language's entire blessed footprint (`_is_corpus_vacuous_for_language`, skipped directly), OR a reviewed entry exists in `scripts/config/artifact-role-exemptions.json` -- the last being reserved for a domain the missing language declares `supported`, whose pattern DOES match elsewhere in the corpus, but which this specific example's blessed manifest still lacks.
- `load_exemptions` refuses (raises `ValueError`, exit 2) an exemption entry naming a `(domain, language)` pair that language currently declares `unsupported` -- such an entry would duplicate a declared absence the gate already reads directly; delete it instead of keeping it.
- **Corpus vacuity is skipped but never silent.** `check_corpus_vacuity_records` censuses EVERY registered language against EVERY domain it declares `supported` (not just the pairs the blessed matrix happens to exercise) and holds each corpus-vacuous `(language, domain)` to a reviewed record in `scripts/config/corpus-vacuity-records.json`. The comparison runs in both directions: a censused pair with no record fails (exit 1), and a record whose pair is no longer vacuous fails as stale (exit 1). Each record carries one of three statuses, which are never interchangeable because each carries a different remedy -- `unreachable-by-design` (no example can produce a matching file at all, whatever it declares or targets), `cloud-platform-only` (only an example resolving `deployment.provider` to a cloud provider could, and the corpus has none), `unexercised` (an ordinary local/docker example could and none declares the construct). `load_corpus_vacuity_records` refuses (exit 2) a missing/malformed file, a status outside those three, a duplicated `(language, domain)`, or an entry count that does not match the pinned `expected_count`.
- Non-vacuity self-test (every invocation): a synthetic matching role-set pair reports zero divergence; a synthetic forced-mismatch pair reports exactly the planted gap; a synthetic manifest/declaration pair proves `classify_paths` buckets matched vs. unclassified paths correctly; `_is_declared_unsupported` correctly distinguishes a declared-unsupported domain, a declared-supported domain, and an undeclared domain id; `_is_corpus_vacuous_for_language` is proven against a pre-populated synthetic cache (never touching real baselines); `_reject_exemptions_for_unsupported_domains` correctly rejects a synthetic entry duplicating a declared-unsupported domain; and `compare_vacuity_records` reports nothing for an agreeing census/record pair, reports a censused pair carrying no record, and reports a record whose pair is no longer censused -- with `_parse_vacuity_record` accepting each declared status and refusing an undeclared one.

**Exit codes:** 0 = every comparable example's role sets agree modulo declared-unsupported skips, recorded corpus-vacuous skips and reviewed exemptions (or a successful `-SelfTest` / `-Census`), 1 = an un-exempted role drift was found over a domain the missing language declares `supported` and whose pattern is non-vacuous corpus-wide, or a corpus-vacuous `(language, domain)` carries no reviewed record (or a record carries no corpus-vacuous pair), 2 = the self-test failed, zero examples have >= 2 blessed language baselines, or the exemption / corpus-vacuity-record file is missing/malformed/miscounted (or, for exemptions, contains an entry duplicating a declared-unsupported domain).

---

### `test\parity-bless-mode-parity-gate.ps1`

Regression gate: `cmd_bless`'s single-process multi-language generation must produce the SAME manifests as generating each language in a fully isolated process. `cmd_bless` (`reference_example_parity.py`) generates one example once per registered language, all in a single process; a shared, non-process-isolated scratch/cache path once let two concurrent invocations interleave writes into the same directory, silently truncating the manifest for whichever language lost the race, with exit code 0 -- corrupting at least seven committed parity baselines before anyone caught it by hand. This gate generates one example two ways -- combined (every registered language, one process, mirrors `cmd_bless` exactly) and isolated (each language generated by its own freshly-spawned process) -- and asserts the manifests are byte-identical per language.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (corpus example)** | `.\test\parity-bless-mode-parity-gate.ps1` | Compare combined vs isolated blessing for the corpus example |
| **Specific example** | `.\test\parity-bless-mode-parity-gate.ps1 -Example "02-features/03-infrastructure-blocks/queue"` | Compare for a specific example |

**Parameters:** `-Example` (path relative to `datrix/examples/`, optional -- default is the corpus example)

**Assertions:**
- For every registered language, the manifest produced by a single-process run of all languages equals the manifest produced by generating that language alone in a fresh process.
- Reports every added/missing/changed path per language on mismatch.

**Exit codes:** 0 = combined and isolated generation agree for every registered language, 1 = at least one language's manifests disagree, 2 = usage error.

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

### `test\pooled-cache-realization-gate.ps1`

Pooled-cache member-slice realization gate: for every registered `datrix.languages` /
`datrix.platforms` target, asserts that a pooled cache member's declared slice
(`PooledMember.slice_index`, `datrix_codegen_common.pooling.contract`) actually reaches that
target's own emitted-output-facing source — not merely that the shared pooling pre-pass computed
it. **Detection is STATIC**: the gate AST-parses each target package's own `src/` tree (never a
substring/regex scan, never `generate.ps1`) for a function that both reads a `.slice_index`
attribute AND is call-reachable from elsewhere in that same tree — declared AND consumed, not dead
code. A target that does not yet realize the slice must carry a typed exemption (axis + target +
reason) in `datrix/scripts/config/pooled-cache-realization-exemptions.json`, whose `pinned_count`
must equal the file's live entry count on every change — a target quietly losing its realization
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
currently-unrealized target (`{axis, target, reason}`), with a hand-reviewed `pinned_count` that
must equal `len(exemptions)`. There is no `-UpdateBaseline`: a realization change removes its own
entry and decrements `pinned_count` in the same change, never a generic freeze command.

**Exit codes:** 0 = every registered target realizes the slice or carries a reviewed exemption
(and no exemption is stale), 1 = at least one unexempted gap or stale exemption was found, or the
exemption file's live count does not match `pinned_count`, 2 = the non-vacuity self-test failed or
fewer than 2 targets are registered on an axis being checked.

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
reason}`), with a hand-reviewed `pinned_count` that must equal `len(exemptions)`. A realization
change removes its own entry and decrements `pinned_count` in the same change; a STALE exemption
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

A language whose response surface genuinely diverges declares it via a reviewed, pinned-count entry
in `datrix/scripts/config/body-wire-naming-exemptions.json` (`{language, schema_kind, template,
reason}`, pinned `expected_count`).

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

A known, reviewed gap is a typed, counted entry in
`datrix/scripts/config/enum-classifier-conformance-exemptions.json` (`{language, reason}`, pinned
`pinned_count`) — never silence.

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
docker-build with every phase SKIPPED, never silently PASSED — transient-vs-logic failure
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
| **Run the gate** | `.\test\shared-library-gate.ps1` | Run all 51 absorbed checks |
| **Harness self-test** | `.\test\shared-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\shared-library-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** 51 named checks covering `structured_log_writer.py`, `test_runner.py`,
`codegen_hint_mapper.py`, `deploy_test_aggregate_writer.py`, `generated_test_log_writer.py`,
`aggregate_test_writer.py`, `deploy_test_log_writer.py`, and `logging_utils.py`'s log-content and
cleanup functions. One of them pins the parallel phase's distribution mode to `-n auto --dist
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
- git's own semantics are honoured: a `!`-re-included path is not reported, and a lowercase `manifest` directory under an uppercase `MANIFEST` rule is detected **iff** `core.ignorecase` is true in that repo;
- the scope glob is segment-aware across nine positive and negative cases.

A self-test failure aborts before any real result is trusted (exit 1).

**Unused exemption entries are reported, never failed.** An entry covers output a tool writes only once it has run (a coverage report, an `npm install`), so its absence on a clean checkout is normal and is not evidence the entry is stale.

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over every dirty repo before it generates a message or stages anything, and refuses the whole run on a violation (`-SkipIgnoredSourceCheck` overrides, loudly); a scanner that fails its own self-test aborts the run rather than returning a verdict nobody can trust. That is the seam this defect is actually about — `git add -A` is where the file is or is not published. This gate is the whole-workspace counterpart: it also covers repos the current run is not committing.

**Exit codes:** 0 = every unstaged working-tree path is a reviewed exemption, 1 = at least one publishable file is shadowed or the self-test failed, 2 = usage error (unknown `-Repo` name, no framework repo found) or a missing/malformed/miscounted exemption file.

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

Derives the reverse-dependency closure of every `datrix-*` package from actual imports (never a hand-maintained table). Discovers packages from disk by `pyproject.toml` presence, builds the import graph from each package's `src/`, `tests/`, and root-level `conftest.py` (the file class that hides test-time-only edges like datrix-common's consumption of datrix-language/datrix-cli) unioned with declared `pyproject.toml` dependencies, and computes each requested package's transitive reverse closure -- the set of packages that must also be tested whenever it changes. `affected-gate.ps1` consumes this module directly. This is a repo-level validation **script** (per the datrix showcase boundary -- no pytest suite lives in datrix).

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

Runs the affected set of Datrix package suites concurrently and returns one GREEN/RED verdict. Derives the affected set (changed packages union their reverse-dependency closure) via `affected-set.ps1`'s own module, schedules `test.ps1 <pkg>` child processes longest-first under a `PYTEST_XDIST_AUTO_NUM_WORKERS` budget so concurrently running children never oversubscribe the machine, and aggregates the final verdict by reusing `gate-verdict.ps1`'s own per-project evaluation -- never reimplementing `index.json` parsing. This is a repo-level validation **script** (per the datrix showcase boundary -- no pytest suite lives in datrix). It only SCHEDULES existing runners; it never duplicates `test.ps1`'s or `gate-verdict.ps1`'s own logic.

| Mode | Command | Description |
|------|---------|-------------|
| **Changed packages** | `.\test\affected-gate.ps1 -Projects datrix-common` | Run datrix-common + its full reverse closure concurrently |
| **Everything** | `.\test\affected-gate.ps1 -All` | Run every discovered package concurrently |
| **Custom budget** | `.\test\affected-gate.ps1 -Projects datrix-cli -MaxConcurrent 2` | Fewer concurrent slots, more workers each |
| **With mypy** | `.\test\affected-gate.ps1 -Projects datrix-common -Mypy` | Also type-check the changed packages, same budget. **Human-only** -- `guard-forbidden-commands.py` refuses this switch from an agent tool call |
| **Force past an in-progress run** | `.\test\affected-gate.ps1 -Projects datrix-cli -Force` | Start even if a requested package's newest run looks in-progress |
| **Self-test only** | `.\test\affected-gate.ps1 -SelfTest` | Run only the scheduler's own edge-case self-test suite |
| **Debug** | `.\test\affected-gate.ps1 -Projects datrix-common -Dbg` | Debug logging |

**Parameters:** `-Projects <comma-separated>` OR `-All`, `-MaxConcurrent <n>` (default 4), `-WorkersPerChild <n>` (default `floor(logical cores / MaxConcurrent)`), `-Mypy`, `-Force`, `-Output <path>`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements, per the datrix showcase boundary) covers the worker-budget invariant over a simulated schedule, longest-first ordering, the missing-`index.json`-falls-back-to-LOC case, same-package double-request rejection, a child that dies without producing an `index.json` forcing RED (never a stale GREEN), and `-MaxConcurrent 1` degenerating to sequential execution. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before real scheduling, exit 1); `-SelfTest` runs it in isolation.

**Assertions:**
- At no point do concurrently-running children's declared `PYTEST_XDIST_AUTO_NUM_WORKERS` values sum above the logical core count.
- The scheduler never launches two live children for the same package.
- A package whose newest run directory has no/INCOMPLETE `index.json` (a run in progress) is refused unless `-Force`.
- A child that exits without advancing its package's newest run directory past its pre-launch baseline is reported RED with reason `CHILD_PRODUCED_NO_RUN`, never silently defaulting to whatever stale prior result exists.

**Exit codes:** 0 = overall GREEN (or a successful `-SelfTest` run), 1 = overall RED (or `-SelfTest` reports a failing check), 2 = usage error (bad `-MaxConcurrent`/`-WorkersPerChild`, unknown/duplicate package name, both `-Projects` and `-All` given).

---
