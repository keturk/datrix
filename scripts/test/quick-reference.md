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

Builds `failure-data.json` inside a run directory: every error/failure cluster with its representative's traceback tail embedded, `codegen_hint`/`generated_file` when present, and (package runs only) a ready-to-run `test_command`. Supports all three index schemas: package (`structured_log_writer`), generated-project unit (`generated_test_log_writer`), and deploy-test (`deploy_test_log_writer` — deploy adds `failed_phase`; infra errors are keyed `phase#id` and may have `traceback_tail: null`).

| Mode | Command | Description |
|------|---------|-------------|
| **Run directory** | `.\test\collect-failure-data.ps1 "D:\datrix\datrix-common\.test_results\test-results-YYYYMMDD-HHMMSS"` | Parse an explicit run dir (or its `index.json` path) |
| **Latest run of a package** | `.\test\collect-failure-data.ps1 -Project datrix-codegen-aws` | Auto-locate the newest `test-results-*` run |
| **Longer tracebacks** | `.\test\collect-failure-data.ps1 -Project datrix-common -MaxLogLines 120` | Embed more tail lines per representative (default 60) |
| **Self-test only** | `.\test\collect-failure-data.ps1 -SelfTest` | Parse one fixture index per supported writer schema; skip the real run analysis |

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

