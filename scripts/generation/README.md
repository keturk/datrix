# Generation Scripts

Scripts around generated output: the parser build, example snapshots and seed datasets, status and
triage of generation runs, comparison of generated trees, evaluation scans of a generated project, and
cleanup. The commands, parameters and exit codes of each script are in
[quick-reference.md](quick-reference.md); this file holds what they do and how they are built. Generating
a project itself is `dev\generate.ps1` (see [../dev/quick-reference.md](../dev/quick-reference.md)).

Every wrapper here is rendered from `common/templates/entrypoint.ps1`; its behaviour is the
`datrix_scripts.generation.*` module (in `common/lib/`) named under it, run in the shared venv. Each has
a POSIX twin `generation/<name>.sh` taking the module's own flags, each parameter as `--kebab-name`
(`bash generation/tree-hash.sh --diff --before a.json --after b.json`). `-SelfTest` runs the module's
self-test (including the wrapper seam) and nothing else. Options are spelled in full: an abbreviation is
a usage error (exit 2).

## Build

### `rebuild-parser.ps1`

Rebuilds the tree-sitter parser from `grammar.js`. The script holds no build logic: it builds through
`datrix_language.parser.tree_sitter_datrix.build` (`build_if_stale`, or
`ensure_grammar_compiled(force=True)` with `-Force`) and writes `tree_sitter_datrix.<platform>.<ext>` and
its staleness record `tree_sitter_datrix.<platform>.hash` into the package's `build\`, where
`<platform>` is the running interpreter's `sysconfig.get_platform()` (`win-arm64`, `win-amd64`,
`linux-x86_64`, …). A record for another platform, or a one-line record without a platform, is stale. The
script rebuilds when the grammar, the generated sources or the platform changed. Output: the library path
and whether a build ran; on failure the `ParseError` text is printed.

Module: `datrix_scripts.generation.rebuild_parser`; POSIX twin `generation/rebuild-parser.sh`
(`--force`, `--self-test`).

The parser's own build machinery (`datrix_language.parser.tree_sitter_datrix.build`) names this wrapper
as the manual rebuild command.

## Snapshots and Datasets

### `refresh-example-snapshot.ps1`

