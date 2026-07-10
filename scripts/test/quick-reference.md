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
| **Keyword filter** | `.\test\test.ps1 datrix-common -Keyword "test_parse"` | Match by keyword (-k) |
| **Verbose output** | `.\test\test.ps1 datrix-common -VerboseOutput` | Verbose pytest output |
| **No log save** | `.\test\test.ps1 datrix-common -NoSave` | Don't save output to log files |
| **Debug logging** | `.\test\test.ps1 datrix-common -Dbg` | Enable DEBUG level |
| **Rerun failed** | `.\test\test.ps1 -Rerun` | Re-run only projects whose latest test log reports failures |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rerun`, `-Coverage`, `-VerboseOutput`, `-NoSave`, `-NoAutoInstall`, `-Unit`, `-Integration`, `-E2E`, `-Fast`, `-Slow` (mutually exclusive), `-Specific <path>`, `-Keyword <expr>`, `-Dbg`

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
| **With debug** | `.\test\status-deploy-tests.ps1 -Dbg` |

**Parameters:** `-Dbg`

### `test\status-unit-tests.ps1`

Reports run test results from `.generated/` tree.

| Mode | Command |
|------|---------|
| **Show status** | `.\test\status-unit-tests.ps1` |
| **With debug** | `.\test\status-unit-tests.ps1 -Dbg` |

**Parameters:** `-Dbg`

---

## Validation Scripts

### `test\type-mapping-completeness.ps1`

Validates that all canonical types in the TypeRegistry have mappings in the requested language generators. This is a repo-level cross-package validation script that checks type mapping completeness across language packages.

| Mode | Command | Description |
|------|---------|-------------|
| **Python only** | `.\test\type-mapping-completeness.ps1 -Languages python` | Check Python type mappings |
| **TypeScript only** | `.\test\type-mapping-completeness.ps1 -Languages typescript` | Check TypeScript type mappings |
| **Both languages** | `.\test\type-mapping-completeness.ps1 -Languages python,typescript` | Check both Python and TypeScript |
| **SQL dialects** | `.\test\type-mapping-completeness.ps1 -Languages sql` | Check SQL type mappings for all dialects |
| **Debug** | `.\test\type-mapping-completeness.ps1 -Languages python -Dbg` | Debug logging |

**Parameters:** `-Languages` (comma-separated list: python, typescript, sql; required), `-Dbg`

**Exit codes:** 0 = all types mapped, 1 = missing mappings found

**Purpose:** This script replaces package-local cross-language type mapping tests. Individual language packages test only their own mappings; this repo-level script validates completeness across all requested languages.

---

### `test\regen-parity-baselines.ps1`

Regenerates the stored reference-example parity baselines consumed by the
`datrix-codegen-common` example-parity test. For every example `system.dtrx` under
`datrix/examples/` × each discovered language, generates output in-process and writes a
deterministic per-file sha256 manifest to
`datrix-codegen-common/tests/parity/baselines/<example_id>/<language>.sha256`. This is the
**only** sanctioned way to update baselines — the test itself never writes them (no
auto-heal). Run it deliberately after an intentional, reviewed change to generated output.

| Mode | Command | Description |
|------|---------|-------------|
| **Regenerate all** | `.\test\regen-parity-baselines.ps1` | Rewrite every example × language baseline |
| **Single example** | `.\test\regen-parity-baselines.ps1 -Example "01-foundation/library"` | Rewrite one example's baselines (path relative to `datrix/examples/`) |
| **Single language** | `.\test\regen-parity-baselines.ps1 -Language python` | Rewrite only the named language's baselines |
| **Debug** | `.\test\regen-parity-baselines.ps1 -Dbg` | Debug logging |

**Parameters:** `-Example` (relative path under `datrix/examples/`, optional — default all), `-Language` (python\|typescript, optional — default all discovered), `-Dbg`

**Note:** Baselines are deterministic (generation output is byte-stable). Regeneration must be reviewed in the diff — an unexpected baseline change signals real cross-language divergence.

---

### `test\typescript-whole-system-gate.ps1`

Whole-system **TypeScript** generation gate: proves the whole-system generate path emits real TypeScript (not a hollow/failed run) and is byte-deterministic. Generates `examples/04-languages/typescript-service` twice into two explicit `--output` dirs and asserts realness + byte-stability. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

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

### `test\ingress-migration-conformance-gate.ps1`

Design 022 (declaration-driven service ingress) migration conformance gate. Repo-level, independent proof that regenerating the framework's own showcase examples under phase-12 code produces only the four intended DI-6 realized-exposure deltas. Regenerates three representative registered examples individually (`identity` for delta d, `shared-block` for delta a, `authentication` + `01-foundation` for delta c) via single-project explicit-output `generate.ps1` calls, separately runs the existing full-tree example generation gate (`run-complete.ps1 -All -Skip3 -Skip4`) over every registered example, diffs the `identity` parity baseline via `regen-parity-baselines.ps1`, and greps for the removed config keys. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (both languages)** | `.\test\ingress-migration-conformance-gate.ps1` | Full DI-6 conformance sweep, python + typescript |
| **Single language** | `.\test\ingress-migration-conformance-gate.ps1 -Languages python` | Faster iteration while debugging |
| **Custom output root** | `.\test\ingress-migration-conformance-gate.ps1 -OutputRoot D:\datrix\.test-output\ingress-gate` | Override scratch generation root |
| **Debug** | `.\test\ingress-migration-conformance-gate.ps1 -Dbg` | Forward `-Dbg` to generate.ps1/run-complete.ps1/regen-parity-baselines.ps1 |

**Parameters:** `-OutputRoot` (default: `D:\datrix\.test-output\ingress-gate`), `-Languages` (comma-separated, default: `python,typescript`), `-Dbg`/`-DebugLogging`

**Assertions:**
- **Step 0 (live counts):** re-verifies `rest_api` file count, `system.dcfg` gateway-declaration count, `auth(service` occurrence count, and that the sole `verify(` usage is paired with `auth(webhook)` (12-17's migration precondition).
- **Delta (a):** shared-block's `publisher-service.dtrx` (all-`auth(service)` surface) derives `INTERNAL` — no gateway route, no bare all-interfaces port publish.
- **Delta (b):** documented, verified absence — no registered example reproduces the name-suppression fixture (owned by 12-10/12-12/12-15's own suites).
- **Delta (c):** a single-service example with a declared `gateway {}` (`authentication`) emits a non-empty `config/nginx/nginx.conf`; a single-service example with NO declared gateway (`01-foundation`) emits none.
- **Delta (d):** the `identity` parity baseline diff (via `regen-parity-baselines.ps1`) contains only mode-literal-class changes, justified by a direct read of the verification-prelude generator code (provably independent of `AuthMode`).
- **Step 3:** zero ING001/ING002/ING003 and webhook-invariant errors across the full-tree generation gate, both languages (known, tracked, out-of-scope failures — e.g. shared-block's pre-existing API003/XSV017 defect — are reported but not conflated with a design-022 regression).
- **Step 4:** zero `publicIngress`/`platforms.azure.services` matches under `datrix/examples`.

**Exit codes:** 0 = every DI-6 delta class accounted for and the negative acceptance property holds, 1 = any finding (including known, out-of-scope pre-existing defects, reported distinctly) causes a non-zero ledger.

---

### `test\check-generated-file-ratchet.ps1`

Design 025 (GenDSL 2) Invariant I5 ratchet: AST-counts direct `GeneratedFile(...)` constructor calls per `datrix-*` package's `src/` tree and fails if any package's count exceeds its frozen baseline at `scripts/config/generated-file-ratchet.json`. Every emitted file should eventually be declared in genDSL rather than hand-constructed; this ratchet freezes the current count per package and only ever allows it to shrink as later migration tasks convert hand-coded construction into genDSL declarations. This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), following the same AST-scan-and-ratchet shape as `dev\check-import-boundaries.ps1`'s I1/I6 ratchets.

| Mode | Command | Description |
|------|---------|-------------|
| **Run ratchet** | `.\test\check-generated-file-ratchet.ps1` | Scan all packages, fail on regressions |
| **Warning mode** | `.\test\check-generated-file-ratchet.ps1 -Warn` | Report regressions but exit 0 |
| **Show files** | `.\test\check-generated-file-ratchet.ps1 -ShowFiles` | Print each file being scanned |
| **Freeze/tighten baseline** | `.\test\check-generated-file-ratchet.ps1 -UpdateBaseline` | Recompute counts and write the baseline (bootstrap freeze if none exists yet; otherwise only accepts decreases) |
| **Custom base dir** | `.\test\check-generated-file-ratchet.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-generated-file-ratchet.ps1 -Dbg` | Debug logging |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-UpdateBaseline`, `-Dbg`

**Assertions:**
- Direct `GeneratedFile(...)` constructor calls (bare or module-qualified) are counted per package's `src/` tree; `GeneratedFile.from_content(...)` is never counted (a distinct call shape).
- `tests/` directories are never scanned (structural: only `src/` is walked).
- `datrix-codegen-common/src/datrix_codegen_common/gendsl/executor.py` is excluded (the declared-render path's own internals).
- A package absent from the baseline has an implicit baseline of 0.

**Exit codes:** 0 = every package's count is at or below its frozen baseline (or a successful `-UpdateBaseline`), 1 = a package's count exceeds its frozen baseline, 2 = usage error, missing baseline, or an attempted baseline increase over an existing baseline.

---

### `test\check-docs-conformance.ps1`

Design 026 (Golden Corpus Verification & Docs Conformance) Invariant I5 gate: extracts repo-relative path references and Python module references from the curated 36-file architecture-doc set (each package's `docs/architecture.md` and/or `docs/architecture/` tree — `datrix-extensions` has neither and contributes zero) and fails if any reference does not resolve to a real file/directory/module in the tree, unless it is recorded in the committed exceptions baseline at `scripts/config/docs-conformance-exceptions.json` (a "what was removed" migration-history claim, a "must never exist" prohibition claim, or another confirmed-intentional non-existence). This is a repo-level validation **script** (per the datrix showcase boundary — no pytest suite lives in datrix), following the same scan-and-baseline shape as `check-generated-file-ratchet.ps1`'s I5 ratchet, except the exceptions baseline is hand-edited and reviewed (no `-UpdateBaseline` flag — every entry needs a human-authored reason a script cannot synthesize).

`ARCHITECTURE_DOC_FILES` is a literal, reviewable constant in the script (never a directory glob) — "architecture docs" is a curated concept, and a new architecture doc added later is a deliberate, reviewed one-line addition to that constant. This v1 only checks path-reference candidates that are fully package-qualified (start with a known package name or `D:\datrix\`) and module-reference candidates that are fully import-qualified (start with a known Python import name) — a bare, package-relative shorthand span with no anchor at all is never a candidate (deliberate scope boundary, not a gap).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\check-docs-conformance.ps1` | Scan all 36 architecture docs, fail on unresolved references |
| **Warning mode** | `.\test\check-docs-conformance.ps1 -Warn` | Report unresolved references but exit 0 |
| **Show files** | `.\test\check-docs-conformance.ps1 -ShowFiles` | Print each architecture doc file being scanned |
| **Custom base dir** | `.\test\check-docs-conformance.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\test\check-docs-conformance.ps1 -Dbg` | Debug logging |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-Dbg`

**Assertions:**
- Every single-backtick inline code span in each of the 36 architecture docs is extracted as a path-reference or module-reference candidate per the fixed extraction rules (package/drive-prefixed for paths, import-name-prefixed dotted chains for modules); a span containing `...`, `<`/`>`, or `*` is rejected outright.
- A path candidate resolves via Tier 1 (exact path exists under the monorepo root; a trailing-slash candidate must be a directory) or Tier 2 (an unambiguous `src/`/`tests/`-relative suffix match — never attempted when the candidate already starts with `src`/`tests`, and never resolved when the suffix matches 2+ files).
- A module candidate resolves when any decreasing-length prefix of its segments after the import name matches a real `.py` file or package `__init__.py` (tolerating a trailing symbol/attribute/function name).
- A candidate unresolved by both tiers is checked against the exceptions baseline (span text -> reason); present spans never fail the gate, absent spans do.

**Exit codes:** 0 = no unresolved references (or a successful `-Warn` run), 1 = at least one unresolved, non-excepted reference found, 2 = usage error, missing exceptions baseline, or a doc in `ARCHITECTURE_DOC_FILES` that no longer exists.
