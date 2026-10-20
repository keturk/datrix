# Quick Reference — Scan Scripts

Static checks over source: `.dtrx`/`.dcfg` syntax and formatting, anti-pattern scanners, import
boundaries and their ratchets, compile/import checks, generated-output audits, and code-structure
reports (duplicated function bodies, unimplemented abstract methods).

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`
>
> **Whole-package scans are phase-boundary acts.** Inside a fix, run `semgrep.ps1`/`libcst.ps1`/`ast-grep.ps1` only with a named `-Rule` (or `-Pattern`, or `-SelfTest`) or a stated `SCAN_QUESTION:`. `guard-untargeted-scans.py` refuses the rest, and it applies the same refusal to their `.sh` twins and to `python -m datrix_scripts.scan.{semgrep,libcst,ast_grep}`, reading `--rule` / `--pattern` / `--all` / `--self-test` there. The guard parses these flags by name, so `-Rule`, `-All` and their `--kebab` forms keep exactly these spellings.

---

## DSL and Config

### `scan\syntax-checker.ps1`

Validates `.dtrx` file syntax using the tree-sitter parser.

| Mode | Command | Description |
|------|---------|-------------|
| **All repos** | `.\scan\syntax-checker.ps1` | Check all .dtrx files in all datrix repos |
| **Single file** | `.\scan\syntax-checker.ps1 path/to/file.dtrx` | Check one file |
| **Directory** | `.\scan\syntax-checker.ps1 examples/` | Check all .dtrx in a directory |
| **With debug** | `.\scan\syntax-checker.ps1 . -Dbg` | Debug logging |

**Parameters:** `-Path` (positional, default: all repos), `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.scan.syntax_checker`; POSIX twin `scan\syntax-checker.sh` (`--path`, `--dbg`, `--self-test`) — `bash scan/syntax-checker.sh --path examples/`.

### `scan\config-linter.ps1`

Lint/format `.dcfg` config documents using the `.dcfg` parser.

| Mode | Command | Description |
|------|---------|-------------|
| **All repos (format)** | `.\scan\config-linter.ps1 -All` | Format all `.dcfg` files across all datrix repos |
| **All repos (check)** | `.\scan\config-linter.ps1 -All -Check` | Check only; no file writes |
| **Specific path** | `.\scan\config-linter.ps1 examples\01-foundation\config` | Format `.dcfg` files under a specific directory |
| **Specific file (check)** | `.\scan\config-linter.ps1 path\to\system.dcfg -Check` | Check one file |
| **Self-test** | `.\scan\config-linter.ps1 -SelfTest` | Run only the formatter self-test (round-trip fidelity fixture); no `-All`/path needed |

**Parameters:** `-All`, `-Path` (positional, variadic), `-Check`, `-SelfTest`, `-Dbg`

**Module:** `datrix_scripts.scan.config_linter`; POSIX twin `scan\config-linter.sh` (`--path`, `--all`, `--check`, `--self-test`, `--dbg`) — `bash scan/config-linter.sh --all --check`.

**Self-test detail:** `-SelfTest` runs the module's `--self-test`, which regression-tests `format_dcfg`'s round-trip fidelity against a fixed `.dcfg` fixture: the name-less `service` wildcard must render as `service from ...`, never the invalid token `service *`; a `replace ... from tpl() { body }` body and an `inheriting base` clause must survive formatting; `format(format(x)) == format(x)` (idempotence); and a comment-bearing file must be left byte-for-byte unchanged with a blocking issue explaining why (the formatter does not preserve `//` comments). Prints `[OK]`/`[FAIL]` per check. Exit codes: 0 = all checks passed, 1 = at least one check failed.

### `scan\datrix-linter.ps1` / `scan\datrix-format.ps1`

`datrix-linter.ps1` runs the full semantic analysis over every `system.dtrx` entry point under the
given paths and reports each diagnostic (code, severity, message, location); exit 1 on an error
(or a warning under `-Strict`). `datrix-format.ps1` formats `.dtrx` files losslessly with the same
formatter as `datrix format`, verifying every token and comment before an atomic write, and writes
nothing if any file fails. `Get-Help .\scan\<script>.ps1 -Full` lists each one's parameters.

**Module:** `datrix_scripts.scan.datrix_linter` (`--path`, `--all`, `--strict`, `--dbg`, `--resolve-configs`, `--profile`, `--self-test`) and `datrix_scripts.scan.datrix_format` (`--path`, `--all`, `--check`, `--diff`, `--indent-size`, `--dbg`, `--self-test`); POSIX twins `scan\datrix-linter.sh`, `scan\datrix-format.sh` — `bash scan/datrix-format.sh --all --check`.

---

## Anti-Pattern Scanners

### `scan\libcst.ps1`

Scans for anti-patterns using LibCST: silent-fallback, empty-except, missing-encoding, banned-test-import, placeholder-body.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\scan\libcst.ps1 datrix-common` | Scan one project |
| **Multiple projects** | `.\scan\libcst.ps1 datrix-common datrix-language` | Scan several |
| **All projects** | `.\scan\libcst.ps1 -All` | Scan entire monorepo |
| **With report** | `.\scan\libcst.ps1 -All -Report libcst-report.md` | Write markdown report |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Report <path>`, `-SelfTest`

**Patterns detected:** `silent-fallback` (`dict.get(key, None)` — use explicit lookup + raise on missing), `empty-except` (`except: pass` / `except Exception: pass` — handle or re-raise), `missing-encoding` (`read_text()` / `write_text()` / `open()` without `encoding="utf-8"`), `banned-test-import` (`MagicMock` / `Mock` / `patch` / `SimpleNamespace` in test files), `placeholder-body` (`pass` or `raise NotImplementedError` as sole function body).

