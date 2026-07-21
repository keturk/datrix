# Quick Reference — Development Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## Code Generation

### `dev\generate.ps1`

Generates Datrix projects from `.dtrx` source files. `-Language`/`-L` and `-Runtime`/`-R` are wrapper-only output-path selectors. The output-path provider segment is read from each project's `config/system.dcfg` deployment block (active `-ConfigProfile`, default `test`), not a flag. The actual language, runtime, provider, service flavor, and infrastructure flavor used for generation are read from project config.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project (auto output)** | `.\dev\generate.ps1 <source.dtrx> -L python` | Output path derived from test-projects.json |
| **Single project (explicit output)** | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python` | Explicit output directory |
| **Single + output target path** | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L typescript -R azure-app-service` | Use explicit output path / runtime segment |
| **All examples** | `.\dev\generate.ps1 -All -L python` | Generate all (test set all) |
| **All + TypeScript** | `.\dev\generate.ps1 -All -L typescript` | All examples for TypeScript |
| **All + custom output base** | `.\dev\generate.ps1 -All -L python -OutputBase .generated2` | Custom output root |
| **Foundation only** | `.\dev\generate.ps1 -TestSet foundation -L python` | examples/01-foundation |
| **Non-foundation only** | `.\dev\generate.ps1 -TestSet non-foundation -L python` | Everything except foundation examples |
| **Domains only** | `.\dev\generate.ps1 -Domains -L python` | examples/03-domains |
| **Custom test set** | `.\dev\generate.ps1 -TestSet features-core -L python` | Any named test set |
| **TypeScript validation subset** | `.\dev\generate.ps1 -TestSet typescript-validation -L typescript` | Quick TS validation |
| **Verbose output** | `.\dev\generate.ps1 -All -L python -VerboseOutput` | Show detailed generation output |
| **Debug logging** | `.\dev\generate.ps1 -All -L python -Dbg` | Enable DEBUG level logging |
| **Config profile** | `.\dev\generate.ps1 <source.dtrx> -L python -ConfigProfile production` | Select non-default config profile |

**Parameters:** `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (python\|typescript, output path), `-Runtime`/`-R` (docker-compose\|azure-container-apps\|azure-app-service\|ecs-fargate\|app-runner, output path), `-ConfigProfile` (config profile that also selects the provider segment read from `config/system.dcfg`, e.g. test\|development\|production; default: test), `-OutputBase` (default: .generated), `-TestSet` (default: all), `-VerboseOutput`, `-Dbg`

### `dev\syntax-checker.ps1`

Validates `.dtrx` file syntax using the tree-sitter parser.

| Mode | Command | Description |
|------|---------|-------------|
| **All repos** | `.\dev\syntax-checker.ps1` | Check all .dtrx files in all datrix repos |
| **Single file** | `.\dev\syntax-checker.ps1 path/to/file.dtrx` | Check one file |
| **Directory** | `.\dev\syntax-checker.ps1 examples/` | Check all .dtrx in a directory |
| **With debug** | `.\dev\syntax-checker.ps1 . -Dbg` | Debug logging |

**Parameters:** `-Path` (positional, default: all repos), `-Dbg`

### `dev\config-linter.ps1`

Lint/format ConfigDSL `.dcfg` files using the ConfigDSL parser.

| Mode | Command | Description |
|------|---------|-------------|
| **All repos (format)** | `.\dev\config-linter.ps1 -All` | Format all `.dcfg` files across all datrix repos |
| **All repos (check)** | `.\dev\config-linter.ps1 -All -Check` | Check only; no file writes |
| **Specific path** | `.\dev\config-linter.ps1 examples\01-foundation\config` | Format `.dcfg` files under a specific directory |
| **Specific file (check)** | `.\dev\config-linter.ps1 path\to\system.dcfg -Check` | Check one file |
| **Self-test** | `.\dev\config-linter.ps1 -SelfTest` | Run only the formatter self-test (round-trip fidelity fixture); no `-All`/path needed |

**Parameters:** `-All`, `-Path` (positional, variadic), `-Check`, `-SelfTest`, `-Dbg`

**Self-test detail:** `-SelfTest` runs `config_linter.py --self-test`, which regression-tests `format_dcfg`'s round-trip fidelity against a fixed `.dcfg` fixture: the name-less `service` wildcard must render as `service from ...`, never the invalid token `service *`; a `replace ... from tpl() { body }` body and an `inheriting base` clause must survive formatting; `format(format(x)) == format(x)` (idempotence); and a comment-bearing file must be left byte-for-byte unchanged with a blocking issue explaining why (the formatter does not preserve `//` comments). Prints `[OK]`/`[FAIL]` per check. Exit codes: 0 = all checks passed, 1 = at least one check failed.

