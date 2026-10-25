# Quick Reference — Visualization & Documentation Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each script does and how it is built: [README.md](README.md).

Batch selection (shared by the scripts that take it): `-All` (every entry of `config/test-projects.json`), `-TestSet <name>` (default `all`; e.g. `foundation`, `features-core`), `-Domains`. Output lands next to the `.dtrx` source.

## `visualize\all-reports.ps1`

Diagrams, OpenAPI/AsyncAPI and docs status for a project (runs `visualize`, `openapi-gen`, `status-docs`). No selection prints usage and exits 1.

| Form | Command |
|------|---------|
| One project | `.\visualize\all-reports.ps1 <source.dtrx>` |
| All | `.\visualize\all-reports.ps1 -All` |
| Test set | `.\visualize\all-reports.ps1 -TestSet foundation` |
| Domains | `.\visualize\all-reports.ps1 -Domains` |

Parameters: `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default all), `-Profile` (default test), `-Dbg`, `-SelfTest`

## `visualize\visualize.ps1`

Mermaid diagrams from `.dtrx` (ERD, service map, event flow, API catalog, CQRS flow, inheritance, infrastructure, system context).

| Form | Command |
|------|---------|
| One project, all types | `.\visualize\visualize.ps1 <source.dtrx>` |
| One type | `.\visualize\visualize.ps1 <source.dtrx> -Type erd` |
| One service | `.\visualize\visualize.ps1 <source.dtrx> -Type erd -Service "ns.SvcName"` |
| Raw Mermaid | `.\visualize\visualize.ps1 <source.dtrx> -Format mmd` |
| Batch | `.\visualize\visualize.ps1 -All` / `-TestSet foundation` / `-Domains` |
| Other profile | `.\visualize\visualize.ps1 <source.dtrx> -Profile production` |

Parameters: `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default all), `-Type` (erd\|service-map\|event-flow\|api-catalog\|cqrs-flow\|inheritance\|infrastructure\|system-context\|all, default all), `-Service`, `-Format` (md\|mmd, default md), `-Profile` (default test), `-Dbg`, `-SelfTest`

## `visualize\schema-diff.ps1`

Structural diff of two `.dtrx` files (breaking vs non-breaking).

| Form | Command |
|------|---------|
| Markdown to stdout | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx` |
| JSON | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Format json` |
| To a file | `.\visualize\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Output changes.md` |

Parameters: `-Before` (positional 0, required), `-After` (positional 1, required), `-Format` (markdown\|json, default markdown), `-Output`, `-Dbg`, `-SelfTest`

## `visualize\schema-snapshot.ps1`

Save the `.dtrx` Application as a JSON snapshot for later diffs.

| Form | Command |
|------|---------|
| One project | `.\visualize\schema-snapshot.ps1 <source.dtrx>` |
| Explicit output | `.\visualize\schema-snapshot.ps1 <source.dtrx> -Output snap.json` |
| Batch | `.\visualize\schema-snapshot.ps1 -All` / `-TestSet foundation` / `-Domains` |

Parameters: `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default all), `-Output`, `-Dbg`, `-SelfTest`

## `visualize\openapi-gen.ps1`

One OpenAPI 3.1 YAML and one AsyncAPI 3.0 YAML per service.

| Form | Command |
|------|---------|
| One project | `.\visualize\openapi-gen.ps1 <source.dtrx>` |
| OpenAPI only | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type openapi` |
| AsyncAPI only | `.\visualize\openapi-gen.ps1 <source.dtrx> -Type asyncapi` |
| Batch | `.\visualize\openapi-gen.ps1 -All` / `-TestSet foundation` / `-Domains` |
| Other profile | `.\visualize\openapi-gen.ps1 <source.dtrx> -Profile staging` |

Parameters: `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default all), `-Type` (openapi\|asyncapi\|all, default all), `-Profile` (default test), `-Dbg`, `-SelfTest`

## `visualize\status-docs.ps1`

Report which docs artifacts (diagrams, OpenAPI, AsyncAPI, snapshots) exist for projects.

| Form | Command |
|------|---------|
| One project | `.\visualize\status-docs.ps1 <source.dtrx>` |
| Batch | `.\visualize\status-docs.ps1 -All` / `-TestSet foundation` / `-Domains` |

Parameters: `-Source` (positional 0), `-All`, `-Domains`, `-TestSet` (default all), `-Dbg`, `-SelfTest`
