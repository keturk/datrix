<#
.SYNOPSIS
 Virtual environment management utilities for Datrix scripts.

.DESCRIPTION
 Provides functions to ensure a virtual environment exists at D:\datrix\.venv,
 create it if needed, and activate it.

 Offline / no-network mode:
 Set environment variable DATRIX_OFFLINE to 1, true, or yes (case-insensitive).
 Scripts that dot-source this file should skip pip installs and only verify that
 dependencies are already present; otherwise they fail with a clear message.
 Orchestrators may set DATRIX_OFFLINE for child processes.

.NOTES
 Usage: . .\datrix\scripts\common\venv.ps1
 Then call: Ensure-DatrixVenv
#>

# Script-level variable to track if this process holds the lock
$script:DatrixPackageLockHeld = $false
$script:DatrixPackageLockFile = $null

# Register cleanup handler for lock release on script termination (Ctrl-C, errors, exit)
# This ensures the lock file is removed even if the script is interrupted
$script:DatrixLockCleanupRegistered = $false

function Test-DatrixVenvVerbose {
 $raw = $env:DATRIX_VENV_VERBOSE
 if ($null -eq $raw -or [string]::IsNullOrWhiteSpace($raw)) {
 return $false
 }
 $t = $raw.Trim().ToLowerInvariant()
 return ($t -eq "1") -or ($t -eq "true") -or ($t -eq "yes")
}

function Write-DatrixVenvInfo {
 param(
 [AllowEmptyString()]
 [string]$Message = "",
 [ConsoleColor]$ForegroundColor = [ConsoleColor]::White
 )

 if (Test-DatrixVenvVerbose) {
 Write-Host $Message -ForegroundColor $ForegroundColor
 }
}

function Write-DatrixVenvWarning {
 param(
 [string]$Message
 )

 if (Test-DatrixVenvVerbose) {
 Write-Warning $Message
 }
}

function Register-DatrixLockCleanup {
 if ($script:DatrixLockCleanupRegistered) {
 return
 }

 # Register for PowerShell exit event
 Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
 if ($script:DatrixPackageLockHeld -and $script:DatrixPackageLockFile) {
 try {
 if (Test-Path $script:DatrixPackageLockFile) {
 Remove-Item -Path $script:DatrixPackageLockFile -Force -ErrorAction SilentlyContinue
 }
 } catch { }
 $script:DatrixPackageLockHeld = $false
 }
 } -SupportEvent | Out-Null

 $script:DatrixLockCleanupRegistered = $true
}

# Auto-register cleanup when module is loaded
Register-DatrixLockCleanup

# True when DATRIX_OFFLINE is set to a truthy value (1, true, yes).
function Test-DatrixOfflineMode {
 <#
 .SYNOPSIS
 Returns whether Datrix scripts should avoid pip and other network installs.
 .NOTES
 Respects environment variable DATRIX_OFFLINE.
 #>
 $raw = $env:DATRIX_OFFLINE
 if ($null -eq $raw -or [string]::IsNullOrWhiteSpace($raw)) {
 return $false
 }
 $t = $raw.Trim().ToLowerInvariant()
 return ($t -eq "1") -or ($t -eq "true") -or ($t -eq "yes")
}

# Get Datrix root directory
function Get-DatrixRoot {
 <#
 .SYNOPSIS
 Find the Datrix root directory.
 #>
 $scriptPath = $PSScriptRoot
 # Go up: common -> scripts -> datrix -> datrix-root
 $datrixRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptPath))
 return $datrixRoot
}

# Map a package directory name to its Python import name
function Get-DatrixModuleName {
 <#
 .SYNOPSIS
 Get the Python module name for a Datrix package directory name.

 .DESCRIPTION
 Every Datrix package maps its directory name to its import name by the same rule:
 datrix-codegen-python -> datrix_codegen_python. Derived, not tabulated, so a new
 datrix-codegen-<lang> package needs no edit here.

 .PARAMETER PackageName
 Package directory name, e.g. "datrix-codegen-python".
 #>
 param(
 [Parameter(Mandatory=$true)]
 [string]$PackageName
 )

 return $PackageName.Replace("-", "_")
}

# Get venv path
function Get-DatrixVenvPath {
 <#
 .SYNOPSIS
 Get the path to the Datrix virtual environment.
 #>
 $datrixRoot = Get-DatrixRoot
 return Join-Path $datrixRoot ".venv"
}

# Get package lock file path
function Get-DatrixPackageLockPath {
 <#
 .SYNOPSIS
 Get the path to the package installation lock file.
 #>
 $datrixRoot = Get-DatrixRoot
 return Join-Path $datrixRoot ".venv-package.lock"
}

function Get-DatrixPythonCachePrefix {
 <#
 .SYNOPSIS
 Get the shared Python bytecode cache directory for Datrix scripts.
 #>
 $datrixRoot = Get-DatrixRoot
 return Join-Path $datrixRoot ".pycache-verify"
}

function Set-DatrixPythonCachePrefix {
 <#
 .SYNOPSIS
 Redirect Python bytecode emitted by Datrix script wrappers out of source trees.
 .NOTES
 Respects an existing PYTHONPYCACHEPREFIX set by the caller.
 #>
 if ($null -ne $env:PYTHONPYCACHEPREFIX -and -not [string]::IsNullOrWhiteSpace($env:PYTHONPYCACHEPREFIX)) {
  return
 }

 $cachePrefix = Get-DatrixPythonCachePrefix
 if (-not (Test-Path -LiteralPath $cachePrefix)) {
  $null = New-Item -ItemType Directory -Path $cachePrefix -Force
 }
 $env:PYTHONPYCACHEPREFIX = $cachePrefix
}