### `dev\status-generation.ps1`

Reports generation status from the latest `generate-results-*.log` file. Lists which projects succeeded/failed.

| Mode | Command |
|------|---------|
| **Show status** | `.\dev\status-generation.ps1` |

**Parameters:** (none)

### `dev\generate-doc-fragments.ps1`

Generates documentation fragments from source code. Extracts semantic pipeline stages (from `SemanticAnalyzer.analyze()` via AST parsing) and CLI help output (from `datrix generate --help`) into markdown files under `datrix/docs/generated/`.

| Mode | Command | Description |
|------|---------|-------------|
| **All fragments** | `.\dev\generate-doc-fragments.ps1` | Generate all fragments |
| **Semantic only** | `.\dev\generate-doc-fragments.ps1 semantic-pipeline` | Generate pipeline stages only |
| **CLI help only** | `.\dev\generate-doc-fragments.ps1 cli-help` | Generate CLI help only |
| **Check mode** | `.\dev\generate-doc-fragments.ps1 -Check` | Verify fragments are up-to-date (non-zero exit if stale) |
| **With debug** | `.\dev\generate-doc-fragments.ps1 -Dbg` | Show detailed output |

**Parameters:** `-Fragment` (positional 0: all\|semantic-pipeline\|cli-help, default: all), `-Check`, `-Dbg`

---

## Documentation Checks

### `dev\check-docs.ps1`

Lints documentation for common drift patterns: deprecated CLI flags, fixed phase counts, CDX doc naming/structure, missing capability status labels.

| Mode | Command | Description |
|------|---------|-------------|
| **All checks** | `.\dev\check-docs.ps1` | Run all docs lint checks |
| **Specific check** | `.\dev\check-docs.ps1 -Check deprecated-cli-flags` | Run one check |
| **Multiple checks** | `.\dev\check-docs.ps1 -Check cdx-filenames -Check cdx-structure` | Run selected checks |
| **Detailed output** | `.\dev\check-docs.ps1 -Detailed` | Show content and suggestions |
| **Custom docs dir** | `.\dev\check-docs.ps1 path\to\docs` | Scan specific directory |
| **Debug** | `.\dev\check-docs.ps1 -Dbg` | Debug logging |

**Parameters:** `-DocsDir` (positional, variadic — defaults to all monorepo docs/), `-Check` (deprecated-cli-flags\|fixed-phase-count\|cdx-filenames\|cdx-structure\|capability-status-labels, repeatable), `-Detailed`, `-Dbg`

**Exit codes:** 0 = clean, 1 = lint failures found

---

## Anti-Pattern Scanners

### `dev\libcst.ps1`

Scans for anti-patterns using LibCST: silent-fallback, empty-except, missing-encoding, banned-test-import, placeholder-body.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\libcst.ps1 datrix-common` | Scan one project |
| **Multiple projects** | `.\dev\libcst.ps1 datrix-common datrix-language` | Scan several |
| **All projects** | `.\dev\libcst.ps1 -All` | Scan entire monorepo |
| **With report** | `.\dev\libcst.ps1 -All -Report libcst-report.md` | Write markdown report |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Report <path>`

### `dev\semgrep.ps1`

Runs Semgrep with Datrix-specific rules from `scripts/config/semgrep-rules/`.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\semgrep.ps1 datrix-common` | All rules on one project |
| **All projects** | `.\dev\semgrep.ps1 -All` | All rules on all projects |
| **Single rule** | `.\dev\semgrep.ps1 -All -Rule empty-except-pass` | One specific rule |
| **Multiple rules** | `.\dev\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup` | Selected rules |
| **List rules** | `.\dev\semgrep.ps1 -ListRules` | Show available rule names |
| **With report** | `.\dev\semgrep.ps1 -All -Report semgrep-report.md` | Write markdown report |
| **Show raw output** | `.\dev\semgrep.ps1 -All -ShowRaw` | Show raw semgrep output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rule <name>` (repeatable), `-ListRules`, `-Report <path>`, `-ShowRaw`

### `dev\ast-grep.ps1`

