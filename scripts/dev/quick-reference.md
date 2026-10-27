# Quick Reference — Development Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each tool does, how it is built and what its gate covers: [README.md](README.md).

Generation, import and parse-tree lookups, the code index, local model servers, the knowledge base, documentation checks and code-health digests. Related: [../generation/quick-reference.md](../generation/quick-reference.md) (parser, snapshots, triage, evaluation), [../scan/quick-reference.md](../scan/quick-reference.md), [../workspace/quick-reference.md](../workspace/quick-reference.md), [../codemods/README.md](../codemods/README.md).

Every module behind a `dev\` wrapper takes its options spelled in full: an abbreviation is a usage error (exit 2). Every script takes `-SelfTest` and has a POSIX twin `dev\<name>.sh` with `--kebab` flags.

## Code Generation

### `dev\generate.ps1`

Generate Datrix projects from `.dtrx` sources. `-Language`/`-L` is mandatory. `-All`, `-Domains` and `-TestSet` are Jon's: `validate-script-invocation.py` refuses them from an agent tool call. Every run writes `generate-results-<timestamp>-<language>[-<profile>].log` to `<workspace>\.generated\.results` and prints `Log saved to: <path>`.

| Form | Command |
|------|---------|
| One project (output path from test-projects.json) | `.\dev\generate.ps1 <source.dtrx> -L python` |
| Explicit output directory | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python` |
| Output runtime segment | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L typescript -R azure-app-service` |
| Config profile | `.\dev\generate.ps1 <source.dtrx> -L python -ConfigProfile production` |
| Validation level | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python -ValidationLevel fast` |
| Carry chains forward with live snapshots (single project) | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python -ConfigProfile staging -CarryForwardLiveSnapshots <dir>` |
| Verbose / debug | `.\dev\generate.ps1 <source.dtrx> -L python -VerboseOutput` (`-Dbg`) |
| Jon's batches | `.\dev\generate.ps1 -All -L python` · `-TestSet foundation` · `-TestSet non-foundation` · `-Domains` · `-OutputBase .generated2` |

Parameters: `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (any registered `datrix.languages` target, mandatory), `-Runtime`/`-R` (docker-compose\|azure-container-apps\|azure-app-service\|ecs-fargate\|app-runner; output path only), `-ConfigProfile` (default `test`), `-ValidationLevel` (none\|fast\|standard), `-OutputBase` (default `.generated`), `-TestSet` (default `all`), `-VerboseOutput`, `-Dbg`, `-CarryForwardLiveSnapshots`

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
