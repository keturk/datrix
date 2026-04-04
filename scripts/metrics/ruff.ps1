#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Ruff (lint/format) for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library ruff.py
 for each project. Modes: check (lint), format. Supports output-format,
 fix, diff, statistics for check; check (dry run), diff for format.
 Console output is written to a timestamped log under each project's
 .ruff_check folder (e.g. .ruff_check/ruff-20260207-143022.log).

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run Ruff for all Datrix projects.

.PARAMETER Mode
 check (lint) or format. Default: check.

.PARAMETER OutputFormat
 For mode=check: full, concise, json, json-lines, junit, grouped, github, etc.

.PARAMETER Fix
 Apply fixes (mode=check).

.PARAMETER Diff
 Show diff only (check: fix diff; format: format diff).

.PARAMETER Statistics
 Show rule counts (mode=check).

.PARAMETER Check
 Dry run for format: exit non-zero if changes needed.

.PARAMETER Test
 Run Ruff on each project's tests/ folder instead of src/.

.PARAMETER StopOnError
 Stop on first project failure.

.PARAMETER VerboseOutput
 Verbose output.

.EXAMPLE
 .\ruff.ps1 datrix-common
 .\ruff.ps1 datrix-common -Mode format -Diff
 .\ruff.ps1 -All -Mode check -OutputFormat json -Statistics
 .\ruff.ps1 -All -Test
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("check", "format")]
 [string]$Mode = "check",
 [string]$OutputFormat = "full",
 [switch]$Fix,
 [switch]$Diff,
 [switch]$Statistics,
 [switch]$Check,
 [switch]$Test,
 [switch]$StopOnError,
 [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$venvUtilsScript = Join-Path $commonDir "venv.ps1"
if (-not (Test-Path $venvUtilsScript)) {
 Write-Error "Error: Common venv utilities not found at: $venvUtilsScript"
 exit 1
}
. $venvUtilsScript

$workspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path
$datrixCommon = Join-Path $workspaceRoot "datrix"
$libraryDir = Join-Path $datrixCommon "scripts\library"
$ruffScript = Join-Path $libraryDir "metrics\ruff.py"

if (-not (Test-Path $ruffScript)) {
 Write-Error "Error: ruff.py not found at: $ruffScript"
 exit 1
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $projectsToAnalyze = @()
 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No Datrix projects in: $workspaceRoot" -ForegroundColor Red; exit 1 }
 $targetLabel = if ($Test) { "tests/" } else { "src/" }
 Write-Host "Running Ruff (mode=$Mode, target=$targetLabel) for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $projectsToAnalyze = ($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No valid projects (datrix excluded)." -ForegroundColor Red; exit 1 }
 $targetLabel = if ($Test) { "tests/" } else { "src/" }
 Write-Host "Running Ruff (mode=$Mode, target=$targetLabel) for: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host "Usage: .\ruff.ps1 <project> [options] or .\ruff.ps1 -All [options]" -ForegroundColor Yellow
 Write-Host " -Mode check|format -OutputFormat full|json|... -Fix -Diff -Statistics -Check -Test" -ForegroundColor Cyan
 exit 1
 }

 if (-not (Ensure-DatrixVenv)) { Write-Error "Failed to ensure venv"; exit 1 }

 $oldErr = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show ruff 2>&1
 $ruffInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErr
 if (-not $ruffInstalled) {
 if (Test-DatrixOfflineMode) {
 Write-Error "DATRIX_OFFLINE is set: ruff is not installed. Install while online: pip install ruff>=0.1.0"
 exit 1
 }
 Write-Host "Installing ruff..." -ForegroundColor Cyan
 & pip install "ruff>=0.1.0"
 }

 $RUFF_CHECK_FOLDER = ".ruff_check"
 $results = @{}
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 $targetLabel = if ($Test) { "tests" } else { "src" }
 Write-Host "======== $project (mode=$Mode, $targetLabel) ========" -ForegroundColor Cyan
 $projectRoot = Join-Path $workspaceRoot $project
 $ruffCheckDir = Join-Path $projectRoot $RUFF_CHECK_FOLDER
 if (-not (Test-Path $ruffCheckDir)) {
 New-Item -Path $ruffCheckDir -ItemType Directory -Force | Out-Null
 }
 $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
 $logFileName = "ruff-$timestamp.log"
 $logFile = Join-Path $ruffCheckDir $logFileName
 Write-Host "Log file: $logFile" -ForegroundColor Gray

 $projectArgs = @(
 $ruffScript,
 "--project-root", $projectRoot,
 "--mode", $Mode,
 "--output-format", $OutputFormat
 )
 if ($Test) { $projectArgs += "--target"; $projectArgs += "tests" }
 if ($Fix) { $projectArgs += "--fix" }
 if ($Diff) { $projectArgs += "--diff" }
 if ($Statistics) { $projectArgs += "--statistics" }
 if ($Check) { $projectArgs += "--check" }
 if ($VerboseOutput) { $projectArgs += "--verbose" }

 $ruffOutput = & python @projectArgs 2>&1
 $ruffExitCode = $LASTEXITCODE
 $ruffOutput | Out-File -FilePath $logFile -Encoding utf8
 $ruffOutput | Write-Host
 $results[$project] = ($ruffExitCode -eq 0)
 if ($ruffExitCode -ne 0 -and $StopOnError) {
 Write-Host "Stopping due to -StopOnError" -ForegroundColor Red
 break
 }
 }

 Write-Host ""
 Write-Host "Ruff Summary (mode=$Mode)" -ForegroundColor Cyan
 foreach ($p in ($results.Keys | Sort-Object)) {
 $status = if ($results[$p]) { "[PASS]" } else { "[FAIL]" }
 $color = if ($results[$p]) { "Green" } else { "Red" }
 Write-Host " $status : $p" -ForegroundColor $color
 }
 $failed = ($results.Values | Where-Object { $_ -eq $false }).Count
 if ($failed -gt 0) { exit 1 }
 exit 0
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