Runs ast-grep structural Python rules from `scripts/config/ast-grep-rules/`, or a one-off ast-grep pattern.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\ast-grep.ps1 datrix-common` | All saved rules on one project |
| **All projects** | `.\dev\ast-grep.ps1 -All` | All saved rules on all projects |
| **Single rule** | `.\dev\ast-grep.ps1 -All -Rule empty-except-pass` | One saved ast-grep rule |
| **Multiple rules** | `.\dev\ast-grep.ps1 -All -Rule empty-except-pass -Rule placeholder-notimplemented-body` | Selected rules |
| **One-off pattern** | `.\dev\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'` | Ad hoc structural search |
| **List rules** | `.\dev\ast-grep.ps1 -ListRules` | Show available rule names |
| **With report** | `.\dev\ast-grep.ps1 -All -Report ast-grep-report.md` | Write markdown report |
| **Show raw output** | `.\dev\ast-grep.ps1 -All -Rule empty-except-pass -ShowRaw` | Show raw ast-grep output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Pattern <pattern>`, `-Rule <name>` (repeatable), `-ListRules`, `-Report <path>`, `-ShowRaw`

**PowerShell note:** Use single quotes for ast-grep metavariables (`'$MSG'`) so PowerShell does not expand them.

### `dev\check-debug-artifacts.ps1`

Detects leftover debug/logging artifacts in source code (print, breakpoint, console.log, debugger, temp comments). Use as a pre-commit check to catch debug scatter.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\check-debug-artifacts.ps1 datrix-codegen-python` | Scan one project |
| **All projects** | `.\dev\check-debug-artifacts.ps1 -All` | Scan entire monorepo |
| **Strict mode** | `.\dev\check-debug-artifacts.ps1 -All -Strict` | Also flag logger.debug/info with f-strings |
| **With details** | `.\dev\check-debug-artifacts.ps1 datrix-common -Dbg` | Show matching line content |

**Parameters:** `-ProjectDir` (positional, variadic), `-All`, `-Strict`, `-IncludeGenerated`, `-Dbg`

**Exit codes:** 0 = clean, 1 = artifacts found, 2 = usage error

### `dev\check-import-boundaries.ps1`

Enforces cross-package import boundary rules across the monorepo. Scans each package's `src/`, `tests/`, `fixtures/`, and `helpers/` directories for forbidden imports using Python AST analysis. See [Import Boundaries](../../../datrix-common/docs/architecture/import-boundaries.md) for the full rule table.

| Mode | Command | Description |
|------|---------|-------------|
| **Fail mode** | `.\dev\check-import-boundaries.ps1` | Report violations, exit 1 on any |
| **Warning mode** | `.\dev\check-import-boundaries.ps1 -Warn` | Report violations, exit 0 |
| **Custom base dir** | `.\dev\check-import-boundaries.ps1 -BaseDir D:\other` | Different workspace |
| **Show files** | `.\dev\check-import-boundaries.ps1 -ShowFiles` | Print each file being scanned |
| **I1 ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckTargetLiterals` | Run the target-literal ratchet against the frozen baseline |
| **Freeze/update baseline** | `.\dev\check-import-boundaries.ps1 -CheckTargetLiterals -UpdateBaseline` | Recompute and overwrite the frozen baseline |
| **I6 successor ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckProviderConditionals` | Run the provider-conditional ratchet (invariant I6, DI-4/DI-5) against the frozen baseline |
| **Freeze/update provider-conditional baseline** | `.\dev\check-import-boundaries.ps1 -CheckProviderConditionals -UpdateBaseline` | Recompute and overwrite the frozen provider-conditional baseline |
| **Function-level-import ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckFunctionLevelImports` | Run the function-level-import ratchet (structural-layering effort, D4/I6 — see [Architecture Overview — Decision 20](../../../datrix/docs/architecture/architecture-overview.md#decision-20-sealed-generated-ast-model-adopted)) against the frozen baseline |
| **Freeze/update function-level-import baseline** | `.\dev\check-import-boundaries.ps1 -CheckFunctionLevelImports -UpdateBaseline` | Recompute and overwrite the frozen function-level-import baseline |
| **Self-test only** | `.\dev\check-import-boundaries.ps1 -SelfTest` | Run only the self-test suite (rule model, scanners, ratchets, CLI mutation proof) and exit |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-CheckTargetLiterals`, `-UpdateBaseline`, `-CheckProviderConditionals`, `-CheckFunctionLevelImports`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = clean (or warning mode), 1 = violations found (import-boundary, I1 target-literal ratchet, I6 provider-conditional ratchet, function-level-import ratchet, or a self-test failure), 2 = usage/config error (including a missing baseline file when `-CheckTargetLiterals`, `-CheckProviderConditionals`, or `-CheckFunctionLevelImports` is passed without having frozen one yet)

**Self-test detail:** the script's own non-vacuity proof (rule-model invariants for `BOUNDARY_RULES`/allowed-subtree carve-outs, the provider-conditional and function-level-import AST scanners' detection + exclusion cases, both ratchet comparators' regression/no-regression/missing-baseline-as-zero behavior, and a real mutation-based CLI proof that plants a regression in an isolated fixture monorepo, proves detection, and proves it clears on revert). Runs automatically as **step 1 of every invocation** of this script (not only when `-SelfTest` is passed) — a self-test failure aborts before any real finding is reported. Pass `-SelfTest` alone to run only the self-test and skip the real scan.

