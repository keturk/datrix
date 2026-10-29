# Development Scripts

Generation, import and parse-tree lookups, the code index, the local model servers and the knowledge
base agents read through, documentation checks and code-health digests, with the gates that hold each
tool. The commands, parameters and exit codes of each script are in
[quick-reference.md](quick-reference.md); this file holds what they do and how they are built.

Every wrapper is rendered from `common/templates/entrypoint.ps1` around the `datrix_scripts.dev.*`
module named below, each with a POSIX twin `dev\<name>.sh` taking the module's own flags as
`--kebab-name`. Every module behind a `dev\` wrapper takes its options spelled in full: an abbreviation
is a usage error (exit 2), never expanded, since the guards read flags by their exact spelling. Every
`-*-gate.ps1` is a repo-level validation **script**, not a pytest suite, and ends with a
`[GATE] <name> PASSED|FAILED` verdict line.

## Code Generation

### `generate.ps1`

Generates Datrix projects from `.dtrx` source files. `-Language`/`-L` is **mandatory** and is the real
generation target — forwarded to `datrix generate --language`, and also selects the output-path language
segment (the two can never disagree). `-Runtime`/`-R` is a wrapper-only output-path selector; the
output-path provider segment is read from each project's `config/system.dcfg` deployment block (active
`-ConfigProfile`, default `test`), not a flag. Deployment runtime/provider, service flavor, and
infrastructure flavor used for generation are read from project config. `-ValidationLevel` is forwarded to
`datrix generate --validation-level` (validated by the CLI; omitted = the CLI default, standard).

`-All`, `-Domains` and `-TestSet` are Jon's: `validate-script-invocation.py` refuses them from an agent
tool call. The batch forms: `-All` (test set all), `-TestSet foundation` (examples/01-foundation),
`-TestSet non-foundation` (everything except foundation), `-Domains` (examples/03-domains), any named
test set (`features-core`, `typescript-validation` for a quick TS validation subset).

Every run writes `generate-results-<timestamp>-<language>[-<profile>].log` to
`<workspace>\.generated\.results`, whatever the output path; product repos' generate scripts call this
script to get that log. `-ResultsSubdir <name>` writes the log to `<workspace>\.generated\.results\<name>\`
instead (created when missing; a relative folder that stays inside `.results`, so `..` or an absolute path
is refused), which lets a product repo keep its logs apart from the others. Tools that default to the
`.results` folder (`status-generation.ps1`, `triage-failures.ps1`) need the log path or `-ResultsDir` for it. Old logs are not deleted automatically. The language and profile segments are
labels, not what keeps two runs apart: each run **claims** its log file
(`datrix_scripts.run_log.claim_run_log_file`), so two runs that compute the same name — two profiles
generated in the same second, or two runs of one profile — get `…-2.log`, `…-3.log`, … rather than
truncating and interleaving one file. Held by `test/run-log-exclusivity-gate.ps1`. Every exit path
prints `Log saved to: <path>`, which the red-run digest hook reads when the Generation Summary reports a
failed project.

Before generating, the script checks the editable installs and that every installed plugin loads (a
`datrix_scripts.plugin_discovery` child over the `datrix.languages`, `datrix.generators`,
`datrix.platforms` and `datrix.extensions` groups), and then verifies the `datrix` CLI
(`datrix_scripts.venv.check_datrix_command`; on failure it prints why, then reinstalls `datrix-cli`
without its `[dev]` extra, which refuses under `DATRIX_OFFLINE`, and checks again). `datrix --version`
loads no plugin, so a package whose plugin fails to register is named here, with the registry's own
error, instead of failing deep inside the pipeline.

Module: `datrix_scripts.dev.generate` (in `common/lib/`), behind a wrapper rendered from
`common/templates/entrypoint.ps1`: it checks the packages, claims the run log and runs
`datrix_scripts.dev.generate_projects`, which resolves the output path and runs `datrix generate` per
project. POSIX twin `dev\generate.sh` (`--source`, `--output`, `--language`, `--runtime`,
`--config-profile`, `--test-set`, `--verbose-output`, `--dbg`, `--self-test`; the `-L`/`-R` aliases are
`--language`/`--runtime`): `bash dev/generate.sh --source examples/02-features/01-core-data-modeling/entities/system.dtrx --language python`.
`-SelfTest` runs the module's self-test and generates nothing.

### `generate-doc-fragments.ps1`

Generates documentation fragments from source code. Extracts semantic pipeline stages (from
`SemanticAnalyzer.analyze()` via AST parsing) and CLI help output (from `datrix generate --help`) into
markdown files under `datrix/docs/generated/`. `-Check` verifies the fragments are up to date
(non-zero exit if stale).

Module: `datrix_scripts.dev.generate_doc_fragments`; POSIX twin `dev\generate-doc-fragments.sh`
(`--check`, `--dbg`, `--self-test`; the fragment positional): `bash dev/generate-doc-fragments.sh --check`.

## Imports and Parse Trees

### `find-imports.ps1`

The worklist before a move or rename: every place that imports names from given modules. It AST-parses
(multi-line safe) every `.py` under each `datrix-*` repository's `src/` and `tests/` trees and root
`*.py` files, the scripts tree and the Claude Code hooks (`datrix_scripts.import_sites`, shared with
`codemods\split-module.ps1`). It resolves relative imports inside `src/` packages and prints
`path:line` per site. The code index's `find_references` resolves symbols; this answers "which import
statements name this module path" and needs no index. Report only (exit 0). A file that does not parse is
printed as UNPARSEABLE and counted.

With `-Module` and `-Name` it prints `[from-import]` sites, plus `[attribute]` reads
(`plugin_mod.PluginError`) on a bound module; with `-Module` alone, every from-import, plus
`[import]`/`[module-import]` statements binding the module itself.

Module: `datrix_scripts.dev.find_imports`; POSIX twin `dev\find-imports.sh` (`--module`, `--name`,
`--dbg`, `--self-test`): `bash dev/find-imports.sh --module datrix_common.errors.plugin --name PluginError`.

### `probe-fixture.ps1`

Shows what the production front half makes of a fixture project before a test run depends on it. For each
`-ConfigProfile` (default `test`) it runs `datrix_testing.project.analyzed_project` on the project (parse,
`.dcfg` resolution, semantic analysis) and prints the error text of a failure, or each service with its
datasource, queue, serverless and integration blocks. It then writes a stamp,
`<workspace>\.tmp\fixture-probes\<sha1 of the project directory>.json`. The Claude Code hook
`guard-test-run-discipline.py` refuses a test run after an edit of a `tests\fixtures\[projects\]<name>\`
file when no stamp is newer than the edit, so a wrong `.dcfg` key or DSL shape is met here in seconds,
not in a suite run. Exit 0 every profile analyzed, 1 a profile failed, 2 usage error.

Module: `datrix_scripts.dev.probe_fixture`; POSIX twin `dev\probe-fixture.sh` (`--path`, `--config-profile`,
`--dbg`, `--self-test`): `bash dev/probe-fixture.sh --path <project dir>`.

### `who-imports.ps1`

Which runtime import chain first loads a module. It imports each `-Root` in a fresh interpreter with an
observer on `sys.meta_path`. At the first lookup of a `-Target` (or any submodule of a target package),
it prints the workspace frames that led there, function-level imports and entry-point loads included. The
observer resolves nothing itself. `scan\check-import-boundaries.ps1` reports *that* a forbidden edge
exists (statically); this shows *which chain* realizes it. A target that never loaded is listed as such.

Module: `datrix_scripts.dev.who_imports`; POSIX twin `dev\who-imports.sh` (`--root`, `--target`,
`--self-test`).

### `print-sexp.ps1`

The tree-sitter parse tree of Datrix source, as a corpus-style S-expression (two-space indent, closing
parentheses on the last child's line) ready to paste into a corpus test. It uses the built Datrix grammar
(`TreeSitterParser.parse_tree`); the native `tree-sitter` CLI cannot load that library on every host.
Named nodes only by default (`-All` adds anonymous nodes); MISSING nodes print as `(MISSING <type>)`.

Module: `datrix_scripts.dev.print_sexp`; POSIX twin `dev\print-sexp.sh` (`--path` or the path positional,
`--text`, `--all`, `--self-test`).

## Documentation Checks

### `check-docs.ps1`

Lints documentation for common drift patterns: deprecated CLI flags, fixed phase counts, CDX doc
naming/structure, missing capability status labels.

Module: `datrix_scripts.dev.check_docs`; POSIX twin `dev\check-docs.sh` (`--docs-dir`, `--check`,
`--detailed`, `--dbg`, `--llm-suggest`, `--self-test`, …): `bash dev/check-docs.sh --check deprecated-cli-flags`.

## Code Index

### `code-index.ps1`

Queries the code index: an SQLite index of every Python, Markdown, PowerShell, `.dtrx`, `.dcfg` and
TypeScript file git sees in the workspace repositories (tracked, plus untracked files no `.gitignore`
excludes, minus `scripts/config/code-index.json`'s `exclude`). Each format is read with its own parser
(`datrix_scripts.code_index.formats`):

- Markdown headings become `section`s, read with markdown-it, so headings inside code fences are skipped.
- PowerShell functions and script/function `parameter`s are read with PowerShell 7's parser (`pwsh` on `PATH`).
- `.dtrx` definitions get the language server's outline kinds (`service`, `entity`, `field`, `endpoint`, ...).
- `.dcfg` `config`s, `block`s, `profile`s, `template`s, `key`s and `setting`s come from the Datrix grammar.
- TypeScript classes, interfaces, types, enums, namespaces, functions, methods and fields come from tree-sitter.

References, imports and logic-map markers are read from Python only. A non-Python file's module name is
its path. It lives beside the checkout at `d:\datrix\.code-index\`. **Each development machine has its
own**, built from its own working tree, so nothing is synchronised between machines.

**Creating and updating.** Run `-Setup` once on each machine, and again whenever the server's script path
changes: it builds the index (about ten seconds) and writes the index's MCP server into
`d:\datrix\.mcp.json` with this machine's paths and the scripts `PYTHONPATH`, keeping any other servers
in the file. It then approves the server for this machine in `.claude\settings.local.json` (gitignored),
because current Claude Code builds ignore an approval in the checked-in `settings.json`. Last, it removes
the local-scope registrations older versions made. Those two files are the only ones `-Setup` writes
(here and in `local-llm.ps1 -Setup`, the same `datrix_scripts.dev.mcp_setup` writer); a file that is not
valid JSON is refused, never overwritten. Claude Code reads `.mcp.json` from the opened folder for every
installation and drive-letter spelling, so an extension update needs no re-run. Then restart Claude Code
(in VS Code: Developer: Reload Window). `claude mcp get datrix-code-index` may still say "Pending
approval"; a real session connects it regardless. There is nothing to schedule after that. Every query,
from this script or an agent's MCP tool call, first brings the index up to date with the working tree
(about 0.2 s when little changed), so edits, pulls and branch switches show up in the next query. Only
files whose content changed are parsed again.

The index also owns the logic map. Every refresh rewrites `d:\datrix\.logic-map\markers.db` whenever the
`@canonical`/`@pattern`/`@boundary`/`@invariant`/`@test-rule` markers in source changed.

Queries never leave the machine. `-Summarize` is the exception, and it only runs when asked for: it sends
each module's outline and source to a local model server (plain HTTP on the local network, like every
local-model script) and caches the summary per machine by content hash.

`-Symbol` takes a bare name, glob (`*Resolver`), `Class.method`, or dotted path; `-Kind` narrows to one
kind (`class`, `function`, `method`, `section`, `parameter`, `entity`, `setting`, ...; an unknown kind is
refused with the full list). `-References` resolves through imports (aliases, re-exports); methods match
every `.name` access. `-Outline` takes a path, unique suffix, or module name and prints definitions with
line ranges and signatures. `-Search` is ranked full-text over names, signatures, docstrings, summaries,
markers. `-Canonical` takes markers by topic path, topic segment, or words; `-IncludeTestRules` adds
`@test-rule`. `-Status` prints counts, summary coverage, files with syntax errors. `-Usage` compares index
tool calls against the greps, whole reads of large `.py` files and shell searches the index could have
answered, with estimated tokens.

**Usage log:** the non-blocking PostToolUse hook `record-search-usage.py` appends one line per
code-search call to `d:\datrix\.code-index\usage.jsonl` on each machine. It records the tool, the pattern
or path searched (never file content) and the size of the answer. A shell search counts when
`rg`/`grep`/`Select-String`/`findstr` starts a command or is piped from a file listing; piped from
anything else it is an output filter and is not logged. After an identifier grep or a whole read of a
large `.py` file the same hook points the agent at the index: at the MCP tool when the server is
registered for the directory the session started in, otherwise at the `code-index.ps1` command. The hook
finds its workspace from its own real path, so it logs to `d:\datrix\.code-index\` however it is started.

**Summaries stay current without `-Summarize`.** A module summary is keyed by the module's content hash,
so every edit leaves the module without one. When a query's refresh (the CLI's, or an MCP tool call's)
finds changed files, or the MCP server's first call finds modules still waiting, it starts a detached
`python -m datrix_scripts.dev.code_index --summarize --limit=0` run in the background and answers at
once; the run summarizes everything pending on the local model servers and exits. Only one summarize run
exists at a time: every run, this one or a manual `-Summarize`, holds
`d:\datrix\.code-index\summarize.lock` (a lock older than 4 hours is taken over), and a second run exits
at once. The background run's output is `d:\datrix\.code-index\summarize.log`. `-Status` shows the
coverage.

**Missing registration is announced.** A session whose start directory lacks the `datrix-code-index` or
`datrix-local-llm` server is told so at session start by `session-context.py`, per server, with its
`-Setup` command (and, for the index, the shell fallback). A server counts when registered in user scope,
in local scope for that exact directory, or in a `.mcp.json` there that this machine has approved
(`enabledMcpjsonServers` in `.claude\settings.local.json` or the project's `~/.claude.json` entry;
`disabledMcpjsonServers` wins). Without it a machine that never ran `-Setup` looks like one that did, and
every agent silently greps instead.

Module: `datrix_scripts.dev.code_index`; POSIX twin `dev\code-index.sh` (`--symbol`, `--references`,
`--outline`, `--search`, `--canonical`, `--status`, `--setup`, `--self-test`, …):
`bash dev/code-index.sh --symbol to_snake_case`. `-Setup` (`datrix_scripts.dev.mcp_setup`) registers the
server as the venv Python running `-m datrix_scripts.dev.code_index_mcp`.

**Agents:** the MCP server (`datrix_scripts.dev.code_index_mcp`, stdio, no socket) offers the same
queries as the tools `find_symbol`, `find_references`, `outline`, `search`, `find_canonical` and
`index_status`.

### `code-index-gate.ps1`

Behaviour checks for the code index (`common/lib/datrix_scripts/code_index/`) and its entry points
(`dev\code-index.ps1`, the MCP server `datrix_scripts.dev.code_index_mcp`, and the logic-map consumers).
Each check builds a real workspace of git repositories in a temporary directory and runs the real index
over it. The checks cover:

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

Module: `datrix_scripts.dev.code_index_gate`; POSIX twin `dev\code-index-gate.sh` (`--only`,
`--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] code-index PASSED|FAILED`
verdict line.

### `logic-map-report.ps1`

Refreshes the code index (which rewrites the logic map database if markers changed), then dumps the logic
map SQLite database to a readable Markdown report for human verification. Exit 1 also when the report
lists dangling `@see` references (section "Dangling @see References").

Module: `datrix_scripts.dev.logic_map_report`; POSIX twin `dev\logic-map-report.sh` (`--output` or the
output positional, `--self-test`).

## Local Models and the Knowledge Base

### `local-llm.ps1`

**Sets up, inspects and measures the local model servers that agents read through.** The Ollama servers
on the network's machines (the only model server they run; searched by
`common/lib/datrix_scripts/local_llm.py`) answer every local-model script, the stop-gate judge, and the
agents' MCP tools from `datrix_scripts.dev.local_llm_mcp`:

| Tool | What the agent gets |
|------|---------------------|
| `ask_files` | A question about up to 40 files (paths or globs) answered in a few lines citing `path:line`, so the agent does not read the text itself. Larger inputs are split into chunks: each chunk is answered separately and the answers are merged. |
| `digest_log` | The distinct failures in a test, generation or deploy log: one entry per cause, with its count, the first log line and the source `file:line` it names. A log too large to read whole is cut to the lines around error markers, or to its end when it has none. |
| `local_models` | Which servers answer, what they hold in memory, and recent usage. |

**What may be read:** files inside the framework repositories (`datrix` and every `datrix-*` git
repository at the workspace root) and `.test-output`. Anything else is refused: another repository at the
workspace root, `.tmp`, `reports`, `design`, `.git` internals. (`skill\skill-assist.ps1` is the one script
that sends design docs and findings files to a model, through the same customer-term filter; see
[../skill/README.md](../skill/README.md).) Paths are resolved before the check, so `..` cannot escape it.
An answer is a lead, not a finding. Every citation is checked against the files and lines that were
actually sent, and one that does not match is called out under the answer. The agent opens the cited
lines with a ranged Read before acting on them.

**The harness uses the models without an agent asking.** Three hooks (`claude-config/.claude/hooks/`)
call them on an agent's behalf; each is bounded, resident-models-only, and fails open (any failure leaves
the tool call exactly as it was):

| Hook | When | What the agent gets | Usage caller |
|------|------|---------------------|--------------|
| `digest-red-test-run.py` (PostToolUse) | a `test.ps1` / `test-single.ps1` run's console output reports a package that is not `[PASSED]` | A local model's list of the distinct failures in the run's `full.log` (up to 2 runs per call), with a pointer to the run's `failure-data.json`. A run whose folder holds `digest.txt` is skipped: `test.ps1` already wrote its failure digest there | `hook:red-test-digest` |
| `redirect-large-read.py` (PreToolUse on `Read`) | the **first** whole read (no `offset`/`limit`), by one agent, of a `.py` file of 14,000 bytes or more in a framework repo, or of a `.log` of 20,000 bytes or more under `.test-output`/`.test_results` | The read is refused with the file's code-index outline (definitions with line ranges, plus the module summary a local model wrote) or, for a log, the model's digest. Repeating the same Read goes through: the notice is shown once per file per agent. Ranged reads, small files, files outside the framework repos or the index, and any failure are never refused | `hook:large-read-digest` |
| `inject-task-orientation.py` (PostToolUse on `Read`) | an agent reads a task file (`.tasks/phase-NN/task-NN-TT-*.md`) that carries an `## Orientation` block | The block answered into the agent's context: `symbol` / `refs` / `outline` / `canonical` entries as exact code-index answers, `explain` entries as a local model's cited reading (marked a lead), and an entry that no longer resolves called out as a stale premise. Once per task per agent; a task with no block, or a ranged read of the middle of a task, gets nothing. Task format and the validator: [../tasks/README.md](../tasks/README.md), `validate-task.ps1` | `hook:task-orientation` |

