# Quick Reference — Development Scripts

Generation, import and parse-tree lookups, the code index, the local model servers and the
knowledge base agents read through, documentation checks and code-health digests, with the gates
that hold each tool. Generation
support (parser, snapshots, triage, evaluation) is in [../generation/quick-reference.md](../generation/quick-reference.md);
static scans in [../scan/quick-reference.md](../scan/quick-reference.md); workspace listing and
cleanup in [../workspace/quick-reference.md](../workspace/quick-reference.md); codemods in
[../codemods/README.md](../codemods/README.md).

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
| **Validation level** | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python -ValidationLevel fast` | Forwarded to `datrix generate --validation-level` |
| **Carry chains forward with live snapshots** | `.\dev\generate.ps1 <source.dtrx> <output-dir> -L python -ConfigProfile staging -CarryForwardLiveSnapshots <dir>` | Forwarded to `datrix generate --carry-forward-live-snapshots`; one `<rdbms_id>.json` per database of that profile; single project only (refused with `-All`/`-Domains`/`-TestSet`) |

`-All`, `-Domains` and `-TestSet` are Jon's: `validate-script-invocation.py` refuses them from an agent tool call.

Every run writes `generate-results-<timestamp>-<language>[-<profile>].log` to `<workspace>\.generated\.results`, whatever the output path; product repos' generate scripts call this script to get that log.

Before generating, the script checks the editable installs and that every installed plugin loads (a `datrix_scripts.plugin_discovery` child over the `datrix.languages`, `datrix.generators`, `datrix.platforms` and `datrix.extensions` groups), and then verifies the `datrix` CLI (`datrix_scripts.venv.check_datrix_command`; on failure it prints why, then reinstalls `datrix-cli` without its `[dev]` extra, which refuses under `DATRIX_OFFLINE`, and checks again). `datrix --version` loads no plugin, so a package whose plugin fails to register is named here, with the registry's own error, instead of failing deep inside the pipeline.

**Parameters:** `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (any registered `datrix.languages` target, **mandatory**, the real generation target — also selects the output-path language segment), `-Runtime`/`-R` (docker-compose\|azure-container-apps\|azure-app-service\|ecs-fargate\|app-runner, output path only), `-ConfigProfile` (config profile that also selects the provider segment read from `config/system.dcfg`, e.g. test\|development\|production; default: test), `-ValidationLevel` (none\|fast\|standard, validated by the CLI; omitted = CLI default, standard), `-OutputBase` (default: .generated), `-TestSet` (default: all), `-VerboseOutput`, `-Dbg`

**Logs:** generation logs are saved to `.generated/.results/generate-results-TIMESTAMP-LANGUAGE[-PROFILE].log`; old logs are not deleted automatically. The language and profile segments are labels, not what keeps two runs apart: each run **claims** its log file (`datrix_scripts.run_log.claim_run_log_file`), so two runs that compute the same name — two profiles generated in the same second, or two runs of one profile — get `…-2.log`, `…-3.log`, … rather than truncating and interleaving one file. Held by `test/run-log-exclusivity-gate.ps1`. Every exit path prints `Log saved to: <path>`, which the red-run digest hook reads when the Generation Summary reports a failed project.

**Module:** `datrix_scripts.dev.generate` (in `common/lib/`), behind a wrapper rendered from `common/templates/entrypoint.ps1`: it checks the packages, claims the run log and runs `datrix_scripts.dev.generate_projects`, which resolves the output path and runs `datrix generate` per project. Its POSIX twin `dev\generate.sh` takes the module's own flags: each parameter as `--kebab-name` (`--source`, `--output`, `--language`, `--runtime`, `--config-profile`, `--test-set`, `--verbose-output`, `--dbg`, `--self-test`; the `-L`/`-R` aliases are `--language`/`--runtime`) — `bash dev/generate.sh --source examples/02-features/01-core-data-modeling/entities/system.dtrx --language python`. `-SelfTest` runs the module's self-test and generates nothing. Every module behind a `dev\` wrapper takes its options spelled in full: an abbreviation is a usage error (exit 2), never expanded, since the guards read flags by their exact spelling.

### `dev\generate-doc-fragments.ps1`

Generates documentation fragments from source code. Extracts semantic pipeline stages (from `SemanticAnalyzer.analyze()` via AST parsing) and CLI help output (from `datrix generate --help`) into markdown files under `datrix/docs/generated/`.

| Mode | Command | Description |
|------|---------|-------------|
| **All fragments** | `.\dev\generate-doc-fragments.ps1` | Generate all fragments |
| **Semantic only** | `.\dev\generate-doc-fragments.ps1 semantic-pipeline` | Generate pipeline stages only |
| **CLI help only** | `.\dev\generate-doc-fragments.ps1 cli-help` | Generate CLI help only |
| **Check mode** | `.\dev\generate-doc-fragments.ps1 -Check` | Verify fragments are up-to-date (non-zero exit if stale) |
| **With debug** | `.\dev\generate-doc-fragments.ps1 -Dbg` | Show detailed output |

**Parameters:** `-Fragment` (positional 0: all\|semantic-pipeline\|cli-help, default: all), `-Check`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.dev.generate_doc_fragments`; POSIX twin `dev\generate-doc-fragments.sh` (`--check`, `--dbg`, `--self-test`; the fragment positional) — `bash dev/generate-doc-fragments.sh --check`.

---

## Imports and Parse Trees

### `dev\find-imports.ps1`

