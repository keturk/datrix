# Quick Reference — Generation Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each script does, its module and POSIX twin: [README.md](README.md).

Scripts around generated output. Generating a project itself is `dev\generate.ps1` ([../dev/quick-reference.md](../dev/quick-reference.md)). `-SelfTest` runs a script's self-test and nothing else; options are spelled in full (an abbreviation is a usage error, exit 2).

## `generation\rebuild-parser.ps1`

Rebuild the tree-sitter parser from `grammar.js` when stale.

| Form | Command |
|------|---------|
| Rebuild if stale | `.\generation\rebuild-parser.ps1` |
| Force | `.\generation\rebuild-parser.ps1 -Force` |

Parameters: `-Force`, `-SelfTest`. Exit: 0 built or fresh, 1 build failed.

## `generation\refresh-example-snapshot.ps1`

Regenerate one example in one language and replace its committed snapshot `<example>/generated/<language>-<platform>/`.

| Form | Command |
|------|---------|
| Refresh | `.\generation\refresh-example-snapshot.ps1 -Source examples/03-domains/ecommerce/system.dtrx -Language python` |
| Other profile | `.\generation\refresh-example-snapshot.ps1 -Source <system.dtrx> -Language python -ConfigProfile aws` |
| Explicit platform | `.\generation\refresh-example-snapshot.ps1 -Source <system.dtrx> -Language python -Platform docker` |

Parameters: `-Source`, `-Language` (a registered `datrix.languages` name), `-Platform` (required when the deployment resolves to none or several), `-ConfigProfile` (default `test`), `-SelfTest`, `-Dbg`. Exit: 0 refreshed, 1 generation or copy failed (old snapshot kept), 2 refused.

## `generation\refresh-seed-datasets.ps1`

Regenerate the builtin seed reference datasets in `datrix-codegen-kernel` from their sources. Needs the network.

| Form | Command |
|------|---------|
| Refresh | `.\generation\refresh-seed-datasets.ps1` |
| Other cache | `.\generation\refresh-seed-datasets.ps1 -CacheDir D:\other` |

Parameters: `-CacheDir`, `-SelfTest`. Exit: 0 regenerated and equal to the schema, 1 schema differs or a source failed.

## `generation\status-generation.ps1`

Which projects succeeded or failed in the latest `generate-results-*.log`.

| Form | Command |
|------|---------|
| Status | `.\generation\status-generation.ps1` |
| Other results folder | `.\generation\status-generation.ps1 -ResultsDir D:\other\.results` |

Parameters: `-ResultsDir` (default `<workspace>\.generated\.results`), `-SelfTest`. Exit: 0 none failed, 1 a project failed or no log.

## `generation\triage-failures.ps1`

Group failures in a test, generation or deploy log by likely root cause (input for `/fix-tests`, `/checkpoint-debug`).

| Form | Command |
|------|---------|
| Parse a log | `.\generation\triage-failures.ps1 "path/to/results.log"` |
| Force the format | `.\generation\triage-failures.ps1 "path/to/output.log" -Format pytest` |
| Save the report | `.\generation\triage-failures.ps1 "path/to/results.log" -OutputFile "triage.md"` |

Parameters: `-LogPath` (positional 0, mandatory), `-Format` (pytest\|generate\|deploy; auto-detected), `-OutputFile <path>`, `-Dbg`, `-LlmSummary`, `-LlmLimit`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout`, `-LlmNumPredict`, `-LlmTemperature`, `-SelfTest`

## `generation\compare-generated.ps1`

Feature-detection comparison of `.generated` against `.generated_saved` → markdown report. Not a byte diff (use `tree-hash.ps1`).

| Form | Command |
|------|---------|
| Default | `.\generation\compare-generated.ps1` |
| Custom report | `.\generation\compare-generated.ps1 -Report my-report.md` |
| Explicit directories | `.\generation\compare-generated.ps1 -Current .generated -Saved .generated_saved` |

Parameters: `-Current` (default `.generated`), `-Saved` (default `.generated_saved`), `-Report` (default `generated-comparison-report.md`), `-LlmSummary`, `-LlmLimit`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout`, `-LlmNumPredict`, `-LlmTemperature`, `-SelfTest`