**Module:** `datrix_scripts.scan.libcst` — a LibCST visitor that traverses the concrete syntax tree and collects findings; POSIX twin `scan\libcst.sh` (`--projects`, `--all`, `--report`, `--self-test`) — `bash scan/libcst.sh --projects datrix-common`. The twin's `--all`, and a bare `--projects` run with no stated `SCAN_QUESTION:`, are refused like the wrapper's.

### `scan\semgrep.ps1`

Runs Semgrep with Datrix-specific rules from `scripts/config/semgrep-rules/`.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\scan\semgrep.ps1 datrix-common` | All rules on one project |
| **All projects** | `.\scan\semgrep.ps1 -All` | All rules on all projects |
| **Single rule** | `.\scan\semgrep.ps1 -All -Rule empty-except-pass` | One specific rule |
| **Multiple rules** | `.\scan\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup` | Selected rules |
| **List rules** | `.\scan\semgrep.ps1 -ListRules` | Show available rule names |
| **With report** | `.\scan\semgrep.ps1 -All -Report semgrep-report.md` | Write markdown report |
| **Show raw output** | `.\scan\semgrep.ps1 -All -ShowRaw` | Show raw semgrep output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Rule <name>` (repeatable), `-ListRules`, `-Report <path>`, `-ShowRaw`, `-SinglePass`, `-SelfTest`

**Rules** (one or a closely related set per YAML file in `scripts/config/semgrep-rules/`; `-ListRules` prints the current set): `silent-fallback-none` (`dict.get(key, None)`, WARNING), `default-type-mapping` (`type_map.get(t, "Any")`, ERROR), `empty-except-pass` (WARNING), `missing-encoding-read` / `missing-encoding-write` (`Path.read_text()` / `write_text()` without `encoding=`, WARNING), `banned-mock-import` (ERROR), `banned-simple-namespace` (in tests, ERROR), `return-none-lookup` (`return None` in `get_*/find_*/lookup_*/resolve_*`, WARNING), `string-concat-codegen` (`code += f"..."`, WARNING), `todo-comment` (INFO), `magic-number-status` (bare `200`/`404`/`500` in comparisons, WARNING). Adding a rule: [config/semgrep-rules/README.md](../config/semgrep-rules/README.md).

**Module:** `datrix_scripts.scan.semgrep` discovers the rules, expands directories into file lists, runs semgrep per rule and aggregates the findings; POSIX twin `scan\semgrep.sh` (`--projects`, `--all`, `--rule`, `--list-rules`, `--report`, `--show-raw`, `--single-pass`, `--self-test`) — `bash scan/semgrep.sh --projects datrix-common --rule empty-except-pass`.

**Installation:** semgrep is declared in the `scripts` dependency group of `datrix/pyproject.toml`,
which the shared venv installs. semgrep publishes no Windows ARM64 wheel, so the group leaves it out
of a native Windows ARM64 venv (an environment marker), and the scanner refuses there with a message
naming the platform; on every other platform a missing semgrep is refused with the install step.

**Notes:** semgrep uses `git ls-files` to discover files in a directory, so the scanner expands directories into explicit `.py` paths (a non-git workspace still works). A full scan with every rule takes ~20-25 minutes; one `-Rule` takes ~2-3. Jinja2 templates (`.j2`) are excluded.

### `scan\ast-grep.ps1`

Runs ast-grep structural Python rules from `scripts/config/ast-grep-rules/`, or a one-off ast-grep pattern.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\scan\ast-grep.ps1 datrix-common` | All saved rules on one project |
| **All projects** | `.\scan\ast-grep.ps1 -All` | All saved rules on all projects |
| **Single rule** | `.\scan\ast-grep.ps1 -All -Rule empty-except-pass` | One saved ast-grep rule |
| **Multiple rules** | `.\scan\ast-grep.ps1 -All -Rule empty-except-pass -Rule placeholder-notimplemented-body` | Selected rules |
| **One-off pattern** | `.\scan\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'` | Ad hoc structural search |
| **List rules** | `.\scan\ast-grep.ps1 -ListRules` | Show available rule names |
| **With report** | `.\scan\ast-grep.ps1 -All -Report ast-grep-report.md` | Write markdown report |
| **Show raw output** | `.\scan\ast-grep.ps1 -All -Rule empty-except-pass -ShowRaw` | Show raw ast-grep output |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Pattern <pattern>`, `-Rule <name>` (repeatable), `-ListRules`, `-Report <path>`, `-ShowRaw`, `-SelfTest`

**Rules** (one per YAML file in `scripts/config/ast-grep-rules/`; `-ListRules` prints the current set): `silent-fallback-none`, `default-type-mapping-any` (error), `empty-except-pass`, `return-none-lookup`, `missing-encoding-read-text`, `missing-encoding-write-text`, `open-without-encoding`, `placeholder-function-body`, `placeholder-notimplemented-body`, `generic-exception-raise`, `legacy-compatibility-call`, `banned-mock-import` (error), `banned-simple-namespace` (error), `codegen-string-append`, `flattened-entity-iteration` (error), `ad-hoc-plugin-registry` (error). Rule details: [config/ast-grep-rules/README.md](../config/ast-grep-rules/README.md).

**Module:** `datrix_scripts.scan.ast_grep`; POSIX twin `scan\ast-grep.sh` (`--projects`, `--all`, `--pattern`, `--rule`, `--list-rules`, `--report`, `--show-raw`, `--self-test`) — `bash scan/ast-grep.sh --projects datrix-common --rule empty-except-pass`. It discovers the rules, expands directories into file lists, runs ast-grep per rule and aggregates the findings. A package contributes its `src/` and `tests/`; the showcase repo (`datrix`, also covered by `-All`) contributes `scripts/`, its only Python.

**Notes:** PowerShell expands `$NAME` in double-quoted strings, so pass metavariable patterns in single quotes (`-Pattern 'raise Exception($MSG)'`). The npm install exposes `sg.cmd` and `ast-grep.cmd` on Windows; the wrapper prefers those shims. Jinja2 templates (`.j2`) are excluded.

**PowerShell note:** Use single quotes for ast-grep metavariables (`'$MSG'`) so PowerShell does not expand them.

### `scan\check-debug-artifacts.ps1`

Detects leftover debug/logging artifacts in source code (print, breakpoint, console.log, debugger, temp comments). Use as a pre-commit check to catch debug scatter.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\scan\check-debug-artifacts.ps1 datrix-codegen-python` | Scan one project |
| **All projects** | `.\scan\check-debug-artifacts.ps1 -All` | Scan entire monorepo |
| **Strict mode** | `.\scan\check-debug-artifacts.ps1 -All -Strict` | Also flag logger.debug/info with f-strings |
| **With details** | `.\scan\check-debug-artifacts.ps1 datrix-common -Dbg` | Show matching line content |
| **Self-test only** | `.\scan\check-debug-artifacts.ps1 -SelfTest` | Run only the detection/false-positive self-test; no project argument needed |

