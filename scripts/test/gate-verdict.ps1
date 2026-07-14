#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Aggregate a GREEN/RED test gate verdict across Datrix packages.

.DESCRIPTION
 Activates the Datrix virtual environment and runs gate_verdict.py. For each
 requested project (or all testable packages with -All), finds the newest
 test-results run and reports a per-project GREEN/RED verdict plus an overall
 verdict. Writes gate-verdict.json to <workspace>\.tmp\test\ by default.
 Exit code 0 only when every project is GREEN.

.PARAMETER Projects
 One or more project names (comma-separated or space-separated).

.PARAMETER All
 Check all testable datrix-* packages.

.PARAMETER Output
 Output JSON path (default <workspace>\.tmp\test\gate-verdict.json).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\gate-verdict.ps1 -Projects datrix-codegen-azure,datrix-language

.EXAMPLE
 .\gate-verdict.ps1 -All
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Projects,

 [switch]$All,

 [string]$Output,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\gate_verdict.py"

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
 foreach ($project in $Projects) {
  if ($project) { $pythonArgs += @("--projects", $project) }
 }
 if ($All) { $pythonArgs += "--all" }
 if ($Output) { $pythonArgs += @("--output", $Output) }
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
