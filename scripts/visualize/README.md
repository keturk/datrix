# Visualization & Documentation Scripts

Diagrams, OpenAPI/AsyncAPI documents and schema snapshots generated from `.dtrx` sources. The commands
and parameters of each script are in [quick-reference.md](quick-reference.md); this file holds what they
do and how they are built.

Every wrapper here is rendered from `common/templates/entrypoint.ps1`; its behaviour is the
`datrix_scripts.visualize.*` module (in `common/lib/`) named below, run in the shared venv. Each has a
POSIX twin `visualize/<name>.sh` taking the module's own flags, each parameter as `--kebab-name`
(`bash visualize/visualize.sh --source examples/01-foundation/system.dtrx --type erd`; `-All` is `--all`,
`-TestSet` is `--test-set`). `-SelfTest` runs the module's self-test (over a planted copy of an example,
including the wrapper seam) and nothing else. Options are spelled in full: an abbreviation is a usage
error (exit 2). The batch modes read `datrix/scripts/config/test-projects.json`; an empty or unreadable
test set is an `ERROR:` on stderr, exit 1.

All output is written next to the `.dtrx` source files (language-agnostic).

## `all-reports.ps1`

Runs the diagram, OpenAPI/AsyncAPI and documentation-status steps for a project (`visualize`,
`openapi-gen`, `status-docs`), each as its own module run with the same selection. Each step runs
independently — a failure in one does not block subsequent steps. With no selection it prints its usage
and exits 1.

Module: `datrix_scripts.visualize.all_reports`; POSIX twin `visualize/all-reports.sh`.

## `visualize.ps1`

Generates Mermaid diagrams from `.dtrx` source files: ERD, service map, event flow, API catalog, CQRS
flow, inheritance tree, infrastructure topology, and system context. The application is loaded exactly as
generation loads it (config resolution under `-Profile`, then semantic analysis with infrastructure
configs resolved before the tree seals). Output is written next to the `.dtrx` source (e.g.
`examples/.../docs/diagrams/`); the script clears only the `docs/diagrams` tree it writes, never
`docs/openapi` or `docs/asyncapi`.

Module: `datrix_scripts.visualize.visualize`; POSIX twin `visualize/visualize.sh`.

## `schema-diff.ps1`

Compares two `.dtrx` files and reports structural changes (breaking vs non-breaking). Each side is loaded
exactly as generation loads it (profile `test`); a `.json` snapshot is refused (pass the `.dtrx` it was
taken from).

Module: `datrix_scripts.visualize.schema_diff`; POSIX twin `visualize/schema-diff.sh` (`--before`,
`--after`, `--format`, `--output`, `--dbg`, `--self-test`).

## `schema-snapshot.ps1`

Saves the `.dtrx` Application as a JSON snapshot for future diffs. The application is loaded exactly as
generation loads it (profile `test`). Output is written next to the `.dtrx` source (e.g.
`examples/.../docs/snapshots/`).

Module: `datrix_scripts.visualize.schema_snapshot`; POSIX twin `visualize/schema-snapshot.sh`.

## `openapi-gen.ps1`

Generates one OpenAPI 3.1 YAML per service — every `rest_api` block of the service in one document, so a
multi-file service keeps every block's paths — and one AsyncAPI 3.0 YAML per service covering every
pubsub block. Two blocks of one service declaring the same path and method (or the same topic) fail the
run rather than overwrite each other. The application is loaded exactly as generation loads it (config
resolution under `-Profile`, then semantic analysis with infrastructure configs resolved before the tree
seals). Output is written next to the `.dtrx` source (e.g. `examples/.../docs/openapi/`); the script
clears only `docs/openapi` and `docs/asyncapi` for the spec types it writes.

Module: `datrix_scripts.visualize.openapi_gen`; POSIX twin `visualize/openapi-gen.sh`.

## `status-docs.ps1`

Reports documentation status for Datrix projects (diagrams, OpenAPI, AsyncAPI, snapshots). Scans project
source directories for docs artifacts.

Module: `datrix_scripts.visualize.status_docs`; POSIX twin `visualize/status-docs.sh`.