# Acquire package installation lock
function Enter-DatrixPackageLock {
 <#
 .SYNOPSIS
 Acquire an exclusive lock for package installation operations.
 This prevents concurrent pip operations that can corrupt the venv.
 .PARAMETER TimeoutSeconds
 Maximum time to wait for the lock. Default is 120 seconds.
 .PARAMETER StaleSeconds
 Consider lock stale if older than this. Default is 300 seconds (5 minutes).
 .RETURNS
 $true if lock acquired, $false if timeout or error.
 #>
 param(
 [int]$TimeoutSeconds = 120,
 [int]$StaleSeconds = 300
 )

 $lockPath = Get-DatrixPackageLockPath
 $startTime = Get-Date
 $currentPid = $PID

 while ($true) {
 # Check if we already hold the lock
 if ($script:DatrixPackageLockHeld -and $script:DatrixPackageLockFile -eq $lockPath) {
 return $true
 }

 # Check for timeout
 $elapsed = ((Get-Date) - $startTime).TotalSeconds
 if ($elapsed -gt $TimeoutSeconds) {
 Write-DatrixVenvWarning "Timeout waiting for package lock after $TimeoutSeconds seconds"
 return $false
 }

 # Check if lock file exists
 if (Test-Path $lockPath) {
 try {
 $lockContent = Get-Content -Path $lockPath -Raw -ErrorAction Stop
 $lockData = $lockContent | ConvertFrom-Json -ErrorAction Stop
 $lockTime = [DateTime]::Parse($lockData.timestamp)
 $lockPid = $lockData.pid
 $lockAge = ((Get-Date) - $lockTime).TotalSeconds

 # Check if lock is stale (process died or took too long)
 if ($lockAge -gt $StaleSeconds) {
 Write-DatrixVenvInfo "Removing stale package lock (age: $([int]$lockAge)s, pid: $lockPid)" -ForegroundColor Yellow
 Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
 }
 # Check if locking process is still running
 elseif (-not (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
 Write-DatrixVenvInfo "Removing orphaned package lock (pid $lockPid no longer running)" -ForegroundColor Yellow
 Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
 }
 else {
 # Lock is held by another active process - wait
 $waitTime = [int]$elapsed
 Write-DatrixVenvInfo "Waiting for package lock (held by pid $lockPid for $([int]$lockAge)s, waited ${waitTime}s)..." -ForegroundColor Cyan
 Start-Sleep -Seconds 2
 continue
 }
 } catch {
 # Corrupted lock file - remove it
 Write-DatrixVenvInfo "Removing corrupted package lock file" -ForegroundColor Yellow
 Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
 }
 }

 # Try to acquire lock using atomic file creation
 try {
 $lockData = @{
 pid = $currentPid
 timestamp = (Get-Date).ToString("o")
 script = $MyInvocation.ScriptName
 } | ConvertTo-Json -Compress

 # Use .NET FileStream with FileShare.None for atomic creation
 $stream = [System.IO.File]::Open(
 $lockPath,
 [System.IO.FileMode]::CreateNew,
 [System.IO.FileAccess]::Write,
 [System.IO.FileShare]::None
 )
 try {
 $writer = New-Object System.IO.StreamWriter($stream)
 $writer.Write($lockData)
 $writer.Flush()
 } finally {
 $stream.Close()
 }

 # Lock acquired successfully
 $script:DatrixPackageLockHeld = $true
 $script:DatrixPackageLockFile = $lockPath
 Write-DatrixVenvInfo "Package lock acquired (pid: $currentPid)" -ForegroundColor Green
 return $true
 } catch [System.IO.IOException] {
 # File already exists (race condition) - retry
 Start-Sleep -Milliseconds 500
 continue
 } catch {
 Write-DatrixVenvWarning "Error acquiring package lock: $_"
 Start-Sleep -Seconds 1
 continue
 }
 }
}

# Release package installation lock
function Exit-DatrixPackageLock {
 <#
 .SYNOPSIS
 Release the package installation lock.
 #>
 $lockPath = Get-DatrixPackageLockPath

 if (-not $script:DatrixPackageLockHeld) {
 return
 }

 if (Test-Path $lockPath) {
 try {
 # Verify we own the lock before removing
 $lockContent = Get-Content -Path $lockPath -Raw -ErrorAction Stop
 $lockData = $lockContent | ConvertFrom-Json -ErrorAction Stop
 if ($lockData.pid -eq $PID) {
 Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
 Write-DatrixVenvInfo "Package lock released (pid: $PID)" -ForegroundColor Green
 }
 } catch {
 # Error reading lock - try to remove anyway if it's ours
 Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
 }
 }

 $script:DatrixPackageLockHeld = $false
 $script:DatrixPackageLockFile = $null
}

# Check if venv exists
function Test-DatrixVenvExists {
 <#
 .SYNOPSIS
 Check if the Datrix virtual environment exists.
 #>
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"
 return (Test-Path $pythonExe)
}

# Check if venv is active
function Test-DatrixVenvActive {
 <#
 .SYNOPSIS
 Check if a virtual environment is currently active.
 #>
 return ($null -ne $env:VIRTUAL_ENV)
}

# Create venv
function New-DatrixVenv {
 <#
 .SYNOPSIS
 Create the Datrix virtual environment.
 #>
 param(
 [switch]$Force
 )

 $venvPath = Get-DatrixVenvPath
 $datrixRoot = Get-DatrixRoot

 if ((Test-DatrixVenvExists) -and (-not $Force)) {
 Write-DatrixVenvInfo "Virtual environment already exists at: $venvPath" -ForegroundColor Green
 return $true
 }

 if ($Force -and (Test-Path $venvPath)) {
 Write-DatrixVenvInfo "Removing existing virtual environment..." -ForegroundColor Yellow
 Remove-Item -Recurse -Force $venvPath
 }

 Write-DatrixVenvInfo "Creating virtual environment at: $venvPath" -ForegroundColor Cyan
 Write-DatrixVenvInfo ""

 # Create venv
 $result = & python -m venv $venvPath
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to create virtual environment"
 return $false
 }

 Write-DatrixVenvInfo "Virtual environment created successfully" -ForegroundColor Green
 return $true
}