The worklist before a move or rename: every place that imports names from given modules. It
AST-parses (multi-line safe) every `.py` under each `datrix-*` repository's `src/` and `tests/`
trees and root `*.py` files, the scripts tree and the Claude Code hooks
(`datrix_scripts.import_sites`, shared with `codemods\split-module.ps1`). It resolves relative
imports inside `src/` packages and prints `path:line` per site. The code index's
`find_references` resolves symbols; this answers "which import statements name this module path"
and needs no index. Report only (exit 0). A file that does not parse is printed as UNPARSEABLE and
counted.

| Mode | Command | Description |
|------|---------|-------------|
| **Importers of a name** | `.\dev\find-imports.ps1 -Module datrix_common.errors.plugin -Name PluginError` | `[from-import]` sites, plus `[attribute]` reads (`plugin_mod.PluginError`) on a bound module |
| **Everything from a module** | `.\dev\find-imports.ps1 -Module datrix_codegen_common.transpiler.base` | Every from-import, plus `[import]`/`[module-import]` statements binding the module itself |

**Parameters:** `-Module <dotted,...>` (required), `-Name <name,...>`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.dev.find_imports`; POSIX twin `dev\find-imports.sh` (`--module`, `--name`, `--dbg`, `--self-test`) — `bash dev/find-imports.sh --module datrix_common.errors.plugin --name PluginError`.

### `dev\who-imports.ps1`

Which runtime import chain first loads a module. It imports each `-Root` in a fresh interpreter
with an observer on `sys.meta_path`. At the first lookup of a `-Target` (or any submodule of a
target package), it prints the workspace frames that led there, function-level imports and
entry-point loads included. The observer resolves nothing itself. `scan\check-import-boundaries.ps1`
reports *that* a forbidden edge exists (statically); this shows *which chain* realizes it.

| Mode | Command | Description |
|------|---------|-------------|
| **Trace a target** | `.\dev\who-imports.ps1 -Root datrix_codegen_kernel.dgen -Target datrix_codegen_common` | Does the kernel load the language layer, and through which import? |

**Module:** `datrix_scripts.dev.who_imports`; POSIX twin `dev\who-imports.sh` (`--root`, `--target`, `--self-test`).

**Parameters:** `-Root <module,...>` (required), `-Target <module,...>` (required), `-SelfTest`. **Exit codes:** 0 = every root imported (a target that never loaded is listed as such), 2 = a root failed to import (its error is printed).

### `dev\print-sexp.ps1`

The tree-sitter parse tree of Datrix source, as a corpus-style S-expression (two-space indent,
closing parentheses on the last child's line) ready to paste into a corpus test. It uses the built
Datrix grammar (`TreeSitterParser.parse_tree`); the native `tree-sitter` CLI cannot load that
library on every host. Named nodes only by default; MISSING nodes print as `(MISSING <type>)`.

| Mode | Command | Description |
|------|---------|-------------|
| **File** | `.\dev\print-sexp.ps1 examples\01-foundation\system.dtrx` | Tree of one file |
| **Inline** | `.\dev\print-sexp.ps1 -Text 'service s { }' -All` | Inline source, anonymous nodes included |

**Module:** `datrix_scripts.dev.print_sexp`; POSIX twin `dev\print-sexp.sh` (`--path` or the path positional, `--text`, `--all`, `--self-test`).

**Parameters:** `-Path` (positional 0) or `-Text`, `-All`, `-SelfTest`. **Exit codes:** 0 = clean tree, 1 = ERROR or MISSING nodes present (tree still printed), 2 = input unreadable.

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

**Parameters:** `-DocsDir` (positional, variadic — defaults to all monorepo docs/), `-Check` (deprecated-cli-flags\|fixed-phase-count\|cdx-filenames\|cdx-structure\|capability-status-labels, repeatable), `-Detailed`, `-Dbg`, `-LlmSuggest` with `-LlmLimit`, `-LlmNumPredict`, `-LlmTemperature` and the shared local-model flags `-LocalMachines`, `-LlmModel`, `-LlmTimeout`, `-SelfTest`

**Module:** `datrix_scripts.dev.check_docs`; POSIX twin `dev\check-docs.sh` (`--docs-dir`, `--check`, `--detailed`, `--dbg`, `--llm-suggest`, `--self-test`, …) — `bash dev/check-docs.sh --check deprecated-cli-flags`.

**Exit codes:** 0 = clean, 1 = lint failures found

---

## Code Index

### `dev\code-index.ps1`

Queries the code index: an SQLite index of every Python, Markdown, PowerShell, `.dtrx`, `.dcfg` and TypeScript file git sees in the workspace repositories (tracked, plus untracked files no `.gitignore` excludes, minus `scripts/config/code-index.json`'s `exclude`). Each format is read with its own parser (`datrix_scripts.code_index.formats`):

- Markdown headings become `section`s, read with markdown-it, so headings inside code fences are skipped.
- PowerShell functions and script/function `parameter`s are read with PowerShell 7's parser (`pwsh` on `PATH`).
- `.dtrx` definitions get the language server's outline kinds (`service`, `entity`, `field`, `endpoint`, ...).
- `.dcfg` `config`s, `block`s, `profile`s, `template`s, `key`s and `setting`s come from the Datrix grammar.
- TypeScript classes, interfaces, types, enums, namespaces, functions, methods and fields come from tree-sitter.

References, imports and logic-map markers are read from Python only. A non-Python file's module name is its path. It lives beside the checkout at `d:\datrix\.code-index\`. **Each development machine has its own**, built from its own working tree, so nothing is synchronised between machines.

**Creating and updating.** Run `-Setup` once on each machine, and again whenever the server's script path changes: it builds the index (about ten seconds) and writes the index's MCP server into `d:\datrix\.mcp.json` with this machine's paths and the scripts `PYTHONPATH`, keeping any other servers in the file. It then approves the server for this machine in `.claude\settings.local.json` (gitignored), because current Claude Code builds ignore an approval in the checked-in `settings.json`. Last, it removes the local-scope registrations older versions made. Those two files are the only ones `-Setup` writes (here and in `local-llm.ps1 -Setup`, the same `datrix_scripts.dev.mcp_setup` writer); a file that is not valid JSON is refused, never overwritten. Claude Code reads `.mcp.json` from the opened folder for every installation and drive-letter spelling, so an extension update needs no re-run. Then restart Claude Code (in VS Code: Developer: Reload Window). `claude mcp get datrix-code-index` may still say "Pending approval"; a real session connects it regardless. There is nothing to schedule after that. Every query, from this script or an agent's MCP tool call, first brings the index up to date with the working tree (about 0.2 s when little changed), so edits, pulls and branch switches show up in the next query. Only files whose content changed are parsed again.

The index also owns the logic map. Every refresh rewrites `d:\datrix\.logic-map\markers.db` whenever the `@canonical`/`@pattern`/`@boundary`/`@invariant`/`@test-rule` markers in source changed.

Queries never leave the machine. `-Summarize` is the exception, and it only runs when asked for: it sends each module's outline and source to a local model server (plain HTTP on the local network, like every local-model script) and caches the summary per machine by content hash.

| Mode | Command | Description |
|------|---------|-------------|
| **Set up a machine** | `.\dev\code-index.ps1 -Setup` | Build the index and register the MCP server; re-run safely |
| **Definitions** | `.\dev\code-index.ps1 -Symbol to_snake_case` | Bare name, glob (`*Resolver`), `Class.method`, or dotted path; `-Kind` narrows to one kind (`class`, `function`, `method`, `section`, `parameter`, `entity`, `setting`, ...; an unknown kind is refused with the full list) |
| **Uses** | `.\dev\code-index.ps1 -References datrix_common.utils.text.to_snake_case` | Resolved through imports (aliases, re-exports); methods match every `.name` access |
| **File outline** | `.\dev\code-index.ps1 -Outline datrix-common/src/datrix_common/utils/text.py` | Definitions with line ranges and signatures; path, unique suffix, or module name |
| **Search** | `.\dev\code-index.ps1 -Search "tenant isolation"` | Ranked full-text over names, signatures, docstrings, summaries, markers |
| **Logic map** | `.\dev\code-index.ps1 -Canonical text/to-snake` | Markers by topic path, topic segment, or words; `-IncludeTestRules` adds `@test-rule` |
| **Status** | `.\dev\code-index.ps1 -Status` | Counts, summary coverage, files with syntax errors |
| **Refresh** | `.\dev\code-index.ps1 -Refresh` | Bring the index up to date and report what changed |
| **Summaries** | `.\dev\code-index.ps1 -Summarize -Limit 100` | Summarize modules lacking a summary (`-Limit 0` = all) |
| **Adoption** | `.\dev\code-index.ps1 -Usage -Days 7` | Index tool calls against the greps, whole reads of large `.py` files and shell searches the index could have answered, with estimated tokens |

**Usage log:** the non-blocking PostToolUse hook `record-search-usage.py` appends one line per code-search call to `d:\datrix\.code-index\usage.jsonl` on each machine. It records the tool, the pattern or path searched (never file content) and the size of the answer. A shell search counts when `rg`/`grep`/`Select-String`/`findstr` starts a command or is piped from a file listing; piped from anything else it is an output filter and is not logged. After an identifier grep or a whole read of a large `.py` file the same hook points the agent at the index: at the MCP tool when the server is registered for the directory the session started in, otherwise at the `code-index.ps1` command. The hook finds its workspace from its own real path, so it logs to `d:\datrix\.code-index\` however it is started.

**Summaries stay current without `-Summarize`.** A module summary is keyed by the module's content hash, so every edit leaves the module without one. When a query's refresh (the CLI's, or an MCP tool call's) finds changed files, or the MCP server's first call finds modules still waiting, it starts a detached `python -m datrix_scripts.dev.code_index --summarize --limit=0` run in the background and answers at once; the run summarizes everything pending on the local model servers and exits. Only one summarize run exists at a time: every run, this one or a manual `-Summarize`, holds `d:\datrix\.code-index\summarize.lock` (a lock older than 4 hours is taken over), and a second run exits at once. The background run's output is `d:\datrix\.code-index\summarize.log`. `-Status` shows the coverage.

**Missing registration is announced.** A session whose start directory lacks the `datrix-code-index` or `datrix-local-llm` server is told so at session start by `session-context.py`, per server, with its `-Setup` command (and, for the index, the shell fallback). A server counts when registered in user scope, in local scope for that exact directory, or in a `.mcp.json` there that this machine has approved (`enabledMcpjsonServers` in `.claude\settings.local.json` or the project's `~/.claude.json` entry; `disabledMcpjsonServers` wins). Without it a machine that never ran `-Setup` looks like one that did, and every agent silently greps instead.

**Parameters:** exactly one action: `-Symbol`, `-References`, `-Outline`, `-Search`, `-Canonical`, `-Status`, `-Refresh`, `-Usage`, `-Summarize`, `-Setup`. Modifiers: `-Kind` (with `-Symbol`), `-IncludeTestRules` (with `-Canonical`), `-Days` (with `-Usage`; default 7, 0 = all), `-Limit` (results, files listed, or modules summarized), `-Workers` (default 4), `-LocalMachines`, `-LlmModel` and `-LlmTimeout` (default 300; all three with `-Summarize`). `-SelfTest` runs the module's self-test.

**Exit codes:** 0 answered; 1 the query or index could not be answered as asked; 2 `-Summarize` found no local model server.

**Module:** `datrix_scripts.dev.code_index`; POSIX twin `dev\code-index.sh` (`--symbol`, `--references`, `--outline`, `--search`, `--canonical`, `--status`, `--setup`, `--self-test`, …) — `bash dev/code-index.sh --symbol to_snake_case`. `-Setup` (`datrix_scripts.dev.mcp_setup`) registers the server as the venv Python running `-m datrix_scripts.dev.code_index_mcp`.

**Agents:** the MCP server (`datrix_scripts.dev.code_index_mcp`, stdio, no socket) offers the same queries as the tools `find_symbol`, `find_references`, `outline`, `search`, `find_canonical` and `index_status`.

### `dev\code-index-gate.ps1`

Behaviour checks for the code index (`common/lib/datrix_scripts/code_index/`) and its entry points (`dev\code-index.ps1`, the MCP server `datrix_scripts.dev.code_index_mcp`, and the logic-map consumers). Each check builds a real workspace of git repositories in a temporary directory and runs the real index over it. The checks cover:

- extraction: definitions, imports and references, a file with a syntax error, and wrapped `@rule` lines
- the file set: git visibility and config excludes
- incremental refresh: a touched-but-unchanged file is not re-parsed, and deleted files leave the index
- references resolved through aliases, re-exports and module imports
- the method-reference caveat
- the logic-map rewrite happening only when markers change
- search and canonical topic matching
- model summaries against a real loopback model server, the summarize lock (exclusive, stale locks taken over), and the background summarize run (started only when modules are pending and no run holds the lock, by the CLI and by the MCP server when its refresh changes files)
- the MCP protocol, in-process and as a subprocess whose stdout must carry only protocol
- the code scan's additions (`dev\code-scan.ps1`): index verdicts for dead-code findings (dead, test-only, refuted by another file's use, unmatched), names used through strings and templates, and changed-package selection

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\dev\code-index-gate.ps1` | Run every check |
| **One area** | `.\dev\code-index-gate.ps1 -Only check_references` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\dev\code-index-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |
| **Self-test** | `.\dev\code-index-gate.ps1 -SelfTest` | Harness self-test, then the gate's checks over planted inputs |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

