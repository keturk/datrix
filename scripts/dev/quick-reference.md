# Quick Reference — Development Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each tool does, how it is built and what its gate covers: [README.md](README.md).

Generation, import and parse-tree lookups, the code index, local model servers, the knowledge base, documentation checks and code-health digests. Related: [../generation/quick-reference.md](../generation/quick-reference.md) (parser, snapshots, triage, evaluation), [../scan/quick-reference.md](../scan/quick-reference.md), [../workspace/quick-reference.md](../workspace/quick-reference.md), [../codemods/README.md](../codemods/README.md).

Every module behind a `dev\` wrapper takes its options spelled in full: an abbreviation is a usage error (exit 2). Every script takes `-SelfTest` and has a POSIX twin `dev\<name>.sh` with `--kebab` flags.

## Code Generation

### `dev\generate.ps1`

Generate Datrix projects from `.dtrx` sources. `-Language`/`-L` is mandatory. `-All`, `-Domains` and `-TestSet` are Jon's: `validate-script-invocation.py` refuses them from an agent tool call. Every run writes `generate-results-<timestamp>-<language>[-<profile>].log` to `<workspace>\.generated\.results` (or `<workspace>\.generated\.results\<ResultsSubdir>` with `-ResultsSubdir`) and prints `Log saved to: <path>`.

| Form | Command |
|------|---------|
| One project (output path from test-projects.json) | `.\dev\generate.ps1 <source.dtrx> -L python` |
| Explicit output directory | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python` |
| Output runtime segment | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L typescript -R azure-app-service` |
| Config profile | `.\dev\generate.ps1 <source.dtrx> -L python -ConfigProfile production` |
| Validation level | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python -ValidationLevel fast` |
| Verbose / debug | `.\dev\generate.ps1 <source.dtrx> -L python -VerboseOutput` (`-Dbg`) |
| Jon's batches | `.\dev\generate.ps1 -All -L python` · `-TestSet foundation` · `-TestSet non-foundation` · `-Domains` · `-OutputBase .generated2` |

