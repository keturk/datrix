# Quick Reference — Visualization & Documentation Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`
>
> **Modules:** every wrapper here is rendered from `common/templates/entrypoint.ps1`; its behaviour is the `datrix_scripts.visualize.*` module (in `common/lib/`) named under it, run in the shared venv. Each has a POSIX twin `visualize/<name>.sh` taking the module's own flags, each parameter as `--kebab-name` (`bash visualize/visualize.sh --source examples/01-foundation/system.dtrx --type erd`; `-All` is `--all`, `-TestSet` is `--test-set`). `-SelfTest` runs the module's self-test (over a planted copy of an example, including the wrapper seam) and nothing else. Options are spelled in full: an abbreviation is a usage error (exit 2). The batch modes read `datrix/scripts/config/test-projects.json`; an empty or unreadable test set is an `ERROR:` on stderr, exit 1.

---

## `visualize\all-reports.ps1`

Runs the diagram, OpenAPI/AsyncAPI and documentation-status steps for a project (`visualize`, `openapi-gen`, `status-docs`), each as its own module run with the same selection. All output is written next to the `.dtrx` source files (language-agnostic). Each step runs independently — a failure in one does not block subsequent steps. With no selection it prints its usage and exits 1.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\all-reports.ps1 <source.dtrx>` | All reports for one project |
| **All projects** | `.\visualize\all-reports.ps1 -All` | All reports for all projects |
| **Foundation only** | `.\visualize\all-reports.ps1 -TestSet foundation` | Foundation examples only |
| **Domains only** | `.\visualize\all-reports.ps1 -Domains` | Domain examples only |
| **Custom test set** | `.\visualize\all-reports.ps1 -TestSet features-core` | Named test set |
| **Debug** | `.\visualize\all-reports.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Profile` (config profile, default: test), `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.visualize.all_reports`; POSIX twin `visualize/all-reports.sh`.

---

## `visualize\visualize.ps1`

Generates Mermaid diagrams from `.dtrx` source files. Produces ERD, service map, event flow, API catalog, CQRS flow, inheritance tree, infrastructure topology, and system context diagrams. The application is loaded exactly as generation loads it (config resolution under `-Profile`, then semantic analysis with infrastructure configs resolved before the tree seals). Output is written next to the `.dtrx` source (e.g., `examples/.../docs/diagrams/`); the script clears only the `docs/diagrams` tree it writes, never `docs/openapi` or `docs/asyncapi`.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\visualize.ps1 <source.dtrx>` | All diagram types, Markdown output |
| **Single + type** | `.\visualize\visualize.ps1 <source.dtrx> -Type erd` | Single diagram type |
| **Single + service** | `.\visualize\visualize.ps1 <source.dtrx> -Type erd -Service "ns.SvcName"` | Scoped to one service |
| **Raw Mermaid** | `.\visualize\visualize.ps1 <source.dtrx> -Format mmd` | Output .mmd files instead of .md |
| **All projects** | `.\visualize\visualize.ps1 -All` | Batch: all test-projects.json |
| **Foundation only** | `.\visualize\visualize.ps1 -TestSet foundation` | Batch: foundation examples |
| **Domains only** | `.\visualize\visualize.ps1 -Domains` | Batch: domain examples |
| **Custom test set** | `.\visualize\visualize.ps1 -TestSet features-core` | Named test set |
| **Non-test profile** | `.\visualize\visualize.ps1 <source.dtrx> -Profile production` | Use non-default config profile |
| **Debug** | `.\visualize\visualize.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Type` (erd\|service-map\|event-flow\|api-catalog\|cqrs-flow\|inheritance\|infrastructure\|system-context\|all, default: all), `-Service`, `-Format` (md\|mmd, default: md), `-Profile` (config profile, default: test), `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.visualize.visualize`; POSIX twin `visualize/visualize.sh`.

---

## `visualize\schema-diff.ps1`

Compares two `.dtrx` files and reports structural changes (breaking vs non-breaking). Each side is loaded exactly as generation loads it (profile `test`); a `.json` snapshot is refused (pass the `.dtrx` it was taken from).

