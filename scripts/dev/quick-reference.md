# Quick Reference — Development Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## Code Generation

### `dev\generate.ps1`

Generates Datrix projects from `.dtrx` source files. `-Language`/`-L` is **mandatory** and is the real generation target — forwarded to `datrix generate --language`, and also selects the output-path language segment (the two can never disagree). `-Runtime`/`-R` is a wrapper-only output-path selector; the output-path provider segment is read from each project's `config/system.dcfg` deployment block (active `-ConfigProfile`, default `test`), not a flag. Deployment runtime/provider, service flavor, and infrastructure flavor used for generation are read from project config.

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

**Parameters:** `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (any registered `datrix.languages` target, **mandatory**, the real generation target — also selects the output-path language segment), `-Runtime`/`-R` (docker-compose\|azure-container-apps\|azure-app-service\|ecs-fargate\|app-runner, output path only), `-ConfigProfile` (config profile that also selects the provider segment read from `config/system.dcfg`, e.g. test\|development\|production; default: test), `-OutputBase` (default: .generated), `-TestSet` (default: all), `-VerboseOutput`, `-Dbg`

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
| **Self-test only** | `.\dev\check-debug-artifacts.ps1 -SelfTest` | Run only the detection/false-positive self-test; no project argument needed |

**Parameters:** `-ProjectDir` (positional, variadic), `-All`, `-Strict`, `-IncludeGenerated`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = clean, 1 = artifacts found, 2 = usage error or self-test failure

**String-literal awareness:** Python files are scanned string-literal-aware — a pattern matching inside a string literal is data, not code, and is never reported. This is what keeps a test that embeds a child-process checker script as a triple-quoted source string from being flagged for every `print(` that child uses to report its result back over stdout (its only channel to the parent). Spans come from `tokenize`, so an f-string's interpolated `{...}` expressions stay scannable while its literal text does not; a file that cannot be tokenized is named loudly on stderr and then scanned line-based, so nothing is ever silently skipped. TypeScript files stay line-based (no correct TS lexer is available here), so the equivalent TS case — a `console.log` inside a template literal — is still reported.

**Self-test detail:** proves both directions — a real artifact IS detected, the same artifact inside a string literal is NOT, and (non-vacuity) those same lines DO match when string-awareness is disabled, so the second check passes because the span logic works rather than because the patterns stopped matching. Runs automatically as **step 1 of every invocation** (not only under `-SelfTest`); a self-test failure exits 2 before any scan result is reported.

### `dev\check-import-boundaries.ps1`

Enforces cross-package import boundary rules across the monorepo. Scans each package's `src/`, `tests/`, `fixtures/`, and `helpers/` directories for forbidden imports using Python AST analysis. See [Import Boundaries](../../../datrix-common/docs/architecture/import-boundaries.md) for the full rule table.

| Mode | Command | Description |
|------|---------|-------------|
| **Fail mode** | `.\dev\check-import-boundaries.ps1` | Report violations, exit 1 on any |
| **Warning mode** | `.\dev\check-import-boundaries.ps1 -Warn` | Report violations, exit 0 |
| **Custom base dir** | `.\dev\check-import-boundaries.ps1 -BaseDir D:\other` | Different workspace |
| **Show files** | `.\dev\check-import-boundaries.ps1 -ShowFiles` | Print each file being scanned |
| **I1 ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckTargetLiterals` | Run the target-literal ratchet (closed-world central-table/enum-member names PLUS a platform-token identifier/module-name shape match PLUS a key/comparand/`.get()`/dict-key/match-value literal-equality shape, an `isinstance`/`issubclass` type-check shape, and an import-module-path shape, each with an own-language exclusion for a language-core package's own served language) against the frozen baseline, over the DERIVED shared-package set |
| **Freeze/update baseline** | `.\dev\check-import-boundaries.ps1 -CheckTargetLiterals -UpdateBaseline` | Recompute and overwrite the frozen baseline |
| **I6 successor ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckProviderConditionals` | Run the provider-conditional ratchet (invariant I6, DI-4/DI-5) — both the `ProviderId`-shaped pattern and the plain-string-literal pattern — against the frozen baseline |
| **Freeze/update provider-conditional baseline** | `.\dev\check-import-boundaries.ps1 -CheckProviderConditionals -UpdateBaseline` | Recompute and overwrite the frozen provider-conditional baseline |
| **Shared-package provider-literal zero-tolerance check** | `.\dev\check-import-boundaries.ps1 -CheckProviderConditionals` | Runs automatically alongside the I6 ratchet above (same flag, no separate switch) — held at a hard zero for the DERIVED shared-package set (today `datrix_common`/`datrix_codegen_common`/`datrix_cli`/`datrix_language`), with **no baseline file**; any hit fails, always |
| **Function-level-import ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckFunctionLevelImports` | Run the function-level-import ratchet (structural layering — see [Architecture Overview — Decision 20](../../../datrix/docs/architecture/architecture-overview.md#decision-20-sealed-generated-ast-model-adopted)) against the frozen baseline. Also runs on every invocation that is not `-SelfTest`/`-UpdateBaseline` — see the detail below |
| **Lower function-level-import baseline** | `.\dev\check-import-boundaries.ps1 -CheckFunctionLevelImports -UpdateBaseline` | Lower each entry to its current count, drop emptied entries (named on stdout) and keep every surviving entry's `reason`; refuses (exit 1, baseline untouched) if any count would rise |
| **Shared-vocabulary ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckSharedVocabulary` | Run the shared-vocabulary ratchet (Decision 34 invariant 2) against the frozen baseline — fails when a `datrix-codegen-{lang}` module declares a module-level set/frozenset/dict whose normalized member set equals one already declared in `datrix_codegen_kernel.enums`, or in one of the additional non-`enums.py` canonical vocabulary homes the scanner declares (`_ADDITIONAL_SHARED_VOCABULARY_SOURCES` in `check-import-boundaries.py`, for a vocabulary moved out of `enums.py`, e.g. `LOG_BUILTIN_METHODS` in `datrix_codegen_common.transpiler.builtin_registry`) |
| **Freeze/update shared-vocabulary baseline** | `.\dev\check-import-boundaries.ps1 -CheckSharedVocabulary -UpdateBaseline` | Recompute and overwrite the frozen shared-vocabulary baseline |
| **Shared-layer target-name ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckSharedTargetNames` | Run the shared-layer target-name ratchet (Decision 34 invariant 3) against the frozen baseline — fails when a class, dataclass field, or type alias declared in `datrix_codegen_common` or `datrix_codegen_kernel` carries a registered **language** name as an identifier segment. Complements `-CheckTargetLiterals`, which matches a frozen list of central table names rather than the identifier shape. Language names come from the installed `datrix.languages` entry-point group at runtime, never a hardcoded literal. Deliberately scoped: **languages only** (the registered platform name `local` is a common English word and returns hundreds of spurious hits) and **`datrix_codegen_common` plus the generation kernel `datrix_codegen_kernel` only** (`datrix_common`/`datrix_cli` hold platform config-schema models and canonical-import API — see Decision 34's scope boundaries). The segment matcher treats `TypeScript` as one segment; a naive CamelCase split yields `type`+`script` and misses every TypeScript-named symbol |
| **Freeze/update shared-target-name baseline** | `.\dev\check-import-boundaries.ps1 -CheckSharedTargetNames -UpdateBaseline` | Recompute and overwrite the frozen shared-target-name baseline |
| **Own-package target-name ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckOwnTargetNames` | Run the own-target-name ratchet (Decision D5, Invariant I4) against the frozen baseline — fails when a function or method defined INSIDE a registered language package carries THAT SAME package's own registered language id or declared alias as an identifier segment. The vocabulary is read from each plugin's `name_tokens` (`declaration_for_language(lang).name_tokens`), never a literal list — a language's own package legitimately references its own types and imports everywhere, so this check is scoped to function/method DEFINITION names only, never a class name, field, or type reference (contrast `-CheckSharedTargetNames`, which is broader but scoped to `datrix_codegen_common` only). |
| **Freeze/update own-target-name baseline** | `.\dev\check-import-boundaries.ps1 -CheckOwnTargetNames -UpdateBaseline` | Recompute and overwrite the frozen own-target-name baseline |
| **Design-document label check** | `.\dev\check-import-boundaries.ps1 -CheckDesignLabels` | Hard zero, no baseline — fails when a docstring, comment, template comment, or runtime string carries a parenthesized or colon-suffixed design/task/phase reference number under any registered package's `src/`+`tests/` trees, or the `datrix` repo's own `scripts/dev`, `scripts/library`, `scripts/test` trees |
| **Cross-package vocabulary ratchet check** | `.\dev\check-import-boundaries.ps1 -CheckCrossPackageVocabulary` | Run the cross-package-vocabulary ratchet against the frozen baseline — fails when a module-level set/frozenset/dict/tuple literal's normalized member set is declared identically in two or more datrix-* packages. Also runs on every invocation that is not `-SelfTest`/`-UpdateBaseline` |
| **Freeze/update cross-package-vocabulary baseline** | `.\dev\check-import-boundaries.ps1 -CheckCrossPackageVocabulary -UpdateBaseline` | Recompute and overwrite the frozen cross-package-vocabulary baseline; every entry's written `reason` is read back and re-emitted, and a reasoned entry with no remaining hit is dropped and named on stderr |
| **Re-export-facade check** | `.\dev\check-import-boundaries.ps1 -CheckReexportFacades` | Hard zero, no baseline — fails when a name has a second import path through a facade (provider side, consumer side, a pyproject.toml entry point, or an unresolved import), relative imports included. `-UpdateBaseline` has no effect on this check. Also runs on every invocation that is not `-SelfTest`/`-UpdateBaseline` |
| **Re-export-facade per-site worklist** | `.\dev\check-import-boundaries.ps1 -CheckReexportFacades -ShowFiles -FacadeModule datrix_common.errors -ConsumerPackage datrix-codegen-python` | Print every hit, one line per site, optionally narrowed to one providing module and/or one repo |
| **Self-test only** | `.\dev\check-import-boundaries.ps1 -SelfTest` | Run only the self-test suite (rule model, scanners, ratchets, CLI mutation proof) and exit |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-CheckTargetLiterals`, `-UpdateBaseline`, `-CheckProviderConditionals`, `-CheckFunctionLevelImports`, `-CheckSharedVocabulary`, `-CheckSharedTargetNames`, `-CheckOwnTargetNames`, `-CheckCrossPackageVocabulary`, `-CheckDesignLabels`, `-CheckReexportFacades`, `-FacadeModule`, `-ConsumerPackage`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = clean (or warning mode), 1 = violations found (import-boundary, I1 target-literal ratchet, I6 provider-conditional ratchet, function-level-import ratchet, shared-vocabulary ratchet, shared-target-name ratchet, own-target-name ratchet, cross-package-vocabulary ratchet, the re-export-facade check, the design-document label check, or a self-test failure), 2 = usage/config error (including a missing baseline file when `-CheckTargetLiterals`, `-CheckProviderConditionals`, `-CheckFunctionLevelImports`, `-CheckSharedVocabulary`, `-CheckSharedTargetNames`, `-CheckOwnTargetNames`, or `-CheckCrossPackageVocabulary` is passed without having frozen one yet)

**Self-test detail:** the script's own non-vacuity proof (rule-model invariants for `BOUNDARY_RULES`/allowed-subtree carve-outs, the provider-conditional and function-level-import AST scanners' detection + exclusion cases, both ratchet comparators' regression/no-regression/missing-baseline-as-zero behavior, and a real mutation-based CLI proof that plants a regression in an isolated fixture monorepo, proves detection, and proves it clears on revert). Runs automatically as **step 1 of every invocation** of this script (not only when `-SelfTest` is passed) — a self-test failure aborts before any real finding is reported. Pass `-SelfTest` alone to run only the self-test and skip the real scan.

**I6 successor ratchet detail:** scans the `src/` `.py` files of every LANGUAGE package the discovered generator taxonomy reports (today `datrix-codegen-python` and `datrix-codegen-typescript` — not a shared-layer scan like I1) for platform-identity conditionals: `== ProviderId(...)` / `!= ProviderId(...)` comparisons, `<deployment>.provider.value`/`str(<deployment>.provider)` string comparisons, `match`/`case` over a provider subject, a bare `<var> == "<provider-id>"` comparison with no `ProviderId`/`.provider` wrapper, and a closed-world provider-id collection literal such as `frozenset({"azure"})`. Excludes other provider axes (StorageProvider/EmailProvider/SmsProvider/SearchProvider/PaymentProvider/metrics-tracing provider), the `resolve_provider_identity` boundary function's own `ProviderId(x.value)` rewrap, and any string literal in a non-conditional position (log messages, docstrings). Baseline: `datrix/scripts/config/provider-conditional-baseline.toml`.

**Shared-package provider-literal zero-tolerance detail:** a DISTINCT, STRICTER check from the I6 successor ratchet above — same AST patterns (`scan_file_for_provider_conditionals`, reused verbatim), but scoped to the DERIVED shared-package set (`discover_shared_packages` — every discovered package registering none of `datrix.languages`/`datrix.platforms`/`datrix.generators`/`datrix.extensions`; today `datrix_common`, `datrix_codegen_common`, `datrix_cli`, `datrix_language`) instead of the language packages, and held at a hard zero instead of a decrease-only ratchet: there is **no baseline file** for shared packages, so any single hit — ever — fails, with no grandfathering mechanism that could hide one. Runs unconditionally whenever `-CheckProviderConditionals` is passed (it needs no `-UpdateBaseline` companion, since there is nothing to freeze); a violation exits 1 alongside the I6 ratchet's own exit behavior.

**Function-level-import ratchet detail:** scans for function-level imports — any `Import`/`ImportFrom` AST node that is not a direct top-level statement of its module (nested in a function/method body, an `if TYPE_CHECKING:` block, or a `try`/`except`). Scope: every `src/` `.py` file of `datrix-common`, `datrix-semantic`, `datrix-migration` and `datrix-testing` (the code that was `datrix-common`'s before those packages were extracted from it; a policed package missing from disk exits 2), plus every file a baseline entry names in another package — a former core module that moved up a layer keeps its entry under its new path at the same count and stays policed there. Baseline: `datrix/scripts/config/function-level-import-baseline.toml`; decrease-only. Every entry carries a `reason` naming the import cycle that forces its deferrals (both modules) or their measured import cost. The check fails closed on an inert entry: one with no reason, a count of zero or less, a file that does not exist, or a file outside every package's `src/` tree fails the flag (exit 1), since an entry no scan reads would hold a count that polices nothing. A malformed or duplicate entry exits 2.

**Always-on wiring:** `check-import-boundaries.ps1` adds `-CheckFunctionLevelImports`, `-CheckCrossPackageVocabulary`, and `-CheckReexportFacades` to every invocation that is not `-SelfTest` or `-UpdateBaseline`. Any gate that runs the script — the default run, `-CheckTargetLiterals`, `-CheckProviderConditionals`, or any other flag — therefore enforces both ratchets and the facade hard zero without naming them.

**Own-target-name ratchet detail:** the mirror image of the shared-layer target-name ratchet above — that check holds the ONE shared package (`datrix_codegen_common`) to zero symbols carrying ANY registered language's name; I4 holds EVERY registered language package to zero function/method DEFINITIONS carrying THAT SAME package's own registered language id or declared alias (a `build_python_thing` inside `datrix_codegen_python` does not need "python" in its name; the package already says it — this is the token that hides a parallel implementation from a name-keyed behaviour-parity scan). The policed package set is the discovered taxonomy's `language_packages` (the same manifest-derived source the I6 and G1 ratchets already use) — never a hardcoded per-language tuple, so a fifth `datrix-codegen-<lang>` package is policed automatically the moment its manifest registers a `datrix.languages` entry point. The per-package vocabulary is read live from `declaration_for_language(lang).name_tokens | {lang}`, never a hardcoded per-language literal set. Scope is FUNCTION/METHOD DEFINITION names only — never a class name, dataclass field, or type reference (a language package legitimately references its own types by name everywhere; G2 already covers that declaration/type-reference shape for the one shared package it polices). A clean run prints each policed package's live count unconditionally (not only under `-ShowFiles`). Baseline: `datrix/scripts/config/own-target-name-baseline.toml`, keyed by package import name (e.g. `datrix_codegen_python`), seeded from the real per-package count and driven to zero as later migration work renames each remaining hit.

**Design-document label check detail:** unlike every ratchet above, this is a HARD ZERO with NO baseline file — a design/task/phase reference number is removed entirely wherever found, never grandfathered, so `-UpdateBaseline` has no effect on this check. A plain per-line text scan (not an AST walk), since a reference can appear in a docstring, a comment, a Jinja template comment, or a runtime string alike. Scans every `.py` and `.j2` file under `src/`+`tests/` of every package `discover_packages()` finds, PLUS the `datrix` repo's own `scripts/dev`, `scripts/library`, and `scripts/test` trees (its equivalent of `src/`/`tests/`, since the bare `datrix` repo carries no `src/` directory and is never a key in `discover_packages()`'s returned mapping). A bare `Decision NN` citation to the architecture overview never matches — the reference letter is never immediately adjacent to the digits in that citation form.

**Cross-package-vocabulary ratchet detail:** a DIFFERENT check from the shared-vocabulary ratchet above — that check asks "does this language package redeclare something `datrix_codegen_kernel.enums` declares?"; this one asks "is the same normalized member set declared, with a bare string literal, in two or more datrix-* packages?", with no notion of a canonical source and never consulting `datrix_codegen_kernel.enums` itself. Scans EVERY discovered `datrix-*` package's `src/` tree (via `discover_packages()`, not the four-package `LANGUAGE_PACKAGES` tuple G1/G2 use) for module-level `Assign`/`AnnAssign` statements whose value is a `set`/`frozenset`/`dict`/bare-`tuple` literal. A container built entirely from qualified `EnumClass.MEMBER` references (no bare string) is recognized by AST SHAPE alone (never by resolving against `datrix_codegen_kernel.enums`) and excluded as consumption, not declaration — this also correctly keeps the bare portion of a MIXED bare+qualified container in scope, rather than silently dropping the whole container when the qualified part references an enum from an arbitrary module. A value set declared twice within the SAME package is not cross-package and is never counted. Baseline: `datrix/scripts/config/cross-package-vocabulary-baseline.toml` — an entry carrying a `reason = "…"` key is a KNOWN-LEGITIMATE duplicate a design requires (Decision 36: the per-platform identity-provider-realization dicts required by Decision 22 I3, and the per-platform model-provider realization column plus the language target's per-provider client table that Decision 46 invariant 5 keeps out of every shared layer) and must never be driven to zero. The reason is part of the frozen record, not a comment: `-UpdateBaseline` reads every reason back through the loader and re-emits it, so a regeneration cannot silently turn a reviewed duplicate into an unexplained count (the self-test plants a reason and proves the round-trip). Every entry WITHOUT a reason drives to 0 as later consolidation work removes the redundant copy.

**Re-export-facade check detail:** enforces that a name has exactly one import path. Reports two AST shapes, both attributed to the PROVIDING module rather than the file where a statement happens to appear: **provider side** — a module whose top-level `from <datrix module> import N` binds a name listed in its own `__all__`, or imported as `N as N`, while the module does not itself define N ("defines" means a top-level `def`/`class`/assignment target, including under a top-level `if`/`try` — both branches of an `if` are walked unconditionally, so a name defined only under `if TYPE_CHECKING: ... else: ...` still counts as defined); **consumer side** — any `from M import N` ANYWHERE in a scanned file (not only at module top) where M is a Datrix module that does not define N and N is not itself a submodule of M (`from pkg import submodule` is a normal package traversal, never a hit). Two more shapes ride the same scan: every `pyproject.toml` `[project.entry-points.*]` value shaped `"module.path:attr"` is a site too (an `attr` the module does not define is a hit attributed to `module.path`), and a `from M import N` whose M resolves to no module on disk at all is a hit on its own (this is what proves, once a facade is emptied and its consumers rewritten, that every rewritten import lands on something real). Relative imports are followed: a `from .a import X` or `from . import sub` is resolved to its absolute module from the scanned file's own dotted name, on both the provider and the consumer side (a submodule bound by `from . import sub` is a package traversal, never a hit). Scope: every discovered package's `src/`+`tests/` trees and root-level `*.py` files (`conftest.py` and the like), every `.py` file under `datrix/scripts/`, and every `.py` file under `datrix/claude-config/.claude/hooks/` (a facade emptied later would otherwise break a script or a hook silently, with no static warning from this check). Hard zero, no baseline file: any hit fails, one failure line per site (`<providing module> [<shape>] <site file>:<line> <name>`), and `-UpdateBaseline` has no effect on this check — the same shape `-CheckDesignLabels` has. To clear a hit, rewrite the consumer to import from the module that defines the name, or remove the name from the facade's `__all__`/re-import. `-FacadeModule`/`-ConsumerPackage` (repeatable) narrow the `-ShowFiles` per-site worklist to one providing module or one repo.

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

**Note:** this is *feature detection* (presence of known content patterns), not a byte-level diff, and it proves nothing about output preservation — a behaviour-preservation claim is proven by a test in the owning package that renders the construct and asserts its output (see `datrix/docs/architecture/generated-output-stability.md`).

### `dev\find-constants.ps1`

Finds string literals in Datrix Python projects and writes a grouped Markdown report (magic-constant audit). The report defaults to the current working directory — always pass `-Output` pointing into `D:\datrix\.test-output\`.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\dev\find-constants.ps1 datrix-common -Output D:\datrix\.test-output\strings.md` | Report string literals in one project |
| **Multiple projects** | `.\dev\find-constants.ps1 datrix-common datrix-language -Output D:\datrix\.test-output\strings.md` | Several projects |
| **All projects** | `.\dev\find-constants.ps1 -All -Output D:\datrix\.test-output\strings.md` | Entire monorepo |
| **Tests only** | `.\dev\find-constants.ps1 -All -Tests -Output D:\datrix\.test-output\strings.md` | Scan only tests trees |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Src`, `-Tests` (default: both trees), `-Output <path>`, `-IncludeDocstrings`, `-MinLength <n>` (default 1), `-MaxValueChars <n>` (default 120)

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

Per-domain census of a language's compiled genDSL definitions: file-clause counts (recursing `domain.files` + iteration/children), domain builders, declaring domains, **double-emit offenders** (declares files AND keeps a domain builder), and **bridgeless-declaring domains** (declares files but no bridge callable carries the `MICRO_GENERATOR_CLS` owning-class attribute). Target list discovered from installed entry points at runtime — never hardcoded. Its own non-vacuity self-test (proves the double-emit and bridgeless comparators can each detect a forced synthetic defect) runs automatically as **step 1 of every invocation**, including a real census — a self-test failure aborts before any real finding is reported.

| Mode | Command | Description |
|------|---------|-------------|
| **Census a target** | `.\dev\gendsl-census.ps1 -Language python` | → `D:\datrix\.tmp\dev\gendsl-census-python.json` |
| **Unknown target** | `.\dev\gendsl-census.ps1 -Language cobol` | Fails loud listing installed targets |
| **Self-test only** | `.\dev\gendsl-census.ps1 -SelfTest` | Run only the non-vacuity self-test; no `-Language` needed |

**Parameters:** `-Language <name>` (required unless `-SelfTest`), `-Output <path>`, `-Dbg`, `-SelfTest`. **Exit codes:** 0 = no double-emit offenders AND no bridgeless-declaring domains, 1 = double-emit offenders OR bridgeless-declaring domains found, 2 = usage / unknown target / the non-vacuity self-test failed.

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

### `dev\code-index.ps1`

Queries the code index: an SQLite index of every Python file git sees in the workspace repositories (tracked, plus untracked files no `.gitignore` excludes, minus `scripts/config/code-index.json`'s `exclude`). It lives beside the checkout at `d:\datrix\.code-index\`. **Each development machine has its own**, built from its own working tree, so nothing is synchronised between machines.

**Creating and updating.** Run `-Setup` once on each machine: it builds the index (about ten seconds) and writes the index's MCP server into `d:\datrix\.mcp.json` with this machine's paths, keeping any other servers in the file. It then approves the server for this machine in `.claude\settings.local.json` (gitignored), because current Claude Code builds ignore an approval in the checked-in `settings.json`. Last, it removes the local-scope registrations older versions made. Claude Code reads `.mcp.json` from the opened folder for every installation and drive-letter spelling, so an extension update needs no re-run. Then restart Claude Code (in VS Code: Developer: Reload Window). `claude mcp get datrix-code-index` may still say "Pending approval"; a real session connects it regardless. There is nothing to schedule after that. Every query, from this script or an agent's MCP tool call, first brings the index up to date with the working tree (about 0.2 s when little changed), so edits, pulls and branch switches show up in the next query. Only files whose content changed are parsed again.

The index also owns the logic map. Every refresh rewrites `d:\datrix\.logic-map\markers.db` whenever the `@canonical`/`@pattern`/`@boundary`/`@invariant`/`@test-rule` markers in source changed.

Queries never leave the machine. `-Summarize` is the exception, and it only runs when asked for: it sends each module's outline and source to a local model server (plain HTTP on the local network, like every local-model script) and caches the summary per machine by content hash.

| Mode | Command | Description |
|------|---------|-------------|
| **Set up a machine** | `.\dev\code-index.ps1 -Setup` | Build the index and register the MCP server; re-run safely |
| **Definitions** | `.\dev\code-index.ps1 -Symbol to_snake_case` | Bare name, glob (`*Resolver`), `Class.method`, or dotted path; `-Kind class\|function\|method\|variable\|attribute` |
| **Uses** | `.\dev\code-index.ps1 -References datrix_common.utils.text.to_snake_case` | Resolved through imports (aliases, re-exports); methods match every `.name` access |
| **File outline** | `.\dev\code-index.ps1 -Outline datrix-common/src/datrix_common/utils/text.py` | Definitions with line ranges and signatures; path, unique suffix, or module name |
| **Search** | `.\dev\code-index.ps1 -Search "tenant isolation"` | Ranked full-text over names, signatures, docstrings, summaries, markers |
| **Logic map** | `.\dev\code-index.ps1 -Canonical text/to-snake` | Markers by topic path, topic segment, or words; `-IncludeTestRules` adds `@test-rule` |
| **Status** | `.\dev\code-index.ps1 -Status` | Counts, summary coverage, files with syntax errors |
| **Refresh** | `.\dev\code-index.ps1 -Refresh` | Bring the index up to date and report what changed |
| **Summaries** | `.\dev\code-index.ps1 -Summarize -Limit 100` | Summarize modules lacking a summary (`-Limit 0` = all) |
| **Adoption** | `.\dev\code-index.ps1 -Usage -Days 7` | Index tool calls against the greps, whole reads of large `.py` files and shell searches the index could have answered, with estimated tokens |

**Usage log:** the non-blocking PostToolUse hook `record-search-usage.py` appends one line per code-search call to `d:\datrix\.code-index\usage.jsonl` on each machine. It records the tool, the pattern or path searched (never file content) and the size of the answer. A shell search counts when `rg`/`grep`/`Select-String`/`findstr` starts a command or is piped from a file listing; piped from anything else it is an output filter and is not logged.

**Parameters:** exactly one action: `-Symbol`, `-References`, `-Outline`, `-Search`, `-Canonical`, `-Status`, `-Refresh`, `-Usage`, `-Summarize`, `-Setup`. Modifiers: `-Kind` (with `-Symbol`), `-IncludeTestRules` (with `-Canonical`), `-Days` (with `-Usage`; default 7, 0 = all), `-Limit` (results, files listed, or modules summarized), `-Workers` (default 4), `-LocalMachines`, `-LlmModel` and `-LlmTimeout` (default 300; all three with `-Summarize`).

**Exit codes:** 0 answered; 1 the query or index could not be answered as asked; 2 `-Summarize` found no local model server.

**Agents:** the MCP server (`library/dev/code_index_mcp.py`, stdio, no socket) offers the same queries as the tools `find_symbol`, `find_references`, `outline`, `search`, `find_canonical` and `index_status`.

### `dev\code-scan.ps1`

**On-demand code-health scan: one ranked digest instead of four scanners' raw output.** By default it scans only the packages whose content changed since their last scan. It tracks this with the code index's file hashes, in `d:\datrix\.code-index\scan-state.json`; the first run covers everything. It runs on this machine and changes nothing but the report and the scan state. Every finding is written, by section and then by package, to `d:\datrix\reports\code-scan\code-scan-<timestamp>.md`, headed by a per-package count table. The console gets one progress line per stage, then one line with the totals and the report's path, so a reader opens just the sections it needs.

| Section | Source | What the scan adds |
|---|---|---|
| Dead code: never used / used only by tests | two-pass Vulture (`metrics/dead_code_report.py`) | Each finding is checked against the code index across the whole workspace, so a use in another package refutes it. It is dropped if a Jinja template, a Python string (a `getattr` name, a dotted resolver path, genDSL text) or a `pyproject.toml` entry point names it. Unused imports are left to ruff. Classes and functions rank above fields. |
| Too complex | cyclomatic + cognitive (`metrics/complexity.py`) | Merged, highest first |
| Duplicated blocks | Pylint R0801 (`metrics/duplicate.py`) | Largest first |
| Docs drift | `dev/check_docs.py` checks over each package's `docs/` | — |

| Mode | Command | Description |
|------|---------|-------------|
| **Changed packages** | `.\dev\code-scan.ps1` | Packages changed since their last scan |
| **Named packages** | `.\dev\code-scan.ps1 datrix-common datrix-cli` | These, changed or not |
| **By folder** | `.\datrix\scripts\dev\code-scan.ps1 .\datrix-cli\` | A package folder in any form: relative, absolute, trailing slash, or a path inside it |
| **Everything** | `.\dev\code-scan.ps1 -All` | Every Python package (about 4 minutes) |

**Parameters:** `-Package` (positional; names or folders), `-All`, `-MinConfidence` (Vulture, default 60), `-DuplicateMinLines` (default 6)

**Exit codes:** 0 = digest written, or nothing changed since the last scan; 1 = the scan could not run (a missing tool such as Vulture, an unknown package, an unreadable scan state).

**Needs** `vulture`, `pylint`, `radon` and `cognitive_complexity` in the shared venv. None is declared by any manifest, so install any that are missing with `D:\datrix\.venv\Scripts\python.exe -m pip install <name>`. A missing Vulture now fails the scan instead of reporting no dead code.

### `dev\logic-map-report.ps1`

Refreshes the code index (which rewrites the logic map database if markers changed), then dumps the logic map SQLite database to a readable Markdown report for human verification.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\dev\logic-map-report.ps1` | Write logic-map-report.md to current dir |
| **Custom output** | `.\dev\logic-map-report.ps1 -Output docs\logic-map.md` | Custom output path |

**Parameters:** `-Output` (positional 0)

### `dev\generate-test-rules.ps1`

Generates `@test-rule` conformance annotations for test functions using a local LLM (the `-Model` model, on whichever local machine `library/shared/local_llm.py` finds serving it). Two phases: default **propose** writes reviewable proposals to `.test-output/test-rules/<model>/<package>.json` (+ `.md` preview) and touches no source; **-Apply** inserts the reviewed markers above the test functions. After generation, a **topic-consolidation pass** merges near-duplicate topic slugs and kebab-normalizes them (skip with `-NoConsolidate`). `tests/e2e` and `tests/integration` are **excluded by default** (opt in with `-IncludeE2e` / `-IncludeIntegration`, or target via `-Path`). Resumable — already-annotated and already-proposed functions are skipped. Output is per-model so different models don't clobber. Markers feed the logic-map Rule Matrix; the existing test-rule topics that seed and anchor consolidation are read from the code index, refreshed first (`code-index.ps1`).

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

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Apply`, `-Review` (triage existing proposals; no LLM/edits), `-Model` (default: exaone-deep:32b), `-LocalMachines` (machines to search, in preference order; default: the list in `library/shared/local_llm.py`), `-Parallel` (default: 4), `-Limit` (default: 0 = no limit), `-Path` (file/dir filter, repeatable; also scopes `-Apply`/`-Review`), `-NoSeed` (don't seed topic vocabulary from existing markers), `-NoConsolidate` (skip topic-merge pass), `-IncludeE2e`, `-IncludeIntegration` (e2e/integration excluded by default), `-Dbg`

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