# Activate venv
function Enable-DatrixVenv {
 <#
 .SYNOPSIS
 Activate the Datrix virtual environment.
 #>
 $venvPath = Get-DatrixVenvPath
 $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

 if (-not (Test-Path $activateScript)) {
 Write-Error "Virtual environment not found at: $venvPath"
 return $false
 }

 Write-DatrixVenvInfo "Activating virtual environment: $venvPath" -ForegroundColor Cyan
 & $activateScript

 if ($env:VIRTUAL_ENV) {
 Write-DatrixVenvInfo "Virtual environment activated: $env:VIRTUAL_ENV" -ForegroundColor Green
 return $true
 } else {
 Write-DatrixVenvWarning "Virtual environment activation may have failed"
 return $false
 }
}

# Deactivate venv
function Disable-DatrixVenv {
 <#
 .SYNOPSIS
 Deactivate the current virtual environment.
 #>
 if ($env:VIRTUAL_ENV) {
 Write-DatrixVenvInfo "Deactivating virtual environment..." -ForegroundColor Cyan
 try {
 if (Get-Command deactivate -ErrorAction SilentlyContinue) {
 deactivate
 } else {
 $env:VIRTUAL_ENV = $null
 $env:VIRTUAL_ENV_PROMPT = $null
 if ($env:_OLD_VIRTUAL_PATH) {
 $env:PATH = $env:_OLD_VIRTUAL_PATH
 $env:_OLD_VIRTUAL_PATH = $null
 }
 }
 } catch {
 $env:VIRTUAL_ENV = $null
 $env:VIRTUAL_ENV_PROMPT = $null
 }
 }
}