Hooks reach the shared scripts package through `add_scripts_lib_to_path()` in `_hook_log.py`.
`code-index.ps1 -Usage` counts redirects as `read_redirect`, and those followed by the same agent reading
the whole file anyway as `read_redirect_repeat`; when most redirects repeat, the 14,000-byte threshold or
the once-per-file rule in `redirect-large-read.py` needs revisiting. The stop-gate judges
(`hook:stop-judge`, `hook:subagent-judge`) use the same models.

**Spreading and failover:** a request goes to an idle ready server. While every ready server is busy, the
next resident one is readied, so concurrent requests use every machine's resident model. The MCP tools
never wait for a model to load: they use resident models only.

**Residency:** because the hooks and MCP tools use resident models only, and a script loads an Ollama
model only when no resident one is left, a machine whose Ollama holds nothing in memory takes no work in
normal use (`-Status` shows it as `resident none; loadable …`). To make it share the work, keep a model
resident there: set `OLLAMA_KEEP_ALIVE=-1` on that machine and load the model once; a load request
carrying `"keep_alive": -1` holds it the same way without the setting, until Ollama restarts. The pool
never shortens a residency a model already has: it sends its own keep-alive (`--local-keep-alive`,
default 30 minutes) only when that outlasts the model's current one, and keeps an indefinite one
indefinite.

