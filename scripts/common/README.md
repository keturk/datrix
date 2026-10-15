# Common Modules

Shared PowerShell modules used by all scripts, and `lib/datrix_scripts/`, the Python package
every scripts folder shares.

## Files

| File | Description |
|------|-------------|
| `DatrixPythonScript.psm1` | `Invoke-DatrixPythonScript`, the one way a wrapper runs Python; gate mode, its verdict line and gate logs |
| `DatrixPaths.psm1` | Path discovery for workspace and repository directories |
| `DatrixScriptCommon.psm1` | Shared project lists and `ConvertTo-DatrixProjectName` (imports `DatrixPaths.psm1`) |
| `venv.ps1` | Virtual environment management (creation, activation, package installation, the scripts `PYTHONPATH`) |
| `venv-install-order.ps1` | Self-test of the package install order (`datrix_scripts.install_order`) |
| `venv-dev-specs.ps1` | Self-test of the `[dev]` specs the venv installs (`datrix_scripts.dev_specs`) |
| `CleanupUtils.psm1` | Cleanup utilities (empty parents, confirmation, folder tree display, size formatting) |
| `DatrixRunLog.psm1` | Run-log file naming and **exclusive** claiming — two runs never share one log file |
| `lib/datrix_scripts/` | The shared Python package (below) |

## Where Python lives

Every Python file sits beside the wrapper that runs it, never in a central tree:

- **One folder uses it** → `<folder>/lib/<name>.py` (for gates, `gates/<family>/lib/`). The
  wrapper runs it by path (`Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot
  "lib\<name>.py")`), so `sys.path[0]` is that `lib/` folder and its siblings import each other by
  bare name (`from compare_tests import ...`).
- **More than one folder, a hook, or a package test imports it** → `common/lib/datrix_scripts/`.
  It is always imported as `datrix_scripts.<name>`, and a wrapper that runs one of its modules
  uses `Invoke-DatrixPythonScript -Module datrix_scripts.<name>`.

`Invoke-DatrixPythonScript` activates the shared venv, which puts `scripts\common\lib` first on
`PYTHONPATH` (`Set-DatrixPythonPath`), so every wrapper's Python can import `datrix_scripts`. A Python process that starts
another Python process passes `datrix_scripts.paths.script_env()` as its environment. Hooks call
`add_scripts_lib_to_path()` (`claude-config/.claude/hooks/_hook_log.py`), and the MCP servers are
registered with `PYTHONPATH` in their `env` (re-run `dev\code-index.ps1 -Setup` and
`dev\local-llm.ps1 -Setup` on each machine after the server paths change).

Never compute a location from `Path(__file__).parents[N]`: import it from `datrix_scripts.paths`
(`SCRIPTS_DIR`, `CONFIG_DIR`, `SHOWCASE_DIR`, `WORKSPACE_DIR`, `lib_script(folder, name)`).

No production script inserts a path into `sys.path`: the venv's editable installs and the
`PYTHONPATH` the runner sets are the only import paths. The only inserts are self-test fixtures
that plant a synthetic distribution in a temp directory, and `hook_modules.py` (the hooks directory
is no package).

### One home per fact

Each of these has exactly one home, and `test\shared-library-gate.ps1` holds it with a census that
must report zero (each census first reports a planted copy):

| Fact | Home | Census |
|------|------|--------|
| Check running, `_ok`/`_fail`, logging setup | `datrix_scripts.gate_harness` | no other top-level `run_checks`, `run_self_test_checks`, `harness_self_test`, `_ok`, `_fail`, `configure_logging` |
| Activating the venv and running Python | `Invoke-DatrixPythonScript` | no `.ps1` but `venv.ps1` calls `Ensure-DatrixVenv`; every gate wrapper prints the verdict line |
| The workspace root | `Get-DatrixWorkspaceRoot` / `datrix_scripts.paths.WORKSPACE_DIR` | no retired resolver is defined or named |
| Enumerating `datrix-*` directories | `framework_repos.workspace_package_dirs` | no loop over an `iterdir()` tests a `datrix` prefix |
| Import paths | the venv | no `sys.path` mutation outside the fixtures above |
| A helper body | its shared module | no function body of three or more statements is AST-identical across two files |
| A gate's self-test | the gate | every gate wrapper declares `-SelfTest` |