# Install package in editable mode
function Install-DatrixPackage {
 <#
 .SYNOPSIS
 Install a Datrix package in editable mode with dev dependencies.
 Uses file-based locking to prevent concurrent pip operations.
 #>
 param(
 [Parameter(Mandatory=$true)]
 [string]$PackageName,

 [switch]$NoDev
 )

 $datrixRoot = Get-DatrixRoot
 $packagePath = Join-Path $datrixRoot $PackageName

 if (-not (Test-Path $packagePath)) {
 Write-Error "Package not found: $packagePath"
 return $false
 }

 $pyprojectToml = Join-Path $packagePath "pyproject.toml"
 if (-not (Test-Path $pyprojectToml)) {
 Write-Error "pyproject.toml not found in: $packagePath"
 return $false
 }

 if (Test-DatrixOfflineMode) {
 Write-Error "DATRIX_OFFLINE is set: pip installs are disabled. Unset DATRIX_OFFLINE and install packages while online."
 return $false
 }

 # Acquire lock if not already held (avoid double-locking when called from Ensure-DatrixPackagesInstalled)
 $acquiredLockHere = $false
 if (-not $script:DatrixPackageLockHeld) {
 $lockAcquired = Enter-DatrixPackageLock -TimeoutSeconds 120 -StaleSeconds 300
 if (-not $lockAcquired) {
 Write-Error "Could not acquire package lock for installing $PackageName"
 return $false
 }
 $acquiredLockHere = $true
 }

 # Clean corrupted packages before installing (~ prefixed directories)
 Remove-CorruptedPipPackages

 try {
 Write-DatrixVenvInfo "Installing $PackageName in editable mode..." -ForegroundColor Cyan

 # Ensure build dependencies are available (required for --no-build-isolation)
 $oldErrorActionPreference = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show setuptools 2>&1
 $setuptoolsInstalled = $LASTEXITCODE -eq 0
 $null = & pip show wheel 2>&1
 $wheelInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErrorActionPreference

 if (-not $setuptoolsInstalled -or -not $wheelInstalled) {
 Write-DatrixVenvInfo "Installing build dependencies (setuptools, wheel)..." -ForegroundColor Cyan
 & pip install --upgrade setuptools wheel 2>&1 | Out-Null
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to install build dependencies (setuptools, wheel)"
 return $false
 }
 }

 # Use a custom temp directory to avoid Windows permission issues
 $customTemp = Join-Path $datrixRoot ".tmp"
 if (-not (Test-Path $customTemp)) {
 $null = New-Item -ItemType Directory -Path $customTemp -Force
 }
 
 # Create subdirectories for pip's various temp needs
 $pipCacheDir = Join-Path $customTemp "pip-cache"
 $null = New-Item -ItemType Directory -Path $pipCacheDir -Force -ErrorAction SilentlyContinue
 
 $oldTmp = $env:TMP
 $oldTemp = $env:TEMP
 $oldTmpdir = $env:TMPDIR
 try {
 # Set all temp-related environment variables that pip might use
 $env:TMP = $customTemp
 $env:TEMP = $customTemp
 $env:TMPDIR = $customTemp
 $env:TMPDIR_WIN = $customTemp
 
 # Run pip and capture all output
 $ErrorActionPreference = 'Continue'
 $pipOutput = @()
 try {
 if ($NoDev) {
 # Capture all output first
 # Use explicit cache directory and let TMPDIR control build directory
 $pipOutput = & pip install --cache-dir $pipCacheDir --no-build-isolation -e $packagePath 2>&1
 } else {
 # Capture all output first
 # Use explicit cache directory and let TMPDIR control build directory
 $pipOutput = & pip install --cache-dir $pipCacheDir --no-build-isolation -e "$packagePath[dev]" 2>&1
 }
 } catch {
 # Ignore warnings that are caught as exceptions
 if ($_.Exception.Message -match "WARNING:") {
 # Non-fatal warning, continue
 } else {
 throw
 }
 }
 } finally {
 if ($oldTmp) { $env:TMP = $oldTmp } else { Remove-Item env:TMP -ErrorAction SilentlyContinue }
 if ($oldTemp) { $env:TEMP = $oldTemp } else { Remove-Item env:TEMP -ErrorAction SilentlyContinue }
 if ($oldTmpdir) { $env:TMPDIR = $oldTmpdir } else { Remove-Item env:TMPDIR -ErrorAction SilentlyContinue }
 if ($env:TMPDIR_WIN) { Remove-Item env:TMPDIR_WIN -ErrorAction SilentlyContinue }
 }

 # Check if package was actually installed (even if pip reported an error)
 # Sometimes pip fails due to temp directory cleanup issues but the package is still installed
 $venvPath = Get-DatrixVenvPath
 $packageInstalled = $false

 # Brief delay to let Windows file system sync (editable installs create .pth files)
 Start-Sleep -Milliseconds 500

 # Check if package is importable (most reliable check)
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"
 if (Test-Path $pythonExe) {
 $moduleName = Get-DatrixModuleName -PackageName $PackageName

 # Check if pip output indicates success first
 $pipSucceeded = $false
 $pipOutputStr = $pipOutput -join "`n"
 if ($pipOutputStr -match "Successfully installed.*$PackageName") {
 $pipSucceeded = $true
 }

 # Check if module can be imported - simple import test
 $importError = & $pythonExe -c "import $moduleName" 2>&1
 if ($LASTEXITCODE -eq 0) {
 $packageInstalled = $true
 } elseif ($pipSucceeded) {
 # Pip succeeded but import failed - still treat as success
 # This can happen if the module has optional import-time dependencies
 Write-DatrixVenvInfo "Note: pip installed $PackageName but import test failed:" -ForegroundColor Yellow
 Write-DatrixVenvInfo ($importError | Out-String) -ForegroundColor Yellow
 Write-DatrixVenvInfo "Continuing since pip reported success." -ForegroundColor Yellow
 $packageInstalled = $true
 }
 }

 # The key check is whether pip succeeded or the package is importable
 # pip exit codes can be unreliable on Windows (temp cleanup issues)
 if ($packageInstalled) {
 Write-DatrixVenvInfo "$PackageName installed successfully" -ForegroundColor Green
 # Update marker file to record successful installation
 $markerDir = Join-Path $venvPath ".datrix-markers"
 if (-not (Test-Path $markerDir)) {
 $null = New-Item -ItemType Directory -Path $markerDir -Force
 }
 $markerPath = Join-Path $markerDir "$PackageName.marker"
 $null = Set-Content -Path $markerPath -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
 return $true
 } else {
 # Installation failed - show detailed error output
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Red
 Write-Host "PIP INSTALLATION FAILED for $PackageName" -ForegroundColor Red
 Write-Host "========================================" -ForegroundColor Red
 Write-Host "Exit code: $LASTEXITCODE" -ForegroundColor Red
 Write-Host ""
 Write-Host "Pip output:" -ForegroundColor Yellow
 $pipOutput | ForEach-Object {
 if ($_ -match "ERROR|error|Error|FAILED|Failed|failed|Exception|Traceback") {
 Write-Host $_ -ForegroundColor Red
 } else {
 Write-Host $_
 }
 }
 Write-Host ""
 Write-Host "Package path: $packagePath" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Red
 Write-Host ""
 
 # Check if this is a permission error
 $isPermissionError = $false
 $pipOutput | ForEach-Object {
 if ($_ -match "Permission denied|Errno 13|Access is denied") {
 $isPermissionError = $true
 }
 }
 
 if ($isPermissionError) {
 Write-Host "This appears to be a permission error with temporary directories." -ForegroundColor Yellow
 Write-Host "Suggestions:" -ForegroundColor Yellow
 Write-Host " 1. Clean up temp directories: Remove-Item -Recurse -Force `$env:TEMP\pip-* -ErrorAction SilentlyContinue" -ForegroundColor Cyan
 Write-Host " 2. Run PowerShell as Administrator and try again" -ForegroundColor Cyan
 Write-Host " 3. The script uses a custom temp directory at: $customTemp" -ForegroundColor Cyan
 Write-Host " Ensure this directory is writable" -ForegroundColor Cyan
 }
 
 Write-Error "Failed to install $PackageName (exit code: $LASTEXITCODE)"
 return $false
 }
 } finally {
 # Release lock if we acquired it in this function
 if ($acquiredLockHere) {
 Exit-DatrixPackageLock
 }
 }
}