**Module:** `datrix_scripts.dev.code_index_gate`; POSIX twin `dev\code-index-gate.sh` (`--only`, `--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] code-index PASSED|FAILED` verdict line.

### `dev\logic-map-report.ps1`

Refreshes the code index (which rewrites the logic map database if markers changed), then dumps the logic map SQLite database to a readable Markdown report for human verification.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\dev\logic-map-report.ps1` | Write logic-map-report.md to current dir |
| **Custom output** | `.\dev\logic-map-report.ps1 -Output docs\logic-map.md` | Custom output path |

**Parameters:** `-Output` (positional 0), `-SelfTest`

**Module:** `datrix_scripts.dev.logic_map_report`; POSIX twin `dev\logic-map-report.sh` (`--output` or the output positional, `--self-test`).

**Exit codes:** 0 = report written and every `@see` names a declared topic; 1 = the index could not be refreshed, or the report lists dangling `@see` references (section "Dangling @see References").

---

## Local Models and the Knowledge Base

### `dev\local-llm.ps1`

**Sets up, inspects and measures the local model servers that agents read through.** The Ollama servers on the network's machines (the only model server they run; searched by `common/lib/datrix_scripts/local_llm.py`) answer every local-model script, the stop-gate judge, and the agents' MCP tools from `datrix_scripts.dev.local_llm_mcp`:

| Tool | What the agent gets |
|------|---------------------|
| `ask_files` | A question about up to 40 files (paths or globs) answered in a few lines citing `path:line`, so the agent does not read the text itself. Larger inputs are split into chunks: each chunk is answered separately and the answers are merged. |
| `digest_log` | The distinct failures in a test, generation or deploy log: one entry per cause, with its count, the first log line and the source `file:line` it names. A log too large to read whole is cut to the lines around error markers, or to its end when it has none. |
| `local_models` | Which servers answer, what they hold in memory, and recent usage. |

**What may be read:** files inside the framework repositories (`datrix` and every `datrix-*` git repository at the workspace root) and `.test-output`. Anything else is refused: another repository at the workspace root, `.tmp`, `reports`, `design`, `.git` internals. (`skill\skill-assist.ps1` is the one script that sends design docs and findings files to a model, through the same customer-term filter; see `skill/quick-reference.md`.) Paths are resolved before the check, so `..` cannot escape it. An answer is a lead, not a finding. Every citation is checked against the files and lines that were actually sent, and one that does not match is called out under the answer. The agent opens the cited lines with a ranged Read before acting on them.

**The harness uses the models without an agent asking.** Three hooks (`claude-config/.claude/hooks/`) call them on an agent's behalf; each is bounded, resident-models-only, and fails open (any failure leaves the tool call exactly as it was):

| Hook | When | What the agent gets | Usage caller |
|------|------|---------------------|--------------|
| `digest-red-test-run.py` (PostToolUse) | a `test.ps1` / `test-single.ps1` run's console output reports a package that is not `[PASSED]` | A local model's list of the distinct failures in the run's `full.log` (up to 2 runs per call), with a pointer to the run's `failure-data.json`. A run whose folder holds `digest.txt` is skipped: `test.ps1` already wrote its failure digest there | `hook:red-test-digest` |
| `redirect-large-read.py` (PreToolUse on `Read`) | the **first** whole read (no `offset`/`limit`), by one agent, of a `.py` file of 14,000 bytes or more in a framework repo, or of a `.log` of 20,000 bytes or more under `.test-output`/`.test_results` | The read is refused with the file's code-index outline (definitions with line ranges, plus the module summary a local model wrote) or, for a log, the model's digest. Repeating the same Read goes through: the notice is shown once per file per agent. Ranged reads, small files, files outside the framework repos or the index, and any failure are never refused | `hook:large-read-digest` |
| `inject-task-orientation.py` (PostToolUse on `Read`) | an agent reads a task file (`.tasks/phase-NN/task-NN-TT-*.md`) that carries an `## Orientation` block | The block answered into the agent's context: `symbol` / `refs` / `outline` / `canonical` entries as exact code-index answers, `explain` entries as a local model's cited reading (marked a lead), and an entry that no longer resolves called out as a stale premise. Once per task per agent; a task with no block, or a ranged read of the middle of a task, gets nothing. Task format and the validator: `tasks/quick-reference.md`, `validate-task.ps1` | `hook:task-orientation` |

Hooks reach the shared scripts package through `add_scripts_lib_to_path()` in `_hook_log.py`. `code-index.ps1 -Usage` counts redirects as `read_redirect`, and those followed by the same agent reading the whole file anyway as `read_redirect_repeat`; when most redirects repeat, the 14,000-byte threshold or the once-per-file rule in `redirect-large-read.py` needs revisiting. The stop-gate judges (`hook:stop-judge`, `hook:subagent-judge`) use the same models.

**Spreading and failover:** a request goes to an idle ready server. While every ready server is busy, the next resident one is readied, so concurrent requests use every machine's resident model. The MCP tools never wait for a model to load: they use resident models only.

**Residency:** because the hooks and MCP tools use resident models only, and a script loads an Ollama model only when no resident one is left, a machine whose Ollama holds nothing in memory takes no work in normal use (`-Status` shows it as `resident none; loadable …`). To make it share the work, keep a model resident there: set `OLLAMA_KEEP_ALIVE=-1` on that machine and load the model once; a load request carrying `"keep_alive": -1` holds it the same way without the setting, until Ollama restarts. The pool never shortens a residency a model already has: it sends its own keep-alive (`--local-keep-alive`, default 30 minutes) only when that outlasts the model's current one, and keeps an indefinite one indefinite.

**Usage log:** every request from any caller (script, hook `hook:<gate>-judge`, MCP tool `mcp:<tool>`) is one line in `d:\datrix\.local-llm\usage.jsonl` on the machine that sent it. Each line records the caller, the server and model, the characters sent and received, the seconds taken and the outcome, never the text. `DATRIX_LOCAL_LLM_USAGE_LOG` points it elsewhere; the gates use it so their loopback servers never count as real use.

| Mode | Command | Description |
|------|---------|-------------|
| **Set up a machine** | `.\dev\local-llm.ps1 -Setup` | Write the MCP server `datrix-local-llm` into `d:\datrix\.mcp.json` (other servers kept, scripts `PYTHONPATH` in its `env`), approve it for this machine in `.claude\settings.local.json`, remove older local-scope registrations; restart Claude Code afterwards. Same mechanism as `code-index.ps1 -Setup` (`datrix_scripts.dev.mcp_setup`) |
| **Status** | `.\dev\local-llm.ps1 -Status` | Servers that answer, resident models, a line per machine holding no model indefinitely, and the last day's usage |
| **Usage** | `.\dev\local-llm.ps1 -Usage -Days 7` | Requests by caller and by server (`-Days 0` = everything logged) |
| **Pin** | `.\dev\local-llm.ps1 -Pin` | On each reachable machine, load the first installed model of the load preference and keep it resident indefinitely, so the resident-only callers (the red-run digest hook) find one; prints per machine what was pinned or why not. Nothing pins automatically |
| **Unpin** | `.\dev\local-llm.ps1 -Unpin` | On each reachable machine, unload every indefinitely resident model; prints what was released |

**Parameters:** exactly one action: `-Setup`, `-Status`, `-Usage`, `-Pin`, `-Unpin`, `-SelfTest`. Modifier: `-Days` (with `-Status`, default 1; with `-Usage`, default 7; 0 = all).

**Exit codes:** 0 done; 1 the request could not be carried out.

**Module:** `datrix_scripts.dev.local_llm`; POSIX twin `dev\local-llm.sh` (`--setup`, `--status`, `--usage`, `--pin`, `--unpin`, `--days`, `--self-test`) — `bash dev/local-llm.sh --status`. `-Setup` registers the server as the venv Python running `-m datrix_scripts.dev.local_llm_mcp`.

### `dev\local-llm-gate.ps1`

Behaviour checks for the local-model reading tools: the reading layer (`common/lib/datrix_scripts/local_reading.py`) and the MCP server built on it (`datrix_scripts.dev.local_llm_mcp`). Each check builds a real workspace in a temporary directory (two framework repositories, a customer-style repository beside them, `.tmp` and `.test-output`) and answers through a real Ollama-shaped server on loopback (`common/lib/datrix_scripts/local_llm_loopback.py`) whose answers depend on the prompt. It never contacts the network's model servers, and it records requests in a temporary usage log, never the machine's own. The checks cover:

- scope: framework repositories and `.test-output` are read; another repository, `.tmp`, `..` escapes, `.git` internals and paths outside the workspace are refused; a glob reaching out of scope is refused whole; at most 40 files per call
- chunking: every chunk opens with its file's header and keeps original line numbers; a long file is split at line boundaries
- log reduction: a large log is cut to the lines around error markers, or to its end when it has none
- answering: one request for one chunk; one request per chunk plus a merge for more; a citation of an unsent file or line is called out (for a log, only citations of the log itself are checked)
- the MCP server: tool listing, an answer, an out-of-scope refusal, bad arguments, no model server reported as a tool error, the usage log entry under `mcp:<tool>`, and stdout carrying only protocol

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\dev\local-llm-gate.ps1` | Run every check |
| **One area** | `.\dev\local-llm-gate.ps1 -Only check_scope` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\dev\local-llm-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |
| **Self-test** | `.\dev\local-llm-gate.ps1 -SelfTest` | Harness self-test, then the gate's checks over planted inputs |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

**Module:** `datrix_scripts.dev.local_llm_gate`; POSIX twin `dev\local-llm-gate.sh` (`--only`, `--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] local-llm PASSED|FAILED` verdict line.

### `dev\line-edit.ps1`

Sets up the `datrix-edit` MCP server (`datrix_scripts.dev.line_edit_mcp`, logic in `common/lib/datrix_scripts/line_edits.py`). Its `read_lines` shows each line as `<number>:<hash>|<text>` (same `file_path`/`offset`/`limit` as Read). Its `edit_lines` replaces lines (`{file_path, start, end, hashes, text}`, `hashes` = the 2-character hash of every replaced line) or inserts after a line (`{file_path, after, hash, text}`, `after` 0 = the top). One call carries up to 200 edits across files.

- **Old text is never re-sent.** An `Edit` re-sends its `old_string`, padded until unique, and every later response re-reads it. In one overnight run, old text made up 46% of all edit input.
- **Checked before written.** Line numbers refer to the files as they were before the call, and edits apply bottom-up. Every edit is checked before any file is written. One wrong hash refuses the whole call and shows the lines now there.
- **Ready for the next edit.** The reply gives each changed range's new numbers and hashes, so a follow-up edit needs no re-read.
- **Files are preserved.** Untouched lines keep their own endings, and the byte-order mark and a missing final newline are kept. Each file is written atomically.
- **Limits.** Only existing UTF-8 text files under the workspace, up to 4 MB, are read or edited. New files are still made with Write.
- **Guarded like Edit.** The `route-line-edits.py` hook hands each file's change, as an `Edit` payload, to every guard `settings.json` registers for Edit. The `datrix-edit` read tool counts as a Read for the mandatory-reads gate and the large-read redirect.
- **After an edit.** Keep editing a file with `edit_lines` once it has changed it: the built-in Edit refuses a file changed outside it until it is read again.

| Mode | Command | Description |
|------|---------|-------------|
| **Set up a machine** | `.\dev\line-edit.ps1 -Setup` | Write `datrix-edit` into `d:\datrix\.mcp.json` (other servers kept), approve it for this machine in `.claude\settings.local.json`, remove older local-scope registrations; restart Claude Code afterwards (`datrix_scripts.dev.mcp_setup`, the writer behind `code-index.ps1 -Setup`). The entry starts the server as `python -m datrix_scripts.dev.line_edit_mcp`, so a machine set up when the server was a script path re-runs `-Setup` |
| **Self-test** | `.\dev\line-edit.ps1 -SelfTest` | `-Setup` is required, the server module it registers resolves, and the wrapper is the template rendered with the module's options; registers nothing |

**Parameters:** `-Setup`, `-SelfTest`

**Exit codes:** 0 done; 1 the request could not be carried out.

**Module:** `datrix_scripts.dev.line_edit`; POSIX twin `dev\line-edit.sh` (`--setup`, `--self-test`).

### `dev\line-edit-gate.ps1`

Behaviour checks for line-addressed editing, run on real files in a temporary workspace through `datrix_scripts.line_edits` and the `datrix-edit` server. The checks cover:

- numbered, hashed reading
- hash-checked replaces, deletes and inserts (top, end, an empty file)
- a whole call refused, with nothing written, when one hash is wrong
- line numbers that refer to the file before the call
- overlapping and misshapen edits refused
- kept CRLF, mixed endings, byte-order mark and missing final newline
- a reply that carries what a follow-up edit needs
- the workspace, NUL-byte and UTF-8 limits
- the span the edit guards are shown
- the MCP protocol, with stdout carrying only protocol

It is a repo-level validation **script**, not a pytest suite. The hook side is checked by `.claude/hooks/test-route-line-edits.py`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\dev\line-edit-gate.ps1` | Run every check |
| **One area** | `.\dev\line-edit-gate.ps1 -Only check_mcp` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\dev\line-edit-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |
| **Self-test** | `.\dev\line-edit-gate.ps1 -SelfTest` | Harness self-test, then the wrapper seam checks |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

