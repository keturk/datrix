# Quick Reference — Testing Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. How each script works, what the runner records, the `index.json` schemas and what each tooling gate proves: [README.md](README.md). Cross-target and repository gates: [../gates/README.md](../gates/README.md).

Every wrapper has a POSIX twin `test/<name>.sh` taking the module's flags as `--kebab-name`; an abbreviated flag is a usage error (exit 2).

## `test\test.ps1`

Runs tests for one or more Datrix projects.

**Agents run only targeted forms** — `-Specific`, `-Keyword`, `-Tag` (never with `-All`/`-Rerun`), plus `-ListTags`, which runs nothing. Every whole-suite form (a package with none of those, several bare packages, `-All`, `-Rerun`, a tier switch `-Unit` / `-Integration` / `-E2E` / `-Fast` / `-Slow`) is **Jon's alone**: `guard-full-suite-runs.py` refuses it from every agent tool call, with no override.

| Form | Command |
|------|---------|
| One test file | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py"` |
| Several files, one pytest session (always batch a targeted set this way; commas inside parametrized IDs `[1,2]` are literal) | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py,tests/unit/test_bar.py"` |
| Keyword (`-k`) | `.\test\test.ps1 datrix-common -Keyword "test_parse"` |
| Feature tag, in every named package (how a change is verified across the packages it reaches) | `.\test\test.ps1 datrix-codegen-python datrix-codegen-typescript -Tag gateway` |
| Several tags (a test runs when it carries ANY) | `.\test\test.ps1 datrix-common -Tag config-resolution,secrets` |
| List tags and untagged tests; runs nothing; exit 1 while any test is untagged | `.\test\test.ps1 datrix-codegen-python -ListTags` |
| List tags over named files/directories only | `.\test\test.ps1 datrix-common -ListTags -Specific "tests/unit/config"` |
| Debug logging | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -Dbg` |
| Coverage | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -Coverage` |
| No failure digest | `.\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py" -NoDigest` |

Parameters: `-Projects` (positional, variadic), `-All`, `-Rerun`, `-Coverage`, `-VerboseOutput` and `-NoSave` (Jon; agents never pass them), `-NoAutoInstall`, `-Unit` / `-Integration` / `-E2E` / `-Fast` / `-Slow` (mutually exclusive), `-Specific <path[,path...]>`, `-Keyword <expr>`, `-Tag <tag[,tag...]>`, `-ListTags`, `-NoDigest`, `-Dbg`, `-SelfTest`. POSIX: `bash test/test.sh datrix-common --list-tags` (`--specific`, `--keyword`, `--tag`, `--e2-e`).

**Never run two `test.ps1` invocations at once — batch the projects into ONE call** (`test.ps1 a b c`). Concurrent runs contend on the workspace package lock (120 s), and the loser dies with `Could not acquire package lock` having run no tests.

**Output.** Unless `-NoSave`, each project's run is saved under its `.test_results/test-results-<stamp>/`. Read the final console lines for the folder, then `index.json`; every test needs a feature tag (`test-guidelines/feature-tags.md`); a failed run writes `digest.txt` there. A `-Tag` selection that keeps the whole test tree, or names a tag no test carries, is refused with exit 4 before any run. Node suites (`datrix-vscode`) take the same options; how each behaves there is in [README.md](README.md#node-suites-datrix-vscode).

## `test\run-complete.ps1`

Complete workflow: syntax check (1), generation (2), unit tests (3), deployment tests (4). `-Language`/`-L` is **mandatory**.