# Check that the full Datrix workspace is present (sibling repos)
function Test-DatrixWorkspacePresent {
 <#
 .SYNOPSIS
 Validates that the required Datrix repositories exist alongside this repo.
 Returns $false and prints a helpful message if any are missing.
 #>
 $datrixRoot = Get-DatrixRoot
 $requiredRepos = @(
 "datrix-cli",
 "datrix-common",
 "datrix-codegen-component",
 "datrix-codegen-common",
 "datrix-codegen-python",
 "datrix-codegen-sql",
 "datrix-codegen-typescript",
 "datrix-language",
 "datrix-codegen-aws",
 "datrix-codegen-azure",
 "datrix-codegen-docker"
 )

 $missing = @()
 foreach ($repo in $requiredRepos) {
 $repoPath = Join-Path $datrixRoot $repo
 if (-not (Test-Path $repoPath)) {
 $missing += $repo
 }
 }

 if ($missing.Count -gt 0) {
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Red
 Write-Host " DATRIX WORKSPACE NOT FOUND" -ForegroundColor Red
 Write-Host "========================================" -ForegroundColor Red
 Write-Host ""
 Write-Host "This is the Datrix showcase repository containing documentation," -ForegroundColor Yellow
 Write-Host "examples, and development scripts." -ForegroundColor Yellow
 Write-Host ""
 Write-Host "The scripts require the full Datrix workspace to function." -ForegroundColor Yellow
 Write-Host "The following repositories are missing:" -ForegroundColor Yellow
 Write-Host ""
 foreach ($repo in $missing) {
 Write-Host "  - $repo" -ForegroundColor Red
 }
 Write-Host ""
 Write-Host "To explore what Datrix generates, browse the examples/ directory" -ForegroundColor Cyan
 Write-Host "and the generated output in examples/02-domains/*/generated/." -ForegroundColor Cyan
 Write-Host ""
 Write-Host "For access to the full platform, visit:" -ForegroundColor Cyan
 Write-Host "  https://github.com/keturk" -ForegroundColor White
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Red
 Write-Host ""
 return $false
 }

 return $true
}

# Main function: Ensure venv exists and is active
function Ensure-DatrixVenv {
 <#
 .SYNOPSIS
 Ensure the Datrix virtual environment exists and is active.
 Creates it if it doesn't exist.

 .EXAMPLE
 Ensure-DatrixVenv
 #>

 # Verify the full workspace is present before doing anything
 if (-not (Test-DatrixWorkspacePresent)) {
 return $false
 }

 Set-DatrixPythonCachePrefix

 $venvPath = Get-DatrixVenvPath

 # Check if venv exists, create if not
 if (-not (Test-DatrixVenvExists)) {
 Write-DatrixVenvInfo "Virtual environment not found at: $venvPath" -ForegroundColor Yellow
 Write-DatrixVenvInfo "Creating virtual environment..." -ForegroundColor Cyan
 Write-DatrixVenvInfo ""

 $created = New-DatrixVenv
 if (-not $created) {
 return $false
 }
 Write-DatrixVenvInfo ""
 }

 # Activate venv if not already active
 if (-not (Test-DatrixVenvActive)) {
 $activated = Enable-DatrixVenv
 if (-not $activated) {
 return $false
 }
 } else {
 # Check if the active venv is the Datrix venv
 if ($env:VIRTUAL_ENV -ne $venvPath) {
 Write-DatrixVenvInfo "Different virtual environment is active: $env:VIRTUAL_ENV" -ForegroundColor Yellow
 Write-DatrixVenvInfo "Switching to Datrix virtual environment..." -ForegroundColor Cyan
 Disable-DatrixVenv
 $activated = Enable-DatrixVenv
 if (-not $activated) {
 return $false
 }
 } else {
 Write-DatrixVenvInfo "Using active virtual environment: $env:VIRTUAL_ENV" -ForegroundColor Green
 }
 }

 return $true
}

# Get list of all Datrix packages
function Get-DatrixPackages {
 <#
 .SYNOPSIS
 Get the installable Datrix package directories, in dependency order.

 .DESCRIPTION
 Discovers every "datrix-*" directory carrying a pyproject.toml rather than hardcoding the
 set. Datrix is a multi-language, multi-platform generator: a new datrix-codegen-<lang>
 package must install into the shared venv as soon as it has a pyproject.toml, with no edit
 here. A repo that has been cloned but not yet populated has no pyproject.toml and is
 correctly skipped until it does.

 The foundation packages are installed first, in the order the dependency graph requires;
 every other discovered package follows in sorted order.
 #>
 $datrixRoot = Get-DatrixRoot

 $foundationOrder = @(
 "datrix-common",
 "datrix-language",
 "datrix-codegen-common",
 "datrix-cli"
 )

 $installable = @()
 Get-ChildItem -Path $datrixRoot -Directory |
 Where-Object {
 $_.Name -like "datrix-*" -and
 (Test-Path (Join-Path $_.FullName "pyproject.toml"))
 } |
 ForEach-Object { $installable += $_.Name }

 $ordered = @()
 foreach ($name in $foundationOrder) {
 if ($installable -contains $name) {
 $ordered += $name
 }
 }
 foreach ($name in ($installable | Sort-Object)) {
 if ($ordered -notcontains $name) {
 $ordered += $name
 }
 }

 return $ordered
}

# Get install marker path for a package
function Get-PackageInstallMarkerPath {
 <#
 .SYNOPSIS
 Get the path to the install marker file for a package.
 #>
 param(
 [Parameter(Mandatory=$true)]
 [string]$PackageName
 )

 $venvPath = Get-DatrixVenvPath
 $markerDir = Join-Path $venvPath ".datrix-markers"

 if (-not (Test-Path $markerDir)) {
 $null = New-Item -ItemType Directory -Path $markerDir -Force
 }

 return Join-Path $markerDir "$PackageName.marker"
}