**Module:** `datrix_scripts.dev.line_edit_gate`; POSIX twin `dev\line-edit-gate.sh` (`--only`, `--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] line-edit PASSED|FAILED` verdict line.

### `dev\ineedtoknow.ps1`

**Ask what you need to know, in your own words, instead of loading whole docs.** The knowledge base answers from the project's own docs (architecture cheat sheet and knowledge packs, the decision log, agent rules, execution contract, script quick-references, package architecture docs; the list is `CURATED_PATTERNS` in `common/lib/datrix_scripts/knowledge/seed.py`), cut into chunks by heading, and from answers learned earlier. A hit is a brief answer plus the file and line range to open. Wrapper over the module `datrix_scripts.dev.ineedtoknow`; the logic is in `common/lib/datrix_scripts/knowledge/`.

**When the knowledge base holds no answer**, a local model server that already has a model in memory (never waits for a load) reads the closest chunks of the docs (with their real line numbers) plus any `-In` files, and writes a short cited answer. The answer is **stored only when grounded**: it cites at least one `path:line`, every citation names a file and line the model was actually sent, and every quoted snippet is in what it was sent. A failed answer is reported with the reason and the closest places to read, and is never stored. With no model server available it says so and lists the same places. A stored answer **expires when a file it cites changes** (content hash).

**Storage and two-machine sync.** The SQLite database is per machine, `d:\datrix\.knowledge\knowledge.db` (`DATRIX_KNOWLEDGE_DB` overrides it); it is a cache and can always be rebuilt. Every learned answer is also written as one markdown file to `datrix\docs\knowledge\learned\<id>.md` (committed; the id is the hash of the question, so two machines never conflict). Each invocation first brings the database up to date with the docs (re-cut by content hash) and with those files: after a pull, a machine imports each learned file whose cited files hash the same there. A file is never deleted by a sync; learning the same question again overwrites it, and `-Prune` deletes the ones whose sources changed.

| Mode | Command | Description |
|------|---------|-------------|
| **Ask** | `.\dev\ineedtoknow.ps1 -Question "which package owns the gateway route enumeration"` (or just `.\dev\ineedtoknow.ps1 "…"`) | Brief answer from the knowledge base; gathers and stores one with a local model when it holds none |
| **Look up only** | `.\dev\ineedtoknow.ps1 "…" -NoLearn` | Never contacts a model; prints the closest places to read when there is no answer |
| **Read specific files** | `.\dev\ineedtoknow.ps1 "…" -In "datrix-semantic/src/**/*tenant*.py"` | A local model reads these files too (framework repositories only) |
| **Re-gather** | `.\dev\ineedtoknow.ps1 "…" -Refresh` | Skip the lookup; read the closest docs again and replace the stored answer |
| **Status** | `.\dev\ineedtoknow.ps1 -Status` | Database path, docs and chunks, learned answers, learned files and how many are stale here |
| **Rebuild** | `.\dev\ineedtoknow.ps1 -Rebuild` | Drop the database and rebuild it from the docs and the committed learned files |
| **Prune** | `.\dev\ineedtoknow.ps1 -Prune` | Delete learned files whose cited files changed on this machine (a git change to commit) |

**Parameters:** exactly one of: a question (positional or `-Question`), `-Status`, `-Rebuild`, `-Prune`. Modifiers: `-In`, `-Refresh`, `-NoLearn`, `-Limit` (answers shown, default 3), and the shared local-model flags `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (seconds, default 120). `-SelfTest` runs the module's self-test.

**Module:** `datrix_scripts.dev.ineedtoknow`; POSIX twin `dev\ineedtoknow.sh` (the question positional or `--question`, `--in`, `--refresh`, `--no-learn`, `--status`, `--rebuild`, `--prune`, `--self-test`, …) — `bash dev/ineedtoknow.sh "which package owns the gateway route enumeration" --no-learn`.

**Exit codes:** 0 answered; 1 the request could not be carried out (the message says why); 2 no answer (not in the knowledge base and no local model could add one). An answer is a lead, not a finding: open the cited lines before acting on it.

### `dev\ineedtoknow-gate.ps1`

Behaviour checks for `dev\ineedtoknow.ps1` (`common/lib/datrix_scripts/knowledge/`, `datrix_scripts.dev.ineedtoknow`). Each check builds a real workspace in a temporary directory (framework repositories plus a customer-style repository), uses real SQLite files, and answers through a real Ollama-shaped server on loopback (`common/lib/datrix_scripts/local_llm_loopback.py`). It never contacts the network's model servers and never touches the machine's own knowledge base. The checks cover:

- chunking: a chunk's body equals the document's own lines `line_start`..`line_end`; a `#` line inside a code fence is not a heading; a long section splits into bounded chunks that keep every line
- sync: docs are added, updated by content hash and removed; a customer repository never enters the knowledge base
- lookup: a question is answered only by a chunk covering most of its significant words (camelCase identifiers match their words); unrelated and stopword-only questions find nothing
- the committed text copy: a learned file round-trips and a hand-edited id, a missing front matter, a bad source hash or an empty answer is refused; a second machine converges from the files alone, a rebuild restores them, and deleting a file drops the answer
- expiry: an answer whose cited file changed is not returned, not imported by another machine, never deleted by a sync, and deleted by `-Prune`
- gathering: the model is sent the closest chunks with their real line numbers and no customer text; an answer is stored only when grounded (no citation, a citation of an unsent file or line, quoted code that was not sent, and "nothing relevant" are each rejected and write nothing); no model server raises `LocalLlmUnavailable`

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\dev\ineedtoknow-gate.ps1` | Run every check |
| **One area** | `.\dev\ineedtoknow-gate.ps1 -Only check_gather` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\dev\ineedtoknow-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |
| **Self-test** | `.\dev\ineedtoknow-gate.ps1 -SelfTest` | Harness self-test, then the gate's checks over planted inputs |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

**Module:** `datrix_scripts.dev.ineedtoknow_gate`; POSIX twin `dev\ineedtoknow-gate.sh` (`--only`, `--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] ineedtoknow PASSED|FAILED` verdict line.

---

## Code Health

### `dev\code-scan.ps1`

**On-demand code-health scan: one ranked digest instead of four scanners' raw output.** By default it scans only the packages whose content changed since their last scan. It tracks this with the code index's file hashes, in `d:\datrix\.code-index\scan-state.json`; the first run covers everything. It runs on this machine and changes nothing but the report and the scan state. Every finding is written, by section and then by package, to `d:\datrix\reports\code-scan\code-scan-<timestamp>.md`, headed by a per-package count table. The console gets one progress line per stage, then one line with the totals and the report's path, so a reader opens just the sections it needs.

| Section | Source | What the scan adds |
|---|---|---|
| Dead code: never used / used only by tests | two-pass Vulture (`common/lib/datrix_scripts/metrics/dead_code_report.py`) | Each finding is checked against the code index across the whole workspace, so a use in another package refutes it. It is dropped if a Jinja template, a Python string (a `getattr` name, a dotted resolver path, DAL generator text) or a `pyproject.toml` entry point names it. Unused imports are left to ruff. Classes and functions rank above fields. |
| Too complex | cyclomatic + cognitive (`common/lib/datrix_scripts/metrics/complexity.py`) | Merged, highest first |
| Duplicated blocks | Pylint R0801 (`common/lib/datrix_scripts/metrics/duplicate.py`) | Largest first |
| Docs drift | `datrix_scripts.dev.check_docs` checks over each package's `docs/` | — |

| Mode | Command | Description |
|------|---------|-------------|
| **Changed packages** | `.\dev\code-scan.ps1` | Packages changed since their last scan |
| **Named packages** | `.\dev\code-scan.ps1 datrix-common datrix-cli` | These, changed or not |
| **By folder** | `.\datrix\scripts\dev\code-scan.ps1 .\datrix-cli\` | A package folder in any form: relative, absolute, trailing slash, or a path inside it |
| **Everything** | `.\dev\code-scan.ps1 -All` | Every Python package (about 4 minutes) |

**Parameters:** `-Package` (positional; names or folders), `-All`, `-MinConfidence` (Vulture, default 60), `-DuplicateMinLines` (default 6), `-SelfTest`

**Module:** `datrix_scripts.dev.code_scan`; POSIX twin `dev\code-scan.sh` (the packages positional or `--package`, `--all`, `--min-confidence`, `--duplicate-min-lines`, `--self-test`) — `bash dev/code-scan.sh datrix-common`.

**Exit codes:** 0 = digest written, or nothing changed since the last scan; 1 = the scan could not run (a missing tool such as Vulture, an unknown package, an unreadable scan state).

**Needs** `vulture`, `pylint`, `radon` and `cognitive_complexity` in the shared venv. `radon` (the datrix-* packages' `[dev]` extras), `pylint` (`datrix-codegen-python`'s `[dev]` extra) and `cognitive_complexity` (the `scripts` dependency group of `datrix/pyproject.toml`) are installed with the venv: a missing one means the venv is broken, and the scan refuses with the repair (`common\venv.ps1 -EnsurePackages`) instead of checking less. `vulture` is declared by no manifest; install it with `D:\datrix\.venv\Scripts\python.exe -m pip install vulture`. A missing Vulture fails the scan instead of reporting no dead code.

### `dev\generate-test-rules.ps1`

Generates `@test-rule` conformance annotations for test functions using a local LLM (the `-Model` model, on whichever local machine `common/lib/datrix_scripts/local_llm.py` finds serving it). Two phases: default **propose** writes reviewable proposals to `.test-output/test-rules/<model>/<package>.json` (+ `.md` preview) and touches no source; **-Apply** inserts the reviewed markers above the test functions. After generation, a **topic-consolidation pass** merges near-duplicate topic slugs and kebab-normalizes them (skip with `-NoConsolidate`). `tests/e2e` and `tests/integration` are **excluded by default** (opt in with `-IncludeE2e` / `-IncludeIntegration`, or target via `-Path`). Resumable — already-annotated and already-proposed functions are skipped. Output is per-model so different models don't clobber. Markers feed the logic-map Rule Matrix; the existing test-rule topics that seed and anchor consolidation are read from the code index, refreshed first (`code-index.ps1`).

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

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Apply`, `-Review` (triage existing proposals; no LLM/edits), `-Model` (default: exaone-deep:32b), `-LocalMachines` (machines to search, in preference order; default: the list in `common/lib/datrix_scripts/local_llm.py`), `-Parallel` (default: 4), `-Limit` (default: 0 = no limit), `-Path` (file/dir filter, repeatable; also scopes `-Apply`/`-Review`), `-NoSeed` (don't seed topic vocabulary from existing markers), `-NoConsolidate` (skip topic-merge pass), `-IncludeE2e`, `-IncludeIntegration` (e2e/integration excluded by default), `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.dev.generate_test_rules`; POSIX twin `dev\generate-test-rules.sh` (the packages positional or `--projects`, `--all`, `--apply`, `--review`, `--model`, `--path`, `--no-seed`, `--self-test`, …) — `bash dev/generate-test-rules.sh datrix-codegen-python --review`.