The same gate proves that every `datrix_scripts` module imports as the first import of a fresh
interpreter, and that every module a hook imports is exercised by a gate or carries its own
`self_test` (`consumed − covered` is empty): hooks fail open, so a broken import would silently
disable one.

`test\shared-library-gate.ps1 -Only check_scripts_tree` holds the layout: no `scripts\library`
folder, every Python file in a `lib/` folder, no `lib/` module named like a stdlib or installed
module, every import resolvable, every script a wrapper runs present, and every script path a doc,
skill, hook, config or package file names present.

### Adding a script

1. Put the Python in the `lib/` of the folder whose wrapper runs it (or in `datrix_scripts`, per
   the rule above).
2. Write the wrapper in that folder: its `param()` block, the mapping of its switches to Python
   flags, and one line, `exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot
   "lib\<name>.py") -Arguments $pythonArgs)` (`-RequirePackages` when it needs the editable
   installs, `-Gate <name>` for a gate, `-ShowCommand:$Dbg`). It never calls `Ensure-DatrixVenv`
   itself (`test\shared-library-gate.ps1`'s runner-adoption census holds that). A gate also
   declares `-SelfTest`.
3. Add its section to the folder's `quick-reference.md`, documenting exactly the parameters it
   declares (`gates\repo-hygiene\script-catalogue-gate.ps1` holds that).

## lib/datrix_scripts

| Module | Description |
|--------|-------------|
| `paths.py` | Fixed locations in the scripts tree, the showcase repository and the workspace; `script_env()` |
| `venv.py` | Virtual environment helpers (Python side): the venv path, its interpreter, whether a venv is active |
| `install_order.py` | The `datrix-*` package install order for the shared venv |
| `dev_specs.py` | A package's `[dev]` specs as the shared venv installs them: a direct-URL spec to a sibling workspace package becomes its bare name, so pip never replaces that package's editable install with a frozen copy |
| `framework_repos.py` | The framework git repositories at the workspace root, discovered, never listed; `workspace_package_dirs(workspace, any_of=…, include_showcase=…)` is the only enumeration of `datrix-*` directories (filtered by `PackageMarker`: `src`, `tests`, `pyproject.toml`, `package.json`, `.git`), and each caller keeps its own keying |
| `gate_harness.py` | The one check loop every gate runs, its non-vacuity proof, `[OK]`/`[FAIL]` printing, logging setup, the shared gate flags and the planted-fixture writer (see [../gates/README.md](../gates/README.md#how-a-gate-is-built)) |
| `count_ratchet.py` | The two count-ratchet semantics (tighten-only, exact-pin) and the fail-closed count-table reader and writers |
| `powershell_ast.py` | Parameters, calls and definitions of PowerShell scripts, read through PowerShell's own parser in one child process |
| `hook_modules.py` | Loads a harness hook module by path, so a gate shares the hook's one definition instead of a copy |
| `registered_targets.py` | The registered `datrix.languages` / `datrix.platforms` targets and their `src/` directories -- the one place a script learns which targets exist |
| `pyproject_deps.py` | `datrix-*` dependency declarations read from `pyproject.toml` |
| `capped_log.py` | Append-only logs with a size cap (hooks and scripts share it) |
| `logging_utils.py` | Logging and tee-style output (console + file); `TeeLogger` claims a run directory exclusively |
| `test_projects.py` | Project discovery from `config/test-projects.json` |
| `test_project.py` | The package test runner behind `test\test.ps1` |
| `test_runner.py`, `node_test_runner.py`, `package_suites.py` | Test execution: pytest phases, Node suites, which packages carry a suite |
| `runner_plugin.py`, `suite_stamp.py`, `suite_inputs.py` | The suite-input stamp: what a run touched, and the fingerprint a carried run is compared on |
| `structured_log_writer.py`, `generated_test_log_writer.py`, `deploy_test_log_writer.py`, `aggregate_test_writer.py`, `deploy_test_aggregate_writer.py` | Structured run directories (`index.json`, clusters) for package, generated-project and deploy runs |
| `codegen_hint_mapper.py` | Maps a generated file to the template and generator that probably wrote it |
| `status_tests.py` | Test status from the newest run of every package (`test\status-tests.ps1`) |
| `collect_failure_data.py`, `classify_run_delta.py`, `run_digest.py` | Failure bundle, run-to-run delta, and the short digest `test.ps1` prints for a red run |
| `affected_set.py` | Reverse-dependency closure of packages, from actual imports |
| `generated_example.py` | Generate one example for one registered language, as `datrix generate` would |
| `evaluate_reports.py` | The report text the evaluation scans write from their own JSON |
| `local_llm.py`, `local_llm_usage.py`, `local_llm_loopback.py` | The machines' Ollama servers (discovery, readiness, load spreading, failover), the usage log, and the loopback Ollama server every local-model check runs against |
| `local_reading.py` | Reads framework files and logs through a local model: read scope, chunking, log reduction, citation checking, the customer-term filter |
| `llm_code_fix.py` | Shared machinery for scripts that ask a local model to rewrite Python |
| `mcp_stdio.py` | The MCP protocol over stdio, shared by every Datrix MCP server |
| `code_index/` | The per-machine code index: definitions, references, outlines, search, summaries, usage |
| `knowledge/` | The knowledge base behind `dev\ineedtoknow.ps1` |
| `logic_map.py` | Logic-map marker syntax, parser and the `markers.db` writer |
| `task_metadata.py`, `task_orientation.py` | Task-file and `dependencies.md` parsing; a task's `## Orientation` block |
| `customer_domain_isolation.py`, `design_task_references.py`, `ignored_source.py`, `polystring_case_roundtrip.py`, `python_lint_correctness.py` | Repo-hygiene detectors shared by their gates, the commit seam and the edit hooks |
| `behaviour_skeleton.py`, `target_literal_positions.py` | Detectors shared by the parity gates and the import-boundary scanner |
| `function_sources.py` | The one walker of module-level functions and class methods in a package tree (`collect_function_sources`), shared by the behaviour-parity and shared-home body gates and `scan\find-duplicate-bodies.ps1` |
| `body_digest.py` | A function body's comparison form (normalized and exact digests, the 8-line / 40-node floor), shared by the shared-home body gate and `scan\find-duplicate-bodies.ps1` |
| `import_sites.py` | Where a module or its names are imported across the workspace (relative imports resolved), shared by `dev\find-imports.ps1` and `codemods\split-module.ps1` |
| `plugin_discovery.py` | Loads every installed plugin group and names the one that fails; run by `dev\generate.ps1` through `Invoke-DatrixPythonScript -RequirePackages` before any generation |
| `complexity.py`, `dead_code_report.py`, `duplicate.py` | Metrics shared by `metrics\` and `dev\code-scan.ps1` |
| `visualization/` | Application loading, serialization, diagrams and OpenAPI/AsyncAPI builders for `visualize\` |

## DatrixPaths.psm1

PowerShell module for discovering datrix workspace paths.

### Functions

```powershell
# Get workspace root (parent of datrix folder)
$root = Get-DatrixWorkspaceRoot

# Get list of repository names
$repos = Get-DatrixDirectories
# Returns: @("datrix", "datrix-cli", "datrix-common", ..., "datrix-extensions")

# Get full paths to all existing repositories
$paths = Get-DatrixDirectoryPaths
```

### Workspace root

`Get-DatrixWorkspaceRoot` is the one PowerShell answer to "where is the workspace": it takes no
parameter and resolves from the module's own location, so it is the same for every script. The
Python side is `datrix_scripts.paths.WORKSPACE_DIR`.

## DatrixPythonScript.psm1

`Invoke-DatrixPythonScript` runs a Python file (`-Script`) or module (`-Module`) in the shared
venv and returns the child's exit code (it never calls `exit`): it activates the venv, checks the
editable installs with `-RequirePackages`, prints the command with `-ShowCommand`, and deactivates
the venv in a `finally` block. `-TeePath <file>` also writes the output to a file;
`-OutputPipeline` / `-OutputLines` hand the output lines to the caller instead of the console.

**Gate mode** (`-Gate <name>`) tees the output to a claimed log under
`<workspace>\.test-output\gates\<name>\` and prints exactly one last line,
`[GATE] <name> PASSED|FAILED exit=<n> log=<path>`. That line is the seam the red-run digest hook
reads (`claude-config/.claude/hooks/digest-red-test-run.py`). A gate that runs no Python claims its
log with `New-DatrixGateLogFile` (or `Write-DatrixGateLog`) and prints the same line with
`Write-DatrixGateVerdict`.

## DatrixScriptCommon.psm1

Imported by metrics wrappers, `test.ps1`, and several dev scripts. Provides:

- `ConvertTo-DatrixProjectName` — path or bare package name to directory name
- `Get-DatrixPackageNamesGlob` — metrics `-All` (`datrix-*` on disk)
- `Get-DatrixPackageNamesGlobWithPyProject` — like above, requires `pyproject.toml` (dependency help text)
- `Test-DatrixNodeSuite` — does this package directory declare a Node test suite?
- `Get-DatrixTestablePackageNames` — packages carrying a suite: a `tests/` folder (pytest) or a `package.json` with a `test` script (Node) — `test.ps1 -All`
- `Get-DatrixMonoProjectNames` — ordered canonical monorepo packages that exist (e.g. `duplicate.ps1 -Mono`)

## venv.ps1

Virtual environment management with concurrent operation support. Wrappers do not call it
directly: `Invoke-DatrixPythonScript` does. Its functions serve the runner, venv setup and the
MCP `-Setup` registrations.

### Key Functions

```powershell
# Source the module
. .\common\venv.ps1

# Ensure venv exists and is activated (creates if needed); the runner calls it
Ensure-DatrixVenv

# Get venv path
$venvPath = Get-DatrixVenvPath # Returns D:\datrix\.venv

# Install a single package in editable mode
Install-DatrixPackage -PackageName "datrix-common"

# Ensure all packages are installed (with change detection)
Ensure-DatrixPackagesInstalled

# Verify the CLI entry point (generate.ps1 runs it after the plugin-discovery check)
Test-DatrixCommand -Detail ([ref]$cliDetail)

# Skip reinstall if already importable (for concurrent operations)
Ensure-DatrixPackagesInstalled -SkipIfInstalled

# Deactivate venv
Disable-DatrixVenv
```

### Concurrent Operation Safety

The module uses file-based locking to prevent concurrent pip operations:

- `Enter-DatrixPackageLock` - Acquire exclusive lock
- `Exit-DatrixPackageLock` - Release lock
- Stale lock detection and cleanup
- Automatic lock release on script exit

### Package Change Detection

Reinstalls packages only when:
- `pyproject.toml` has changed
- Source files in `src/` have changed
- Package is not importable

## Usage in Scripts

```powershell
[CmdletBinding()]
param([string[]]$Projects, [switch]$Dbg)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force
# Project discovery, when the wrapper needs it (also loads DatrixPaths.psm1)
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force

$pythonArgs = @("--workspace-root", (Get-DatrixWorkspaceRoot)) + $Projects
if ($Dbg) { $pythonArgs += "--debug" }
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\example.py") -Arguments $pythonArgs -ShowCommand:$Dbg)
```

Scripts that only need `DatrixPaths.psm1` can import it alone; otherwise prefer `DatrixScriptCommon.psm1` to avoid duplicating project-discovery logic.

## CleanupUtils.psm1

- `Remove-EmptyParentFolders`, `Confirm-YesNo` — existing behavior
- `Format-CleanupSize` — human-readable byte sizes
- `Get-CleanupFolderSize` — recursive file size sum
- `Get-CleanupFolderContents` — tree listing; use `-WarnOnFolderReadError` for non-fatal read warnings (tasks cleanup)

## DatrixRunLog.psm1

Names a run's log file, and claims it so no other run can be handed the same one.

```powershell
$base = Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @($Language, $ConfigProfile)
$logFile = New-DatrixRunLogFile -Directory $resultsDir -BaseName $base
```

- `ConvertTo-DatrixRunLogSegment` — reduce one label to name-safe characters (a label from a command line can never traverse out of the results directory)
- `Get-DatrixRunLogBaseName` — `<prefix>-<timestamp>[-<label>...]`, timestamp leading so name-sorting stays chronological; pass `-Timestamp` to compose deterministically
- `New-DatrixRunLogFile` — creates and returns a log file this run owns alone

**The labels are not what makes the name unique.** Two runs agreeing on every label
(two profiles of one project started in the same second, or two runs of one profile)
compute one name; `New-DatrixRunLogFile` claims it with `FileMode.CreateNew`, an atomic
create-or-fail, and falls through to `<base>-2`, `<base>-3`, … when a name is taken.
Never relax that to `Create`/`OpenOrCreate` — both succeed on an existing file, which is
how two runs end up truncating and interleaving one log.

File-level twin of `TeeLogger._claim_run_dir` (`scripts/common/lib/datrix_scripts/logging_utils.py`),
which does the same for test run *directories*. Held by
`scripts/test/run-log-exclusivity-gate.ps1`.
