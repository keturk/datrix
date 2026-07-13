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

### `test\reference-example-parity-gate.ps1`

**The repo's proof that generated output does not change unintentionally.** For every example
`system.dtrx` under `datrix/examples/`, runs the **real generation pipeline**
(`datrix_cli.pipeline.generation.GenerationPipeline` — the same code path `generate.ps1` runs,
with the same `PipelineConfig` defaults: profile `test`, `format_output=True`,
`validation_level=STANDARD`) and compares a per-file sha256 manifest of the **whole generated
output tree** against the stored baseline in
`datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256`. Any changed byte in any
generated file, and any file that appears or disappears, fails the gate.

Repo-level validation **script**, not a pytest suite (per the datrix showcase boundary), and
`datrix_codegen_common` may not import `datrix_cli`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\test\reference-example-parity-gate.ps1` | Check every example against its baseline (~4 min) |
| **Single example** | `.\test\reference-example-parity-gate.ps1 -Example "01-foundation"` | Check one example (fast iteration on a generator) |
| **Debug** | `.\test\reference-example-parity-gate.ps1 -Dbg` | DEBUG logging (very verbose: every pipeline stage) |

**Parameters:** `-Example` (path relative to `datrix/examples/`, optional — default all), `-Dbg`

**One language per example — NOT a language matrix.** The generator reads the target language
from each project's `config/system.dcfg`; `generate.ps1`'s `-L` only labels the output path. Each
example is therefore generated exactly once, in its declared language (52 python + 1 typescript
today). The gate never enumerates languages.

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

**Exit codes:** 0 = every example matches its baseline and the comparator is non-vacuous,
1 = drift / missing baseline / generation failure / self-test failure, 2 = usage or config error.

---

### `test\regen-parity-baselines.ps1`

**The single re-bless command** for the reference-example parity gate. Regenerates the stored
baselines by running the same real pipeline and writing a per-file sha256 manifest to
`datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256`. This is the **only**
sanctioned baseline writer — the gate never writes baselines (no auto-heal). Run it deliberately,
**after** you have explained the change.

| Mode | Command | Description |
|------|---------|-------------|
| **Re-bless one example** | `.\test\regen-parity-baselines.ps1 -Example "01-foundation"` | The normal case: one intentional change → one example re-blessed |
| **Re-bless all** | `.\test\regen-parity-baselines.ps1` | Only for a change that legitimately moves every example's output |
| **Debug** | `.\test\regen-parity-baselines.ps1 -Dbg` | Debug logging |

**Parameters:** `-Example` (path relative to `datrix/examples/`, optional — default all), `-Dbg`

**Per-example granularity is the point:** an intentional change affecting one example re-blesses
one example, not all 53. The full generated tree of each blessed example is kept under
`.test-output/parity-baseline-cache/` so a later failing gate can show a real unified diff.

**Note:** an example that cannot generate is never blessed — the run fails and names it. Always
review the resulting baseline diff before committing: **an unexpected baseline change is a
generator regression, not a baseline update.**

**Exit codes:** 0 = all selected baselines written, 1 = an example failed to generate, 2 = usage
or config error.

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

---

### `test\test-specific-selection-gate.ps1`

**The repo's proof that `test.ps1 <package> -Specific <file>` really runs THAT file.** A `-Specific` run
that prints `[PASSED]` while its own `index.json` / JUnit XML describe a **different** file's tests is a
silent false green — the caller "proves" a fix that never ran. That was a real defect (task 17-14):
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

### `test\gendsl-corpus-resolution-gate.ps1`

Design 025 (GenDSL 2) D1/I1 corpus proof (task 13-04, relocated task 17-10): eager builder/call-expression reference resolution runs at `@generator_definition` registration time (`datrix_codegen_common.gendsl.resolver`). Importing each consumer package's genDSL definitions module (`datrix_codegen_python.gendsl.definitions`, `datrix_codegen_typescript.gendsl_definitions`, `datrix_codegen_sql.gendsl.sql_definitions`, `datrix_codegen_docker.gendsl_definitions`, `datrix_codegen_aws.gendsl.aws_definitions`, `datrix_codegen_azure.gendsl.azure_definitions`, `datrix_codegen_component.gendsl_definitions`) IS the assertion: a bad reference raises `GenDSLReferenceResolutionError` at import time.

This gate previously lived as a pytest test inside `datrix-codegen-common` (`tests/integration/gendsl/test_resolution_corpus.py`) that imported all seven concrete target packages directly — a `datrix_codegen_common`-must-not-import-concrete-target-packages boundary violation **and** a cross-package test (prohibited everywhere in the repo, not only in the showcase package). The proof is inherently repo-level, so task 17-10 moved it here (deleting the pytest test) rather than allowlisting the violation — the allowlist is terminal-empty (design 023 I7) and adding an entry would be a regression.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\test\gendsl-corpus-resolution-gate.ps1` | Import all seven packages' genDSL definitions, fail on any unresolved reference |
| **Debug** | `.\test\gendsl-corpus-resolution-gate.ps1 -Dbg` | Debug logging |

**Parameters:** `-Dbg`

**Exit codes:** 0 = every package's genDSL corpus resolved at import, 1 = at least one package failed to resolve or import.