# Check if package needs reinstallation
function Test-PackageNeedsReinstall {
 <#
 .SYNOPSIS
 Check if a package needs reinstallation based on pyproject.toml or source file changes.
 Also verifies the package is actually importable (not just that marker exists).
 Source file checks exclude .generated, tests, __pycache__, .pytest_cache to avoid
 unnecessary reinstalls when coverage or tools touch those paths.
 #>
 param(
 [Parameter(Mandatory=$true)]
 [string]$PackageName
 )

 $datrixRoot = Get-DatrixRoot
 $packagePath = Join-Path $datrixRoot $PackageName
 $pyprojectToml = Join-Path $packagePath "pyproject.toml"

 if (-not (Test-Path $pyprojectToml)) {
 return $false
 }

 $markerPath = Get-PackageInstallMarkerPath -PackageName $PackageName

 # If no marker exists, package needs installation
 if (-not (Test-Path $markerPath)) {
 return $true
 }

 # Verify the package is actually importable (marker might exist but install is broken)
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"
 if (Test-Path $pythonExe) {
 $moduleName = Get-DatrixModuleName -PackageName $PackageName

 # Simple import test - use single-line command to avoid Windows heredoc issues
 $oldErrorActionPreference = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & $pythonExe -c "import $moduleName" 2>&1
 $importExitCode = $LASTEXITCODE
 $ErrorActionPreference = $oldErrorActionPreference

 if ($importExitCode -ne 0) {
 # Package is not importable despite marker existing - needs reinstall
 return $true
 }
 }

 $markerTime = (Get-Item $markerPath).LastWriteTime

 # Check pyproject.toml
 $pyprojectTime = (Get-Item $pyprojectToml).LastWriteTime
 if ($pyprojectTime -gt $markerTime) {
 return $true
 }

 # Check source files in src directory. Exclude paths that are not real package source
 # (e.g. .generated, tests, __pycache__) so that coverage/tools touching them do not trigger reinstalls.
 $srcPath = Join-Path $packagePath "src"
 if (Test-Path $srcPath) {
 $excludePattern = '(\\|/)__(pycache__|pycache)(\\|/)|(\\|/)\.(generated|pytest_cache)(\\|/)|(\\|/)tests(\\|/)'
 $newestSourceFile = Get-ChildItem -Path $srcPath -Recurse -Filter "*.py" -File |
 Where-Object { $_.FullName -notmatch $excludePattern } |
 Sort-Object LastWriteTime -Descending |
 Select-Object -First 1

 if ($newestSourceFile -and ($newestSourceFile.LastWriteTime -gt $markerTime)) {
 return $true
 }
 }

 return $false
}

# Update install marker for a package
function Update-PackageInstallMarker {
 <#
 .SYNOPSIS
 Update the install marker after successful package installation.
 #>
 param(
 [Parameter(Mandatory=$true)]
 [string]$PackageName
 )

 $markerPath = Get-PackageInstallMarkerPath -PackageName $PackageName

 # Write current timestamp to marker file
 $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
 Set-Content -Path $markerPath -Value $timestamp -Force
}

# Remove corrupted pip package directories (those with ~ prefix)
function Remove-CorruptedPipPackages {
 <#
 .SYNOPSIS
 Remove corrupted pip package directories from site-packages.
 These are leftover directories from interrupted pip installations
 and cause "WARNING: Ignoring invalid distribution" messages.
 #>
 $venvPath = Get-DatrixVenvPath
 $sitePackages = Join-Path $venvPath "Lib\site-packages"

 if (-not (Test-Path $sitePackages)) {
 return
 }

 # Find directories starting with ~
 $corruptedDirs = Get-ChildItem -Path $sitePackages -Directory -Filter "~*" -ErrorAction SilentlyContinue

 if ($corruptedDirs) {
 foreach ($dir in $corruptedDirs) {
 try {
 Remove-Item -Recurse -Force $dir.FullName -ErrorAction Stop
 Write-DatrixVenvInfo "Removed corrupted package directory: $($dir.Name)" -ForegroundColor Yellow
 } catch {
 Write-DatrixVenvWarning "Could not remove corrupted directory: $($dir.FullName)"
 }
 }
 }
}

# Check if editable install .pth files exist for datrix packages
function Test-EditableInstallsIntact {
 <#
 .SYNOPSIS
 Check if editable install .pth files exist in site-packages.
 Returns $true if at least one datrix .pth file exists, $false if all are missing.
 #>
 $venvPath = Get-DatrixVenvPath
 $sitePackages = Join-Path $venvPath "Lib\site-packages"

 if (-not (Test-Path $sitePackages)) {
 return $false
 }

 # Look for any .pth files that might contain datrix paths
 # Editable installs create .pth files or __editable__ directories
 $pthFiles = Get-ChildItem -Path $sitePackages -Filter "*.pth" -File -ErrorAction SilentlyContinue
 $editableDirs = Get-ChildItem -Path $sitePackages -Directory -Filter "__editable__*datrix*" -ErrorAction SilentlyContinue
 $datrixEggLinks = Get-ChildItem -Path $sitePackages -Filter "datrix*.egg-link" -File -ErrorAction SilentlyContinue

 # Check if any .pth file contains a datrix path
 foreach ($pth in $pthFiles) {
 $content = Get-Content -Path $pth.FullName -ErrorAction SilentlyContinue
 if ($content -match "datrix") {
 return $true
 }
 }

 # Check for editable install directories (newer pip style)
 if ($editableDirs -and $editableDirs.Count -gt 0) {
 return $true
 }

 # Check for egg-link files (older pip style)
 if ($datrixEggLinks -and $datrixEggLinks.Count -gt 0) {
 return $true
 }

 return $false
}