**Usage log:** every request from any caller (script, hook `hook:<gate>-judge`, MCP tool `mcp:<tool>`) is
one line in `d:\datrix\.local-llm\usage.jsonl` on the machine that sent it. Each line records the caller,
the server and model, the characters sent and received, the seconds taken and the outcome, never the
text. `DATRIX_LOCAL_LLM_USAGE_LOG` points it elsewhere; the gates use it so their loopback servers never
count as real use.

Actions: `-Setup` writes the MCP server `datrix-local-llm` into `d:\datrix\.mcp.json` (other servers
kept, scripts `PYTHONPATH` in its `env`), approves it for this machine in `.claude\settings.local.json`,
and removes older local-scope registrations — the same mechanism as `code-index.ps1 -Setup`
(`datrix_scripts.dev.mcp_setup`); restart Claude Code afterwards. `-Status` lists the servers that
answer, resident models, a line per machine holding no model indefinitely, and the last day's usage.
`-Usage` lists requests by caller and by server. `-Pin` loads, on each reachable machine, the first
installed model of the load preference and keeps it resident indefinitely, so the resident-only callers
(the red-run digest hook) find one; it prints per machine what was pinned or why not, and nothing pins
automatically. `-Unpin` unloads every indefinitely resident model.

Module: `datrix_scripts.dev.local_llm`; POSIX twin `dev\local-llm.sh` (`--setup`, `--status`, `--usage`,
`--pin`, `--unpin`, `--days`, `--self-test`): `bash dev/local-llm.sh --status`. `-Setup` registers the
server as the venv Python running `-m datrix_scripts.dev.local_llm_mcp`.

