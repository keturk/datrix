# Quick Reference — Repo-Hygiene Gates

Bash: prefix `powershell -File`, forward slashes, quoted path ([../../quick-reference.md](../../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each gate proves, how it decides and what its self-test plants: [README.md](README.md).

Gates over the repositories themselves: what may be committed, what docs may claim, what examples must satisfy, and code shapes held at zero. Each has a POSIX twin `gates/repo-hygiene/<name>.sh` with `--kebab` flags and ends with `[GATE] <name> PASSED|FAILED exit=<n> log=<path>`. Every gate takes `-SelfTest` (non-vacuity proof, no real scan; it also runs before every real scan) and, unless noted, `-Dbg`. Exit 0 is clean, 1 a finding or failed self-test, 2 a usage error or a gate that cannot judge.

## `gates\repo-hygiene\customer-domain-isolation-gate.ps1`

No customer/project term (hashed corpus `scripts/config/customer-term-hashes.json`) in any publishable file of any framework repo.

| Form | Command |
|------|---------|
| Every repo | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1` |
| One repo | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1 -Repo datrix` |
| Pending changes only | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1 -PendingOnly` |
| Register a term (stores only its digest) | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1 -AddTerm acmecorp -Hint "customer project"` |

Parameters: `-Repo <name[,name...]>`, `-PendingOnly`, `-AddTerm <term>`, `-Hint <text>` (default `customer project`), `-SelfTest`, `-Dbg`. Exit: 0 no violation (or no term registered: `NOT ENFORCED`), 1 a violation / failing self-test, 2 usage / malformed corpus / unlistable repo / unreadable file.

## `gates\repo-hygiene\retired-dsl-names-gate.ps1`

No retired internal-DSL name (spellings in `scripts/config/retired-dsl-names.json`) in any file content, file name or directory name.

| Form | Command |
|------|---------|
| Every repo | `.\gates\repo-hygiene\retired-dsl-names-gate.ps1` |
| One repo | `.\gates\repo-hygiene\retired-dsl-names-gate.ps1 -Repo datrix-common` |

Parameters: `-Repo <name[,name...]>`, `-SelfTest`, `-Dbg`. Exit: 0 none, 1 a retired name / failing self-test, 2 usage / malformed spellings file / unlistable repo / unreadable file.

## `gates\repo-hygiene\design-task-reference-gate.ps1`

No committed artifact cites a design document, a task file or a gitignored item label.

| Form | Command |
|------|---------|
| Every committed tree | `.\gates\repo-hygiene\design-task-reference-gate.ps1` |
| One tree | `.\gates\repo-hygiene\design-task-reference-gate.ps1 -Roots D:/datrix/datrix/scripts/config` |
| Several trees | `.\gates\repo-hygiene\design-task-reference-gate.ps1 -Roots D:/datrix/datrix-common/src,D:/datrix/datrix-common/docs` |

Parameters: `-Roots <dir[,dir...]>` (default every committed tree), `-SelfTest`. Exit: 0 none, 1 a reference / unreadable file / failing self-test.

## `gates\repo-hygiene\package-data-coverage-gate.ps1`

Every runtime resource (`*.j2`, `*.dal`) a package loads is matched by a `[tool.setuptools.package-data]` glob.

| Form | Command |
|------|---------|
| Every package | `.\gates\repo-hygiene\package-data-coverage-gate.ps1` |
| One package | `.\gates\repo-hygiene\package-data-coverage-gate.ps1 -Package datrix-codegen-python` |

Parameters: `-Package <name[,name...]>`, `-SelfTest`, `-Dbg`. Exit: 0 every resource ships, 1 a resource ships with no glob / failing self-test, 2 unknown `-Package`.

## `gates\repo-hygiene\line-ending-gate.ps1`

Every framework repo normalizes text to LF (`* text=auto eol=lf`) and commits no CRLF line.

| Form | Command |
|------|---------|
| Every repo | `.\gates\repo-hygiene\line-ending-gate.ps1` |
| One repo | `.\gates\repo-hygiene\line-ending-gate.ps1 -Repo datrix-codegen-flutter` |

Parameters: `-Repo <name[,name...]>`, `-SelfTest`, `-Dbg`. Exit: 0 both facts hold, 1 a violation / failing self-test, 2 unknown `-Repo` / no repo / git failed.

## `gates\repo-hygiene\hidden-code-point-gate.ps1`

No hidden code point (bidi control, zero-width, non-ASCII space, control) in any `src/` file of a `datrix-codegen-*` repo.

| Form | Command |
|------|---------|
| Every generator repo | `.\gates\repo-hygiene\hidden-code-point-gate.ps1` |
| One repo | `.\gates\repo-hygiene\hidden-code-point-gate.ps1 -Repo datrix-codegen-angular` |

Parameters: `-Repo <name[,name...]>`, `-SelfTest`, `-Dbg`. Exit: 0 none, 1 a hidden code point / non-UTF-8 file / failing self-test / package installs not current, 2 unknown `-Repo` / no generator repo / git or read failure.

## `gates\repo-hygiene\ignored-source-gate.ps1`

No `.gitignore` rule silently shadows a publishable file (working tree vs `git add -A`); reviewed exemptions in `scripts/config/ignored-source-exemptions.json`.

| Form | Command |
|------|---------|
| Every repo | `.\gates\repo-hygiene\ignored-source-gate.ps1` |
| One repo | `.\gates\repo-hygiene\ignored-source-gate.ps1 -Repo datrix-language` |
| Several repos | `.\gates\repo-hygiene\ignored-source-gate.ps1 -Repo datrix-language,datrix-vscode` |
| Print every exemption with its reason, then scan | `.\gates\repo-hygiene\ignored-source-gate.ps1 -ShowExempt` |

Parameters: `-Repo <name[,name...]>`, `-SelfTest`, `-ShowExempt`, `-Dbg`. Exit: 0 every unstaged path is a reviewed exemption, 1 a shadowed publishable file / failing self-test, 2 unknown `-Repo` / no repo / missing, malformed or miscounted exemption file.

## `gates\repo-hygiene\polystring-case-roundtrip-gate.ps1`

No `to_*_case(str(E))`, `to_*_case(NAME)` with `NAME = str(E)`, nested case calls or `to_*_case(extract_simple_name(E))` in any publishable `.py`. Hard zero.

| Form | Command |
|------|---------|
| Every repo | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1` |
| One repo | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1 -Repo datrix-codegen-aws` |
| Pending changes only (commit-path form) | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1 -PendingOnly` |

Parameters: `-Repo <name[,name...]>`, `-SelfTest`, `-PendingOnly`, `-Dbg`. Exit: 0 none, 1 a round trip / failing self-test, 2 unknown `-Repo` / no repo / unparseable file.

## `gates\repo-hygiene\python-lint-correctness-gate.ps1`

Zero ruff `F` findings and zero `E302`/`E305` in every package's `src/` and `tests/` (and the showcase repo's `scripts/`).

| Form | Command |
|------|---------|
| Every package | `.\gates\repo-hygiene\python-lint-correctness-gate.ps1` |

Parameters: `-SelfTest`, `-Dbg`. Exit: 0 none, 1 a finding / failing self-test, 2 usage / ruff could not run.

## `gates\repo-hygiene\import-name-existence-gate.ps1`

No `from <datrix module> import <name>` names something that does not exist (including under `TYPE_CHECKING`). Hard zero.

| Form | Command |
|------|---------|
| Every datrix package tree | `.\gates\repo-hygiene\import-name-existence-gate.ps1` |
| One tree | `.\gates\repo-hygiene\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src` |
| Several trees | `.\gates\repo-hygiene\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src,D:/datrix/datrix-codegen-common/src` |

Parameters: `-Roots <dir[,dir...]>` (default every datrix package tree), `-SelfTest`. Exit: 0 every name resolves, 1 a dead name / failing self-test, 2 no datrix `src/` tree found.

## `gates\repo-hygiene\check-docs-conformance.ps1`

Every path, module, class-member, anchor, decision-status, dependency-graph, package-count and tooling claim in the curated architecture docs resolves; exceptions baseline `scripts/config/docs-conformance-exceptions.json` (hand-edited).

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\check-docs-conformance.ps1` |
| Report only, exit 0 | `.\gates\repo-hygiene\check-docs-conformance.ps1 -Warn` |
| Print each doc scanned | `.\gates\repo-hygiene\check-docs-conformance.ps1 -ShowFiles` |
| Other monorepo root | `.\gates\repo-hygiene\check-docs-conformance.ps1 -BaseDir D:\datrix` |

Parameters: `-Warn`, `-ShowFiles`, `-BaseDir`, `-SelfTest`, `-Dbg`. Exit: 0 none unresolved (or `-Warn` / `-SelfTest`), 1 an unresolved, non-excepted reference / failing check, 2 usage / missing baseline / a registered doc gone / the automatic self-test failed. A new package's architecture doc is added to `ARCHITECTURE_DOC_FILES` by hand ([README.md](README.md#check-docs-conformanceps1)).

## `gates\repo-hygiene\instruction-surface-gate.ps1`

No agent-facing document prescribes a whole-suite `test.ps1` run or an `affected-gate.ps1` sweep; `<!-- forbidden-example -->` on the same or previous line exempts a deliberate example.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\instruction-surface-gate.ps1` |

Parameters: `-SelfTest`, `-Dbg`. Exit: 0 none, 1 an un-exempted whole-suite form / failing self-test, 2 usage / `_suite_invocation.py` or `_command_shape.py` could not be loaded.

## `gates\repo-hygiene\check-cross-package-fixture-reads.ps1`

No package's tests resolve a path inside another package's `tests/`, and no statically-resolved fixture path is missing.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1` |
| Print each file scanned | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1 -ShowFiles` |
| Other monorepo root | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1 -BaseDir D:\datrix` |

Parameters: `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`. Exit: 0 clean, 1 a cross-package reference / missing fixture, 2 usage / no package / failing self-test.

## `gates\repo-hygiene\check-enum-value-literals.ps1`

No generator branches on a user enum's member values (`.get_value("X")`, `"X" in value_names`). Hard zero, no exemption file.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\check-enum-value-literals.ps1` |
| Print each file scanned | `.\gates\repo-hygiene\check-enum-value-literals.ps1 -ShowFiles` |
| Other monorepo root | `.\gates\repo-hygiene\check-enum-value-literals.ps1 -BaseDir D:\datrix` |

Parameters: `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`. Exit: 0 clean, 1 a violation, 2 usage / no package / failing self-test.

## `gates\repo-hygiene\check-handler-name-dedup.ps1`

No `datrix-codegen-*` package de-duplicates a REST handler name with a numeric-suffix loop. Hard zero, no exemption file.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\check-handler-name-dedup.ps1` |
| Print each file scanned | `.\gates\repo-hygiene\check-handler-name-dedup.ps1 -ShowFiles` |
| Other monorepo root | `.\gates\repo-hygiene\check-handler-name-dedup.ps1 -BaseDir D:\datrix` |

Parameters: `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`. Exit: 0 clean, 1 a violation, 2 usage / too few packages / failing self-test.

## `gates\repo-hygiene\check-observability-native-only.ps1`

No example profile pairs a portable observability provider with an `aws`/`azure` deployment target.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\check-observability-native-only.ps1` |
| Report only, exit 0 | `.\gates\repo-hygiene\check-observability-native-only.ps1 -Warn` |
| Scan a hand-made examples tree | `.\gates\repo-hygiene\check-observability-native-only.ps1 -ExamplesRoot D:\datrix\.tmp\obs-guard-check\examples` |
| Print each `system.dcfg` scanned | `.\gates\repo-hygiene\check-observability-native-only.ps1 -ShowFiles` |

Parameters: `-Warn`, `-ExamplesRoot`, `-SelfTest`, `-ShowFiles`, `-Dbg`. Exit: 0 none (or `-Warn` / `-SelfTest`), 1 a violation / failing check, 2 usage / missing examples root / the automatic self-test failed.

## `gates\repo-hygiene\emitted-escape-integrity-gate.ps1`

No `*.py.j2` template carries a doubled backslash before `n`/`t`/`r`; exemptions in `scripts/config/emitted-escape-exemptions.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\emitted-escape-integrity-gate.ps1` |
| Print each template read | `.\gates\repo-hygiene\emitted-escape-integrity-gate.ps1 -ShowFiles` |
| Other monorepo root | `.\gates\repo-hygiene\emitted-escape-integrity-gate.ps1 -BaseDir D:\datrix` |

Parameters: `-BaseDir` (default the workspace root), `-ShowFiles`, `-SelfTest`. Exit: 0 clean, 1 an escaped escape / an exemption matching nothing, 2 usage / bad baseline / no templates / unreadable template / failing self-test.

## `gates\repo-hygiene\app-probe-path-literal-gate.ps1`

No platform package hardcodes a route a registered language declares as its readiness or liveness probe; exemptions in `scripts/config/app-probe-path-exemptions.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\app-probe-path-literal-gate.ps1` |
| Print each file scanned | `.\gates\repo-hygiene\app-probe-path-literal-gate.ps1 -ShowFiles` |

Parameters: `-BaseDir <path>`, `-SelfTest`, `-ShowFiles`, `-Dbg`. Exit: 0 clean, 1 an unexempted hit / stale exemption, 2 failing self-test / too few packages or languages / unparseable manifest or exemption file.

## `gates\repo-hygiene\template-reachability-gate.ps1`

Every `.j2` a framework package ships is named by something that can render it; exemptions in `scripts/config/template-reachability-exemptions.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\template-reachability-gate.ps1` |

Parameters: `-BaseDir <path>`, `-SelfTest`, `-Dbg`. Exit: 0 every template named, 1 an unnamed template / dangling DAL generator name / stale exemption, 2 failing self-test / unparseable template / missing or malformed exemptions file.

## `gates\repo-hygiene\example-registry-gate.ps1`

Every `system.dtrx` under `datrix/examples/` is in a test set of `scripts/config/test-projects.json` or excluded in `test-set-exclusions.json`, and the examples tree's layout holds (no nested, shared or unowned examples).

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\example-registry-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 registry and layout consistent, 1 a violation, 2 failing self-test / no examples / config file missing, malformed or miscounted.

## `gates\repo-hygiene\example-snapshot-gate.ps1`

Every committed `generated/<language>-<platform>/` snapshot names registered targets and carries every registered language; every dotted `datrix_*` reference in a snapshot or `.j2` template resolves. Refresh a snapshot with `generation\refresh-example-snapshot.ps1`.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\example-snapshot-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 clean, 1 a violation, 2 fewer than two languages / failing self-test / no snapshot / no template reference.

## `gates\repo-hygiene\source-comment-reference-gate.ps1`

Every module a framework `src/` comment or docstring cites (dotted reference or `.py` file citation) exists. Hard zero.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\source-comment-reference-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every citation resolves, 1 a violation, 2 failing self-test / no package / no citation seen.

## `gates\repo-hygiene\example-secret-seed-gate.ps1`

On the `test` profile every `required = true` operator-provisioned secret handle of every example service has a `localDefault`.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\example-secret-seed-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every handle seeded, 1 an unseeded handle, 2 failing self-test / no examples or service configs / a config fails to parse or resolve.

## `gates\repo-hygiene\example-config-load-gate.ps1`

Every declared profile of every example `.dcfg` loads through the real loaders, and every example analyzes clean under every leaf profile of its system config (a profile no other profile `extends`). About 90 s.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\example-config-load-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every profile loads and every leaf profile analyzes, 1 a profile failed to load or a leaf profile failed analysis, 2 failing self-test / no `.dcfg` or `system.dtrx` / a file does not parse.

## `gates\repo-hygiene\docs-fence-gate.ps1`

Every `datrix` fence under `datrix/docs` states a fact that holds (parses, analyzes clean or to its `expect=` codes, `rejected` stays rejected).

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\docs-fence-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every fence holds, 1 a fence fails or is refused, 2 failing self-test.

## `gates\repo-hygiene\no-body-walk-gate.ps1`

A `datrix-codegen-*` function walks a model body only where `scripts/config/no_body_walk_allowlist.json` lists it. Adding an entry needs Jon's approval.

| Form | Command |
|------|---------|
| Run | `.\gates\repo-hygiene\no-body-walk-gate.ps1` |

Parameters: `-SelfTest`, `-Dbg`. Exit: 0 flagged set equals the allowlist, 1 an unlisted function / stale entry, 2 cannot judge (failing self-test, malformed allowlist, unparseable source).

## `gates\repo-hygiene\no-import-registration-gate.ps1`

Importing a framework module registers nothing: no import-time `*register*` call, no registration-only `noqa: F401` import. Hard zero.

| Form | Command |
|------|---------|
| Every `datrix-*/src` tree | `.\gates\repo-hygiene\no-import-registration-gate.ps1` |
| Some trees | `.\gates\repo-hygiene\no-import-registration-gate.ps1 -Roots D:/datrix/datrix-common/src` |

Parameters: `-Roots <dir[,dir...]>` (default every `datrix-*/src`), `-SelfTest`, `-Dbg`. Exit: 0 none, 1 a hit, 2 cannot judge (failing self-test, unparseable or non-UTF-8 source).

## `gates\repo-hygiene\stateless-generator-gate.ps1`

A generator class holds no run state: no attribute write outside `__init__`, no `CodegenContext` constructor parameter. Hard zero.

| Form | Command |
|------|---------|
| Every `datrix-*/src` tree | `.\gates\repo-hygiene\stateless-generator-gate.ps1` |
| Some trees (the kernel's `src` must be among them) | `.\gates\repo-hygiene\stateless-generator-gate.ps1 -Roots D:/datrix/datrix-codegen-kernel/src,D:/datrix/datrix-codegen-docker/src` |

Parameters: `-Roots <dir[,dir...]>` (default every `datrix-*/src`), `-SelfTest`, `-Dbg`. Exit: 0 none, 1 a hit, 2 cannot judge (failing self-test, no generator class found, unparseable or non-UTF-8 source).

## `gates\repo-hygiene\seal-integrity-gate.ps1`

Only `Node.seal` and `Node.__deepcopy__` in datrix-common's model `base.py` write the `_sealed` flag. Hard zero.

| Form | Command |
|------|---------|
| Every `datrix-*/src` tree | `.\gates\repo-hygiene\seal-integrity-gate.ps1` |
| Some trees (datrix-common's `src` must be among them) | `.\gates\repo-hygiene\seal-integrity-gate.ps1 -Roots D:/datrix/datrix-common/src,D:/datrix/datrix-cli/src` |

Parameters: `-Roots <dir[,dir...]>` (default every `datrix-*/src`), `-SelfTest`, `-Dbg`. Exit: 0 none, 1 a hit, 2 cannot judge (failing self-test, no permitted write found in `Node.seal`, unparseable or non-UTF-8 source).

## `gates\repo-hygiene\script-catalogue-gate.ps1`

The scripts tree's documentation matches the tree: every `.ps1` is a heading of its folder's `quick-reference.md`, every flag written after a script name is declared by its `param()`, every relative link resolves. Hard zero.

| Form | Command |
|------|---------|
| Planted checks, then the real tree | `.\gates\repo-hygiene\script-catalogue-gate.ps1` |
| Real tree only | `.\gates\repo-hygiene\script-catalogue-gate.ps1 -Only scripts_tree` |

Parameters: `-SelfTest`, `-Only <prefix>`, `-Dbg`. Exit: 0 no hit, 1 a hit / failing self-test, 2 usage error.

## `gates\repo-hygiene\thin-entrypoint-gate.ps1`

Every `.ps1` under `scripts\` is the rendered thin-wrapper template (at most 40 code lines) with a rendered `.sh` twin, and parses. Hard zero.

| Form | Command |
|------|---------|
| Planted checks, then the real tree | `.\gates\repo-hygiene\thin-entrypoint-gate.ps1` |
| Real tree only | `.\gates\repo-hygiene\thin-entrypoint-gate.ps1 -Only scripts_tree` |

Parameters: `-SelfTest`, `-Only <prefix>`, `-Dbg`. Exit: 0 no hit, 1 a hit / failing self-test, 2 usage error.