**Parameters:** `-ProjectDir` (positional, variadic), `-All`, `-Strict`, `-IncludeGenerated`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = clean, 1 = artifacts found, 2 = usage error or self-test failure

**Module:** `datrix_scripts.scan.check_debug_artifacts`; POSIX twin `scan\check-debug-artifacts.sh` (`--project-dir`, `--all`, `--strict`, `--include-generated`, `--self-test`, `--dbg`) — `bash scan/check-debug-artifacts.sh --project-dir datrix-common`.

**String-literal awareness:** Python files are scanned string-literal-aware — a pattern matching inside a string literal is data, not code, and is never reported. This is what keeps a test that embeds a child-process checker script as a triple-quoted source string from being flagged for every `print(` that child uses to report its result back over stdout (its only channel to the parent). Spans come from `tokenize`, so an f-string's interpolated `{...}` expressions stay scannable while its literal text does not; a file that cannot be tokenized is named loudly on stderr and then scanned line-based, so nothing is ever silently skipped. TypeScript files stay line-based (no correct TS lexer is available here), so the equivalent TS case — a `console.log` inside a template literal — is still reported.

**Self-test detail:** proves both directions — a real artifact IS detected, the same artifact inside a string literal is NOT, and (non-vacuity) those same lines DO match when string-awareness is disabled, so the second check passes because the span logic works rather than because the patterns stopped matching. Runs automatically as **step 1 of every invocation** (not only under `-SelfTest`); a self-test failure exits 2 before any scan result is reported.

### `scan\check-python-bytecode.ps1` / `scan\extra-parens.ps1`

`check-python-bytecode.ps1` fails when `.pyc`/`.pyo` files or `__pycache__` directories sit under a
package's `src/` tree; it needs only the standard library, and runs with `PYTHONPYCACHEPREFIX` set, so
the check itself writes no bytecode into any `src/`.
`extra-parens.ps1` removes extraneous parentheses with Ruff rule `UP034` only, over named projects
or `-All`. `Get-Help .\scan\<script>.ps1 -Full` lists each one's parameters.

**Module:** `datrix_scripts.scan.check_python_bytecode` (`--base-dir`, `--project-dir`, `--self-test`) and `datrix_scripts.scan.extra_parens` (`--projects`, `--all`, `--dry-run`, `--diff`, `--self-test`); POSIX twins `scan\check-python-bytecode.sh`, `scan\extra-parens.sh` — `bash scan/check-python-bytecode.sh --project-dir datrix-common`.

### `scan\ruff-checker.ps1`

Checks Jinja2 Python templates by rendering them with mock values and running ruff on the output. The report goes to `D:\datrix\.test-output\ruff-checker\ruff-report-<yyyyMMdd-HHmmss>.txt`, never into the scanned folder.

| Mode | Command |
|------|---------|
| **Templates under the current directory** | `.\scan\ruff-checker.ps1` |
| **One template folder** | `.\scan\ruff-checker.ps1 -TemplatesDir D:\datrix\datrix-codegen-python\src\datrix_codegen_python\templates` |
| **Debug** | `.\scan\ruff-checker.ps1 -Dbg` |

**Parameters:** `-TemplatesDir` (default: the current directory), `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.scan.ruff_checker`; POSIX twin `scan\ruff-checker.sh` (`--templates-dir`, `--dbg`, `--self-test`).

---

## Import Boundaries

### `scan\check-import-boundaries.ps1`

Enforces cross-package import boundary rules across the monorepo. Scans each package's `src/`, `tests/`, `fixtures/`, and `helpers/` directories for forbidden imports using Python AST analysis (`datrix_scripts.scan.import_boundaries`). See [Import Boundaries](../../../datrix-common/docs/architecture/import-boundaries.md) for the full rule table.