### `local-llm-gate.ps1`

Behaviour checks for the local-model reading tools: the reading layer
(`common/lib/datrix_scripts/local_reading.py`) and the MCP server built on it
(`datrix_scripts.dev.local_llm_mcp`). Each check builds a real workspace in a temporary directory (two
framework repositories, a customer-style repository beside them, `.tmp` and `.test-output`) and answers
through a real Ollama-shaped server on loopback (`common/lib/datrix_scripts/local_llm_loopback.py`) whose
answers depend on the prompt. It never contacts the network's model servers, and it records requests in a
temporary usage log, never the machine's own. The checks cover:

- scope: framework repositories and `.test-output` are read; another repository, `.tmp`, `..` escapes, `.git` internals and paths outside the workspace are refused; a glob reaching out of scope is refused whole; at most 40 files per call
- chunking: every chunk opens with its file's header and keeps original line numbers; a long file is split at line boundaries
- log reduction: a large log is cut to the lines around error markers, or to its end when it has none
- answering: one request for one chunk; one request per chunk plus a merge for more; a citation of an unsent file or line is called out (for a log, only citations of the log itself are checked)
- the MCP server: tool listing, an answer, an out-of-scope refusal, bad arguments, no model server reported as a tool error, the usage log entry under `mcp:<tool>`, and stdout carrying only protocol