| Form | Command |
|------|---------|
| One example, output from `test-projects.json` | `.\test\run-complete.ps1 "examples/.../system.dtrx" -L python` |
| Explicit output path | `.\test\run-complete.ps1 "examples/.../system.dtrx" ".generated/python/docker/..." -L python` |
| Explicit platform | `.\test\run-complete.ps1 "examples/.../system.dtrx" -L python -P docker` |
| Every example | `.\test\run-complete.ps1 -All -L python` |
| Named test set | `.\test\run-complete.ps1 -TestSet foundation -L python` (`non-foundation`, `features-core`, …) |
| Domain examples | `.\test\run-complete.ps1 -Domains -L typescript` |
| Skip steps | `.\test\run-complete.ps1 -All -L python -Skip1` (`-Skip2`, `-Skip3`, `-Skip4`; generate only: `-Skip3 -Skip4`) |
| Force `--no-cache` deploy builds | `.\test\run-complete.ps1 -TestSet foundation -L python -FreshBuild` |
| Re-run failed or untested projects | `.\test\run-complete.ps1 -Rerun -L python` (`-Rerun -Domains`; tests only: `-Rerun -Skip2`) |
| Detailed output / debug | `.\test\run-complete.ps1 -All -L python -VerboseOutput` (`-Dbg`) |

Parameters: `-ExamplePath` (positional 0), `-OutputPath` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (a registered `datrix.languages` target, mandatory), `-Platform`/`-P` (default docker-compose), `-Hosting`/`-H`, `-TestSet` (default all), `-Rerun`, `-VerboseOutput`, `-Skip1`–`-Skip4`, `-Skip5` (deprecated, ignored), `-FreshBuild`, `-Dbg`/`-DebugLogging`, `-LlmSummary` (advisory post-run summary from a local model), `-LlmLimit` (12), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (180), `-LlmNumPredict` (4096), `-LlmTemperature` (0.1), `-SelfTest`. Exit: 1 missing `-Language` / no example selector / unregistered language, 2 an example outside `examples/`, 130 Ctrl-C during `-Rerun`.

## `test\dual-target.ps1`

Generate one test set for every registered language and compare per-project results (parity table).

| Form | Command |
|------|---------|
| typescript-validation set, every language | `.\test\dual-target.ps1` |
| Every example | `.\test\dual-target.ps1 -TestSet all` |
| Syntax + generation + unit tests, no deploy | `.\test\dual-target.ps1 -Skip4 -Skip5` |
| Same, `--no-cache` deploy builds | `.\test\dual-target.ps1 -Skip4 -Skip5 -FreshBuild` |

Parameters: `-TestSet` (default typescript-validation), `-Platform` (an installed `datrix.platforms` name; default docker), `-Skip4`, `-Skip5` (both required for the complete run), `-FreshBuild`, `-Dbg`/`-DebugLogging`, `-SelfTest`. Exit: 0 every project `Success` in every language, 1 a failure / missing project / unregistered platform / no language or log, 2 usage error.

## `test\test-single.ps1`

Single-test runner for checkpoint debugging; runs exactly what is named.

| Form | Command |
|------|---------|
| One file | `.\test\test-single.ps1 "D:\datrix\datrix-codegen-python\tests\test_entity.py"` |
| One node ID | `.\test\test-single.ps1 "tests/test_entity.py::TestEntity::test_basic" -Project datrix-codegen-python` |
| Keyword | `.\test\test-single.ps1 -Project datrix-common -Keyword "test_poly_string"` |
| Stop on first failure | `.\test\test-single.ps1 "tests/test_enum.py" -Project datrix-codegen-typescript -FailFast` |
| Full pytest output | `.\test\test-single.ps1 "tests/test_foo.py" -Project datrix-common -VerboseOutput` |

Parameters: `-TestPath` (positional 0), `-Project` (needed for relative paths and keyword-only runs), `-Keyword`, `-Marker`, `-VerboseOutput`, `-FailFast`, `-Dbg`, `-SelfTest`.

## `test\cases.ps1`

Authoring tool for declarative test cases (`tests/cases/<area>.cases.yaml`). Commands: `check`, `observe`, `new`, `migrate`, `accept`.