# Repair broken editable installs
function Repair-BrokenEditableInstalls {
 <#
 .SYNOPSIS
 Detect and repair broken editable installs where markers exist but .pth files are missing.
 This can happen due to interrupted pip operations or file system issues.
 .RETURNS
 $true if repair was needed and succeeded (or no repair needed), $false if repair failed.
 #>
 param(
 [int]$RetryDelaySeconds = 2,
 [int]$MaxRetries = 3
 )

 $venvPath = Get-DatrixVenvPath
 $markerDir = Join-Path $venvPath ".datrix-markers"

 # Check if we have markers but no editable installs
 $hasMarkers = (Test-Path $markerDir) -and ((Get-ChildItem -Path $markerDir -Filter "*.marker" -ErrorAction SilentlyContinue).Count -gt 0)
 $hasEditableInstalls = Test-EditableInstallsIntact

 if (-not $hasMarkers) {
 # No markers, nothing to repair - fresh install will happen
 return $true
 }

 if ($hasEditableInstalls) {
 # Editable installs are intact, no repair needed
 return $true
 }

 # Broken state detected: markers exist but editable installs are missing
 Write-DatrixVenvInfo ""
 Write-DatrixVenvInfo "========================================" -ForegroundColor Yellow
 Write-DatrixVenvInfo "DETECTED: Broken editable installs" -ForegroundColor Yellow
 Write-DatrixVenvInfo "========================================" -ForegroundColor Yellow
 Write-DatrixVenvInfo "Markers exist but .pth files are missing." -ForegroundColor Yellow
 Write-DatrixVenvInfo "This can happen due to interrupted pip operations." -ForegroundColor Yellow
 Write-DatrixVenvInfo ""
 Write-DatrixVenvInfo "Initiating automatic repair..." -ForegroundColor Cyan

 # Wait before attempting repair (allows any pending file operations to complete)
 Write-DatrixVenvInfo "Waiting $RetryDelaySeconds seconds before repair..." -ForegroundColor Cyan
 Start-Sleep -Seconds $RetryDelaySeconds

 # Remove all marker files to force reinstallation
 Write-DatrixVenvInfo "Removing stale marker files..." -ForegroundColor Cyan
 try {
 Remove-Item -Path (Join-Path $markerDir "*.marker") -Force -ErrorAction Stop
 Write-DatrixVenvInfo "Marker files removed successfully." -ForegroundColor Green
 } catch {
 Write-DatrixVenvWarning "Could not remove all marker files: $_"
 # Try to remove the entire marker directory
 try {
 Remove-Item -Recurse -Force $markerDir -ErrorAction Stop
 Write-DatrixVenvInfo "Marker directory removed." -ForegroundColor Green
 } catch {
 Write-Error "Failed to remove marker directory: $_"
 return $false
 }
 }

 # Clean up any corrupted pip packages
 Remove-CorruptedPipPackages

 Write-DatrixVenvInfo ""
 Write-DatrixVenvInfo "Repair preparation complete. Packages will be reinstalled." -ForegroundColor Green
 Write-DatrixVenvInfo "========================================" -ForegroundColor Yellow
 Write-DatrixVenvInfo ""

 return $true
}

# Test if datrix command works (verifies console script entry point)
function Test-DatrixCommand {
 <#
 .SYNOPSIS
 Test if the datrix command works by running 'datrix --version'.
 This verifies the console script entry point is properly installed.
 .RETURNS
 $true if datrix command works, $false otherwise.
 #>
 $venvPath = Get-DatrixVenvPath
 $datrixExe = Join-Path $venvPath "Scripts\datrix.exe"

 if (-not (Test-Path $datrixExe)) {
 return $false
 }

 $oldErrorActionPreference = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 try {
 $null = & $datrixExe --version 2>&1
 return $LASTEXITCODE -eq 0
 } catch {
 return $false
 } finally {
 $ErrorActionPreference = $oldErrorActionPreference
 }
}