Parameters: `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (any registered `datrix.languages` target, mandatory), `-Runtime`/`-R` (docker-compose\|azure-container-apps\|azure-app-service\|ecs-fargate\|app-runner; output path only), `-ConfigProfile` (default `test`), `-ValidationLevel` (none\|fast\|standard), `-OutputBase` (default `.generated`), `-TestSet` (default `all`), `-VerboseOutput`, `-Dbg`, `-ResultsSubdir` (folder inside `.generated\.results` for the log)

### `dev\generate-doc-fragments.ps1`

Generate documentation fragments (semantic pipeline stages, CLI help) under `datrix/docs/generated/`.

| Form | Command |
|------|---------|
| All fragments | `.\dev\generate-doc-fragments.ps1` |
| One fragment | `.\dev\generate-doc-fragments.ps1 semantic-pipeline` (`cli-help`) |
| Check they are current (non-zero if stale) | `.\dev\generate-doc-fragments.ps1 -Check` |

Parameters: `-Fragment` (positional 0: all\|semantic-pipeline\|cli-help, default all), `-Check`, `-Dbg`, `-SelfTest`

## Imports and Parse Trees

### `dev\find-imports.ps1`

Every import statement naming given modules (the worklist before a move or rename). Report only (exit 0).

| Form | Command |
|------|---------|
| Importers of a name | `.\dev\find-imports.ps1 -Module datrix_common.errors.plugin -Name PluginError` |
| Everything from a module | `.\dev\find-imports.ps1 -Module datrix_codegen_common.transpiler.base` |

Parameters: `-Module <dotted,...>` (required), `-Name <name,...>`, `-Dbg`, `-SelfTest`

### `dev\probe-fixture.ps1`

Analyze a fixture project (`tests\fixtures\[projects\]<name>\`) the way a test does and print the error text or each service's blocks, in seconds. Run it after every edit of a fixture project and before the first suite run that uses it: it writes the stamp `guard-test-run-discipline.py` checks. Exit: 0 every profile analyzed, 1 a profile failed.

| Form | Command |
|------|---------|
| A project, profile `test` | `.\dev\probe-fixture.ps1 -Path d:\datrix\datrix-codegen-azure\tests\fixtures\projects\data-plane` |
| Several profiles | `.\dev\probe-fixture.ps1 -Path <project dir or system.dtrx> -ConfigProfile production,ungrouped` |

Parameters: `-Path` (required; the `.dtrx` or its directory), `-ConfigProfile <name,...>` (default `test`), `-Dbg`, `-SelfTest`

### `dev\fixture-author.ps1`

Author a package's diagnostics area fixtures from the diagnostic catalog: draft the areas with a local model, plan them, copy their scaffold, verify each area reports exactly what it annotates. Or inventory what every package's tests read and need (`needs`), and draft the shared fixture corpus to hold it (`library`).

`needs` finds, statically, the inputs each `tests/**/*.py` module reads (fixture file names, inline `.dtrx`/`.dcfg` literals, `FIXTURE_SYSTEM_*` names, conftest pair fixtures) and has a local model say, per test function, the declarations its assertions depend on. It writes `.tmp\fixture-author\needs.json` (a working file, never committed): one `module` row per module found and one `tree` row per reader of a whole tree, sorted by module path, byte-identical on an unchanged tree (answers are cached under `.tmp\fixture-author\needs-cache\`). It writes only when every module found has its row, and prints per package the modules, inputs read, declarations needed, distinct paths and local tests, then the declaration kinds per block family.

| Form | Command |
|------|---------|
| Inventory every package | `.\dev\fixture-author.ps1 needs` |
| Inventory one package | `.\dev\fixture-author.ps1 needs -Package datrix-testing` |

Exit of `needs`: 0 written, 1 a module found is not inventoried (its answer refused; nothing is written), a tree reader moved or a test module cannot be parsed, 2 usage error or a tree the inventory reads is missing, 3 no local model can read (nothing is written).

`library` drafts the shared fixture corpus to hold what `needs.json` needs: per block family a local model writes or extends `services\<family>.dtrx` and its owner configs (importing the datasource templates), per new entry its system; each round analyzes every entry under every profile it runs, and a unit passes when needed − provided is empty and nothing errs. It works on a staging copy and writes only the units that pass. A draft holding a secret-looking literal is queued and never written; a unit still failing after 4 rounds goes to `.tmp\fixture-author\queue\library-<unit>.md`; a rename keeping two colliding needs apart is recorded in `.tmp\fixture-author\renames.json`.

| Form | Command |
|------|---------|
| Draft the corpus library | `.\dev\fixture-author.ps1 library` |

Exit of `library`: 0 every unit landed or was provided, 1 a unit was queued or the inventory cannot be read, 2 usage error (`-Package` or a diagnostics switch given, `needs.json` missing), 3 no local model can draft (nothing is written).

`repoint` rewrites the test modules `needs.json` lists for `-Package` so their tests read the shared corpus: per module a local model is given the module, its needs, the corpus entry that provides them and `renames.json`. The module is saved to `.tmp\fixture-author\undo\` and written; the rewrite is kept only when every test and assertion (`assert` plus `pytest.raises` blocks) stays, the module reads no input but one opening with `// @local <reason>`, a module holding a test with no local reason names `corpus_project` or `corpus_project_copy`, and `test.ps1 <p> -Specific` over it (over the modules depending on a conftest or helper) passes. Otherwise it is written back byte for byte (never by git) and, after 4 rounds, queued in `.tmp\fixture-author\queue\repoint-<package>--<module>.md`; a secret-literal draft is queued and never written. A module finished by hand is found done on the next run. The run ends on inventoried − rewritten − local, computed from the code.

