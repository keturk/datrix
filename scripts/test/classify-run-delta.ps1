#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Classify the delta between two structured test-results runs.

.DESCRIPTION
 Activates the Datrix virtual environment and runs classify_run_delta.py.
 Compares the failing sets and cluster patterns of a previous and a current
 run of the same project, writes run-delta.json into the CURRENT run
 directory, and reports a verdict (SUCCESS / PARTIAL / NO_CHANGE /
 REGRESSION). Exit code 0 only for SUCCESS.

.PARAMETER Previous
 Previous run directory or index.json path (also accepted as the first
 positional argument).

.PARAMETER Current
 Current run directory or index.json path (also accepted as the second
 positional argument).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\classify-run-delta.ps1 -Previous D:\datrix\datrix-codegen-aws\.test_results\test-results-20260712-235813 -Current D:\datrix\datrix-codegen-aws\.test_results\test-results-20260713-000700

.EXAMPLE
 .\classify-run-delta.ps1 <previous-run-dir> <current-run-dir>
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Previous,

 [Parameter(Position=1)]
 [string]$Current,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\classify_run_delta.py"

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
 if ($Previous) { $pythonArgs += @("--previous", $Previous) }
 if ($Current) { $pythonArgs += @("--current", $Current) }
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
