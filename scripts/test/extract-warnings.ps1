#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Extract and deduplicate pytest warnings from a test run's full.log.

.DESCRIPTION
 Activates the Datrix virtual environment and runs extract_warnings.py against
 a test-results run directory (or an index.json / full.log path inside one).
 Writes warnings.json into the run directory.

.PARAMETER Path
 Run directory, index.json path, or full.log path.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\extract-warnings.ps1 D:\datrix\datrix-codegen-aws\.test_results\test-results-20260712-121900
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Path,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\extract_warnings.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

function Invoke-Cleanup {
 Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
  Write-Error "Failed to activate virtual environment"
  exit 1
 }

 $venvPath = Get-DatrixVenvPath
 $PythonExe = Join-Path $venvPath "Scripts\python.exe"

 if (-not (Test-Path $PythonScript)) {
  Write-Error "Python script not found: $PythonScript"
  exit 1
 }

 $pythonArgs = @($PythonScript)
 if ($Path) { $pythonArgs += $Path }
 if ($Dbg) { $pythonArgs += "--debug" }

 & $PythonExe @pythonArgs
 exit $LASTEXITCODE
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