# Ensure all Datrix packages are installed and up-to-date
function Ensure-DatrixPackagesInstalled {
 <#
 .SYNOPSIS
 Check all Datrix packages and reinstall those with changed pyproject.toml.
 Uses file-based locking to prevent concurrent pip operations.
 .PARAMETER Force
 Force reinstallation of all packages regardless of marker files.
 .PARAMETER SkipIfInstalled
 Skip reinstall checks if packages are already importable. Use this for
 concurrent operations where you know packages are stable and don't want
 to risk mid-run reinstalls.
 .PARAMETER Offline
 Verify packages and CLI only; never run pip. Implied when DATRIX_OFFLINE is set.
 #>
 param(
 [switch]$Force,
 [switch]$SkipIfInstalled,
 [switch]$Offline
 )

 Set-DatrixPythonCachePrefix

 $isOffline = $Offline -or (Test-DatrixOfflineMode)

 if ($isOffline -and $Force) {
 Write-Error "Cannot use -Force with offline mode (DATRIX_OFFLINE environment variable or -Offline switch)."
 return $false
 }

 if ($isOffline) {
 Remove-CorruptedPipPackages

 $packages = Get-DatrixPackages
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 if (-not (Test-Path $pythonExe)) {
 Write-Error "DATRIX_OFFLINE: Python not found in venv at $pythonExe"
 return $false
 }

 $oldErrorActionPreference = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"

 foreach ($package in $packages) {
 $moduleName = $package.Replace("-", "_")
 $null = & $pythonExe -c "import $moduleName" 2>&1
 if ($LASTEXITCODE -ne 0) {
 $ErrorActionPreference = $oldErrorActionPreference
 Write-Error "DATRIX_OFFLINE: package '$package' is not importable. Install editable packages while online, then retry."
 return $false
 }
 if (Test-PackageNeedsReinstall -PackageName $package) {
 $ErrorActionPreference = $oldErrorActionPreference
 Write-Error "DATRIX_OFFLINE: package '$package' is out of date (pyproject.toml or sources changed). Reinstall while online, then retry."
 return $false
 }
 }

 $ErrorActionPreference = $oldErrorActionPreference

 if (-not (Test-DatrixCommand)) {
 Write-Error "DATRIX_OFFLINE: 'datrix --version' failed. Fix the CLI while online (e.g. pip install -e datrix-cli)."
 return $false
 }

 Write-DatrixVenvInfo "Offline mode: Datrix packages and CLI verified (no pip)." -ForegroundColor Green
 return $true
 }

 # If SkipIfInstalled is set, verify packages are importable and check for pyproject.toml changes
 # This is useful for concurrent operations where reinstalls could corrupt the venv
 if ($SkipIfInstalled -and -not $Force) {
 # Clean corrupted packages FIRST before any import tests
 # These ~ prefixed directories can cause Python errors
 Remove-CorruptedPipPackages

 $packages = Get-DatrixPackages
 $allImportable = $true
 $anyNeedsReinstall = $false
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 if (Test-Path $pythonExe) {
 # Suppress errors during import tests - we check exit codes manually
 $oldErrorActionPreference = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"

 foreach ($package in $packages) {
 $moduleName = $package.Replace("-", "_")
 $null = & $pythonExe -c "import $moduleName" 2>&1
 if ($LASTEXITCODE -ne 0) {
 $allImportable = $false
 $ErrorActionPreference = $oldErrorActionPreference
 Write-DatrixVenvInfo "Package '$package' is not importable" -ForegroundColor Yellow
 $ErrorActionPreference = "SilentlyContinue"
 break
 }
 # Also check if pyproject.toml changed (new dependencies)
 if (Test-PackageNeedsReinstall -PackageName $package) {
 $anyNeedsReinstall = $true
 $ErrorActionPreference = $oldErrorActionPreference
 Write-DatrixVenvInfo "Package '$package' has changed pyproject.toml or source files" -ForegroundColor Yellow
 $ErrorActionPreference = "SilentlyContinue"
 }
 }

 $ErrorActionPreference = $oldErrorActionPreference
 } else {
 $allImportable = $false
 }

 if ($allImportable -and -not $anyNeedsReinstall) {
 Write-DatrixVenvInfo "All packages are importable and up-to-date, skipping reinstall (SkipIfInstalled mode)" -ForegroundColor Green
 return $true
 }
 # If not all importable or some need reinstall, fall through to normal installation
 if (-not $allImportable) {
 Write-DatrixVenvInfo "Some packages are not importable, proceeding with installation..." -ForegroundColor Yellow
 } elseif ($anyNeedsReinstall) {
 Write-DatrixVenvInfo "Some packages have changed, proceeding with installation..." -ForegroundColor Yellow
 }
 }

 # Acquire exclusive lock for package operations
 # This prevents race conditions when running generate.ps1 and test.ps1 concurrently
 $lockAcquired = Enter-DatrixPackageLock -TimeoutSeconds 120 -StaleSeconds 300
 if (-not $lockAcquired) {
 Write-Error "Could not acquire package lock - another process may be installing packages"
 return $false
 }

 try {
 # Check for and repair broken editable installs first
 $repairResult = Repair-BrokenEditableInstalls -RetryDelaySeconds 2 -MaxRetries 3
 if (-not $repairResult) {
 Write-Error "Failed to repair broken editable installs"
 return $false
 }

 # Clean up any corrupted pip packages
 Remove-CorruptedPipPackages

 $packages = Get-DatrixPackages
 $reinstalled = @()

 foreach ($package in $packages) {
 $needsReinstall = $Force -or (Test-PackageNeedsReinstall -PackageName $package)

 if ($needsReinstall) {
 Write-DatrixVenvInfo "Package '$package' needs reinstallation (source files changed)" -ForegroundColor Yellow

 # Retry logic for transient failures
 $maxInstallRetries = 2
 $installRetry = 0
 $success = $false

 while (-not $success -and $installRetry -lt $maxInstallRetries) {
 if ($installRetry -gt 0) {
 Write-DatrixVenvInfo "Retrying installation of '$package' (attempt $($installRetry + 1)/$maxInstallRetries)..." -ForegroundColor Yellow
 Start-Sleep -Seconds 2
 }

 $success = Install-DatrixPackage -PackageName $package -NoDev
 $installRetry++
 }

 if ($success) {
 Update-PackageInstallMarker -PackageName $package
 $reinstalled += $package
 } else {
 Write-Error "Failed to reinstall package: $package after $maxInstallRetries attempts"
 return $false
 }
 }
 }

 if ($reinstalled.Count -gt 0) {
 Write-DatrixVenvInfo ""
 Write-DatrixVenvInfo "Reinstalled $($reinstalled.Count) package(s): $($reinstalled -join ', ')" -ForegroundColor Green
 }

 return $true
 } finally {
 # Always release the lock when done
 Exit-DatrixPackageLock
 }
}