| Mode | Command | Description |
|------|---------|-------------|
| **Markdown diff** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx` | Print Markdown report to stdout |
| **JSON diff** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Format json` | JSON output |
| **To file** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Output changes.md` | Write to file |
| **Debug** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Dbg` | Debug logging |

**Parameters:** `-Before` (positional 0, required), `-After` (positional 1, required), `-Format` (markdown\|json, default: markdown), `-Output`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.visualize.schema_diff`; POSIX twin `visualize/schema-diff.sh` (`--before`, `--after`, `--format`, `--output`, `--dbg`, `--self-test`).

---

## `visualize\schema-snapshot.ps1`

Saves `.dtrx` Application as a JSON snapshot for future diffs. The application is loaded exactly as generation loads it (profile `test`). Output is written next to the `.dtrx` source (e.g., `examples/.../docs/snapshots/`).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\schema-snapshot.ps1 <source.dtrx>` | Save to source dir docs/snapshots/ |
| **Explicit output** | `.\visualize\schema-snapshot.ps1 <source.dtrx> -Output snap.json` | Custom output path |
| **All projects** | `.\visualize\schema-snapshot.ps1 -All` | Batch: all test-projects.json |
| **Foundation only** | `.\visualize\schema-snapshot.ps1 -TestSet foundation` | Batch: foundation examples |
| **Domains only** | `.\visualize\schema-snapshot.ps1 -Domains` | Batch: domain examples |
| **Debug** | `.\visualize\schema-snapshot.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Output`, `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.visualize.schema_snapshot`; POSIX twin `visualize/schema-snapshot.sh`.

---

## `visualize\openapi-gen.ps1`

Generates one OpenAPI 3.1 YAML per service — every `rest_api` block of the service in one document, so a multi-file service keeps every block's paths — and one AsyncAPI 3.0 YAML per service covering every pubsub block. Two blocks of one service declaring the same path and method (or the same topic) fail the run rather than overwrite each other. The application is loaded exactly as generation loads it (config resolution under `-Profile`, then semantic analysis with infrastructure configs resolved before the tree seals). Output is written next to the `.dtrx` source (e.g., `examples/.../docs/openapi/`); the script clears only `docs/openapi` and `docs/asyncapi` for the spec types it writes.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\openapi-gen.ps1 <source.dtrx>` | Generate all spec types |
| **OpenAPI only** | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type openapi` | Only OpenAPI specs |
| **AsyncAPI only** | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type asyncapi` | Only AsyncAPI specs |
| **All projects** | `.\visualize\openapi-gen.ps1 -All` | Batch: all test-projects.json |
| **Foundation only** | `.\visualize\openapi-gen.ps1 -TestSet foundation` | Batch: foundation examples |
| **Domains only** | `.\visualize\openapi-gen.ps1 -Domains` | Batch: domain examples |
| **Non-test profile** | `.\visualize\openapi-gen.ps1 <source.dtrx> -Profile staging` | Use non-default config profile |
| **Debug** | `.\visualize\openapi-gen.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Type` (openapi\|asyncapi\|all, default: all), `-Profile` (config profile, default: test), `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.visualize.openapi_gen`; POSIX twin `visualize/openapi-gen.sh`.

---

## `visualize\status-docs.ps1`

Reports documentation status for Datrix projects (diagrams, OpenAPI, AsyncAPI, snapshots). Scans project source directories for docs artifacts.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\status-docs.ps1 <source.dtrx>` | Status for one project |
| **All projects** | `.\visualize\status-docs.ps1 -All` | All test-projects.json |
| **Foundation only** | `.\visualize\status-docs.ps1 -TestSet foundation` | Foundation examples only |
| **Domains only** | `.\visualize\status-docs.ps1 -Domains` | Domain examples only |
| **Debug** | `.\visualize\status-docs.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Dbg`, `-SelfTest`

**Module:** `datrix_scripts.visualize.status_docs`; POSIX twin `visualize/status-docs.sh`.
