# Common Modules

Shared PowerShell modules and utilities used by all scripts.

## Files

| File | Description |
|------|-------------|
| `DatrixPaths.psm1` | Path discovery for workspace and repository directories |
| `venv.ps1` | Virtual environment management (creation, activation, package installation) |
| `CleanupUtils.psm1` | Cleanup utilities for temporary files |

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

# Import path utilities
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force

# Source venv utilities
. (Join-Path $commonDir "venv.ps1")

# Get paths
$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

# Activate venv and ensure packages
$venvActivated = Ensure-DatrixVenv
$packagesInstalled = Ensure-DatrixPackagesInstalled -SkipIfInstalled
```
