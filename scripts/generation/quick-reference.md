# Quick Reference — Generation Scripts

Scripts around generated output: the parser build, example snapshots and seed datasets, status
and triage of generation runs, evaluation scans of a generated project, and cleanup. Generating
a project itself is `dev\generate.ps1` (see [../dev/quick-reference.md](../dev/quick-reference.md)).

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## Build

### `generation\rebuild-parser.ps1`

Rebuilds the tree-sitter parser from `grammar.js` (`generation\lib\rebuild_parser.py`).

| Mode | Command | Description |
|------|---------|-------------|
| **Rebuild** | `.\generation\rebuild-parser.ps1` | Rebuild if grammar changed |
| **Force rebuild** | `.\generation\rebuild-parser.ps1 -Force` | Rebuild even if unchanged |

**Parameters:** `-Force`

---

## Snapshots and Datasets

### `generation\refresh-example-snapshot.ps1`

Refreshes one committed example snapshot (`<example>/generated/<language>-<platform>/`) with one command: runs single-project `generate.ps1 <source> <scratch> -L <language>` into `D:\datrix\.tmp\example-snapshots\<example>\<language>-<platform>\` (never `-All`, `-Domains` or `-TestSet`), replaces the snapshot directory with that output, then deletes every path git ignores there (the repository's `.datrix/` rule and the generated project's own `.gitignore`: build output, per-service `secrets/`) -- asked of `git ls-files --others --ignored --exclude-standard`, never restated. `<platform>` is a registered platform taken from the example's resolved deployment (profile `test` by default): the provider-owned platform when the provider owns one (`aws`), otherwise the platform that emits the runtime's container scaffolding (`docker` for docker-compose).

| Mode | Command | Description |
|------|---------|-------------|
| **Refresh** | `.\generation\refresh-example-snapshot.ps1 -Source examples/03-domains/ecommerce/system.dtrx -Language python` | Regenerate one example in one language and replace its snapshot |
| **Other profile** | `.\generation\refresh-example-snapshot.ps1 -Source <system.dtrx> -Language python -ConfigProfile aws` | Snapshot the deployment of another profile |
| **Explicit platform** | `.\generation\refresh-example-snapshot.ps1 -Source <system.dtrx> -Language python -Platform docker` | Override the derived platform (required when the deployment resolves to none or several) |
| **Self-test only** | `.\generation\refresh-example-snapshot.ps1 -SelfTest` | Fixture project with `secrets/` and `.datrix/` copies neither |

**Parameters:** `-Source`, `-Language` (a registered `datrix.languages` name), `-Platform`, `-ConfigProfile` (default `test`), `-SelfTest`, `-Dbg`

**Exit codes:** 0 = refreshed (or a successful `-SelfTest`), 1 = generation or copy failed (the previous snapshot is left in place when generation fails), 2 = refused: unregistered language or platform, missing source, ambiguous platform, or a failed self-test. Verified by `gates\repo-hygiene\example-snapshot-gate.ps1`.

### `generation\refresh-seed-datasets.ps1`

Regenerates the seven builtin SeedDSL reference datasets (`Seed.countries()`, `Seed.currencies()`, …) in `datrix-codegen-kernel/src/datrix_codegen_kernel/seed_data/` from their authoritative sources. Needs the network. Every file records its source, URL, version, retrieval date, licence and transform; afterwards the script compares the files with `SEED_DATASETS` and exits 1 while the schema constants differ, printing what they must carry.

| Mode | Command | Description |
|------|---------|-------------|
| **Refresh** | `.\generation\refresh-seed-datasets.ps1` | Download (cached), transform, write, compare with the schema |
| **Custom cache** | `.\generation\refresh-seed-datasets.ps1 -CacheDir D:\other` | Cache downloaded sources elsewhere |

**Parameters:** `-CacheDir`. **Exit codes:** 0 = regenerated and equal to the schema, 1 = schema differs or a source failed.

---

## Status and Triage

### `generation\status-generation.ps1`

Reports generation status from the latest `generate-results-*.log` file. Lists which projects succeeded/failed.

| Mode | Command |
|------|---------|
| **Show status** | `.\generation\status-generation.ps1` |

**Parameters:** (none)

### `generation\triage-failures.ps1`

Parses test/generation logs and groups failures by likely root cause. Produces a triage report suitable for feeding into `/fix-tests` or `/checkpoint-debug`.

| Mode | Command | Description |
|------|---------|-------------|
| **Parse log** | `.\generation\triage-failures.ps1 "path/to/results.log"` | Auto-detect format, output to stdout |
| **Force format** | `.\generation\triage-failures.ps1 "path/to/output.log" -Format pytest` | Force pytest parser |
| **Save report** | `.\generation\triage-failures.ps1 "path/to/results.log" -OutputFile "triage.md"` | Write Markdown report |
| **Debug** | `.\generation\triage-failures.ps1 "path/to/results.log" -Dbg` | Show auto-detect reasoning |

**Parameters:** `-LogPath` (positional 0, mandatory), `-Format` (pytest\|generate\|deploy), `-OutputFile <path>`, `-Dbg`

**Supported formats:** pytest output, generation result logs, deploy test logs. Auto-detected from file content.

### `generation\compare-generated.ps1`

Compares `.generated` vs `.generated_saved` with content-level feature detection. Writes a markdown report.

| Mode | Command | Description |
|------|---------|-------------|
| **Default** | `.\generation\compare-generated.ps1` | Compare defaults, write report |
| **Custom report** | `.\generation\compare-generated.ps1 -Report my-report.md` | Custom report path |
| **Custom dirs** | `.\generation\compare-generated.ps1 -Current .generated -Saved .generated_saved` | Explicit directories |

**Parameters:** `-Current` (default: .generated), `-Saved` (default: .generated_saved), `-Report` (default: generated-comparison-report.md)

**Note:** this is *feature detection* (presence of known content patterns), not a byte-level diff, and it proves nothing about output preservation — a behaviour-preservation claim is proven by a test in the owning package that renders the construct and asserts its output (see `datrix/docs/architecture/generated-output-stability.md`).

---

## Evaluation

### `generation\evaluate-generated-scan.ps1`

Mechanical core of `/evaluate-generated` (quick mode): parses the system DSL with the real parser pipeline, then writes `project-scan.json` (service inventory with expected/actual dirs, manifest aggregation, language/platform detection, infra existence checklist, docker-compose cross-check, rolled-up `critical_blockers`/`warnings`), the quick report `project-evaluation-quick.md` rendered from that JSON (`common/lib/datrix_scripts/evaluate_reports.py`), plus one `service-{name}.prompt.md` per service into the eval dir.

| Mode | Command | Description |
|------|---------|-------------|
| **Scan a project** | `.\generation\evaluate-generated-scan.ps1 -Source "examples/03-domains/ecommerce/system.dtrx" -Generated "D:\datrix\.generated\python\...\ecommerce" -EvalDir "D:\datrix\eval\2026-07-14-...-ecommerce"` | Full project scan + prompts |
| **Default eval dir** | omit `-EvalDir` | → `D:\datrix\.tmp\eval\<project>\` |
| **Non-default profile** | append `-ConfigProfile staging` | Config profile for the parse (default `test`) |

**Parameters:** `-Source <system.dtrx>` (required), `-Generated <dir>` (required), `-EvalDir <dir>`, `-ConfigProfile <name>`, `-Dbg`. **Exit codes:** 0 = scanned, 2 = usage / parse failure (analyzer diagnostics printed — usually itself the finding).

### `generation\evaluate-service-scan.ps1`

Mechanical core of `/evaluate-generated-service`: writes `service-<name>-scan.json` with the service's DSL feature inventory, manifest subset + both-direction filesystem set-diff, directory-name convention check, per-block/per-entity expected-artifact existence table, dead-code candidates, and Dockerfile/migrations/env-var data, and beside it `service-<name>-mechanical.md`: those facts as the report's tables (`common/lib/datrix_scripts/evaluate_reports.py`). Semantic verification (skill Phase 3.5) stays with the model.

| Mode | Command | Description |
|------|---------|-------------|
| **Scan a service** | `.\generation\evaluate-service-scan.ps1 -Source "{system.dtrx}" -Service ProductService -Generated "{service dir}" -ProjectGenerated "{project root}"` | Single service deep scan |
| **Single-service source** | omit `-Service` | Auto-selected when the source defines one service |
| **Explicit output** | append `-Output D:\datrix\eval\...\service-x-scan.json` | Default: `D:\datrix\.tmp\eval\<project>\` |

**Parameters:** `-Source <dtrx>` (required), `-Service <name>` (required for multi-service sources — fails loud listing names), `-Generated <dir>` (required), `-ProjectGenerated <dir>` (required), `-Output <path>`, `-ConfigProfile <name>`, `-Dbg`. **Exit codes:** 0 = scanned, 2 = usage / parse failure.

### `generation\evaluate-services.ps1`

Runs `/evaluate-generated-service` prompts in parallel using Claude Code CLI in non-interactive mode. Finds all `service-*.prompt.md` files in the evaluation folder and processes up to 5 concurrently.

| Mode | Command | Description |
|------|---------|-------------|
| **From eval dir** | `cd eval\2026-05-16-...; ..\..\datrix\scripts\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen>` | Uses current dir as eval folder |
| **Explicit eval dir** | `.\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -EvalDir <path>` | Specify eval folder |
| **Custom parallelism** | `.\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -Parallel 3` | Fewer concurrent jobs |
| **Different model** | `.\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -Model sonnet` | Use sonnet instead of opus |

**Parameters:** `-SourceDir` (mandatory), `-GeneratedDir` (mandatory), `-EvalDir` (default: current directory), `-Parallel` (default: 5), `-Model` (default: opus)

**Prereqs:** Run `/evaluate-generated` first to produce `service-*.prompt.md` files.

---

## Cleanup

### `generation\delete-generated.ps1`

Renames `.generated` to `.generated_old` (or `_old_01` through `_old_99`) then deletes the renamed folder in a background job.

| Mode | Command | Description |
|------|---------|-------------|
| **Background delete** | `.\generation\delete-generated.ps1` | Rename + async delete |
| **Wait for delete** | `.\generation\delete-generated.ps1 -Wait` | Synchronous deletion |
| **Custom base** | `.\generation\delete-generated.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Wait`