| Form | Command |
|------|---------|
| Repoint one package | `.\dev\fixture-author.ps1 repoint -Package datrix-common` |
| Delete what it no longer reads | `.\dev\fixture-author.ps1 repoint -Package datrix-common -Prune` |

Exit of `repoint`: 0 inventoried − rewritten − local is empty, 1 a module is not done or the inventory cannot be read, 2 usage error (no `-Package`, a diagnostics switch, `needs.json` missing), 3 no local model can rewrite (with none from the start, nothing is written).

`repoint -Prune` is refused while `.tmp\fixture-author\queue\` holds a module of the package. It deletes each fixture file under `tests/` nothing reads: not named by needs discovery rerun now, not under a directory a module reads whole, not in `tests/fixtures/diagnostics/`, not reached by a kept file (a kept file that does not parse keeps its directory). Each is saved to `.tmp\fixture-author\undo\` first; a deletion leaving a model with no contract sample (when a module calls `package_contracts`), or changing the package's semantic manifest other than by the deleted keys leaving and the corpus keys arriving, refuses the run and every file is written back byte for byte. An accepted run writes the regenerated manifest and runs `fixture-budget-gate.ps1 -UpdateBaseline`. Exit: 0 pruned and banked, 1 refused or the baseline not tightened, 2 usage error.

Drafting (no action switch) asks the model for one fragment per variant, analyzes the area once per round, and sends a cascade or a variant not provoked back, at most 4 rounds. A variant still failing is written to `.tmp\fixture-author\queue\<area>.md` with its last analysis output and draft, for a person to finish; a draft holding a secret-looking literal is queued and never written. An area on disk is never drafted over.

Target-check variants (the package whose session registers the target checks) go to one area, `targets`, declaring `// @analysis targets` and naming no language: it is one input per registered backend language, and drafting and `-Verify` analyze every input, so a variant provoked under one language only is not provoked.

| Form | Command |
|------|---------|
| Draft every absent area | `.\dev\fixture-author.ps1 diagnostics -Package datrix-semantic` |
| Draft one area | `.\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Area svc` |
| Needs and planned areas | `.\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Plan` |
| One area's variants | `.\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Area svc -Plan` |
| Copy the scaffold | `.\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Scaffold` |
| Verify one area | `.\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Area svc -Verify` |