**I6 successor ratchet detail:** scans `datrix-codegen-python/src` and `datrix-codegen-typescript/src` `.py` files (the LANGUAGE packages only — not a shared-layer scan like I1) for platform-identity conditionals: `== ProviderId(...)` / `!= ProviderId(...)` comparisons, `<deployment>.provider.value`/`str(<deployment>.provider)` string comparisons, and `match`/`case` over a provider subject. Excludes other provider axes (StorageProvider/EmailProvider/SmsProvider/SearchProvider/PaymentProvider/metrics-tracing provider), the `resolve_provider_identity` boundary function's own `ProviderId(x.value)` rewrap, and dict-dispatch-table lookups (`in`/`not in`, `.get(...)`) — those are a different successor shape not yet in scope. Baseline: `datrix/scripts/config/provider-conditional-baseline.toml`.

**Function-level-import ratchet detail:** scans ONLY `datrix-common/src` `.py` files (the structural-layering effort's own package-scoped ratchet, D4/I6 — never extend to other packages) for function-level imports: any `Import`/`ImportFrom` AST node that is not a direct top-level statement of its module (nested in a function/method body, an `if TYPE_CHECKING:` block, or a `try`/`except`). Baseline: `datrix/scripts/config/function-level-import-baseline.toml`, frozen after the `Service`/`Shared` decomposition landed.

### `dev\triage-failures.ps1`

Parses test/generation logs and groups failures by likely root cause. Produces a triage report suitable for feeding into `/fix-tests` or `/checkpoint-debug`.

| Mode | Command | Description |
|------|---------|-------------|
| **Parse log** | `.\dev\triage-failures.ps1 "path/to/results.log"` | Auto-detect format, output to stdout |
| **Force format** | `.\dev\triage-failures.ps1 "path/to/output.log" -Format pytest` | Force pytest parser |
| **Save report** | `.\dev\triage-failures.ps1 "path/to/results.log" -OutputFile "triage.md"` | Write Markdown report |
| **Debug** | `.\dev\triage-failures.ps1 "path/to/results.log" -Dbg` | Show auto-detect reasoning |

**Parameters:** `-LogPath` (positional 0, mandatory), `-Format` (pytest\|generate\|deploy), `-OutputFile <path>`, `-Dbg`

**Supported formats:** pytest output, generation result logs, deploy test logs. Auto-detected from file content.

### `dev\ruff-checker.ps1`

Checks Jinja2 templates by rendering with mock values and running ruff. No parameters.

| Mode | Command |
|------|---------|
| **Check templates** | `.\dev\ruff-checker.ps1` |

**Parameters:** (none)

---

## Build & Compile

### `dev\compile.ps1`

Compiles all Python in Datrix project folders (syntax + import check, including cross-project).

| Mode | Command | Description |
|------|---------|-------------|
| **All projects** | `.\dev\compile.ps1 -All` | Check all datrix repos |
| **One project** | `.\dev\compile.ps1 datrix-common` | Check one project |
| **Multiple projects** | `.\dev\compile.ps1 datrix-common datrix-language` | Check several |
| **By full path** | `.\dev\compile.ps1 D:\datrix\datrix-common` | Full path input |
| **With debug** | `.\dev\compile.ps1 -All -Dbg` | Debug output |

**Parameters:** `-All`, `-ProjectDir` (positional, variadic), `-Dbg`

### `dev\compile-any-path.ps1`

Syntax + import check for any Python path (files, directories, subfolders). Unlike `compile.ps1`, works for arbitrary paths (e.g., a routes folder inside generated code). Finds the containing installable package and runs that package's full import check.

| Mode | Command | Description |
|------|---------|-------------|
| **Directory** | `.\dev\compile-any-path.ps1 .\.generated\...\routes` | Check a subfolder |
| **Src dir** | `.\dev\compile-any-path.ps1 D:\datrix\datrix-common\src` | Check a src directory |
| **Multiple paths** | `.\dev\compile-any-path.ps1 path1 path2` | Check multiple paths |
| **With debug** | `.\dev\compile-any-path.ps1 path -Dbg` | Debug output |

**Parameters:** `-Path` (positional, variadic), `-Dbg`

### `dev\rebuild-parser.ps1`

Rebuilds the tree-sitter parser from `grammar.js`.

| Mode | Command | Description |
|------|---------|-------------|
| **Rebuild** | `.\dev\rebuild-parser.ps1` | Rebuild if grammar changed |
| **Force rebuild** | `.\dev\rebuild-parser.ps1 -Force` | Rebuild even if unchanged |

**Parameters:** `-Force`

---

## Audit & Comparison

### `dev\audit.ps1`

Audits generated Python code for placeholders and syntax errors under `.generated/python/docker`.

| Mode | Command | Description |
|------|---------|-------------|
| **With report** | `.\dev\audit.ps1 -Report examples-generated-audit-report.md` | Write markdown report |
| **Fail on issues** | `.\dev\audit.ps1 -Report report.md -FailOnSyntax -FailOnPlaceholders` | Non-zero exit on issues |
| **Custom output base** | `.\dev\audit.ps1 -OutputBase .generated2 -Report report.md` | Different generated root |

**Parameters:** `-OutputBase` (default: .generated), `-Report <path>`, `-FailOnSyntax`, `-FailOnPlaceholders`

### `dev\compare-generated.ps1`

Compares `.generated` vs `.generated_saved` with content-level feature detection. Writes a markdown report.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\dev\compare-generated.ps1` | Compare defaults, write report |
| **Custom report** | `.\dev\compare-generated.ps1 -Report my-report.md` | Custom report path |
| **Custom dirs** | `.\dev\compare-generated.ps1 -Current .generated -Saved .generated_saved` | Explicit directories |

**Parameters:** `-Current` (default: .generated), `-Saved` (default: .generated_saved), `-Report` (default: generated-comparison-report.md)

**Note:** this is *feature detection* (presence of known content patterns), not a byte-level diff — for byte-identity proofs use `dev\byte-identity-generate.ps1`.

### `dev\find-constants.ps1`

Finds string literals in Datrix Python projects and writes a grouped Markdown report (magic-constant audit). The report defaults to the current working directory — always pass `-Output` pointing into `D:\datrix\.test-output\`.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\find-constants.ps1 datrix-common -Output D:\datrix\.test-output\strings.md` | Report string literals in one project |
| **Multiple projects** | `.\dev\find-constants.ps1 datrix-common datrix-language -Output D:\datrix\.test-output\strings.md` | Several projects |
| **All projects** | `.\dev\find-constants.ps1 -All -Output D:\datrix\.test-output\strings.md` | Entire monorepo |
| **Tests only** | `.\dev\find-constants.ps1 -All -Tests -Output D:\datrix\.test-output\strings.md` | Scan only tests trees |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Src`, `-Tests` (default: both trees), `-Output <path>`, `-IncludeDocstrings`, `-MinLength <n>` (default 1), `-MaxValueChars <n>` (default 120)

### `dev\byte-identity-generate.ps1`

Proves a code change is **output-neutral**: generates a corpus of examples twice — once under a "before" code state, once under the working tree — and byte-diffs the two trees (per-file sha256; reports EVERY added/removed/changed path). Replaces the hand-rolled `byte_identity_*` scripts from `D:\datrix\.scripts`. Handles the two proven traps internally: equal-length output roots (`bef`/`aft` — unequal path lengths cause phantom ruff-batching diffs) and subprocess-isolated PYTHONPATH shadowing for the "before" generation. Uses `git archive` only (read-only — never checkout). Reuses the parity gate's pipeline + manifest code.

| Mode | Command | Description |
|------|---------|-------------|
| **Against a git ref** | `.\dev\byte-identity-generate.ps1 -Example "01-foundation" -BeforeRef HEAD -Packages datrix-codegen-python` | Snapshot named packages' `src/` at the ref for the "before" side |
| **Against a prebuilt tree** | `.\dev\byte-identity-generate.ps1 -Example "01-foundation" -BeforeTree D:\datrix\.tmp\before-overlay` | Caller-supplied "before" source overlay |
| **Test set corpus** | `.\dev\byte-identity-generate.ps1 -TestSet foundation -BeforeRef HEAD -Packages datrix-codegen-common` | Whole test set |

**Parameters:** `-Example <rel-path>` (repeatable/comma) OR `-TestSet <name>`; exactly one of `-BeforeRef <git-ref>` + `-Packages <pkg,pkg>` or `-BeforeTree <dir>`; `-Output <path>`; `-Dbg`

**Output:** `D:\datrix\.test-output\byte-identity\report.json` + `report.md` (unified diffs of changed text files). **Exit codes:** 0 = byte-identical, 1 = differences, 2 = usage / generation failure.

### `dev\conformance-gate.ps1`

Declarative design-acceptance assertion runner over a tree (generated output or package src) — the reusable backbone behind ad-hoc `prove_*`/`gate_*`/`*_conformance` scripts. Spec JSON: `{target, negative_control, assertions:[{id, type, pattern?, path?, glob?, expected_count?, description}]}` with types `must_contain`, `must_not_contain`, `file_exists`, `file_absent`, `count_equals` (regex patterns; binaries skipped). **Non-vacuity built in:** with `negative_control` set, a `must_not_contain` pattern must appear in the control tree or the assertion FAILS as vacuous. A self-test of every assertion type runs as step 1 of every invocation.

| Mode | Command | Description |
|------|---------|-------------|
| **Run a spec** | `.\dev\conformance-gate.ps1 -Spec D:\datrix\.tmp\my-invariant.spec.json` | PASS/FAIL ledger per assertion |
| **Self-test only** | `.\dev\conformance-gate.ps1 -SelfTest` | Prove every assertion type detects and passes |
| **Custom ledger path** | `.\dev\conformance-gate.ps1 -Spec ... -Output D:\datrix\.test-output\my-ledger.json` | Override ledger location |

**Parameters:** `-Spec <path>` (required unless `-SelfTest`), `-SelfTest`, `-Output <path>`, `-Dbg`

**Output:** `D:\datrix\.test-output\conformance\<spec-stem>-ledger.json` (violating/matching paths per assertion, cap 100 + total). **Exit codes:** 0 = all assertions pass, 1 = any fail, 2 = usage / bad spec / self-test failure.

### `dev\gendsl-census.ps1`

Per-domain census of a language's compiled genDSL definitions: file-clause counts (recursing `domain.files` + iteration/children), domain builders, declaring domains, **double-emit offenders** (declares files AND keeps a domain builder), and bridgeless declaring domains. Target list discovered from installed entry points at runtime — never hardcoded.

| Mode | Command | Description |
|------|---------|-------------|
| **Census a target** | `.\dev\gendsl-census.ps1 -Language python` | → `D:\datrix\.tmp\dev\gendsl-census-python.json` |
| **Unknown target** | `.\dev\gendsl-census.ps1 -Language cobol` | Fails loud listing installed targets |

**Parameters:** `-Language <name>` (required), `-Output <path>`, `-Dbg`. **Exit codes:** 0 = no double-emit offenders, 1 = offenders found, 2 = usage / unknown target.

---

## Evaluation

### `dev\evaluate-generated-scan.ps1`

Mechanical core of `/evaluate-generated` (quick mode): parses the system DSL with the real parser pipeline, then writes `project-scan.json` (service inventory with expected/actual dirs, manifest aggregation, language/platform detection, infra existence checklist, docker-compose cross-check, rolled-up `critical_blockers`/`warnings`) plus one `service-{name}.prompt.md` per service into the eval dir.

| Mode | Command | Description |
|------|---------|-------------|
| **Scan a project** | `.\dev\evaluate-generated-scan.ps1 -Source "examples/03-domains/ecommerce/system.dtrx" -Generated "D:\datrix\.generated\python\...\ecommerce" -EvalDir "D:\datrix\eval\2026-07-14-...-ecommerce"` | Full project scan + prompts |
| **Default eval dir** | omit `-EvalDir` | → `D:\datrix\.tmp\eval\<project>\` |
| **Non-default profile** | append `-ConfigProfile staging` | Config profile for the parse (default `test`) |

**Parameters:** `-Source <system.dtrx>` (required), `-Generated <dir>` (required), `-EvalDir <dir>`, `-ConfigProfile <name>`, `-Dbg`. **Exit codes:** 0 = scanned, 2 = usage / parse failure (analyzer diagnostics printed — usually itself the finding).

### `dev\evaluate-service-scan.ps1`

Mechanical core of `/evaluate-generated-service`: writes `service-<name>-scan.json` with the service's DSL feature inventory, manifest subset + both-direction filesystem set-diff, directory-name convention check, per-block/per-entity expected-artifact existence table, dead-code candidates, and Dockerfile/migrations/env-var data. Semantic verification (skill Phase 3.5) stays with the model.

| Mode | Command | Description |
|------|---------|-------------|
| **Scan a service** | `.\dev\evaluate-service-scan.ps1 -Source "{system.dtrx}" -Service ProductService -Generated "{service dir}" -ProjectGenerated "{project root}"` | Single service deep scan |
| **Single-service source** | omit `-Service` | Auto-selected when the source defines one service |
| **Explicit output** | append `-Output D:\datrix\eval\...\service-x-scan.json` | Default: `D:\datrix\.tmp\eval\<project>\` |

**Parameters:** `-Source <dtrx>` (required), `-Service <name>` (required for multi-service sources — fails loud listing names), `-Generated <dir>` (required), `-ProjectGenerated <dir>` (required), `-Output <path>`, `-ConfigProfile <name>`, `-Dbg`. **Exit codes:** 0 = scanned, 2 = usage / parse failure.

### `dev\evaluate-services.ps1`

Runs `/evaluate-generated-service` prompts in parallel using Claude Code CLI in non-interactive mode. Finds all `service-*.prompt.md` files in the evaluation folder and processes up to 5 concurrently.

| Mode | Command | Description |
|------|---------|-------------|
| **From eval dir** | `cd eval\2026-05-16-...; .\..\..\datrix\scripts\dev\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen>` | Uses current dir as eval folder |
| **Explicit eval dir** | `.\dev\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -EvalDir <path>` | Specify eval folder |
| **Custom parallelism** | `.\dev\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -Parallel 3` | Fewer concurrent jobs |
| **Different model** | `.\dev\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -Model sonnet` | Use sonnet instead of opus |

**Parameters:** `-SourceDir` (mandatory), `-GeneratedDir` (mandatory), `-EvalDir` (default: current directory), `-Parallel` (default: 5), `-Model` (default: opus)

**Prereqs:** Run `/evaluate-generated` first to produce `service-*.prompt.md` files.

---

## Utilities

### `dev\projects.ps1`

Lists Datrix project directories and subfolders.

| Mode | Command | Description |
|------|---------|-------------|
| **Project names** | `.\dev\projects.ps1` | List all project directory names |
| **Src paths** | `.\dev\projects.ps1 -Src` | Full path to each project's src/ |
| **Tests paths** | `.\dev\projects.ps1 -Tests` | Full path to each project's tests/ |
| **Docs paths** | `.\dev\projects.ps1 -Docs` | Full path to each project's docs/ |

**Parameters:** `-Src`, `-Tests`, `-Docs`

### `dev\project-structure.ps1`

Generates `.project-structure.md` files containing annotated ASCII directory trees (src/, tests/, templates/) for specified projects.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\project-structure.ps1 datrix-codegen-typescript` | Generate for one project |
| **Multiple projects** | `.\dev\project-structure.ps1 datrix-codegen-typescript datrix-codegen-python` | Generate for several |
| **All projects** | `.\dev\project-structure.ps1 -All` | All projects with src/ or tests/ |
| **Custom depth** | `.\dev\project-structure.ps1 datrix-codegen-typescript -Depth 6` | Deeper tree traversal |
| **Debug** | `.\dev\project-structure.ps1 datrix-codegen-typescript -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Depth` (default: 4), `-Dbg`

**Output:** Writes `.project-structure.md` to each project's root directory. File is gitignored.

### `dev\logic-map.ps1`

Extracts logic map markers from Python source files into a SQLite database (`d:\datrix\.logic-map\markers.db`). Markers are structured comments (`@canonical`, `@pattern`, `@boundary`, `@invariant`) that document canonical implementations and patterns.

| Mode | Command | Description |
|------|---------|-------------|
| **All projects** | `.\dev\logic-map.ps1 -All` | Rebuild entire database |
| **One project** | `.\dev\logic-map.ps1 datrix-language` | Scan one project |
| **Multiple projects** | `.\dev\logic-map.ps1 datrix-language datrix-common` | Scan several |
| **Src only** | `.\dev\logic-map.ps1 -All -Src` | Only src/ directories |
| **Tests only** | `.\dev\logic-map.ps1 -All -Tests` | Only tests/ directories |
| **Debug** | `.\dev\logic-map.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Src`, `-Tests`, `-Dbg`

### `dev\logic-map-report.ps1`

Dumps the logic map SQLite database to a readable Markdown report for human verification.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\dev\logic-map-report.ps1` | Write logic-map-report.md to current dir |
| **Custom output** | `.\dev\logic-map-report.ps1 -Output docs\logic-map.md` | Custom output path |

**Parameters:** `-Output` (positional 0)

### `dev\generate-test-rules.ps1`

Generates `@test-rule` conformance annotations for test functions using a local LLM (Ollama at `10.94.0.100`). Two phases: default **propose** writes reviewable proposals to `.test-output/test-rules/<model>/<package>.json` (+ `.md` preview) and touches no source; **-Apply** inserts the reviewed markers above the test functions. After generation, a **topic-consolidation pass** merges near-duplicate topic slugs and kebab-normalizes them (skip with `-NoConsolidate`). `tests/e2e` and `tests/integration` are **excluded by default** (opt in with `-IncludeE2e` / `-IncludeIntegration`, or target via `-Path`). Resumable — already-annotated and already-proposed functions are skipped. Output is per-model so different models don't clobber. Markers feed the logic-map Rule Matrix (`logic-map.ps1`).

| Mode | Command | Description |
|------|---------|-------------|
| **Propose (one package)** | `.\dev\generate-test-rules.ps1 datrix-codegen-python` | Propose for one package's tests |
| **Propose (sample)** | `.\dev\generate-test-rules.ps1 datrix-codegen-python -Limit 20` | Cap functions this run |
| **Propose (one file/subtree)** | `.\dev\generate-test-rules.ps1 -Path datrix-codegen-typescript\tests\unit\transpiler\test_operators.py -NoSeed` | Target a file/dir; package derived from path |
| **Propose (multiple subtrees)** | run once per `-Path` (e.g. `tests\transpiler` then `tests\unit\transpiler`) | Same package's runs share one proposal file and consolidate together; `powershell -File` can't pass `-Path` as an array |
| **Propose (all)** | `.\dev\generate-test-rules.ps1 -All` | Every package's tests tree |
| **Review (triage)** | `.\dev\generate-test-rules.ps1 datrix-codegen-typescript -Review` | Print triage: suspicious dims, weak behaviors, over-grouped/single-target topics (no LLM, no edits) |
| **Apply** | `.\dev\generate-test-rules.ps1 datrix-codegen-python -Apply` | Insert reviewed proposals |
| **Apply one file/subtree** | `.\dev\generate-test-rules.ps1 datrix-codegen-typescript -Apply -Path datrix-codegen-typescript\tests\unit\transpiler\test_operators.py` | Apply only proposals under the path |
| **Custom model** | `.\dev\generate-test-rules.ps1 -All -Model qwen3-coder:30b-ctx32k` | Override the model |
| **Debug** | `.\dev\generate-test-rules.ps1 datrix-codegen-python -Limit 5 -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Apply`, `-Review` (triage existing proposals; no LLM/edits), `-Model` (default: exaone-deep:32b), `-Endpoint` (default: http://10.94.0.100:11434), `-Parallel` (default: 4), `-Limit` (default: 0 = no limit), `-Path` (file/dir filter, repeatable; also scopes `-Apply`/`-Review`), `-NoSeed` (don't seed topic vocabulary from existing markers), `-NoConsolidate` (skip topic-merge pass), `-IncludeE2e`, `-IncludeIntegration` (e2e/integration excluded by default), `-Dbg`

### `dev\run-codemod.ps1`

Runs a Bowler codemod from `scripts/dev/codemods/`. All arguments after codemod name are passed through.

| Mode | Command | Description |
|------|---------|-------------|
| **Rename function** | `.\dev\run-codemod.ps1 01_rename_function parse_file parse_path` | Preview diff |
| **Rename class** | `.\dev\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src` | Rename in path |
| **Rename imports** | `.\dev\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src` | Update imports |

**Parameters:** `-CodemodName` (positional 0, required), `-CodemodArgs` (positional, variadic)

### `dev\datrix-count.ps1`

Counts `.dtrx` and `.dtrx.false` files across all datrix project directories.

| Mode | Command |
|------|---------|
| **Count** | `.\dev\datrix-count.ps1` |

**Parameters:** (none)

### `dev\file-count.ps1`

Counts files with a specified extension across all datrix project directories.

| Mode | Command | Description |
|------|---------|-------------|
| **Default (.j2)** | `.\dev\file-count.ps1` | Count Jinja2 template files |
| **Python files** | `.\dev\file-count.ps1 py` | Count .py files |
| **Any extension** | `.\dev\file-count.ps1 exe` | Count .exe files |

**Parameters:** `-Extension` (positional, default: j2)

---

## Cleanup

### `dev\cleanup-temps.ps1`

Lists/deletes temporary cache folders and files across the monorepo (`.pytest_cache`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.coverage`, etc.).

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\dev\cleanup-temps.ps1` | Show cache items with sizes |
| **Delete** | `.\dev\cleanup-temps.ps1 -Force` | Delete after confirmation |
| **Extra folders** | `.\dev\cleanup-temps.ps1 -Force -AdditionalFolders ".coverage","__pycache__"` | Add extra folder names |
| **Custom base** | `.\dev\cleanup-temps.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Force`, `-AdditionalFolders`, `-Dbg`

### `dev\delete-generated.ps1`

Renames `.generated` to `.generated_old` (or `_old_01` through `_old_99`) then deletes the renamed folder in a background job.

| Mode | Command | Description |
|------|---------|-------------|
| **Background delete** | `.\dev\delete-generated.ps1` | Rename + async delete |
| **Wait for delete** | `.\dev\delete-generated.ps1 -Wait` | Synchronous deletion |
| **Custom base** | `.\dev\delete-generated.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Wait`

### `dev\empty-folders.ps1`

Finds and lists all empty folders recursively from a given path.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\dev\empty-folders.ps1` | Find empty folders in current dir |
| **Custom path** | `.\dev\empty-folders.ps1 -Path D:\datrix` | Specific directory |
| **Delete** | `.\dev\empty-folders.ps1 -Force` | Delete after confirmation |
| **Delete at path** | `.\dev\empty-folders.ps1 -Path D:\datrix -Force` | Delete at specific path |

**Parameters:** `-Path` (default: current directory), `-Force`, `-Dbg`
