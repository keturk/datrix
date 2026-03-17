#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List Datrix projects or full paths to src/tests/docs folders.

.DESCRIPTION
 With no parameters, lists all Datrix project directory names (one per line).
 With -Src, prints the full path of each project's src folder (only for projects that have one).
 With -Tests, prints the full path of each project's tests folder (only for projects that have one).
 With -Docs, prints the full path of each project's docs folder (only for projects that have one).
 Activates the datrix virtual environment and runs projects.py. Ensures virtual environment
 is deactivated even if the script is interrupted (Ctrl-C).

.PARAMETER Src
 Display full paths to the src folder of each project that has one.

.PARAMETER Tests
 Display full paths to the tests folder of each project that has one.

.PARAMETER Docs
 Display full paths to the docs folder of each project that has one.

.EXAMPLE
 .\projects.ps1
 List all Datrix projects.

.EXAMPLE
 .\projects.ps1 -Src
 List full paths to each project's src folder.

.EXAMPLE
 .\projects.ps1 -Tests
 List full paths to each project's tests folder.

.EXAMPLE
 .\projects.ps1 -Docs
 List full paths to each project's docs folder.
#>

[CmdletBinding()]
param(
 [Parameter()]
 [switch]$Src,

 [Parameter()]
 [switch]$Tests,

 [Parameter()]
 [switch]$Docs
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\projects.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: projects.py not found at: $pythonScript"
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

 # Build arguments for Python script
 $pythonArgs = @($pythonScript)
 if ($Src) {
  $pythonArgs += "--src"
 }
 if ($Tests) {
  $pythonArgs += "--tests"
 }
 if ($Docs) {
  $pythonArgs += "--docs"
 }

 # Run the Python script
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