Parameters: `-Kind diagnostics|library|needs` (required, positional), `-Package <name>` (required by `diagnostics`; `needs` defaults to every package holding `tests\`; `library` takes none), `-Area <area>` (default every planned area), at most one of `-Plan`, `-Scaffold`, `-Verify` (none drafts; `diagnostics` only), `-LocalMachines <host,...>`, `-LlmModel <model,...>`, `-LlmTimeout <seconds>` (default 300), `-Dbg`, `-SelfTest`

Exit of `diagnostics`: 0 done, 1 a variant was queued, an area failed verification or the package's state refuses the run, 2 usage error, 3 no local model can draft (nothing is written).

### `dev\who-imports.ps1`

Which runtime import chain first loads a module.

| Form | Command |
|------|---------|
| Trace a target | `.\dev\who-imports.ps1 -Root datrix_codegen_kernel.dgen -Target datrix_codegen_common` |

Parameters: `-Root <module,...>` (required), `-Target <module,...>` (required), `-SelfTest`. Exit: 0 every root imported, 2 a root failed to import.

### `dev\print-sexp.ps1`

The tree-sitter parse tree of Datrix source as a corpus-style S-expression.

| Form | Command |
|------|---------|
| A file | `.\dev\print-sexp.ps1 examples\01-foundation\system.dtrx` |
| Inline, anonymous nodes included | `.\dev\print-sexp.ps1 -Text 'service s { }' -All` |

Parameters: `-Path` (positional 0) or `-Text`, `-All`, `-SelfTest`. Exit: 0 clean tree, 1 ERROR or MISSING nodes (tree still printed), 2 input unreadable.

## Documentation Checks

### `dev\check-docs.ps1`

Lint documentation for drift: deprecated CLI flags, fixed phase counts, CDX naming/structure, missing capability status labels.

| Form | Command |
|------|---------|
| All checks | `.\dev\check-docs.ps1` |
| One check | `.\dev\check-docs.ps1 -Check deprecated-cli-flags` |
| Several checks | `.\dev\check-docs.ps1 -Check cdx-filenames -Check cdx-structure` |
| Content and suggestions | `.\dev\check-docs.ps1 -Detailed` |
| One directory | `.\dev\check-docs.ps1 path\to\docs` |

Parameters: `-DocsDir` (positional, variadic; default all monorepo docs/), `-Check` (deprecated-cli-flags\|fixed-phase-count\|cdx-filenames\|cdx-structure\|capability-status-labels, repeatable), `-Detailed`, `-Dbg`, `-LlmSuggest`, `-LlmLimit`, `-LlmNumPredict`, `-LlmTemperature`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout`, `-SelfTest`. Exit: 0 clean, 1 lint failures.

## Code Index

### `dev\code-index.ps1`

Query the code index (SQLite index of every Python, Markdown, PowerShell, `.dtrx`, `.dcfg` and TypeScript file). Every query first brings the index up to date. Agents use the MCP tools `find_symbol`, `find_references`, `outline`, `search`, `find_canonical`, `index_status` instead when the server is registered.

| Form | Command |
|------|---------|
| Set up a machine (once; then restart Claude Code) | `.\dev\code-index.ps1 -Setup` |
| Definitions | `.\dev\code-index.ps1 -Symbol to_snake_case` |
| Uses | `.\dev\code-index.ps1 -References datrix_common.utils.identifier_case.to_snake_case` |
| File outline | `.\dev\code-index.ps1 -Outline datrix-common/src/datrix_common/utils/text.py` |
| Search | `.\dev\code-index.ps1 -Search "tenant isolation"` |
| Logic map markers | `.\dev\code-index.ps1 -Canonical text/to-snake` |
| Status | `.\dev\code-index.ps1 -Status` |
| Refresh | `.\dev\code-index.ps1 -Refresh` |
| Summaries | `.\dev\code-index.ps1 -Summarize -Limit 100` |
| Adoption | `.\dev\code-index.ps1 -Usage -Days 7` |

`-Symbol` takes a bare name, glob (`*Resolver`), `Class.method` or dotted path; `-Kind` narrows (`class`, `function`, `method`, `section`, `parameter`, `entity`, `setting`, ...).

Parameters: exactly one action: `-Symbol`, `-References`, `-Outline`, `-Search`, `-Canonical`, `-Status`, `-Refresh`, `-Usage`, `-Summarize`, `-Setup`. Modifiers: `-Kind` (with `-Symbol`), `-IncludeTestRules` (with `-Canonical`), `-Days` (with `-Usage`; default 7, 0 = all), `-Limit`, `-Workers` (default 4), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 300; all three with `-Summarize`). `-SelfTest`. Exit: 0 answered, 1 could not be answered as asked, 2 `-Summarize` found no local model server.

### `dev\code-index-gate.ps1`

Behaviour checks for the code index, its MCP server and the logic-map consumers.