| Form | Command |
|------|---------|
| Check a package | `.\test\cases.ps1 check datrix-codegen-docker` |
| Observe a value | `.\test\cases.ps1 observe basic generate surface "{path: docker-compose.yml, unit: keys, key: [services]}" -Package datrix-codegen-docker` |
| Observe a fixture line | `.\test\cases.ps1 observe -Package datrix-language -At tests/fixtures/cases/lsp-shop/system.dtrx:14` |
| Add one case | `.\test\cases.ps1 new datrix-codegen-docker compose -Id compose.basic.services -Tags compose -Input basic -Stage generate -Observer surface -Selector "{path: docker-compose.yml, unit: keys, key: [services]}" -Expectation "[api, postgres]" -Reason "..."` |
| Propose a migration | `.\test\cases.ps1 migrate datrix-codegen-typescript` (named modules: `... unit/auth/test_x.py`) |
| Propose fixture annotations | `.\test\cases.ps1 migrate datrix-semantic unit/validators/test_x.py -Annotations` |
| Accept an approved proposal (needs Jon's `<name>.cases.approved`) | `.\test\cases.ps1 accept D:\datrix\.tmp\case-proposals\<name>.proposal.json` |
| Accept some rows | `.\test\cases.ps1 accept <proposal> <case id> <case id>` |

Parameters: `-Command` (positional), the command's positional arguments, `-Package`, `-At`, `-Annotations`, `-Id`, `-Tags`, `-Input`, `-Stage`, `-Observer`, `-Selector`, `-Expectation`, `-Reason`, `-Dbg`, `-SelfTest`. Exit: 0 done and clean, 1 refused or problems found, 2 usage error. Case format and rules: [README.md](README.md#casesps1).

## `test\model-contracts.ps1`

Schema-derived model contract tool (`tests/test_model_contracts.py`). Commands: `facts`, `inventory`, `migrate`, `accept`.

| Form | Command |
|------|---------|
| Show the facts | `.\test\model-contracts.ps1 facts datrix-codegen-docker` |
| One model | `.\test\model-contracts.ps1 facts datrix-common ExternOAuth2ClientCredentialsConfig` |
| Inventory schema-shaped tests | `.\test\model-contracts.ps1 inventory datrix-codegen-aws` |
| Propose deletions | `.\test\model-contracts.ps1 migrate datrix-codegen-aws` |
| Accept (needs Jon's `<proposal name>.cases.approved`) | `.\test\model-contracts.ps1 accept D:\datrix\.tmp\case-proposals\<package>.model-contracts.proposal.json` |

Parameters: `-Command` (positional), the command's positional arguments, `-Dbg`, `-SelfTest`. Exit: 0 done, 1 refused, 2 usage error.

## `test\tables.ps1`

Table-contract tool (`tests/test_tables.py`). Commands: `rows`, `inventory`, `migrate`, `accept`.

| Form | Command |
|------|---------|
| Every table and item id | `.\test\tables.ps1 rows datrix-codegen-python` |
| One table | `.\test\tables.ps1 rows datrix-codegen-python builtins` |
| Inventory per-row hand tests | `.\test\tables.ps1 inventory datrix-codegen-python` |
| Propose deletions | `.\test\tables.ps1 migrate datrix-codegen-python` |
| Accept (needs Jon's `<proposal name>.cases.approved`) | `.\test\tables.ps1 accept D:\datrix\.tmp\case-proposals\<package>.tables.proposal.json` |

Parameters: `-Command` (positional), the command's positional arguments, `-Dbg`, `-SelfTest`. Exit: 0 done, 1 refused, 2 usage error.

## `test\retag.ps1`

Rename feature tags across pytest `tag(...)` calls and fixture `// @tags` headers from a mapping file `{"retags": [{"from": "<old>", "to": "<new>", "paths": [...]}]}` (`paths` optional).

| Form | Command |
|------|---------|
| Preview (lists changes, writes `D:\datrix\.tmp\retag\retag.diff`, writes no file) | `.\test\retag.ps1 -Mapping D:\datrix\.tmp\retags.json` |
| Apply | `.\test\retag.ps1 -Mapping D:\datrix\.tmp\retags.json -Apply` |
| Self-test only | `.\test\retag.ps1 -SelfTest` |

Parameters: `-Mapping`, `-Apply`, `-SelfTest`. Exit: 0 done, 1 a refused occurrence or bad mapping (nothing written), 2 self-test failure / usage error.

## `test\cleanup.ps1`

List or delete `.test_results` folders under each package, `.generated/` and `.projects/`.

| Form | Command |
|------|---------|
| List (dry run) | `.\test\cleanup.ps1` |
| Delete after typed `yes` | `.\test\cleanup.ps1 -Force` |
| Keep the 10 newest, delete older | `.\test\cleanup.ps1 -Force -Trim` |
| Other workspace | `.\test\cleanup.ps1 -BaseDir D:\other` |

Parameters: `-BaseDir` (default the workspace root), `-Force`, `-Trim`, `-Dbg`, `-SelfTest`. Exit: 0 listed / deleted / trimmed / cancelled, 1 `-BaseDir` not a directory / failed self-test, 2 usage error.

## `test\compare-tests.ps1`

Compare timestamped runs inside one explicit `.test_results` folder.

| Form | Command |
|------|---------|
| Compare runs | `.\test\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results` |
| Write a Markdown report | `.\test\compare-tests.ps1 <.test_results path> -Report D:\datrix\ecommerce-test-comparison.md` |

Parameters: `-TestResults` (positional, required; alias `-Path`; must be a `.test_results` folder), `-Report`, `-Dbg`, `-SelfTest` (own parameter set). Exit: 1 path missing / not a directory / not a `.test_results` folder, 2 no runs.

## `test\mypy.ps1`

Type-check projects. **Jon only** — `guard-forbidden-commands.py` refuses it, its twin, `mypy_check` and `affected-gate.ps1 -Mypy` from any agent tool call; only `-SelfTest` passes. Why: [README.md](README.md#mypyps1).

| Form | Command |
|------|---------|
| One / several projects | `.\test\mypy.ps1 datrix-common` (`datrix-common datrix-language`) |
| Every package | `.\test\mypy.ps1 -All` |
| One file or directory | `.\test\mypy.ps1 datrix-common -Specific "src/datrix_common/utils.py"` |
| The showcase repo (always pass `-Specific`) | `.\test\mypy.ps1 datrix -Specific "scripts/common/lib/datrix_scripts/gates/ratchet/check_generated_file_ratchet.py"` |

Parameters: `-Projects` (positional, variadic), `-All`, `-VerboseOutput`, `-NoSave`, `-Specific <path>`, `-Dbg`, `-SelfTest`; the test-selection flags of `test.ps1` are accepted and ignored. Exit: 2 `-All` together with names.

## `test\status-tests.ps1`

Latest test results for all datrix projects.

| Form | Command |
|------|---------|
| Show status | `.\test\status-tests.ps1` |

Parameters: `-Dbg`, `-SelfTest`.

## `test\status-deploy-tests.ps1`

Deployment test results from the `.generated/` tree.

| Form | Command |
|------|---------|
| Every language | `.\test\status-deploy-tests.ps1` |
| One language | `.\test\status-deploy-tests.ps1 -L typescript` |
| Markdown report | `.\test\status-deploy-tests.ps1 -Report <path>` |

Parameters: `-Report <path>`, `-Language`/`-L <lang>`, `-Dbg`, `-SelfTest`.

## `test\status-unit-tests.ps1`

Unit test results from the `.generated/` tree.

| Form | Command |
|------|---------|
| Every language | `.\test\status-unit-tests.ps1` |
| One language | `.\test\status-unit-tests.ps1 -L python` |

Parameters: `-Language`/`-L <lang>`, `-Dbg`, `-SelfTest`.

## `test\collect-failure-data.ps1`

Build `failure-data.json` in a run directory: every cluster with its traceback tail, hints and a ready-to-run re-run command.

| Form | Command |
|------|---------|
| A run directory (or its `index.json`) | `.\test\collect-failure-data.ps1 "D:\datrix\datrix-common\.test_results\test-results-YYYYMMDD-HHMMSS"` |
| Newest run of a package | `.\test\collect-failure-data.ps1 -Project datrix-codegen-aws` |
| More traceback lines (default 60) | `.\test\collect-failure-data.ps1 -Project datrix-common -MaxLogLines 120` |
| No local-model hints | `.\test\collect-failure-data.ps1 -Project datrix-common -NoLlmHints` |

Parameters: a positional run-dir/`index.json` path OR `-Project <name>` (exactly one), `-MaxLogLines <n>`, `-NoLlmHints`, `-LlmHintLimit <n>` (default 5; 0 = none), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (120), `-SelfTest`, `-Dbg`. Output: `{run-dir}\failure-data.json`. Exit: 0 analysis completed, 1 a failing `-SelfTest` case, 2 usage / input not found / unrecognized schema.

## `test\extract-warnings.ps1`

Parse the pytest warnings summary of a run's `full.log` into `warnings.json`.

| Form | Command |
|------|---------|
| Run directory | `.\test\extract-warnings.ps1 "D:\datrix\datrix-codegen-aws\.test_results\test-results-YYYYMMDD-HHMMSS"` |
| `index.json` or `full.log` path | `.\test\extract-warnings.ps1 "...\test-results-YYYYMMDD-HHMMSS\index.json"` |

Parameters: positional path, `-Dbg`, `-SelfTest`. Output: `{run-dir}\warnings.json`. Exit: 0 done, 2 usage error.

## `test\classify-run-delta.ps1`

Compare two runs of one package: `SUCCESS`, `PARTIAL`, `NO_CHANGE` or `REGRESSION`; writes `run-delta.json` in the current run directory.

| Form | Command |
|------|---------|
| Named | `.\test\classify-run-delta.ps1 -Previous "{old-run-dir}" -Current "{new-run-dir}"` |
| Positional | `.\test\classify-run-delta.ps1 "{old-run-dir}" "{new-run-dir}"` |

Parameters: `-Previous`, `-Current` (run dirs or `index.json` paths, same project), `-Dbg`, `-SelfTest`. Exit: 0 SUCCESS, 1 PARTIAL / NO_CHANGE / REGRESSION, 2 usage error.

## `test\failure-ledger.ps1`

Whether a multi-suite fix job is finished, by test id: store the starting `index.json` runs, then replay every later run of each package and list the ids still open. Open = the last run covering the id's file failed it (`FAILING`), no run since covered its file (`NOT-RERUN`), or it failed in a later run and in no starting run (`NEW`). A full run, or a `-Specific` run naming the file or its directory, covers it; a `-Tag` / `-Keyword` run covers nothing. Finished at zero open ids.

| Form | Command |
|------|---------|
| Store the starting runs | `.\test\failure-ledger.ps1 -Runs <index.json>,<index.json>` |
| Open ids now | `.\test\failure-ledger.ps1 -Status` |

Parameters: `-Runs <index.json,...>`, `-Status`, `-Dbg`, `-SelfTest`. Exit: 0 no open id (or runs stored), 1 open ids, 2 usage error.

## `test\gate-verdict.ps1`

GREEN/RED verdict for the newest run of each requested package; no results, in-progress or any failure is RED.

| Form | Command |
|------|---------|
| Named packages | `.\test\gate-verdict.ps1 -Projects datrix-common,datrix-language` |
| Every testable package | `.\test\gate-verdict.ps1 -All` |
| Other output path | `.\test\gate-verdict.ps1 -All -Output D:\datrix\.tmp\test\my-gate.json` |

Parameters: `-Projects <comma-separated>` OR `-All`, `-Output <path>` (default `D:\datrix\.tmp\test\gate-verdict.json`), `-SelfTest`, `-Dbg`. Exit: 0 overall GREEN, 1 overall RED, 2 usage error. Ends with `[GATE] gate-verdict PASSED|FAILED exit=<n> log=<path>`.

## `test\affected-set.ps1`

Reverse-dependency closure of each `datrix-*` package, derived from actual imports: which packages a change might reach.

| Form | Command |
|------|---------|
| One package | `.\test\affected-set.ps1 -Projects datrix-language` |
| Several | `.\test\affected-set.ps1 -Projects datrix-language,datrix-cli` |
| Every package | `.\test\affected-set.ps1 -All` |
| Other output path | `.\test\affected-set.ps1 -All -Output D:\datrix\.tmp\test\my-closure.json` |

Parameters: `-Projects <comma-separated>` OR `-All`, `-Output <path>`, `-SelfTest`, `-Dbg`. Exit: 0 done, 1 non-vacuity check failed, 2 usage error / unreadable input / unknown name / no packages.

## `test\affected-gate.ps1`

**Jon only** — it runs whole package suites; `guard-full-suite-runs.py` refuses it from every agent tool call except `-SelfTest`. Agents verify with `test.ps1 -Specific` / `-Tag`. Unless `-All`, one of `-Consumers` / `-NoConsumers` is required.

| Form | Command |
|------|---------|
| Changed + reached consumers | `.\test\affected-gate.ps1 -Projects datrix-codegen-common -Consumers datrix-codegen-python,datrix-cli` |
| Changed only | `.\test\affected-gate.ps1 -Projects datrix-codegen-typescript -NoConsumers` |
| Everything | `.\test\affected-gate.ps1 -All` |
| Cap concurrency | `.\test\affected-gate.ps1 -Projects datrix-cli -NoConsumers -MaxConcurrent 2` |
| Uniform workers | `.\test\affected-gate.ps1 -Projects datrix-cli -NoConsumers -WorkersPerChild 4` |
| Also type-check | `.\test\affected-gate.ps1 -Projects datrix-common -Consumers datrix-cli -Mypy` |
| Start past an in-progress run | `.\test\affected-gate.ps1 -Projects datrix-cli -NoConsumers -Force` |
| Run even when a recorded green run still matches | `.\test\affected-gate.ps1 -Projects datrix-common -Consumers datrix-cli -NoCarry` |

Parameters: `-Projects` with `-Consumers` or `-NoConsumers`, OR `-All`; `-MaxConcurrent <n>`, `-WorkersPerChild <n>`, `-Mypy`, `-Force`, `-NoCarry`, `-Output <path>`, `-SelfTest`, `-Dbg`. Exit: 0 overall GREEN, 1 overall RED / failed install check / failing self-test, 2 usage error. Ends with `[GATE] affected PASSED|FAILED exit=<n> log=<path>`. Worker allotment, carry rules and the completion row: [README.md](README.md#affected-gateps1).

## `test\shared-library-gate.ps1`

Behaviour checks for the shared scripts package and the layout of the scripts tree.

| Form | Command |
|------|---------|
| Every check | `.\test\shared-library-gate.ps1` |
| One area (name prefix) | `.\test\shared-library-gate.ps1 -Only check_scripts_tree` (`check_run_complete`) |
| Harness self-test | `.\test\shared-library-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\test\shared-library-gate.ps1 -SelfTest` |

Parameters: `-SelfTest`, `-HarnessSelfTest`, `-Only <prefix>`. Exit: 0 every check passed, 1 a check failed, 2 `-Only` names no check. Ends with `[GATE] shared-library PASSED|FAILED exit=<n> log=<path>`.

## `test\runner-plugin-gate.ps1`

Behaviour checks for the test runner's pytest plugin, each in a real pytest process.

| Form | Command |
|------|---------|
| Every check | `.\test\runner-plugin-gate.ps1` |
| One check (name prefix) | `.\test\runner-plugin-gate.ps1 -Only check_records_are_named` |
| Harness self-test | `.\test\runner-plugin-gate.ps1 -HarnessSelfTest` |

Parameters: `-Only <prefix>`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 every check passed, 1 a check failed, 2 usage error. Ends with `[GATE] runner-plugin PASSED|FAILED exit=<n> log=<path>`.

## `test\test-tooling-parsing-gate.ps1`

Checks of how the test tooling reads run results (run discovery, status parsing, writers).

| Form | Command |
|------|---------|
| Every check | `.\test\test-tooling-parsing-gate.ps1` |
| One area (name prefix) | `.\test\test-tooling-parsing-gate.ps1 -Only find_runs` |
| Harness self-test | `.\test\test-tooling-parsing-gate.ps1 -HarnessSelfTest` |

Parameters: `-Only <prefix>`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 every check passed, 1 a check failed, 2 usage error. Ends with `[GATE] test-tooling-parsing PASSED|FAILED exit=<n> log=<path>`.

## `test\test-specific-selection-gate.ps1`

Proof that `test.ps1 <package> -Specific <file>` runs exactly that file and that concurrent runs never share a run directory (about 2 min).

| Form | Command |
|------|---------|
| Default package and file pair | `.\test\test-specific-selection-gate.ps1` |
| Other package | `.\test\test-specific-selection-gate.ps1 -Package datrix-common -FileA "tests/unit/datrix_model/test_seal.py" -FileB "tests/unit/datrix_model/test_traits.py"` |

Parameters: `-Package` (default `datrix-codegen-python`), `-FileA` / `-FileB` (two different package-relative test files), `-SelfTest`, `-HarnessSelfTest`, `-Dbg`. Exit: 0 selection correct and check non-vacuous, 1 wrong-file selection / shared run directory / vacuous comparator, 2 `test.ps1` or a test file not found. Ends with `[GATE] test-specific-selection PASSED|FAILED exit=<n> log=<path>`.

## `test\run-log-exclusivity-gate.ps1`

Proof that two concurrent runs never share one log file (`generate.ps1` logs, `DatrixRunLog.psm1`, `datrix_scripts.run_log`).

| Form | Command |
|------|---------|
| Run (8 racers) | `.\test\run-log-exclusivity-gate.ps1` |
| More racers | `.\test\run-log-exclusivity-gate.ps1 -Racers 32` |

Parameters: `-Racers` (default 8, range 2–64), `-SelfTest`, `-Dbg`. Exit: 0 every step held, 1 a shared or reused name / escaped label / unwired generate module / vacuous comparator, 2 `-Racers` out of range or a required file missing. Ends with `[GATE] run-log-exclusivity PASSED|FAILED exit=<n> log=<path>`.

## `test\toolchain-free-suites-gate.ps1`

No framework test suite compiles or executes generated output (no toolchain subprocess, no in-process execution, no nested pytest or repo-script subprocess). Hard zero for the two suite-in-suite shapes.

| Form | Command |
|------|---------|
| Every `datrix-*` package suite | `.\test\toolchain-free-suites-gate.ps1` |
| One suite | `.\test\toolchain-free-suites-gate.ps1 -Suites D:/datrix/datrix-codegen-typescript/tests` |
| Only the suite-in-suite shapes | `.\test\toolchain-free-suites-gate.ps1 -Shapes suite-in-suite-pytest,suite-in-suite-script` |

Parameters: `-Suites <path[,path...]>` (each a directory), `-Shapes <kind[,kind...]>` (`toolchain-subprocess`, `in-process-execution`, `suite-in-suite-pytest`, `suite-in-suite-script`, `unparseable`), `-SelfTest`. Exit: 0 no violation of the requested shapes, 1 a violation / failed self-test, 2 a `-Suites` entry not a directory or an unknown `-Shapes` kind. Ends with `[GATE] toolchain-free-suites PASSED|FAILED exit=<n> log=<path>`.
