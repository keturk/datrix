# Quick Reference — Development Scripts

Generation, the code index, the local model servers and the knowledge base agents read through,
documentation checks and code-health digests, with the gates that hold each tool. Generation
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

`-All`, `-Domains` and `-TestSet` are Jon's: `validate-script-invocation.py` refuses them from an agent tool call.

**Parameters:** `-Source` (positional 0), `-Output` (positional 1), `-All`, `-Domains`, `-Language`/`-L` (any registered `datrix.languages` target, **mandatory**, the real generation target — also selects the output-path language segment), `-Runtime`/`-R` (docker-compose\|azure-container-apps\|azure-app-service\|ecs-fargate\|app-runner, output path only), `-ConfigProfile` (config profile that also selects the provider segment read from `config/system.dcfg`, e.g. test\|development\|production; default: test), `-OutputBase` (default: .generated), `-TestSet` (default: all), `-VerboseOutput`, `-Dbg`

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

## Code Index

### `dev\code-index.ps1`

Queries the code index: an SQLite index of every Python file git sees in the workspace repositories (tracked, plus untracked files no `.gitignore` excludes, minus `scripts/config/code-index.json`'s `exclude`). It lives beside the checkout at `d:\datrix\.code-index\`. **Each development machine has its own**, built from its own working tree, so nothing is synchronised between machines.

**Creating and updating.** Run `-Setup` once on each machine, and again whenever the server's script path changes: it builds the index (about ten seconds) and writes the index's MCP server into `d:\datrix\.mcp.json` with this machine's paths and the scripts `PYTHONPATH`, keeping any other servers in the file. It then approves the server for this machine in `.claude\settings.local.json` (gitignored), because current Claude Code builds ignore an approval in the checked-in `settings.json`. Last, it removes the local-scope registrations older versions made. Claude Code reads `.mcp.json` from the opened folder for every installation and drive-letter spelling, so an extension update needs no re-run. Then restart Claude Code (in VS Code: Developer: Reload Window). `claude mcp get datrix-code-index` may still say "Pending approval"; a real session connects it regardless. There is nothing to schedule after that. Every query, from this script or an agent's MCP tool call, first brings the index up to date with the working tree (about 0.2 s when little changed), so edits, pulls and branch switches show up in the next query. Only files whose content changed are parsed again.

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

**Usage log:** the non-blocking PostToolUse hook `record-search-usage.py` appends one line per code-search call to `d:\datrix\.code-index\usage.jsonl` on each machine. It records the tool, the pattern or path searched (never file content) and the size of the answer. A shell search counts when `rg`/`grep`/`Select-String`/`findstr` starts a command or is piped from a file listing; piped from anything else it is an output filter and is not logged. After an identifier grep or a whole read of a large `.py` file the same hook points the agent at the index: at the MCP tool when the server is registered for the directory the session started in, otherwise at the `code-index.ps1` command. The hook finds its workspace from its own real path, so it logs to `d:\datrix\.code-index\` however it is started.

**Summaries stay current without `-Summarize`.** A module summary is keyed by the module's content hash, so every edit leaves the module without one. When a query's refresh (the CLI's, or an MCP tool call's) finds changed files, or the MCP server's first call finds modules still waiting, it starts a detached `code_index_cli.py summarize --limit 0` run in the background and answers at once; the run summarizes everything pending on the local model servers and exits. Only one summarize run exists at a time: every run, this one or a manual `-Summarize`, holds `d:\datrix\.code-index\summarize.lock` (a lock older than 4 hours is taken over), and a second run exits at once. The background run's output is `d:\datrix\.code-index\summarize.log`. `-Status` shows the coverage.

**Missing registration is announced.** A session whose start directory lacks the `datrix-code-index` or `datrix-local-llm` server is told so at session start by `session-context.py`, per server, with its `-Setup` command (and, for the index, the shell fallback). A server counts when registered in user scope, in local scope for that exact directory, or in a `.mcp.json` there that this machine has approved (`enabledMcpjsonServers` in `.claude\settings.local.json` or the project's `~/.claude.json` entry; `disabledMcpjsonServers` wins). Without it a machine that never ran `-Setup` looks like one that did, and every agent silently greps instead.

**Parameters:** exactly one action: `-Symbol`, `-References`, `-Outline`, `-Search`, `-Canonical`, `-Status`, `-Refresh`, `-Usage`, `-Summarize`, `-Setup`. Modifiers: `-Kind` (with `-Symbol`), `-IncludeTestRules` (with `-Canonical`), `-Days` (with `-Usage`; default 7, 0 = all), `-Limit` (results, files listed, or modules summarized), `-Workers` (default 4), `-LocalMachines`, `-LlmModel` and `-LlmTimeout` (default 300; all three with `-Summarize`).

**Exit codes:** 0 answered; 1 the query or index could not be answered as asked; 2 `-Summarize` found no local model server.

**Agents:** the MCP server (`dev/lib/code_index_mcp.py`, stdio, no socket) offers the same queries as the tools `find_symbol`, `find_references`, `outline`, `search`, `find_canonical` and `index_status`.

### `dev\code-index-gate.ps1`

Behaviour checks for the code index (`common/lib/datrix_scripts/code_index/`) and its entry points (`dev\code-index.ps1`, the MCP server `dev/lib/code_index_mcp.py`, and the logic-map consumers). Each check builds a real workspace of git repositories in a temporary directory and runs the real index over it. The checks cover:

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

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

### `dev\logic-map-report.ps1`

Refreshes the code index (which rewrites the logic map database if markers changed), then dumps the logic map SQLite database to a readable Markdown report for human verification.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\dev\logic-map-report.ps1` | Write logic-map-report.md to current dir |
| **Custom output** | `.\dev\logic-map-report.ps1 -Output docs\logic-map.md` | Custom output path |

**Parameters:** `-Output` (positional 0)

**Exit codes:** 0 = report written and every `@see` names a declared topic; 1 = the index could not be refreshed, or the report lists dangling `@see` references (section "Dangling @see References").

---

## Local Models and the Knowledge Base

### `dev\local-llm.ps1`

**Sets up, inspects and measures the local model servers that agents read through.** The model servers on the network (Ollama, vLLM, llama-server, searched by `common/lib/datrix_scripts/local_llm.py`) answer every local-model script, the stop-gate judge, and the agents' MCP tools from `dev/lib/local_llm_mcp.py`:

| Tool | What the agent gets |
|------|---------------------|
| `ask_files` | A question about up to 40 files (paths or globs) answered in a few lines citing `path:line`, so the agent does not read the text itself. Larger inputs are split into chunks: each chunk is answered separately and the answers are merged. |
| `digest_log` | The distinct failures in a test, generation or deploy log: one entry per cause, with its count, the first log line and the source `file:line` it names. A log too large to read whole is cut to the lines around error markers, or to its end when it has none. |
| `local_models` | Which servers answer, what they hold in memory, and recent usage. |

**What may be read:** files inside the framework repositories (`datrix` and every `datrix-*` git repository at the workspace root) and `.test-output`. Anything else is refused: another repository at the workspace root, `.tmp`, `reports`, `design`, `.git` internals. (`skill\skill-assist.ps1` is the one script that sends design docs and findings files to a model, through the same customer-term filter; see `skill/quick-reference.md`.) Paths are resolved before the check, so `..` cannot escape it. An answer is a lead, not a finding. Every citation is checked against the files and lines that were actually sent, and one that does not match is called out under the answer. The agent opens the cited lines with a ranged Read before acting on them.

**The harness uses the models without an agent asking.** Three hooks (`claude-config/.claude/hooks/`) call them on an agent's behalf; each is bounded, resident-models-only, and fails open (any failure leaves the tool call exactly as it was):

| Hook | When | What the agent gets | Usage caller |
|------|------|---------------------|--------------|
| `digest-red-test-run.py` (PostToolUse) | a `test.ps1` / `test-single.ps1` run's console output reports a package that is not `[PASSED]` | A local model's list of the distinct failures in the run's `full.log` (up to 2 runs per call), with a pointer to the run's `failure-data.json`. A run whose folder holds `digest.txt` is skipped: `test.ps1` already printed its failure digest in the same output | `hook:red-test-digest` |
| `redirect-large-read.py` (PreToolUse on `Read`) | the **first** whole read (no `offset`/`limit`), by one agent, of a `.py` file of 14,000 bytes or more in a framework repo, or of a `.log` of 20,000 bytes or more under `.test-output`/`.test_results` | The read is refused with the file's code-index outline (definitions with line ranges, plus the module summary a local model wrote) or, for a log, the model's digest. Repeating the same Read goes through: the notice is shown once per file per agent. Ranged reads, small files, files outside the framework repos or the index, and any failure are never refused | `hook:large-read-digest` |
| `inject-task-orientation.py` (PostToolUse on `Read`) | an agent reads a task file (`.tasks/phase-NN/task-NN-TT-*.md`) that carries an `## Orientation` block | The block answered into the agent's context: `symbol` / `refs` / `outline` / `canonical` entries as exact code-index answers, `explain` entries as a local model's cited reading (marked a lead), and an entry that no longer resolves called out as a stale premise. Once per task per agent; a task with no block, or a ranged read of the middle of a task, gets nothing. Task format and the validator: `tasks/quick-reference.md`, `validate-task.ps1` | `hook:task-orientation` |

Hooks reach the shared scripts package through `add_scripts_lib_to_path()` in `_hook_log.py`. `code-index.ps1 -Usage` counts redirects as `read_redirect`. The stop-gate judges (`hook:stop-judge`, `hook:subagent-judge`) use the same models.

**Spreading and failover:** a request goes to an idle ready server. While every ready server is busy, the next resident one is readied, so concurrent requests use every machine's resident model. The MCP tools never wait for a model to load: they use resident models only.

**Usage log:** every request from any caller (script, hook `hook:<gate>-judge`, MCP tool `mcp:<tool>`) is one line in `d:\datrix\.local-llm\usage.jsonl` on the machine that sent it. Each line records the caller, the server and model, the characters sent and received, the seconds taken and the outcome, never the text. `DATRIX_LOCAL_LLM_USAGE_LOG` points it elsewhere; the gates use it so their loopback servers never count as real use.

| Mode | Command | Description |
|------|---------|-------------|
| **Set up a machine** | `.\dev\local-llm.ps1 -Setup` | Write the MCP server `datrix-local-llm` into `d:\datrix\.mcp.json` (other servers kept, scripts `PYTHONPATH` in its `env`), approve it for this machine in `.claude\settings.local.json`, remove older local-scope registrations; restart Claude Code afterwards. Same mechanism as `code-index.ps1 -Setup` (`Install-DatrixProjectMcpServer`) |
| **Status** | `.\dev\local-llm.ps1 -Status` | Servers that answer, resident models, and the last day's usage |
| **Usage** | `.\dev\local-llm.ps1 -Usage -Days 7` | Requests by caller and by server (`-Days 0` = everything logged) |

**Parameters:** exactly one action: `-Setup`, `-Status`, `-Usage`. Modifier: `-Days` (with `-Status`, default 1; with `-Usage`, default 7; 0 = all).

**Exit codes:** 0 done; 1 the request could not be carried out.

### `dev\local-llm-gate.ps1`

Behaviour checks for the local-model reading tools: the reading layer (`common/lib/datrix_scripts/local_reading.py`) and the MCP server built on it (`dev/lib/local_llm_mcp.py`). Each check builds a real workspace in a temporary directory (two framework repositories, a customer-style repository beside them, `.tmp` and `.test-output`) and answers through a real OpenAI-compatible server on loopback whose answers depend on the prompt. It never contacts the network's model servers, and it records requests in a temporary usage log, never the machine's own. The checks cover:

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

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

### `dev\ineedtoknow.ps1`

**Ask what you need to know, in your own words, instead of loading whole docs.** The knowledge base answers from the project's own docs (architecture cheat sheet and knowledge packs, the decision log, agent rules, execution contract, script quick-references, package architecture docs; the list is `CURATED_PATTERNS` in `common/lib/datrix_scripts/knowledge/seed.py`), cut into chunks by heading, and from answers learned earlier. A hit is a brief answer plus the file and line range to open. Wrapper over `dev/lib/ineedtoknow_cli.py`; the logic is in `common/lib/datrix_scripts/knowledge/`.

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

**Parameters:** exactly one of: a question (positional or `-Question`), `-Status`, `-Rebuild`, `-Prune`. Modifiers: `-In`, `-Refresh`, `-NoLearn`, `-Limit` (answers shown, default 3), and the shared local-model flags `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (seconds, default 120).

**Exit codes:** 0 answered; 1 the request could not be carried out (the message says why); 2 no answer (not in the knowledge base and no local model could add one). An answer is a lead, not a finding: open the cited lines before acting on it.

### `dev\ineedtoknow-gate.ps1`

Behaviour checks for `dev\ineedtoknow.ps1` (`common/lib/datrix_scripts/knowledge/`, `dev/lib/ineedtoknow_cli.py`). Each check builds a real workspace in a temporary directory (framework repositories plus a customer-style repository), uses real SQLite files, and answers through a real OpenAI-compatible server on loopback. It never contacts the network's model servers and never touches the machine's own knowledge base. The checks cover:

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

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

---

## Code Health

### `dev\code-scan.ps1`

**On-demand code-health scan: one ranked digest instead of four scanners' raw output.** By default it scans only the packages whose content changed since their last scan. It tracks this with the code index's file hashes, in `d:\datrix\.code-index\scan-state.json`; the first run covers everything. It runs on this machine and changes nothing but the report and the scan state. Every finding is written, by section and then by package, to `d:\datrix\reports\code-scan\code-scan-<timestamp>.md`, headed by a per-package count table. The console gets one progress line per stage, then one line with the totals and the report's path, so a reader opens just the sections it needs.

| Section | Source | What the scan adds |
|---|---|---|
| Dead code: never used / used only by tests | two-pass Vulture (`common/lib/datrix_scripts/dead_code_report.py`) | Each finding is checked against the code index across the whole workspace, so a use in another package refutes it. It is dropped if a Jinja template, a Python string (a `getattr` name, a dotted resolver path, genDSL text) or a `pyproject.toml` entry point names it. Unused imports are left to ruff. Classes and functions rank above fields. |
| Too complex | cyclomatic + cognitive (`common/lib/datrix_scripts/complexity.py`) | Merged, highest first |
| Duplicated blocks | Pylint R0801 (`common/lib/datrix_scripts/duplicate.py`) | Largest first |
| Docs drift | `dev/lib/check_docs.py` checks over each package's `docs/` | — |

| Mode | Command | Description |
|------|---------|-------------|
| **Changed packages** | `.\dev\code-scan.ps1` | Packages changed since their last scan |
| **Named packages** | `.\dev\code-scan.ps1 datrix-common datrix-cli` | These, changed or not |
| **By folder** | `.\datrix\scripts\dev\code-scan.ps1 .\datrix-cli\` | A package folder in any form: relative, absolute, trailing slash, or a path inside it |
| **Everything** | `.\dev\code-scan.ps1 -All` | Every Python package (about 4 minutes) |

**Parameters:** `-Package` (positional; names or folders), `-All`, `-MinConfidence` (Vulture, default 60), `-DuplicateMinLines` (default 6)

**Exit codes:** 0 = digest written, or nothing changed since the last scan; 1 = the scan could not run (a missing tool such as Vulture, an unknown package, an unreadable scan state).

**Needs** `vulture`, `pylint`, `radon` and `cognitive_complexity` in the shared venv. None is declared by any manifest, so install any that are missing with `D:\datrix\.venv\Scripts\python.exe -m pip install <name>`. A missing Vulture fails the scan instead of reporting no dead code.

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

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Apply`, `-Review` (triage existing proposals; no LLM/edits), `-Model` (default: exaone-deep:32b), `-LocalMachines` (machines to search, in preference order; default: the list in `common/lib/datrix_scripts/local_llm.py`), `-Parallel` (default: 4), `-Limit` (default: 0 = no limit), `-Path` (file/dir filter, repeatable; also scopes `-Apply`/`-Review`), `-NoSeed` (don't seed topic vocabulary from existing markers), `-NoConsolidate` (skip topic-merge pass), `-IncludeE2e`, `-IncludeIntegration` (e2e/integration excluded by default), `-Dbg`