| Form | Command |
|------|---------|
| Run the gate | `.\dev\code-index-gate.ps1` |
| One area | `.\dev\code-index-gate.ps1 -Only check_references` |
| Harness self-test | `.\dev\code-index-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\dev\code-index-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error.

### `dev\logic-map-report.ps1`

Refresh the index, then dump the logic map database to a Markdown report.

| Form | Command |
|------|---------|
| Write `logic-map-report.md` here | `.\dev\logic-map-report.ps1` |
| Custom output | `.\dev\logic-map-report.ps1 -Output docs\logic-map.md` |

Parameters: `-Output` (positional 0), `-SelfTest`. Exit: 0 report written and every `@see` names a declared topic, 1 index not refreshed or dangling `@see` references.

## Local Models and the Knowledge Base

### `dev\local-llm.ps1`

Set up, inspect and measure the local model servers behind `ask_files`, `digest_log` and `local_models` (MCP server `datrix-local-llm`).

| Form | Command |
|------|---------|
| Set up a machine (once; then restart Claude Code) | `.\dev\local-llm.ps1 -Setup` |
| Servers, resident models, last day's usage | `.\dev\local-llm.ps1 -Status` |
| Usage by caller and server | `.\dev\local-llm.ps1 -Usage -Days 7` |
| Keep a model resident on each machine | `.\dev\local-llm.ps1 -Pin` |
| Release resident models | `.\dev\local-llm.ps1 -Unpin` |

Parameters: exactly one action: `-Setup`, `-Status`, `-Usage`, `-Pin`, `-Unpin`, `-SelfTest`. Modifier `-Days` (with `-Status` default 1; with `-Usage` default 7; 0 = all). Exit: 0 done, 1 could not be carried out.

### `dev\local-llm-gate.ps1`

Behaviour checks for the local-model reading layer and its MCP server.

| Form | Command |
|------|---------|
| Run the gate | `.\dev\local-llm-gate.ps1` |
| One area | `.\dev\local-llm-gate.ps1 -Only check_scope` |
| Harness self-test | `.\dev\local-llm-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\dev\local-llm-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error.

### `dev\line-edit.ps1`

Set up the `datrix-edit` MCP server (`read_lines`, `edit_lines`, `read_symbol`: line-addressed and symbol-addressed edits that never re-send old text).

| Form | Command |
|------|---------|
| Set up a machine (then restart Claude Code) | `.\dev\line-edit.ps1 -Setup` |

Parameters: `-Setup`, `-SelfTest`. Exit: 0 done, 1 could not be carried out.

### `dev\line-edit-gate.ps1`

Behaviour checks for line-addressed editing on real files in a temporary workspace.

| Form | Command |
|------|---------|
| Run the gate | `.\dev\line-edit-gate.ps1` |
| One area | `.\dev\line-edit-gate.ps1 -Only check_mcp` |
| Harness self-test | `.\dev\line-edit-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\dev\line-edit-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error.

### `dev\ineedtoknow.ps1`

Ask in your own words instead of loading whole docs. A hit is a brief answer plus the file and line range to open; an answer is a lead, so open the cited lines before acting.

| Form | Command |
|------|---------|
| Ask | `.\dev\ineedtoknow.ps1 -Question "which package owns the gateway route enumeration"` (or `.\dev\ineedtoknow.ps1 "…"`) |
| Look up only, no model | `.\dev\ineedtoknow.ps1 "…" -NoLearn` |
| Also read files (framework repos only) | `.\dev\ineedtoknow.ps1 "…" -In "datrix-semantic/src/**/*tenant*.py"` |
| Re-gather and replace the stored answer | `.\dev\ineedtoknow.ps1 "…" -Refresh` |
| Status | `.\dev\ineedtoknow.ps1 -Status` |
| Rebuild the database | `.\dev\ineedtoknow.ps1 -Rebuild` |
| Delete learned files whose sources changed | `.\dev\ineedtoknow.ps1 -Prune` |

Parameters: exactly one of: a question (positional or `-Question`), `-Status`, `-Rebuild`, `-Prune`. Modifiers: `-In`, `-Refresh`, `-NoLearn`, `-Limit` (default 3), `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 120). `-SelfTest`. Exit: 0 answered, 1 could not be carried out, 2 no answer.

### `dev\ineedtoknow-gate.ps1`

Behaviour checks for `ineedtoknow.ps1` over a temporary workspace and a loopback model server.

