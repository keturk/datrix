# Common Modules

Shared PowerShell modules and utilities used by all scripts.

## Files

| File | Description |
|------|-------------|
| `DatrixPaths.psm1` | Path discovery for workspace and repository directories |
| `DatrixScriptCommon.psm1` | Shared project lists and `Normalize-DatrixProjectInput` (imports `DatrixPaths.psm1`) |
| `venv.ps1` | Virtual environment management (creation, activation, package installation) |
| `CleanupUtils.psm1` | Cleanup utilities (empty parents, confirmation, folder tree display, size formatting) |

## DatrixPaths.psm1

PowerShell module for discovering datrix workspace paths.

### Functions

```powershell
# Get workspace root (parent of datrix folder)
$root = Get-DatrixWorkspaceRoot

# Get list of repository names
$repos = Get-DatrixDirectories
# Returns: @("datrix", "datrix-cli", "datrix-common", "datrix-language", ...)

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
- `Normalize-DatrixProjectInput` — path or bare package name to directory name
- `Get-DatrixPackageNamesGlob` — metrics `-All` (`datrix-*` on disk)
- `Get-DatrixPackageNamesGlobWithPyProject` — like above, requires `pyproject.toml` (dependency help text)
- `Get-DatrixTestablePackageNames` — canonical repos with a `tests/` folder (`test.ps1 -All`)
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