## `generation\tree-hash.ps1`

Byte-level diff of generated trees: snapshot SHA-256 of every file, then diff two snapshots. Keep manifests outside the package repos.

| Form | Command |
|------|---------|
| Snapshot | `.\generation\tree-hash.ps1 -Snapshot -Manifest D:\datrix\.tmp\before.json -Root <generated tree>` |
| Diff | `.\generation\tree-hash.ps1 -Diff -Before D:\datrix\.tmp\before.json -After D:\datrix\.tmp\after.json` |
| Diff, every path | `.\generation\tree-hash.ps1 -Diff -Before ... -After ... -Limit 0` |

Parameters: `-Snapshot -Manifest <path> -Root <dir,...>` (root names must differ), or `-Diff -Before <path> -After <path> [-Limit <n>]` (default 50; 0 = all); `-SelfTest`. Exit: `-Diff` 0 identical, 1 differences, 2 bad input.

## `generation\evaluate-generated-scan.ps1`

Mechanical scan behind `/evaluate-generated` → `project-scan.json`, `project-evaluation-quick.md`, one `service-{name}.prompt.md` per service.

| Form | Command |
|------|---------|
| Scan a project | `.\generation\evaluate-generated-scan.ps1 -Source "examples/03-domains/ecommerce/system.dtrx" -Generated "D:\datrix\.generated\python\...\ecommerce" -EvalDir "D:\datrix\eval\<dir>"` |
| Other profile | add `-ConfigProfile staging` |

Parameters: `-Source <system.dtrx>` (required), `-Generated <dir>` (required), `-EvalDir <dir>` (default `D:\datrix\.tmp\eval\<project>\`), `-ConfigProfile <name>` (default `test`), `-Dbg`, `-SelfTest`. Exit: 0 scanned, 2 usage or parse failure.

## `generation\evaluate-service-scan.ps1`

Mechanical scan behind `/evaluate-generated-service` → `service-<name>-scan.json` and `service-<name>-mechanical.md`.

| Form | Command |
|------|---------|
| Scan a service | `.\generation\evaluate-service-scan.ps1 -Source "{system.dtrx}" -Service ProductService -Generated "{service dir}" -ProjectGenerated "{project root}"` |
| Explicit output | add `-Output D:\datrix\eval\...\service-x-scan.json` |

Parameters: `-Source <dtrx>` (required), `-Service <name>` (required for multi-service sources), `-Generated <dir>` (required), `-ProjectGenerated <dir>` (required), `-Output <path>` (default `D:\datrix\.tmp\eval\<project>\`), `-ConfigProfile <name>`, `-Dbg`, `-SelfTest`. Exit: 0 scanned, 2 usage or parse failure.

## `generation\evaluate-services.ps1`

Run the `/evaluate-generated-service` prompts (up to 5 in parallel) after local triage. Run `/evaluate-generated` first to produce `service-*.prompt.md`.

| Form | Command |
|------|---------|
| Run | `.\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -EvalDir <path>` |
| Skip the local triage | `.\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -Full` |
| Fewer jobs | `.\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -Parallel 3` |
| Other model | `.\generation\evaluate-services.ps1 -SourceDir <src> -GeneratedDir <gen> -Model sonnet` |
| Self-test | `.\generation\evaluate-services.ps1 -SelfTest` |

Parameters: `-SourceDir` (mandatory), `-GeneratedDir` (mandatory), `-EvalDir` (default current directory), `-Parallel` (default 5), `-Model` (default opus), `-Full`, `-SelfTest` (alone)

## `generation\delete-generated.ps1`

Rename `.generated` to `.generated_old[_NN]` and delete it in a detached background process.

| Form | Command |
|------|---------|
| Background delete | `.\generation\delete-generated.ps1` |
| Wait | `.\generation\delete-generated.ps1 -Wait` |
| Dry run | `.\generation\delete-generated.ps1 -DryRun` |
| Other base | `.\generation\delete-generated.ps1 -BaseDir D:\other` |

Parameters: `-BaseDir` (default the workspace), `-Wait`, `-DryRun`, `-SelfTest`. Exit: 0 done or nothing to do, 1 refused or no free `.generated_old*` name.