Refreshes one committed example snapshot (`<example>/generated/<language>-<platform>/`) with one
command: runs single-project generation (`datrix_scripts.dev.generate`, the module behind
`dev\generate.ps1`) into `D:\datrix\.tmp\example-snapshots\<example>\<language>-<platform>\` (never
`-All`, `-Domains` or `-TestSet`), replaces the snapshot directory with that output, then deletes every
path git ignores there (the repository's `.datrix/` rule and the generated project's own `.gitignore`:
build output, per-service `secrets/`) -- asked of `git ls-files --others --ignored --exclude-standard`,
never restated. `<platform>` is a registered platform taken from the example's resolved deployment
(profile `test` by default): the provider-owned platform when the provider owns one (`aws`), otherwise
the platform that emits the runtime's container scaffolding (`docker` for docker-compose).

`-SelfTest` runs a fixture project with `secrets/` and `.datrix/` copies neither.

Exit codes: 0 = refreshed (or a successful `-SelfTest`), 1 = generation or copy failed (the previous
snapshot is left in place when generation fails), 2 = refused: unregistered language or platform,
missing source, ambiguous platform, or a failed self-test. Verified by
`gates\repo-hygiene\example-snapshot-gate.ps1`.

Module: `datrix_scripts.generation.refresh_example_snapshot`; POSIX twin
`generation/refresh-example-snapshot.sh` (`--source`, `--language`, `--platform`, `--config-profile`,
`--dbg`, `--self-test`).

### `refresh-seed-datasets.ps1`

Regenerates the seven builtin seed reference datasets (`Seed.countries()`, `Seed.currencies()`, …) in
`datrix-codegen-kernel/src/datrix_codegen_kernel/seed_data/` from their authoritative sources. Needs the
network. Every file records its source, URL, version, retrieval date, licence and transform; afterwards
the script compares the files with `SEED_DATASETS` and exits 1 while the schema constants differ,
printing what they must carry. Downloads are cached (`-CacheDir`). `-SelfTest` uses a planted cache, no
network, and writes nothing.

Module: `datrix_scripts.generation.refresh_seed_datasets`; POSIX twin
`generation/refresh-seed-datasets.sh` (`--cache-dir`, `--self-test`).

## Status and Triage

### `status-generation.ps1`

Reports generation status from the latest `generate-results-*.log` file. Lists which projects
succeeded/failed. `-ResultsDir` defaults to `<workspace>\.generated\.results`; a relative path is taken
from the workspace. It does not look in subfolders: logs written with `generate.ps1 -ResultsSubdir <name>`
are in `<workspace>\.generated\.results\<name>`, so pass that as `-ResultsDir`.

Module: `datrix_scripts.generation.status_generation`; POSIX twin `generation/status-generation.sh`
(`--results-dir`, `--self-test`).

### `triage-failures.ps1`

Parses test/generation logs and groups failures by likely root cause. Produces a triage report suitable
for feeding into `/fix-tests` or `/checkpoint-debug`. Supported formats: pytest output, generation
result logs, deploy test logs, auto-detected from file content (`-Dbg` shows the reasoning).

Module: `datrix_scripts.generation.triage_failures`; POSIX twin `generation/triage-failures.sh` (the log
path positional or `--log-path`, `--format`, `--output-file`, `--dbg`, `--llm-summary`, …,
`--self-test`).

### `compare-generated.ps1`

Compares `.generated` vs `.generated_saved` with content-level feature detection. Writes a markdown
report.

This is *feature detection* (presence of known content patterns), not a byte-level diff, and it proves
nothing about output preservation — a behaviour-preservation claim is proven by a test in the owning
package that renders the construct and asserts its output (see
`datrix/docs/architecture/generated-output-stability.md`).

Module: `datrix_scripts.generation.compare_generated`; POSIX twin `generation/compare-generated.sh`
(`--current`, `--saved`, `--report`, `--llm-summary`, …, `--self-test`).

### `tree-hash.ps1`

Byte-level diff of generated trees: snapshot the SHA-256 of every file under one or more roots, then
diff two snapshots into **added / removed / changed** paths. Keys are `<root name>/<relative path>`, so
two output directories or two checkouts compare file by file. `.git`, `node_modules`, `__pycache__` and
tool caches are skipped. This is the measurement behind "this refactor changes no output": snapshot,
change, regenerate, snapshot, diff. When the diff is not empty, the behaviour-preservation proof is still
a test in the owning package (see the note above). Keep manifests outside the package repos.

Module: `datrix_scripts.generation.tree_hash`; POSIX twin `generation/tree-hash.sh` (`--snapshot`,
`--manifest`, `--root`, `--diff`, `--before`, `--after`, `--limit`, `--self-test`).

## Evaluation

### `evaluate-generated-scan.ps1`

Mechanical core of `/evaluate-generated` (quick mode): parses the system DSL with the real parser
pipeline, then writes `project-scan.json` (service inventory with expected/actual dirs, manifest
aggregation, language/platform detection, infra existence checklist, docker-compose cross-check,
rolled-up `critical_blockers`/`warnings`), the quick report `project-evaluation-quick.md` rendered from
that JSON (`common/lib/datrix_scripts/evaluate_reports.py`), plus one `service-{name}.prompt.md` per
service into the eval dir. A parse failure prints the analyzer diagnostics, which are usually themselves
the finding.

Module: `datrix_scripts.generation.evaluate_generated_scan`; POSIX twin
`generation/evaluate-generated-scan.sh` (`--source`, `--generated`, `--eval-dir`, `--config-profile`,
`--dbg`, `--self-test`).

### `evaluate-service-scan.ps1`

Mechanical core of `/evaluate-generated-service`: writes `service-<name>-scan.json` with the service's
DSL feature inventory, manifest subset + both-direction filesystem set-diff, directory-name convention
check, per-block/per-entity expected-artifact existence table, dead-code candidates, and
Dockerfile/migrations/env-var data, and beside it `service-<name>-mechanical.md`: those facts as the
report's tables (`common/lib/datrix_scripts/evaluate_reports.py`). Semantic verification (skill Phase
3.5) stays with the model. `-Service` is auto-selected when the source defines one service; for a
multi-service source it fails loud listing the names.

Module: `datrix_scripts.generation.evaluate_service_scan`; POSIX twin
`generation/evaluate-service-scan.sh` (`--source`, `--service`, `--generated`, `--project-generated`,
`--output`, `--config-profile`, `--dbg`, `--self-test`).

### `evaluate-services.ps1`

Runs `/evaluate-generated-service` prompts in parallel using Claude Code CLI in non-interactive mode.
Finds all `service-*.prompt.md` files in the evaluation folder and processes up to 5 concurrently.
Prerequisite: run `/evaluate-generated` first to produce them. Run from an eval directory, or name it
with `-EvalDir`.

First, each service is triaged by the local model servers
(`datrix_scripts.generation.service_triage`, one child process per service): the service scan is written
into the evaluation folder, and each Phase 3.5 category the service has (computed fields, lifecycle
hooks, validation blocks, REST endpoint logic, event handlers) is judged `clean`, `finding` or
`unverifiable` over the DSL source and the generated files the scan maps it to, into
`service-<name>.local-triage.json`. A service with every category clean and no failed artifact check gets
its report in `evaluated\` marked "local triage only" and no Claude Code run; every other service goes to
Claude Code with `LOCAL_TRIAGE: <triage file>` appended to its prompt. No local server answering makes
every category unverifiable. The reads are confined to the framework repositories, the workspace logs and
`-SourceDir`/`-GeneratedDir`, with every line carrying a registered customer term withheld. `-Full` skips
the triage. `-SelfTest` alone runs the triage's checks over a planted prompt and scan and a loopback
model, and the runner's checks.

Each Claude Code run gets its prompt on stdin; its argument vector carries only flags, the model and the
two directories. Where `claude` resolves to a `.cmd` launcher (Windows), an argument holding a `cmd.exe`
metacharacter is refused (exit 2) rather than handed to `cmd.exe`. `-Parallel` below 1 is refused.

Module: `datrix_scripts.generation.evaluate_services`; POSIX twin `generation/evaluate-services.sh`
(`--source-dir`, `--generated-dir`, `--eval-dir`, `--parallel`, `--model`, `--full`, `--self-test`).

## Cleanup

### `delete-generated.ps1`

Renames `<base>\.generated` to `.generated_old` (or `.generated_old_01` through `_99`, the first free
name), then deletes the renamed folder in a detached background process that outlives the shell (its
output: `<workspace>\.tmp\delete-generated\`). Only a real directory directly under the base is touched:
a `.generated` that is a file, a symbolic link or a junction is refused, and the deleting process checks
again, before removing, that its target is a `.generated_old*` directory directly under the base.
`-SelfTest` uses planted trees: the rename, the dry run, the link/junction and non-child refusals.

Module: `datrix_scripts.generation.delete_generated`; POSIX twin `generation/delete-generated.sh`
(`--base-dir`, `--wait`, `--dry-run`, `--self-test`).
