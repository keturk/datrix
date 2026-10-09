# Common Modules

Shared PowerShell modules used by all scripts, and `lib/datrix_scripts/`, the Python package
every scripts folder shares.

## Files

| File | Description |
|------|-------------|
| `DatrixPaths.psm1` | Path discovery for workspace and repository directories |
| `DatrixScriptCommon.psm1` | Shared project lists and `ConvertTo-DatrixProjectName` (imports `DatrixPaths.psm1`) |
| `venv.ps1` | Virtual environment management (creation, activation, package installation, the scripts `PYTHONPATH`) |
| `venv-install-order.ps1` | Self-test of the package install order (`datrix_scripts.install_order`) |
| `CleanupUtils.psm1` | Cleanup utilities (empty parents, confirmation, folder tree display, size formatting) |
| `DatrixRunLog.psm1` | Run-log file naming and **exclusive** claiming — two runs never share one log file |
| `lib/datrix_scripts/` | The shared Python package (below) |

## Where Python lives

Every Python file sits beside the wrapper that runs it, never in a central tree:

- **One folder uses it** → `<folder>/lib/<name>.py` (for gates, `gates/<family>/lib/`). The
  wrapper runs it by path (`Join-Path $scriptDir "lib\<name>.py"`), so `sys.path[0]` is that
  `lib/` folder and its siblings import each other by bare name (`from compare_tests import ...`).
- **More than one folder, a hook, or a package test imports it** → `common/lib/datrix_scripts/`.
  It is always imported as `datrix_scripts.<name>`, and a wrapper that runs one of its modules
  uses `python -m datrix_scripts.<name>`.

`Ensure-DatrixVenv` calls `Set-DatrixPythonPath`, which puts `scripts\common\lib` first on
`PYTHONPATH`, so every wrapper's Python can import `datrix_scripts`. A Python process that starts
another Python process passes `datrix_scripts.paths.script_env()` as its environment. Hooks call
`add_scripts_lib_to_path()` (`claude-config/.claude/hooks/_hook_log.py`), and the MCP servers are
registered with `PYTHONPATH` in their `env` (re-run `dev\code-index.ps1 -Setup` and
`dev\local-llm.ps1 -Setup` on each machine after the server paths change).

Never compute a location from `Path(__file__).parents[N]`: import it from `datrix_scripts.paths`
(`SCRIPTS_DIR`, `CONFIG_DIR`, `SHOWCASE_DIR`, `WORKSPACE_DIR`, `lib_script(folder, name)`).

`test\shared-library-gate.ps1 -Only check_scripts_tree` holds the layout: no `scripts\library`
folder, every Python file in a `lib/` folder, no `lib/` module named like a stdlib or installed
module, every import resolvable, every script a wrapper runs present, and every script path a doc,
skill, hook, config or package file names present.

### Adding a script

1. Put the Python in the `lib/` of the folder whose wrapper runs it (or in `datrix_scripts`, per
   the rule above).
2. Write the wrapper in that folder. It imports `common/DatrixScriptCommon.psm1` (or
   `DatrixPaths.psm1` alone when it needs no project discovery), dot-sources `common/venv.ps1`,
   calls `Ensure-DatrixVenv` (and `Ensure-DatrixPackagesInstalled` when it needs the packages),
   runs the Python with its arguments, and deactivates the venv on exit.
3. Add its section to the folder's `quick-reference.md`.

## lib/datrix_scripts

| Module | Description |
|--------|-------------|
| `paths.py` | Fixed locations in the scripts tree, the showcase repository and the workspace; `script_env()` |
| `venv.py` | Virtual environment helpers (Python side): the venv interpreter, the workspace root |
| `install_order.py` | The `datrix-*` package install order for the shared venv |
| `framework_repos.py` | The framework git repositories at the workspace root, discovered, never listed |
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

### Workspace root: `Get-DatrixRoot` vs `Get-DatrixWorkspaceRoot`

For scripts located under `datrix/scripts/**`, both resolve to the **same monorepo workspace root** (the parent of the inner `datrix` package folder):

- **`Get-DatrixRoot`** — defined in `venv.ps1` (relative to `common/`).
- **`Get-DatrixWorkspaceRoot`** — defined in `DatrixPaths.psm1` (relative to the invoking script path).

Prefer **`Get-DatrixWorkspaceRootFromScript`** from `DatrixScriptCommon.psm1` when you have `$MyInvocation.MyCommand.Path` and want an explicit, consistent resolution.

## DatrixScriptCommon.psm1

Imported by metrics wrappers, `test.ps1`, and several dev scripts. Provides:

- `Get-DatrixWorkspaceRootFromScript` — `-ScriptPath $MyInvocation.MyCommand.Path`
- `ConvertTo-DatrixProjectName` — path or bare package name to directory name
- `Get-DatrixPackageNamesGlob` — metrics `-All` (`datrix-*` on disk)
- `Get-DatrixPackageNamesGlobWithPyProject` — like above, requires `pyproject.toml` (dependency help text)
- `Test-DatrixNodeSuite` — does this package directory declare a Node test suite?
- `Get-DatrixTestablePackageNames` — packages carrying a suite: a `tests/` folder (pytest) or a `package.json` with a `test` script (Node) — `test.ps1 -All`
- `Get-DatrixMonoProjectNames` — ordered canonical monorepo packages that exist (e.g. `duplicate.ps1 -Mono`)

## venv.ps1

Virtual environment management with concurrent operation support.

### Key Functions

```powershell
# Source the module
. .\common\venv.ps1

# Ensure venv exists and is activated (creates if needed)
Ensure-DatrixVenv

# Get venv path
$venvPath = Get-DatrixVenvPath # Returns D:\datrix\.venv

# Install a single package in editable mode
Install-DatrixPackage -PackageName "datrix-common"

# Ensure all packages are installed (with change detection)
Ensure-DatrixPackagesInstalled

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
# Standard script header
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"

# Shared script helpers (also loads DatrixPaths.psm1)
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

# Source venv utilities
. (Join-Path $commonDir "venv.ps1")

# Monorepo workspace root (optional: use module helper instead of both)
$workspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

# Activate venv and ensure packages
$venvActivated = Ensure-DatrixVenv
$packagesInstalled = Ensure-DatrixPackagesInstalled -SkipIfInstalled
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
