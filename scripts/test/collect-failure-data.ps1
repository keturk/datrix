#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Collect per-cluster failure data from a structured test-results run.

.DESCRIPTION
 Activates the Datrix virtual environment and runs collect_failure_data.py.
 Resolves the representative entry of every error/failure cluster in the
 run's index.json, embeds the tail of its detail log and a ready-to-run
 single-test command, and writes failure-data.json into the run directory.

.PARAMETER Path
 Run directory or index.json path (alternative to -Project).

.PARAMETER Project
 Project name; auto-locates the newest test-results-* run directory under
 <workspace>\<project>\.test_results.

.PARAMETER MaxLogLines
 How many tail lines of each representative log to embed (default 60).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\collect-failure-data.ps1 -Project datrix-codegen-azure

.EXAMPLE
 .\collect-failure-data.ps1 D:\datrix\datrix-codegen-aws\.test_results\test-results-20260712-235813
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Path,

 [string]$Project,

 [int]$MaxLogLines = 60,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\collect_failure_data.py"

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
 if ($Project) { $pythonArgs += @("--project", $Project) }
 $pythonArgs += @("--max-log-lines", "$MaxLogLines")
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
