#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run error message quality detection and scoring for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library error_messages.py
 for each project. Modes: check (enforce minimum quality score), report (list all sites).

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run metrics for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Mode
 Mode to run: check (enforce min score) or report (list all sites). Default: check.

.PARAMETER MinScore
 Minimum quality score for check mode (0-4). Default: 2.

.PARAMETER Fix
 Fix the worst error-message violation using local Ollama (check mode only).

.PARAMETER FixAll
 Fix ALL violations, not just the worst. Implies -Fix.

.PARAMETER Test
 Run pytest after each fix to verify; revert if tests fail (-Fix/-FixAll only).

.PARAMETER MaxRetries
 Max Ollama retry attempts per violation. Default: 3.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from the script.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\error-messages.ps1 datrix-common
 Check error message quality in datrix-common with default min-score 2.

.EXAMPLE
 .\error-messages.ps1 datrix-common -Mode report
 Report all error sites with scores for datrix-common.

.EXAMPLE
 .\error-messages.ps1 -All
 Check all projects with default settings.

.EXAMPLE
 .\error-messages.ps1 -All -MinScore 3
 Enforce minimum score 3 across all projects.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("check", "report")]
 [string]$Mode = "check",
 [Parameter()]
 [int]$MinScore = 2,
 [switch]$Fix,
 [switch]$FixAll,
 [switch]$Test,
 [int]$MaxRetries = 3,
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
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
$errorMessagesScript = Join-Path $libraryDir "metrics\error_messages.py"

if (-not (Test-Path $errorMessagesScript)) {
 Write-Error "Error: error_messages.py not found at: $errorMessagesScript"
 exit 1
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

if ($FixAll) { $Fix = $true }
if ($Fix -and $Mode -ne "check") {
 Write-Host "ERROR: -Fix/-FixAll can only be used with -Mode check (the default)." -ForegroundColor Red
 exit 1
}
if ($Test -and -not $Fix) {
 Write-Host "ERROR: -Test can only be used with -Fix/-FixAll." -ForegroundColor Red
 exit 1
}

try {
 $projectsToAnalyze = @()

 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No Datrix projects found in: $workspaceRoot" -ForegroundColor Red
 exit 1
 }
 Write-Host "Running error-messages (mode=$Mode, min-score=$MinScore) for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $normalized = $Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }
 $projectsToAnalyze = $normalized | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No valid projects specified (datrix is excluded)." -ForegroundColor Red
 exit 1
 }
 Write-Host "Running error-messages (mode=$Mode, min-score=$MinScore) for projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "ERROR: No projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\error-messages.ps1 <project-name> [options]" -ForegroundColor Cyan
 Write-Host " .\error-messages.ps1 <folder-path> [options]" -ForegroundColor Cyan
 Write-Host " .\error-messages.ps1 -All [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\error-messages.ps1 datrix-common" -ForegroundColor Cyan
 Write-Host " .\error-messages.ps1 datrix-common -Mode report" -ForegroundColor Cyan
 Write-Host " .\error-messages.ps1 -All -MinScore 3" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Parameters:" -ForegroundColor Yellow
 Write-Host " -Mode check | report (default: check)" -ForegroundColor Gray
 Write-Host " -MinScore Minimum quality score 0-4 for mode=check (default: 2)" -ForegroundColor Gray
 Write-Host " -All Run for all datrix-* projects" -ForegroundColor Gray
 Write-Host " -StopOnError Stop on first project failure" -ForegroundColor Gray
 Write-Host " -VerboseOutput Verbose output" -ForegroundColor Gray
 Write-Host " -Dbg Debug output" -ForegroundColor Gray
 Write-Host ""
 $available = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($available.Count -gt 0) {
 Write-Host "Available projects:" -ForegroundColor Yellow
 foreach ($p in $available) { Write-Host " - $p" -ForegroundColor Cyan }
 }
 Write-Host ""
 exit 1
 }

 if (-not (Ensure-DatrixVenv)) {
 Write-Error "Failed to ensure virtual environment is ready"
 exit 1
 }

 $results = @{}
 $totalProjects = $projectsToAnalyze.Count
 $currentProject = 0

 foreach ($project in $projectsToAnalyze) {
 $currentProject++
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "[$currentProject/$totalProjects] $project (mode=$Mode, min-score=$MinScore)" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""

 $projectRoot = Join-Path $workspaceRoot $project
 $projectArgs = @(
 $errorMessagesScript,
 "--project-root", $projectRoot,
 "--mode", $Mode,
 "--min-score", $MinScore
 )
 if ($project -eq "datrix-common") {
   $projectArgs += "--ignore-path-contains", "builtins,objects"
 }
 if ($Fix) {
   $projectArgs += "--fix"
   if ($FixAll) { $projectArgs += "--fix-all" }
   if ($MaxRetries -ne 3) { $projectArgs += "--max-retries", $MaxRetries }
 }
 if ($Test) { $projectArgs += "--test" }

 & python @projectArgs
 $exitCode = $LASTEXITCODE

 if ($exitCode -eq 0) {
 $results[$project] = $true
 Write-Host ""
 Write-Host "[PASS] Error message quality ($Mode) passed for $project" -ForegroundColor Green
 } else {
 $results[$project] = $false
 Write-Host ""
 Write-Host "[FAIL] Error message quality ($Mode) failed for $project (exit code: $exitCode)" -ForegroundColor Red
 if ($StopOnError) {
 Write-Host "Stopping due to -StopOnError flag" -ForegroundColor Red
 break
 }
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Error Message Quality Summary (mode=$Mode)" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan

 $passed = ($results.Values | Where-Object { $_ -eq $true }).Count
 $failed = ($results.Values | Where-Object { $_ -eq $false }).Count

 foreach ($p in ($results.Keys | Sort-Object)) {
 $status = if ($results[$p]) { "[PASS]" } else { "[FAIL]" }
 $color = if ($results[$p]) { "Green" } else { "Red" }
 Write-Host " $status : $p" -ForegroundColor $color
 }

 Write-Host ""
 Write-Host "Total: $totalProjects | Passed: $passed | Failed: $failed" -ForegroundColor Cyan

 if ($failed -gt 0) { exit 1 }
 exit 0

} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