| Mode | Command | Description |
|------|---------|-------------|
| **Fail mode** | `.\scan\check-import-boundaries.ps1` | Report violations, exit 1 on any |
| **Warning mode** | `.\scan\check-import-boundaries.ps1 -Warn` | Report violations, exit 0 |
| **Custom base dir** | `.\scan\check-import-boundaries.ps1 -BaseDir D:\other` | Different workspace |
| **Show files** | `.\scan\check-import-boundaries.ps1 -ShowFiles` | Print each file being scanned |
| **Target-literal ratchet check** | `.\scan\check-import-boundaries.ps1 -CheckTargetLiterals` | Run the target-literal ratchet (closed-world central-table/enum-member names, never counting a reference the module binds only by a third-party import such as `tree_sitter.Language`, PLUS a platform-token identifier/module-name shape match PLUS a key/comparand/`.get()`/dict-key/match-value literal-equality shape, an `isinstance`/`issubclass` type-check shape (never the whole test of a narrowing `assert`, and never `local` as an identifier segment, where it is the English word), and an import-module-path shape, each with an own-language exclusion for a language-core package's own served language; the literal vocabulary also carries every identity provider type an installed platform package owns, plus an `IdentityProvider.<member>` attribute kind for those types and the built-in `external`, with `datrix-common`'s `identity/` tree held at a hard zero and no baseline entry admitted for it) against the frozen baseline, over the DERIVED shared-package set |
| **Freeze/update baseline** | `.\scan\check-import-boundaries.ps1 -CheckTargetLiterals -UpdateBaseline` | Recompute and overwrite the frozen baseline |
| **Provider-conditional ratchet check** | `.\scan\check-import-boundaries.ps1 -CheckProviderConditionals` | Run the provider-conditional ratchet — both the `ProviderId`-shaped pattern and the plain-string-literal pattern — against the frozen baseline |
| **Freeze/update provider-conditional baseline** | `.\scan\check-import-boundaries.ps1 -CheckProviderConditionals -UpdateBaseline` | Recompute and overwrite the frozen provider-conditional baseline |
| **Shared-package provider-literal zero-tolerance check** | `.\scan\check-import-boundaries.ps1 -CheckProviderConditionals` | Runs automatically alongside the provider-conditional ratchet above (same flag, no separate switch) — held at a hard zero for the DERIVED shared-package set (today `datrix_common`/`datrix_codegen_kernel`/`datrix_codegen_common`/`datrix_codegen_typescript_core`/`datrix_cli`/`datrix_language`/`datrix_semantic`/`datrix_migration`/`datrix_testing`), with **no baseline file**; any hit fails, always |
| **Function-level-import ratchet check** | `.\scan\check-import-boundaries.ps1 -CheckFunctionLevelImports` | Run the function-level-import ratchet (structural layering — see [Architecture Overview — Decision 20](../../../datrix/docs/architecture/architecture-overview.md#decision-20-sealed-generated-ast-model-adopted)) against the frozen baseline. Also runs on every invocation that is not `-SelfTest`/`-UpdateBaseline` — see the detail below |
| **Lower function-level-import baseline** | `.\scan\check-import-boundaries.ps1 -CheckFunctionLevelImports -UpdateBaseline` | Lower each entry to its current count, drop emptied entries (named on stdout) and keep every surviving entry's `reason`; refuses (exit 1, baseline untouched) if any count would rise |
| **Shared-vocabulary ratchet check** | `.\scan\check-import-boundaries.ps1 -CheckSharedVocabulary` | Run the shared-vocabulary ratchet (Decision 34 invariant 2) against the frozen baseline — fails when a `datrix-codegen-{lang}` module declares a module-level set/frozenset/dict whose normalized member set equals one already declared in `datrix_codegen_kernel.enums`, or in one of the additional non-`enums.py` canonical vocabulary homes the scanner declares (`_ADDITIONAL_SHARED_VOCABULARY_SOURCES` in `datrix_scripts.scan.import_boundaries.shared_vocabulary`, for a vocabulary moved out of `enums.py`, e.g. `LOG_BUILTIN_METHODS` in `datrix_codegen_common.transpiler.builtin_registry`) |
| **Freeze/update shared-vocabulary baseline** | `.\scan\check-import-boundaries.ps1 -CheckSharedVocabulary -UpdateBaseline` | Recompute and overwrite the frozen shared-vocabulary baseline |
| **Shared-layer target-name ratchet check** | `.\scan\check-import-boundaries.ps1 -CheckSharedTargetNames` | Run the shared-layer target-name ratchet (Decision 34 invariant 3) against the frozen baseline — fails when a class, dataclass field, or type alias declared in `datrix_codegen_common` or `datrix_codegen_kernel` carries a registered **language** name or one of that language's declared alias tokens (`declaration_for_language(lang).name_tokens`, such as `ts`) as an identifier segment. Complements `-CheckTargetLiterals`, which matches a frozen list of central table names rather than the identifier shape. Language names and aliases come from the installed `datrix.languages` entry-point group and each language's own declaration at runtime, never a hardcoded literal. A short alias can be an ordinary abbreviation, so each hit is either renamed or becomes a reviewed baseline entry with a written `reason`; an entry without a reason fails the check. Deliberately scoped to **languages** — each name and its aliases, never platform names (excluded: the registered platform name `local` is a common English word and returns hundreds of spurious hits) — and **`datrix_codegen_common` plus the generation kernel `datrix_codegen_kernel` only** (`datrix_common`/`datrix_cli` hold platform config-schema models and canonical-import API — see Decision 34's scope boundaries). The segment matcher treats `TypeScript` as one segment; a naive CamelCase split yields `type`+`script` and misses every TypeScript-named symbol |
| **Freeze/update shared-target-name baseline** | `.\scan\check-import-boundaries.ps1 -CheckSharedTargetNames -UpdateBaseline` | Recompute and overwrite the frozen shared-target-name baseline counts; every written `reason` is preserved, and a reasoned entry that no longer has a hit is named on stderr and dropped |
| **Own-package target-name ratchet check** | `.\scan\check-import-boundaries.ps1 -CheckOwnTargetNames` | Run the own-target-name ratchet against the frozen baseline — fails when a function or method defined INSIDE a registered language package carries THAT SAME package's own registered language id or declared alias as an identifier segment. The vocabulary is read from each plugin's `name_tokens` (`declaration_for_language(lang).name_tokens`), never a literal list — a language's own package legitimately references its own types and imports everywhere, so this check is scoped to function/method DEFINITION names only, never a class name, field, or type reference (contrast `-CheckSharedTargetNames`, which is broader but scoped to `datrix_codegen_common` only). |
| **Freeze/update own-target-name baseline** | `.\scan\check-import-boundaries.ps1 -CheckOwnTargetNames -UpdateBaseline` | Recompute and overwrite the frozen own-target-name baseline |
| **Cross-package vocabulary ratchet check** | `.\scan\check-import-boundaries.ps1 -CheckCrossPackageVocabulary` | Run the cross-package-vocabulary ratchet against the frozen baseline — fails when a module-level set/frozenset/dict/tuple literal's normalized member set is declared identically in two or more datrix-* packages. Also runs on every invocation that is not `-SelfTest`/`-UpdateBaseline` |
| **Freeze/update cross-package-vocabulary baseline** | `.\scan\check-import-boundaries.ps1 -CheckCrossPackageVocabulary -UpdateBaseline` | Recompute and overwrite the frozen cross-package-vocabulary baseline; every entry's written `reason` is read back and re-emitted, and a reasoned entry with no remaining hit is dropped and named on stderr |
| **Re-export-facade check** | `.\scan\check-import-boundaries.ps1 -CheckReexportFacades` | Hard zero, no baseline — fails when a name has a second import path through a facade (provider side, consumer side, a module object read by `m.attr`/`getattr(m, "attr")`, a pyproject.toml entry point, or an unresolved import), relative imports and `tests.<module>` test-tree modules included. A test proving a module uses its shared home calls `datrix_testing.module_sources.assert_module_uses_shared` rather than comparing `module.name` by identity. `-UpdateBaseline` has no effect on this check. Also runs on every invocation that is not `-SelfTest`/`-UpdateBaseline` |
| **Re-export-facade per-site worklist** | `.\scan\check-import-boundaries.ps1 -CheckReexportFacades -ShowFiles -FacadeModule datrix_common.errors -ConsumerPackage datrix-codegen-python` | Print every hit, one line per site, optionally narrowed to one providing module and/or one repo |
| **Self-test only** | `.\scan\check-import-boundaries.ps1 -SelfTest` | Run only the self-test suite (rule model, scanners, ratchets, CLI mutation proof) and exit |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-CheckTargetLiterals`, `-UpdateBaseline`, `-CheckProviderConditionals`, `-CheckFunctionLevelImports`, `-CheckSharedVocabulary`, `-CheckSharedTargetNames`, `-CheckOwnTargetNames`, `-CheckCrossPackageVocabulary`, `-CheckReexportFacades`, `-FacadeModule`, `-ConsumerPackage`, `-SelfTest`, `-Dbg`

**Module:** `datrix_scripts.scan.check_import_boundaries` (the wrapper's options, the always-on ratchets and the self-test) over the `datrix_scripts.scan.import_boundaries` package (the rule model, the scanners and the ratchets; `python -m datrix_scripts.scan.import_boundaries` runs the scan alone); POSIX twin `scan\check-import-boundaries.sh` (`--warn`, `--show-files`, `--base-dir`, `--check-target-literals`, `--update-baseline`, `--check-provider-conditionals`, `--check-function-level-imports`, `--check-shared-vocabulary`, `--check-shared-target-names`, `--check-own-target-names`, `--check-cross-package-vocabulary`, `--check-reexport-facades`, `--facade-module`, `--consumer-package`, `--self-test`, `--dbg`) — `bash scan/check-import-boundaries.sh --check-target-literals`.

**Exit codes:** 0 = clean (or warning mode), 1 = violations found (import-boundary, target-literal ratchet, provider-conditional ratchet, function-level-import ratchet, shared-vocabulary ratchet, shared-target-name ratchet, own-target-name ratchet, cross-package-vocabulary ratchet, the re-export-facade check, or a self-test failure), 2 = usage/config error (including a missing baseline file when `-CheckTargetLiterals`, `-CheckProviderConditionals`, `-CheckFunctionLevelImports`, `-CheckSharedVocabulary`, `-CheckSharedTargetNames`, `-CheckOwnTargetNames`, or `-CheckCrossPackageVocabulary` is passed without having frozen one yet)

**Self-test detail:** the script's own non-vacuity proof (rule-model invariants for `BOUNDARY_RULES`/allowed-subtree carve-outs, the provider-conditional and function-level-import AST scanners' detection + exclusion cases, both ratchet comparators' regression/no-regression/missing-baseline-as-zero behavior, and a real mutation-based CLI proof that plants a regression in an isolated fixture monorepo, proves detection, and proves it clears on revert). Runs automatically as **step 1 of every invocation** of this script (not only when `-SelfTest` is passed) — a self-test failure aborts before any real finding is reported. Pass `-SelfTest` alone to run only the self-test and skip the real scan.

**Provider-conditional ratchet detail:** scans the `src/` `.py` files of every LANGUAGE package the discovered generator taxonomy reports (not a shared-layer scan like the target-literal ratchet) for platform-identity conditionals: `== ProviderId(...)` / `!= ProviderId(...)` comparisons, `<deployment>.provider.value`/`str(<deployment>.provider)` string comparisons, `match`/`case` over a provider subject, a bare `<var> == "<provider-id>"` comparison with no `ProviderId`/`.provider` wrapper, and a closed-world provider-id collection literal such as `frozenset({"azure"})`. Excludes other provider axes (StorageProvider/EmailProvider/SmsProvider/SearchProvider/PaymentProvider/metrics-tracing provider), the `resolve_provider_identity` boundary function's own `ProviderId(x.value)` rewrap, and any string literal in a non-conditional position (log messages, docstrings). Baseline: `datrix/scripts/config/provider-conditional-baseline.toml`.

**Shared-package provider-literal zero-tolerance detail:** a DISTINCT, STRICTER check from the provider-conditional ratchet above — same AST patterns (`scan_file_for_provider_conditionals`, reused verbatim), but scoped to the DERIVED shared-package set (`discover_shared_packages` — every discovered package registering none of `datrix.languages`/`datrix.platforms`/`datrix.generators`/`datrix.extensions`) instead of the language packages, and held at a hard zero instead of a decrease-only ratchet: there is **no baseline file** for shared packages, so any single hit — ever — fails, with no grandfathering mechanism that could hide one. Runs unconditionally whenever `-CheckProviderConditionals` is passed (it needs no `-UpdateBaseline` companion, since there is nothing to freeze); a violation exits 1 alongside the ratchet's own exit behavior.

**Function-level-import ratchet detail:** scans for function-level imports — any `Import`/`ImportFrom` AST node that is not a direct top-level statement of its module (nested in a function/method body, an `if TYPE_CHECKING:` block, or a `try`/`except`). Scope: every `src/` `.py` file of `datrix-common`, `datrix-semantic`, `datrix-migration` and `datrix-testing` (the code that was `datrix-common`'s before those packages were extracted from it; a policed package missing from disk exits 2), plus every file a baseline entry names in another package — a former core module that moved up a layer keeps its entry under its new path at the same count and stays policed there. Baseline: `datrix/scripts/config/function-level-import-baseline.toml`; decrease-only. Every entry carries a `reason` naming the import cycle that forces its deferrals (both modules) or their measured import cost. The check fails closed on an inert entry: one with no reason, a count of zero or less, a file that does not exist, or a file outside every package's `src/` tree fails the flag (exit 1), since an entry no scan reads would hold a count that polices nothing. A malformed or duplicate entry exits 2.

**Always-on wiring:** `check-import-boundaries.ps1` (its module) adds `-CheckFunctionLevelImports`, `-CheckCrossPackageVocabulary`, and `-CheckReexportFacades` to every invocation that is not `-SelfTest` or `-UpdateBaseline`. Any gate that runs the script — the default run, `-CheckTargetLiterals`, `-CheckProviderConditionals`, or any other flag — therefore enforces both ratchets and the facade hard zero without naming them.

**Own-target-name ratchet detail:** the mirror image of the shared-layer target-name ratchet above — that check holds the shared layer to zero symbols carrying ANY registered language's name; this one holds EVERY registered language package to zero function/method DEFINITIONS carrying THAT SAME package's own registered language id or declared alias (a `build_python_thing` inside `datrix_codegen_python` does not need "python" in its name; the package already says it — this is the token that hides a parallel implementation from a name-keyed behaviour-parity scan). The policed package set is the discovered taxonomy's `language_packages` — never a hardcoded per-language tuple, so a new `datrix-codegen-<lang>` package is policed automatically the moment its manifest registers a `datrix.languages` entry point. The per-package vocabulary is read live from `declaration_for_language(lang).name_tokens | {lang}`, never a hardcoded per-language literal set. Scope is FUNCTION/METHOD DEFINITION names only — never a class name, dataclass field, or type reference. A clean run prints each policed package's live count unconditionally (not only under `-ShowFiles`). Baseline: `datrix/scripts/config/own-target-name-baseline.toml`, keyed by package import name (e.g. `datrix_codegen_python`), seeded from the real per-package count and driven to zero as later migration work renames each remaining hit.

**Cross-package-vocabulary ratchet detail:** a DIFFERENT check from the shared-vocabulary ratchet above — that check asks "does this language package redeclare something `datrix_codegen_kernel.enums` declares?"; this one asks "is the same normalized member set declared, with a bare string literal, in two or more datrix-* packages?", with no notion of a canonical source and never consulting `datrix_codegen_kernel.enums` itself. Scans EVERY discovered `datrix-*` package's `src/` tree (via `discover_packages()`) for module-level `Assign`/`AnnAssign` statements whose value is a `set`/`frozenset`/`dict`/bare-`tuple` literal. A container built entirely from qualified `EnumClass.MEMBER` references (no bare string) is recognized by AST SHAPE alone (never by resolving against `datrix_codegen_kernel.enums`) and excluded as consumption, not declaration — this also correctly keeps the bare portion of a MIXED bare+qualified container in scope, rather than silently dropping the whole container when the qualified part references an enum from an arbitrary module. A value set declared twice within the SAME package is not cross-package and is never counted. Baseline: `datrix/scripts/config/cross-package-vocabulary-baseline.toml` — an entry carrying a `reason = "…"` key is a KNOWN-LEGITIMATE duplicate a design requires (Decision 36: the per-platform identity-provider-realization dicts, and the per-platform model-provider realization column plus the language target's per-provider client table that Decision 46 keeps out of every shared layer) and must never be driven to zero. The reason is part of the frozen record, not a comment: `-UpdateBaseline` reads every reason back through the loader and re-emits it, so a regeneration cannot silently turn a reviewed duplicate into an unexplained count (the self-test plants a reason and proves the round-trip). Every entry WITHOUT a reason drives to 0 as later consolidation work removes the redundant copy.

**Re-export-facade check detail:** enforces that a name has exactly one import path. Reports two AST shapes, both attributed to the PROVIDING module rather than the file where a statement happens to appear: **provider side** — a module whose top-level `from <datrix module> import N` binds a name listed in its own `__all__`, or imported as `N as N`, while the module does not itself define N ("defines" means a top-level `def`/`class`/assignment target, including under a top-level `if`/`try` — both branches of an `if` are walked unconditionally, so a name defined only under `if TYPE_CHECKING: ... else: ...` still counts as defined); **consumer side** — any `from M import N` ANYWHERE in a scanned file (not only at module top) where M is a Datrix module that does not define N and N is not itself a submodule of M (`from pkg import submodule` is a normal package traversal, never a hit). Two more shapes ride the same scan: every `pyproject.toml` `[project.entry-points.*]` value shaped `"module.path:attr"` is a site too (an `attr` the module does not define is a hit attributed to `module.path`), and a `from M import N` whose M resolves to no module on disk at all is a hit on its own (this is what proves, once a facade is emptied and its consumers rewritten, that every rewritten import lands on something real). Relative imports are followed: a `from .a import X` or `from . import sub` is resolved to its absolute module from the scanned file's own dotted name, on both the provider and the consumer side (a submodule bound by `from . import sub` is a package traversal, never a hit). Scope: every discovered package's `src/`+`tests/` trees and root-level `*.py` files (`conftest.py` and the like), every `.py` file under `datrix/scripts/`, and every `.py` file under `datrix/claude-config/.claude/hooks/` (a facade emptied later would otherwise break a script or a hook silently, with no static warning from this check). Hard zero, no baseline file: any hit fails, one failure line per site (`<providing module> [<shape>] <site file>:<line> <name>`), and `-UpdateBaseline` has no effect on this check. To clear a hit, rewrite the consumer to import from the module that defines the name, or remove the name from the facade's `__all__`/re-import. `-FacadeModule`/`-ConsumerPackage` (repeatable) narrow the `-ShowFiles` per-site worklist to one providing module or one repo.

---

## Compile and Audit

### `scan\compile.ps1`

Syntax + import check of Python, in two parameter sets. **Projects:** every Python file of the named Datrix projects (including cross-project imports). **Path:** any file or directory (a routes folder inside generated code, say); it finds the containing installable package and runs that package's full import check, so a missing import is caught. Relative names and paths resolve against the workspace root.

| Mode | Command | Description |
|------|---------|-------------|
| **All projects** | `.\scan\compile.ps1 -All` | Check all datrix repos |
| **One project** | `.\scan\compile.ps1 datrix-common` | Check one project |
| **Multiple projects** | `.\scan\compile.ps1 datrix-common datrix-language` | Check several |
| **By full path** | `.\scan\compile.ps1 D:\datrix\datrix-common` | Full path input |
| **Any path** | `.\scan\compile.ps1 -Path .\.generated\...\routes` | Check a subfolder of generated code |
| **Several paths** | `.\scan\compile.ps1 -Path path1,path2` | Check multiple paths |
| **With debug** | `.\scan\compile.ps1 -All -Dbg` | Debug output |

**Parameters:** Projects set: `-All`, `-ProjectDir` (positional, variadic); Path set: `-Path` (one or more); both: `-Dbg`; SelfTest set: `-SelfTest`

**What it does:** (1) **syntax check** — every discovered `.py` file goes through `py_compile`; (2) **import check** — each installable package (`src/` and `pyproject.toml`) is imported with **all its submodules** in a subprocess whose `PYTHONPATH` holds every Datrix project's `src`, which exercises cross-package imports: a module doing `from datrix_language.parser import ModuleNode` that fails is reported as an import error.

**Module:** `datrix_scripts.scan.compile` — the Projects set (file discovery, `py_compile`, per-package import check with the submodule walk) and the Path set (`compile_any_path`: finds the package containing each path and runs that package's check); POSIX twin `scan\compile.sh` (`--all`, `--project-dir`, `--path`, `--dbg`, `--self-test`) — `bash scan/compile.sh --project-dir datrix-common`.

### `scan\audit.ps1`

Audits generated Python code for placeholders and syntax errors under `.generated/python/docker`.

| Mode | Command | Description |
|------|---------|-------------|
| **With report** | `.\scan\audit.ps1 -Report examples-generated-audit-report.md` | Write markdown report |
| **Fail on issues** | `.\scan\audit.ps1 -Report report.md -FailOnSyntax -FailOnPlaceholders` | Non-zero exit on issues |
| **Custom output base** | `.\scan\audit.ps1 -OutputBase .generated2 -Report report.md` | Different generated root |

**Parameters:** `-OutputBase` (default: .generated), `-Report <path>`, `-FailOnSyntax`, `-FailOnPlaceholders`, the local-model triage set (`-LlmTriage`, `-LlmLimit`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout`, `-LlmNumPredict`, `-LlmTemperature`), `-SelfTest`

**Module:** `datrix_scripts.scan.audit`; POSIX twin `scan\audit.sh` (`--output-base`, `--report`, `--fail-on-syntax`, `--fail-on-placeholders`, `--llm-triage`, `--llm-limit`, `--local-machines`, `--llm-model`, `--llm-timeout`, `--llm-num-predict`, `--llm-temperature`, `--self-test`) — `bash scan/audit.sh --report report.md`.

### `scan\dgen-census.ps1`

Per-domain census of a language's compiled DAL generator definitions: file-clause counts (recursing `domain.files` + iteration/children), domain builders, declaring domains, and **double-emit offenders** (declares files AND keeps a domain builder). Target list discovered from installed entry points at runtime — never hardcoded. Its own non-vacuity self-test (proves the double-emit comparator detects a forced synthetic defect and leaves a clean domain alone) runs automatically as **step 1 of every invocation**, including a real census — a self-test failure aborts before any real finding is reported.

| Mode | Command | Description |
|------|---------|-------------|
| **Census a target** | `.\scan\dgen-census.ps1 -Language python` | → `D:\datrix\.tmp\dev\dgen-census-python.json` |
| **Unknown target** | `.\scan\dgen-census.ps1 -Language cobol` | Fails loud listing installed targets |
| **Self-test only** | `.\scan\dgen-census.ps1 -SelfTest` | Run only the non-vacuity self-test; no `-Language` needed |

**Parameters:** `-Language <name>` (required unless `-SelfTest`), `-Output <path>`, `-Dbg`, `-SelfTest`. **Exit codes:** 0 = no double-emit offenders, 1 = double-emit offenders found, 2 = usage / unknown target / the non-vacuity self-test failed.

**Module:** `datrix_scripts.scan.dgen_census`; POSIX twin `scan\dgen-census.sh` (`--language`, `--output`, `--dbg`, `--self-test`) — `bash scan/dgen-census.sh --language python`.

---

## Code Structure Reports

### `scan\find-duplicate-bodies.ps1`

Function bodies duplicated anywhere across every `datrix-*` package's `src/` tree (whole bodies only: a similar run of lines inside otherwise different functions, or in a module-level table, is `metrics\duplicate.ps1`'s class). Every
module-level function and class method at or above the floor (8 lines, 40 AST nodes) is grouped
two ways: **exact** (identical body, names and constants kept: a straight copy) and **normalized**
(identical once parameters/locals become positional tokens and constants collapse to their type:
a renamed copy). It uses the same walker (`datrix_scripts.function_sources`) and normalization
(`datrix_scripts.body_digest`) as `gates\parity\shared-home-body-gate.ps1`, which pins only copies
of a *public shared-home* function. This report also shows copies where neither side is in a shared
home: the hoist candidates. Cross-package groups are listed first, largest first. Report only.

| Mode | Command | Description |
|------|---------|-------------|
| **Cross-package groups** | `.\scan\find-duplicate-bodies.ps1 -CrossPackage` | The 25 largest groups spanning two or more packages |
| **One package** | `.\scan\find-duplicate-bodies.ps1 -Package datrix_codegen_python -Limit 0` | Every group with a member in that package (import name) |
| **JSON** | `.\scan\find-duplicate-bodies.ps1 -Limit 0 -JsonOut D:\datrix\.tmp\duplicate-bodies.json` | Also write every selected group as JSON |

**Parameters:** `-CrossPackage`, `-Package <import name,...>`, `-Limit <n>` (default 25; 0 = all), `-JsonOut <path>`, `-Dbg`, `-SelfTest`. **Exit codes:** 0 = report printed, 1 = the package install check failed, 2 = a source file did not parse (named) or a bad argument.

**Module:** `datrix_scripts.scan.find_duplicate_bodies`; POSIX twin `scan\find-duplicate-bodies.sh` (`--cross-package`, `--package`, `--limit`, `--json-out`, `--dbg`, `--self-test`) — `bash scan/find-duplicate-bodies.sh --cross-package`.

### `scan\find-unimplemented-abstracts.ps1`

Classes that inherit abstract methods they never implement. Imports every module of the selected
packages and lists every class whose `__abstractmethods__` is non-empty. A class counts as an
**intended abstract base** when it subclasses `abc.ABC` directly, declares an abstract method
itself, is a `typing.Protocol`, or is subclassed. Every other such class is a leaf meant to be
concrete: it is **INCOMPLETE** (it cannot be instantiated, and nothing says so until something
tries), printed with each missing method and the base declaring it. A module that fails to import
is listed, never skipped.

| Mode | Command | Description |
|------|---------|-------------|
| **All packages** | `.\scan\find-unimplemented-abstracts.ps1` | Every incomplete class |
| **One package, with bases** | `.\scan\find-unimplemented-abstracts.ps1 -Package datrix_codegen_python -ShowBases` | Also list the intended abstract bases |

**Parameters:** `-Package <import name,...>` (default: every `datrix-*` package), `-ShowBases`, `-Dbg`, `-SelfTest`. **Exit codes:** 0 = no incomplete class, 1 = incomplete class(es) found or the package install check failed, 2 = a module failed to import or a bad argument.

**Module:** `datrix_scripts.scan.find_unimplemented_abstracts`; POSIX twin `scan\find-unimplemented-abstracts.sh` (`--package`, `--show-bases`, `--dbg`, `--self-test`) — `bash scan/find-unimplemented-abstracts.sh --package datrix_codegen_python --show-bases`.
