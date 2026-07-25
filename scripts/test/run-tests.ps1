#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run full-package tests, batch generation, and complete workflow (orchestrated).

.DESCRIPTION
 Activates the Datrix virtual environment and runs unit_tests.py, which executes:
 1. test.ps1 -All
 2. For each target language: generate.ps1 -All -L <lang>
 3. If generate succeeded for that language: run-complete.ps1 -All -Skip1 -Skip2 -L <lang>

 If test.ps1 fails, nothing else runs. If generate fails for a language, run-complete
 is skipped for that language only.

.PARAMETER Language
 Target language for steps 2-3 only. When omitted, runs every registered
 datrix.languages target (sorted), discovered at runtime -- never a hardcoded
 python/typescript list. Accepts any installed language. Can be abbreviated as -L.

.EXAMPLE
 .\unit-tests.ps1
 Run tests, then generate and run-complete for every registered language.

.EXAMPLE
 .\unit-tests.ps1 -L typescript
 Run tests, then generate and run-complete for typescript only.
#>

[CmdletBinding()]
param(
 [Parameter()]
 [Alias("L")]
 [string]$Language
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runTestsScript = Join-Path $libraryDir "test\run_tests.py"

# DatrixScriptCommon is imported BEFORE DatrixPaths: the former nested-imports
# DatrixPaths with -Force, which would strip a prior top-level DatrixPaths import
# out of script scope. Importing DatrixPaths last keeps its exports at script scope.
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot

if (-not (Test-Path $runTestsScript)) {
 Write-Error "unit_tests.py not found at: $runTestsScript"
 exit 1
}

function Invoke-Cleanup {
 Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Host ""
 Write-Host "ERROR: Failed to activate virtual environment!" -ForegroundColor Red
 Write-Host ""
 Write-Host "To create the Datrix common virtual environment, run:" -ForegroundColor Yellow
 Write-Host " cd $datrixRoot" -ForegroundColor Cyan
 Write-Host " python -m venv .venv" -ForegroundColor Cyan
 Write-Host " .\.venv\Scripts\Activate.ps1" -ForegroundColor Cyan
 Write-Host ""
 exit 1
 }

 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 $pythonArgs = @($runTestsScript)
 if (-not [string]::IsNullOrWhiteSpace($Language)) {
 # Validate against the installed datrix.languages set (runtime discovery,
 # never a hardcoded literal) so a newly installed datrix-codegen-<lang>
 # package is accepted with no edit to this script.
 $installedLanguages = Get-DatrixInstalledLanguages -PythonExe $pythonExe
 if ($Language -notin $installedLanguages) {
 Write-Error "Language '$Language' is not an installed datrix.languages target. Installed: $($installedLanguages -join ', ')."
 exit 1
 }
 $pythonArgs += "-L"
 $pythonArgs += $Language
 }

 & $pythonExe @pythonArgs
 $exitCode = $LASTEXITCODE
 exit $exitCode
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