Docs-conformance Invariant I5 gate: extracts repo-relative path references and Python module references from the curated 37-file architecture-doc set (each package's `docs/architecture.md` and/or `docs/architecture/` tree — `datrix-extensions` has neither and contributes zero) and fails if any reference does not resolve to a real file/directory/module in the tree, unless it is recorded in the committed exceptions baseline at `scripts/config/docs-conformance-exceptions.json` (a "what was removed" migration-history claim, a "must never exist" prohibition claim, or another confirmed-intentional non-existence). This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), following the same scan-and-baseline shape as `check-generated-file-ratchet.ps1`'s I5 ratchet, except the exceptions baseline is hand-edited and reviewed (no `-UpdateBaseline` flag — every entry needs a human-authored reason a script cannot synthesize).

`ARCHITECTURE_DOC_FILES` is a literal, reviewable constant in the script (never a directory glob) — "architecture docs" is a curated concept, and a new architecture doc added later is a deliberate, reviewed one-line addition to that constant. This v1 only checks path-reference candidates that are fully package-qualified (start with a known package name or `D:\datrix\`) and module-reference candidates that are fully import-qualified (start with a known Python import name) — a bare, package-relative shorthand span with no anchor at all is never a candidate (deliberate scope boundary, not a gap).

> **`ARCHITECTURE_DOC_FILES` is the one registry in the repo that does NOT self-update.** Everywhere else the package set is discovered from disk (`Get-DatrixDirectories`, `Get-DatrixPackages`, the metrics reports, `commit-and-push`), so a new package is picked up with no edit. This tuple is deliberately the exception — a curated list, reviewed by a human. Consequence: when a new `datrix-codegen-<lang>` package ships its own `docs/architecture.md`, that entry must be **added to the tuple by hand** (and the doc count in this section bumped), or the new package's architecture doc is silently never scanned by the gate. A package with no architecture doc yet contributes zero entries and is correctly absent — as `datrix-extensions` already is.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-docs-conformance.ps1` | Scan all 37 architecture docs, fail on unresolved references |
| **Warning mode** | `.\test\check-docs-conformance.ps1 -Warn` | Report unresolved references but exit 0 |
| **Show files** | `.\test\check-docs-conformance.ps1 -ShowFiles` | Print each architecture doc file being scanned |
| **Self-test only** | `.\test\check-docs-conformance.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite; skip the real docs scan |
| **Custom base dir** | `.\test\check-docs-conformance.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-docs-conformance.ps1 -Dbg` | Debug logging |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements, per the datrix showcase boundary) covers `extract_path_candidates`, `extract_module_candidates`, `resolve_path_candidate` (Tier 1 + Tier 2, including the adversarial ambiguous-Tier-2-match case, which must stay unresolved), `resolve_module_candidate`, `load_exceptions`, and `check_against_exceptions`. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation and skips the real scan. `--harness-self-test` (no `.ps1` switch -- diagnostic only) registers one intentionally-failing dummy check to prove the `[OK]`/`[FAIL]` harness itself is not vacuous.

**Assertions:**
- Every single-backtick inline code span in each of the 37 architecture docs is extracted as a path-reference or module-reference candidate per the fixed extraction rules (package/drive-prefixed for paths, import-name-prefixed dotted chains for modules); a span containing `...`, `<`/`>`, or `*` is rejected outright.
- A path candidate resolves via Tier 1 (exact path exists under the monorepo root; a trailing-slash candidate must be a directory) or Tier 2 (an unambiguous `src/`/`tests/`-relative suffix match — never attempted when the candidate already starts with `src`/`tests`, and never resolved when the suffix matches 2+ files).
- A module candidate resolves when any decreasing-length prefix of its segments after the import name matches a real `.py` file or package `__init__.py` (tolerating a trailing symbol/attribute/function name).
- A candidate unresolved by both tiers is checked against the exceptions baseline (span text -> reason); present spans never fail the gate, absent spans do.

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

**Exit codes:** 0 = `-Specific` selects only the requested file and the check is non-vacuous, 1 = wrong-file
selection, shared run directory, or a vacuous comparator, 2 = usage error (`test.ps1` or the named test
files not found).

---

### `test\supported-domain-parity-gate.ps1`

G3 final cross-language parity proof: EVERY registered `datrix.languages` plugin's derived SUPPORTED domain set — the **FULL set** (every domain a plugin declares `status == "supported"`, no pre-filtering to any subset) sourced from `datrix_codegen_common.parity.domain_registry.SHARED_CONTEXT_TYPES` (currently 39 domain ids) — must be identical. Derives its target LANGUAGE set from `importlib.metadata.entry_points(group="datrix.languages")` at runtime — never a hardcoded language literal — so a future `datrix-codegen-<lang>` package is covered automatically with no edit to this gate. The DOMAIN scope is likewise never a hardcoded literal: it comes directly from each language's own `domain_declarations`, compared unrestricted (a domain a plugin has no declaration for is simply absent from its set — every declared domain id is itself validated against `SHARED_CONTEXT_TYPES` elsewhere, by each language package's own domain self-consistency gate). An earlier revision restricted the compared scope to the seven "rich" cross-language domains on the stated rationale that the remaining domains belonged only to individual languages — that rationale was verifiably false (`function`/`helper` are registered by all four languages, `dev_scripts` by three) and hid real divergence the gate exists to catch; the restriction was removed so the full 39-domain universe is compared. Compares the union of all registered languages' supported sets against each language's own set and reports, per language, which domains its set is missing relative to the union. With all four registered languages' declarations landed, the gate agrees on 37 of the 39 shared domains (`discovery` and `resilience` are supported by no registered language and are simply absent from every set — no exemption list is needed for that; set identity already covers it).

**Supersedes `shared39-supported-parity-gate.ps1`** (java<->python only, restricted to the seven rich/shared-39 domains, now deleted): this gate's N-language FULL-set identity comparison strictly implies that narrower 2-language restricted comparison (a subset of two identical sets is itself identical) — a strict generalization of both targets and scope, not a narrower reproduction.

**The MariaDB engine boundary needs no special-case code** — it is an engine choice inside the `rdbms`/migration domains, not a withheld domain, so it never shows up as a domain-id-level diff at all (this script compares at `domain_id` grain, coarser than per-engine).

**Built-in non-vacuity self-test, every invocation.** Before any real comparison is trusted, the script feeds the comparator a synthetic matching pair (must report zero divergence) and a synthetic forced-mismatch pair (must report the missing domain); a comparator that cannot detect the forced mismatch aborts the gate (exit 2) before any real comparison runs. Fails loud (exit 2) if fewer than 2 languages are registered — a cross-language comparison over 0 or 1 language is vacuous.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\supported-domain-parity-gate.ps1` | Compare every registered language's derived supported-domain set |
| **Debug** | `.\test\supported-domain-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\supported-domain-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every registered language's supported-domain set is identical, 1 = a divergence was found for at least one language, 2 = the non-vacuity self-test failed or fewer than 2 languages are registered.

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

### `test\artifact-role-parity-gate.ps1`

Cross-language artifact-role parity gate (D7) -- the G-A closure: detects a language silently emitting nothing for a construct another language realizes, without generating anything. For every example with >= 2 blessed language baselines under `scripts/config/parity-baselines/`, classifies each blessed manifest's paths by domain role via that language's own derived `DomainDeclaration.structural_pattern` set (the same fnmatch globs the domain self-consistency gate uses) and asserts the role set is identical across the example's blessed languages. Paths matching no pattern are reported in an "unclassified" bucket but never compared -- template-level naming legitimately differs by language; the role SET is the contract. Replaces nothing: `reference-example-parity-gate.ps1` still pins byte-level CONTENT per pair; this gate pins cross-language PRESENCE. Its coverage grows automatically as later phases bless more of the `(example, language)` matrix -- no code change needed here when that happens.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\artifact-role-parity-gate.ps1` | Compare role sets for every example with >= 2 blessed language baselines |
| **Debug** | `.\test\artifact-role-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\artifact-role-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Every example directory under `scripts/config/parity-baselines/` with >= 2 registered-language `.sha256` manifests is compared.
- A domain role present (>= 1 matching path) in one blessed language's manifest for an example and absent from another blessed language's manifest for the SAME example is a violation, unless a reviewed entry exists in `scripts/config/artifact-role-exemptions.json`.
- Non-vacuity self-test (every invocation): a synthetic matching role-set pair reports zero divergence; a synthetic forced-mismatch pair reports exactly the planted gap; a synthetic manifest/declaration pair proves `classify_paths` buckets matched vs. unclassified paths correctly.

**Exit codes:** 0 = every comparable example's role sets agree modulo reviewed exemptions (or a successful `-SelfTest`), 1 = an un-exempted role drift was found, 2 = the self-test failed, zero examples have >= 2 blessed language baselines, or the exemption file is missing/malformed/miscounted.

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

### `test\builtin-claims-parity-gate.ps1`

Cross-language builtin-claims parity gate (D2). Two independent surfaces: (1) every registered
`datrix.languages` plugin's `CLAIMED_BUILTIN_GROUPS` must be identical — no exemption path; (2) for
every builtin in the full `BUILTIN_REGISTRY`, **including `group=None` ("optional everywhere")
members** (Log, Seed, Microservice, Crypto, Auth, JSON, Array — structurally invisible to the
existing per-package `validate_builtin_coverage`), a builtin mapped by at least one registered
language and unmapped by another must carry a reviewed entry in
`datrix/scripts/config/builtin-mapping-exemptions.json` (`{language, category, method, reason}`,
pinned `expected_count`).

Derives its target language set from `importlib.metadata.entry_points(group="datrix.languages")`
at runtime — never a hardcoded `python`/`typescript`/`dotnet`/`java` literal.

**Built-in non-vacuity self-test, every invocation.** Feeds both comparators a synthetic matching
pair (must report zero divergence) and a synthetic forced-mismatch pair (must report the planted
gap) — plus a synthetic "mapped by neither language" case that must never be flagged. Fails loud
(exit 2) if fewer than 2 languages are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\test\builtin-claims-parity-gate.ps1` | Compare every registered language's claimed groups and mapped-builtin sets |
| **Debug** | `.\test\builtin-claims-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\test\builtin-claims-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = claim sets identical and every mapped-set hole is exempted, 1 = a claim-set
divergence or an unexempted mapped-set hole was found, 2 = the non-vacuity self-test failed or
fewer than 2 languages are registered.

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
| **Run the gate** | `.\test\test-tooling-parsing-gate.ps1` | Run all 26 absorbed checks |
| **Harness self-test** | `.\test\test-tooling-parsing-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\test-tooling-parsing-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** 26 named checks covering `compare_tests.py`, `status_tests.py`, and
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
| **Run the gate** | `.\test\shared-library-gate.ps1` | Run all 50 absorbed checks |
| **Harness self-test** | `.\test\shared-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\test\shared-library-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** 50 named checks covering `structured_log_writer.py`, `test_runner.py`,
`codegen_hint_mapper.py`, `deploy_test_aggregate_writer.py`, `generated_test_log_writer.py`,
`aggregate_test_writer.py`, `deploy_test_log_writer.py`, and `logging_utils.py`'s log-content and
cleanup functions. Several are inherently adversarial (corrupt/truncated/empty JUnit XML →
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
| **With mypy** | `.\test\affected-gate.ps1 -Projects datrix-common -Mypy` | Also type-check the changed packages, same budget |
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
