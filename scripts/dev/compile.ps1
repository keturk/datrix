#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compile all Python in Datrix project folders

.DESCRIPTION
 Compiles all Python scripts in Datrix project folders to find syntax and import issues.
 Supports -All (all datrix repositories) or one or more project directory paths.
 Activates the datrix virtual environment and runs compile.py. Ensures virtual environment
 is deactivated even if the script is interrupted (Ctrl-C).

.PARAMETER All
 Compile Python in all datrix repositories (same list as Get-DatrixDirectoryPaths).

.PARAMETER ProjectDir
 One or more project directories to check (positional). Can be names (e.g. datrix-common)
 or full paths. Names are resolved against the workspace root.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\compile.ps1 -All
 Check all Python files in all datrix repositories.

.EXAMPLE
 .\compile.ps1 datrix-common
 Check one project (resolved against workspace root).

.EXAMPLE
 .\compile.ps1 datrix-common datrix-language -Dbg
 Check multiple projects with debug output.

.EXAMPLE
 .\compile.ps1 D:\datrix\datrix-common
 Check one project by full path.
#>

[CmdletBinding()]
param(
 [Parameter()]
 [switch]$All,

 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$ProjectDir = @(),

 [Parameter()]
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\compile.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: compile.py not found at: $pythonScript"
 exit 1
}

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Trap Ctrl-C to ensure proper cleanup (PowerShell.Exiting may not fire on Ctrl-C)
trap {
 Write-Host ""
 Write-Warning "Interrupted by user (Ctrl-C)"
 Invoke-Cleanup
 exit 130
}

# Require -All or ProjectDir before activating venv
if (-not $All -and (-not $ProjectDir -or $ProjectDir.Count -eq 0)) {
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host "  .\compile.ps1 -All" -ForegroundColor White
 Write-Host "  .\compile.ps1 datrix-common [datrix-language ...]" -ForegroundColor White
 Write-Host "  .\compile.ps1 D:\datrix\datrix-common" -ForegroundColor White
 Write-Host ""
 Write-Host "Use Get-Help .\compile.ps1 -Full for detailed help." -ForegroundColor Yellow
 exit 1
}

# Main execution with proper error handling
try {
 # Activate virtual environment
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Error "Failed to activate virtual environment"
 exit 1
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 # Get workspace root for resolving relative project names
 $datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

 # Determine which directories to check (-All or positional ProjectDir)
 $pathsToCheck = @()
 if ($All) {
 $directories = Get-DatrixDirectoryPaths
 foreach ($dirPath in $directories) {
 if (Test-Path $dirPath) {
 $pathsToCheck += $dirPath
 }
 }
 } else {
 foreach ($p in $ProjectDir) {
 $fullPath = if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $datrixWorkspaceRoot $p }
 if (Test-Path $fullPath) {
 $pathsToCheck += $fullPath
 } else {
 Write-Error "Path not found: $fullPath"
 exit 1
 }
 }
 }

 # Build arguments for Python script
 $pythonArgs = @($pythonScript) + $pathsToCheck
 if ($Dbg) {
 $pythonArgs += "--debug"
 }

 # Run the Python script
 Write-Host "Running compile (syntax and import check)..." -ForegroundColor Cyan
 Write-Host ""

 & $pythonExe @pythonArgs
 $exitCode = $LASTEXITCODE

 # Exit with the same code as the Python script
 exit $exitCode

} catch {
 Write-Host ""
 Write-Host "Error occurred:" -ForegroundColor Red
 Write-Host $_.Exception.Message -ForegroundColor Red
 Write-Host ""
 if ($_.Exception.InnerException) {
 Write-Host "Inner exception:" -ForegroundColor Red
 Write-Host $_.Exception.InnerException.Message -ForegroundColor Red
 Write-Host ""
 }
 Invoke-Cleanup
 exit 1
} finally {
 # Ensure virtual environment is deactivated even on Ctrl-C
 Invoke-Cleanup
}