Module: `datrix_scripts.dev.local_llm_gate`; POSIX twin `dev\local-llm-gate.sh` (`--only`,
`--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] local-llm PASSED|FAILED`
verdict line.

### `line-edit.ps1`

Sets up the `datrix-edit` MCP server (`datrix_scripts.dev.line_edit_mcp`, logic in
`common/lib/datrix_scripts/line_edits.py`). Its `read_lines` shows each line as `<number>:<hash>|<text>`
(same `file_path`/`offset`/`limit` as Read). Its `edit_lines` replaces lines
(`{file_path, start, end, hashes, text}`, `hashes` = the 2-character hash of every replaced line) or
inserts after a line (`{file_path, after, hash, text}`, `after` 0 = the top). One call carries up to 200
edits across files.

In a **Python file** a function, class or module/class-level variable is named instead of numbered
(`datrix_scripts.symbol_spans`). `read_symbol` takes `{file_path, symbols}` (dotted names such as
`Class.method`; a name defined twice is `name@<first line>`) and shows each symbol under a header with its
line range and **span hash**, every line numbered and hashed as in `read_lines`. Two more `edit_lines`
shapes use the span hash: `{file_path, symbol, span_hash, text}` replaces the whole symbol (`text` `''`
deletes it) and `{file_path, after_symbol, span_hash, text}` inserts directly below its last line, so
`text` starts with the blank line(s) the new code needs. A symbol's span runs from its first decorator, or
the comment lines directly above it, to its last line.

- **Symbol edits are line edits.** Each symbol edit is turned into the line replace or insert it stands for, so it shares the overlap check, the atomic write, the reply and the guards. A span hash that no longer matches refuses the whole call and shows the symbol now there.
- **Python only.** Another file type, a file that does not parse, or a lone carriage return inside a line is refused with a pointer to `read_lines`/`edit_lines`.
- **Old text is never re-sent.** An `Edit` re-sends its `old_string`, padded until unique, and every later response re-reads it. In one overnight run, old text made up 46% of all edit input.
- **Checked before written.** Line numbers refer to the files as they were before the call, and edits apply bottom-up. Every edit is checked before any file is written. One wrong hash refuses the whole call and shows the lines now there.
- **Ready for the next edit.** The reply gives each changed range's new numbers and hashes, so a follow-up edit needs no re-read.
- **Files are preserved.** Untouched lines keep their own endings, and the byte-order mark and a missing final newline are kept. Each file is written atomically.
- **Limits.** Only existing UTF-8 text files under the workspace, up to 4 MB, are read or edited. New files are still made with Write.
- **Guarded like Edit.** The `route-line-edits.py` hook hands each file's change, as an `Edit` payload, to every guard `settings.json` registers for Edit. The `datrix-edit` read tool counts as a Read for the mandatory-reads gate and the large-read redirect.
- **After an edit.** Keep editing a file with `edit_lines` once it has changed it: the built-in Edit refuses a file changed outside it until it is read again.

`-Setup` writes `datrix-edit` into `d:\datrix\.mcp.json` (other servers kept), approves it for this
machine in `.claude\settings.local.json`, and removes older local-scope registrations; restart Claude Code
afterwards (`datrix_scripts.dev.mcp_setup`, the writer behind `code-index.ps1 -Setup`). The entry starts
the server as `python -m datrix_scripts.dev.line_edit_mcp`, so a machine set up when the server was a
script path re-runs `-Setup`. `-SelfTest` checks that `-Setup` is required, that the server module it
registers resolves, and that the wrapper is the template rendered with the module's options; it registers
nothing.

Module: `datrix_scripts.dev.line_edit`; POSIX twin `dev\line-edit.sh` (`--setup`, `--self-test`).

### `line-edit-gate.ps1`

Behaviour checks for line-addressed editing, run on real files in a temporary workspace through
`datrix_scripts.line_edits` and the `datrix-edit` server. The checks cover:

- numbered, hashed reading
- hash-checked replaces, deletes and inserts (top, end, an empty file)
- Python symbols read and edited by name: dotted names, decorators and leading comments in the span, definitions inside `if`/`try` blocks, a name defined twice, replace, delete and insert-below, a stale span hash, non-Python and unparsable files, symbol and line edits in one call
- a whole call refused, with nothing written, when one hash is wrong
- line numbers that refer to the file before the call
- overlapping and misshapen edits refused
- kept CRLF, mixed endings, byte-order mark and missing final newline
- a reply that carries what a follow-up edit needs
- the workspace, NUL-byte and UTF-8 limits
- the span the edit guards are shown
- the MCP protocol, with stdout carrying only protocol

The hook side is checked by `.claude/hooks/test-route-line-edits.py`.

Module: `datrix_scripts.dev.line_edit_gate`; POSIX twin `dev\line-edit-gate.sh` (`--only`,
`--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] line-edit PASSED|FAILED`
verdict line.

### `ineedtoknow.ps1`

**Ask what you need to know, in your own words, instead of loading whole docs.** The knowledge base
answers from the project's own docs (architecture cheat sheet and knowledge packs, the decision log,
agent rules, execution contract, script quick-references, package architecture docs; the list is
`CURATED_PATTERNS` in `common/lib/datrix_scripts/knowledge/seed.py`), cut into chunks by heading, and
from answers learned earlier. A hit is a brief answer plus the file and line range to open. Wrapper over
the module `datrix_scripts.dev.ineedtoknow`; the logic is in `common/lib/datrix_scripts/knowledge/`.

**When the knowledge base holds no answer**, a local model server that already has a model in memory
(never waits for a load) reads the closest chunks of the docs (with their real line numbers) plus any
`-In` files, and writes a short cited answer. The answer is **stored only when grounded**: it cites at
least one `path:line`, every citation names a file and line the model was actually sent, and every quoted
snippet is in what it was sent. A failed answer is reported with the reason and the closest places to
read, and is never stored. With no model server available it says so and lists the same places. A stored
answer **expires when a file it cites changes** (content hash). `-NoLearn` never contacts a model;
`-Refresh` skips the lookup, reads the closest docs again and replaces the stored answer.

**Storage and two-machine sync.** The SQLite database is per machine,
`d:\datrix\.knowledge\knowledge.db` (`DATRIX_KNOWLEDGE_DB` overrides it); it is a cache and can always be
rebuilt. Every learned answer is also written as one markdown file to
`datrix\docs\knowledge\learned\<id>.md` (committed; the id is the hash of the question, so two machines
never conflict). Each invocation first brings the database up to date with the docs (re-cut by content
hash) and with those files: after a pull, a machine imports each learned file whose cited files hash the
same there. A file is never deleted by a sync; learning the same question again overwrites it, and
`-Prune` deletes the ones whose sources changed (a git change to commit). `-Status` prints the database
path, docs and chunks, learned answers, learned files and how many are stale here; `-Rebuild` drops the
database and rebuilds it from the docs and the committed learned files.

Module: `datrix_scripts.dev.ineedtoknow`; POSIX twin `dev\ineedtoknow.sh` (the question positional or
`--question`, `--in`, `--refresh`, `--no-learn`, `--status`, `--rebuild`, `--prune`, `--self-test`, …):
`bash dev/ineedtoknow.sh "which package owns the gateway route enumeration" --no-learn`. Exit 2 = no
answer (not in the knowledge base and no local model could add one).

### `ineedtoknow-gate.ps1`

Behaviour checks for `dev\ineedtoknow.ps1` (`common/lib/datrix_scripts/knowledge/`,
`datrix_scripts.dev.ineedtoknow`). Each check builds a real workspace in a temporary directory
(framework repositories plus a customer-style repository), uses real SQLite files, and answers through a
real Ollama-shaped server on loopback (`common/lib/datrix_scripts/local_llm_loopback.py`). It never
contacts the network's model servers and never touches the machine's own knowledge base. The checks
cover:

- chunking: a chunk's body equals the document's own lines `line_start`..`line_end`; a `#` line inside a code fence is not a heading; a long section splits into bounded chunks that keep every line
- sync: docs are added, updated by content hash and removed; a customer repository never enters the knowledge base
- lookup: a question is answered only by a chunk covering most of its significant words (camelCase identifiers match their words); unrelated and stopword-only questions find nothing
- the committed text copy: a learned file round-trips and a hand-edited id, a missing front matter, a bad source hash or an empty answer is refused; a second machine converges from the files alone, a rebuild restores them, and deleting a file drops the answer
- expiry: an answer whose cited file changed is not returned, not imported by another machine, never deleted by a sync, and deleted by `-Prune`
- gathering: the model is sent the closest chunks with their real line numbers and no customer text; an answer is stored only when grounded (no citation, a citation of an unsent file or line, quoted code that was not sent, and "nothing relevant" are each rejected and write nothing); no model server raises `LocalLlmUnavailable`

Module: `datrix_scripts.dev.ineedtoknow_gate`; POSIX twin `dev\ineedtoknow-gate.sh` (`--only`,
`--harness-self-test`, `--self-test`, `--dbg`). The run ends with the `[GATE] ineedtoknow PASSED|FAILED`
verdict line.

## Code Health

### `code-scan.ps1`

**On-demand code-health scan: one ranked digest instead of four scanners' raw output.** By default it
scans only the packages whose content changed since their last scan. It tracks this with the code
index's file hashes, in `d:\datrix\.code-index\scan-state.json`; the first run covers everything. It runs
on this machine and changes nothing but the report and the scan state. Every finding is written, by
section and then by package, to `d:\datrix\reports\code-scan\code-scan-<timestamp>.md`, headed by a
per-package count table. The console gets one progress line per stage, then one line with the totals and
the report's path, so a reader opens just the sections it needs.

| Section | Source | What the scan adds |
|---|---|---|
| Dead code: never used / used only by tests | two-pass Vulture (`common/lib/datrix_scripts/metrics/dead_code_report.py`) | Each finding is checked against the code index across the whole workspace, so a use in another package refutes it. It is dropped if a Jinja template, a Python string (a `getattr` name, a dotted resolver path, DAL generator text) or a `pyproject.toml` entry point names it. Unused imports are left to ruff. Classes and functions rank above fields. |
| Too complex | cyclomatic + cognitive (`common/lib/datrix_scripts/metrics/complexity.py`) | Merged, highest first |
| Duplicated blocks | Pylint R0801 (`common/lib/datrix_scripts/metrics/duplicate.py`) | Largest first |
| Docs drift | `datrix_scripts.dev.check_docs` checks over each package's `docs/` | — |

A package folder may be given in any form: relative, absolute, trailing slash, or a path inside it.
`-All` covers every Python package (about 4 minutes).

Module: `datrix_scripts.dev.code_scan`; POSIX twin `dev\code-scan.sh` (the packages positional or
`--package`, `--all`, `--min-confidence`, `--duplicate-min-lines`, `--self-test`):
`bash dev/code-scan.sh datrix-common`.

**Needs** `vulture`, `pylint`, `radon` and `cognitive_complexity` in the shared venv. `radon` (the
datrix-* packages' `[dev]` extras), `pylint` (`datrix-codegen-python`'s `[dev]` extra) and
`cognitive_complexity` (the `scripts` dependency group of `datrix/pyproject.toml`) are installed with the
venv: a missing one means the venv is broken, and the scan refuses with the repair
(`common\venv.ps1 -EnsurePackages`) instead of checking less. `vulture` is declared by no manifest;
install it with `D:\datrix\.venv\Scripts\python.exe -m pip install vulture`. A missing Vulture fails the
scan instead of reporting no dead code.

### `generate-test-rules.ps1`

Generates `@test-rule` conformance annotations for test functions using a local LLM (the `-Model` model,
on whichever local machine `common/lib/datrix_scripts/local_llm.py` finds serving it). Two phases:
default **propose** writes reviewable proposals to `.test-output/test-rules/<model>/<package>.json`
(+ `.md` preview) and touches no source; **-Apply** inserts the reviewed markers above the test
functions. After generation, a **topic-consolidation pass** merges near-duplicate topic slugs and
kebab-normalizes them (skip with `-NoConsolidate`). `tests/e2e` and `tests/integration` are **excluded by
default** (opt in with `-IncludeE2e` / `-IncludeIntegration`, or target via `-Path`). Resumable —
already-annotated and already-proposed functions are skipped. Output is per-model so different models
don't clobber. Markers feed the logic-map Rule Matrix; the existing test-rule topics that seed and anchor
consolidation are read from the code index, refreshed first (`code-index.ps1`).

`-Review` prints triage: suspicious dims, weak behaviors, over-grouped/single-target topics (no LLM, no
edits). With several `-Path` subtrees, run once per `-Path`: the same package's runs share one proposal
file and consolidate together, and `powershell -File` cannot pass `-Path` as an array.

Module: `datrix_scripts.dev.generate_test_rules`; POSIX twin `dev\generate-test-rules.sh` (the packages
positional or `--projects`, `--all`, `--apply`, `--review`, `--model`, `--path`, `--no-seed`,
`--self-test`, …): `bash dev/generate-test-rules.sh datrix-codegen-python --review`.