| Form | Command |
|------|---------|
| Run the gate | `.\dev\ineedtoknow-gate.ps1` |
| One area | `.\dev\ineedtoknow-gate.ps1 -Only check_gather` |
| Harness self-test | `.\dev\ineedtoknow-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\dev\ineedtoknow-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error.

## Code Health

### `dev\code-scan.ps1`

On-demand code-health scan: one ranked digest (dead code, complexity, duplicated blocks, docs drift) → `d:\datrix\reports\code-scan\code-scan-<timestamp>.md`. By default only packages changed since their last scan.

| Form | Command |
|------|---------|
| Changed packages | `.\dev\code-scan.ps1` |
| Named packages | `.\dev\code-scan.ps1 datrix-common datrix-cli` |
| By folder | `.\datrix\scripts\dev\code-scan.ps1 .\datrix-cli\` |
| Everything (about 4 minutes) | `.\dev\code-scan.ps1 -All` |

Parameters: `-Package` (positional; names or folders), `-All`, `-MinConfidence` (Vulture, default 60), `-DuplicateMinLines` (default 6), `-SelfTest`. Exit: 0 digest written or nothing changed, 1 the scan could not run (missing tool, unknown package, unreadable scan state). Needs `vulture`, `pylint`, `radon` and `cognitive_complexity` in the shared venv (see [README.md](README.md#code-scanps1)).

### `dev\generate-test-rules.ps1`

Generate `@test-rule` conformance annotations for tests with a local LLM. Default proposes (writes `.test-output/test-rules/<model>/<package>.json` plus a `.md` preview, touches no source); `-Apply` inserts the reviewed markers.

| Form | Command |
|------|---------|
| Propose for one package | `.\dev\generate-test-rules.ps1 datrix-codegen-python` |
| Cap the functions this run | `.\dev\generate-test-rules.ps1 datrix-codegen-python -Limit 20` |
| One file or subtree | `.\dev\generate-test-rules.ps1 -Path datrix-codegen-typescript\tests\unit\transpiler\test_operators.py -NoSeed` |
| Every package | `.\dev\generate-test-rules.ps1 -All` |
| Triage (no LLM, no edits) | `.\dev\generate-test-rules.ps1 datrix-codegen-typescript -Review` |
| Apply reviewed proposals | `.\dev\generate-test-rules.ps1 datrix-codegen-python -Apply` |
| Apply under a path | `.\dev\generate-test-rules.ps1 datrix-codegen-typescript -Apply -Path datrix-codegen-typescript\tests\unit\transpiler\test_operators.py` |
| Other model | `.\dev\generate-test-rules.ps1 -All -Model qwen3-coder:30b-ctx32k` |

Parameters: `-Projects` (positional, variadic), `-All`, `-Apply`, `-Review`, `-Model` (default `exaone-deep:32b`), `-LocalMachines`, `-Parallel` (default 4), `-Limit` (default 0 = none), `-Path` (file/dir filter, repeatable; also scopes `-Apply`/`-Review`; run once per path, `powershell -File` cannot pass an array), `-NoSeed`, `-NoConsolidate`, `-IncludeE2e`, `-IncludeIntegration` (excluded by default), `-Dbg`, `-SelfTest`

## Container Image Pins

### `dev\refresh-image-pins.ps1`

Rewrite every package's `image_pins.json` (the digests of the images its generators choose) from the registries. Needs `docker buildx` and network; no framework test runs it.

| Form | Command |
|------|---------|
| Re-resolve every table | `.\dev\refresh-image-pins.ps1` |
| One package's table | `.\dev\refresh-image-pins.ps1 -Package datrix-codegen-docker` |
| Pin a new image | `.\dev\refresh-image-pins.ps1 -Package datrix-codegen-docker -Add redis:7` |

Parameters: `-Package` (package directory; limits the run to its table; required with `-Add`), `-Add <name:tag,...>`, `-SelfTest`. Exit: 0 every table rewritten, 1 a reference did not resolve (no table written), 2 usage error.
