# Quick Reference — Visualization & Documentation Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `visualize\all-reports.ps1`

Runs all visualization and documentation scripts for a project: diagrams, schema snapshot, OpenAPI/AsyncAPI specs, and status report. All output is written next to the `.dtrx` source files (language-agnostic). Each step runs independently — a failure in one does not block subsequent steps.

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\all-reports.ps1 <source.dtrx>` | All reports for one project |
| **All projects** | `.\visualize\all-reports.ps1 -All` | All reports for all projects |
| **Foundation only** | `.\visualize\all-reports.ps1 -TestSet foundation` | Foundation examples only |
| **Domains only** | `.\visualize\all-reports.ps1 -Domains` | Domain examples only |
| **Custom test set** | `.\visualize\all-reports.ps1 -TestSet features-core` | Named test set |
| **Debug** | `.\visualize\all-reports.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Profile` (config profile, default: test), `-Dbg`

---

## `visualize\visualize.ps1`

Generates Mermaid diagrams from `.dtrx` source files. Produces ERD, service map, event flow, API catalog, CQRS flow, inheritance tree, infrastructure topology, and system context diagrams. Output is written next to the `.dtrx` source (e.g., `examples/.../docs/diagrams/`).

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

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Type` (erd\|service-map\|event-flow\|api-catalog\|cqrs-flow\|inheritance\|infrastructure\|system-context\|all, default: all), `-Service`, `-Format` (md\|mmd, default: md), `-Profile` (config profile, default: test), `-Dbg`

---

## `visualize\schema-diff.ps1`

Compares two `.dtrx` files and reports structural changes (breaking vs non-breaking).

| Mode | Command | Description |
|------|---------|-------------|
| **Markdown diff** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx` | Print Markdown report to stdout |
| **JSON diff** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Format json` | JSON output |
| **To file** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Output changes.md` | Write to file |
| **Debug** | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Dbg` | Debug logging |

**Parameters:** `-Before` (positional 0, required), `-After` (positional 1, required), `-Format` (markdown\|json, default: markdown), `-Output`, `-Dbg`

---

## `visualize\schema-snapshot.ps1`

Saves `.dtrx` Application as a JSON snapshot for future diffs. Output is written next to the `.dtrx` source (e.g., `examples/.../docs/snapshots/`).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\schema-snapshot.ps1 <source.dtrx>` | Save to source dir docs/snapshots/ |
| **Explicit output** | `.\visualize\schema-snapshot.ps1 <source.dtrx> -Output snap.json` | Custom output path |
| **All projects** | `.\visualize\schema-snapshot.ps1 -All` | Batch: all test-projects.json |
| **Foundation only** | `.\visualize\schema-snapshot.ps1 -TestSet foundation` | Batch: foundation examples |
| **Domains only** | `.\visualize\schema-snapshot.ps1 -Domains` | Batch: domain examples |
| **Debug** | `.\visualize\schema-snapshot.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Output`, `-Dbg`

---

## `visualize\openapi-gen.ps1`

Generates OpenAPI 3.1 YAML per REST API and AsyncAPI 3.0 YAML per PubSub block. Output is written next to the `.dtrx` source (e.g., `examples/.../docs/openapi/`).

| Mode | Command | Description |
|------|---------|-------------|
| **Single project** | `.\visualize\openapi-gen.ps1 <source.dtrx>` | Generate all spec types |
| **OpenAPI only** | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type openapi` | Only OpenAPI specs |
| **AsyncAPI only** | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type asyncapi` | Only AsyncAPI specs |
| **All projects** | `.\visualize\openapi-gen.ps1 -All` | Batch: all test-projects.json |
| **Foundation only** | `.\visualize\openapi-gen.ps1 -TestSet foundation` | Batch: foundation examples |
| **Domains only** | `.\visualize\openapi-gen.ps1 -Domains` | Batch: domain examples |
| **Debug** | `.\visualize\openapi-gen.ps1 -All -Dbg` | Debug logging |

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Type` (openapi\|asyncapi\|all, default: all), `-Dbg`

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

**Parameters:** `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default: all), `-Dbg`
