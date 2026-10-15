#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Pylint duplicate-code detection (R0801) for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs datrix_scripts.duplicate
 for each project. Finds similar/duplicated code blocks across files.

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run for all Datrix projects.

.PARAMETER Mono
 Run duplicate detection across the full monorepo (datrix + all datrix-* packages). Mutually exclusive with -All.

.PARAMETER MinLines
 Minimum similar lines to report. Default: 4 for a single project, 30 for a
 multi-root (-Mono) run, unless explicitly overridden.

.PARAMETER Tests
 Also include tests/ in duplicate-code detection.

.PARAMETER StopOnError
 Stop on first project failure.

.PARAMETER VerboseOutput
 Verbose output.

.PARAMETER LlmRefactorPlan
 Add an advisory local LLM refactor plan for duplicate-code groups.

.PARAMETER LlmLimit
 Maximum duplicate groups to include in the advisory LLM refactor plan. Default: 20.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
 Models to use for advisory refactor plan, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for advisory refactor plan.

.PARAMETER LlmNumPredict
 Max generated tokens for advisory refactor plan.

.PARAMETER LlmTemperature
 Sampling temperature for advisory refactor plan.

.EXAMPLE
 .\duplicate.ps1 datrix-common
 .\duplicate.ps1 datrix-common -MinLines 6
 .\duplicate.ps1 datrix-common -Tests
 .\duplicate.ps1 -All
 .\duplicate.ps1 -Mono
 .\duplicate.ps1 -Mono -LlmRefactorPlan -LlmLimit 10
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [switch]$Mono,
 [int]$MinLines,
 [switch]$Tests,
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$LlmRefactorPlan,
 [int]$LlmLimit = 20,
 [string[]]$LocalMachines = @(),
 [string[]]$LlmModel = @(),
 [int]$LlmTimeout = 180,
 [int]$LlmNumPredict = 4096,
 [double]$LlmTemperature = 0.1
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$workspaceRoot = Get-DatrixWorkspaceRoot
# Shared with dev\code-scan.ps1, so it lives in the shared scripts package and runs as a module.
# pylint comes with the shared venv's dev install.
$duplicateModule = "datrix_scripts.duplicate"

if ($All -and $Mono) {
 Write-Host "Error: -All and -Mono are mutually exclusive. Use one or the other." -ForegroundColor Red
 exit 1
}

 $projectsToAnalyze = @()
 $isMonoRun = $false
 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No Datrix projects in: $workspaceRoot" -ForegroundColor Red; exit 1 }
 Write-Host "Running duplicate-code detection for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Mono) {
 $projectsToAnalyze = Get-DatrixMonoProjectNames -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No mono project directories found under: $workspaceRoot" -ForegroundColor Red; exit 1 }
 $isMonoRun = $true
 Write-Host "Running duplicate-code detection across monorepo (Mono): $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $projectsToAnalyze = ($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No valid projects (datrix excluded)." -ForegroundColor Red; exit 1 }
 Write-Host "Running duplicate-code detection for: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host "Usage: .\duplicate.ps1 <project> [options] or .\duplicate.ps1 -All [options] or .\duplicate.ps1 -Mono [options]" -ForegroundColor Yellow
 Write-Host " -MinLines N -Tests -StopOnError -VerboseOutput" -ForegroundColor Cyan
 exit 1
 }

 # Filter out projects without src/ — they have nothing to scan for duplicates
 $projectsToAnalyze = @($projectsToAnalyze | Where-Object {
  $projectDir = Join-Path $workspaceRoot $_
  $hasSrc = Test-Path (Join-Path $projectDir "src")
  if (-not $hasSrc) { Write-Host "Skipping $_ (no src/ directory)" -ForegroundColor Yellow }
  $hasSrc
 })
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "No projects with src/ to scan." -ForegroundColor Yellow; exit 0 }

 # The options every run shares, after its --project-root arguments.
 $commonArgs = @()
 if ($PSBoundParameters.ContainsKey('MinLines')) { $commonArgs += @("--min-lines", "$MinLines") }
 if ($Tests) { $commonArgs += "--tests" }
 if ($VerboseOutput) { $commonArgs += "--verbose" }
 if ($LlmRefactorPlan) {
 $commonArgs += @(
 "--llm-refactor-plan",
 "--llm-limit", "$LlmLimit",
 "--llm-num-predict", "$LlmNumPredict",
 "--llm-temperature", "$LlmTemperature"
 )
 $commonArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
 }

 $results = @{}
 if ($isMonoRun) {
 Write-Host ""
 Write-Host "======== mono (all projects) ========" -ForegroundColor Cyan
 $projectArgs = @()
 foreach ($project in $projectsToAnalyze) { $projectArgs += @("--project-root", (Join-Path $workspaceRoot $project)) }
 $monoExit = Invoke-DatrixPythonScript -Module $duplicateModule -Arguments ($projectArgs + $commonArgs)
 $results["mono"] = ($monoExit -eq 0)
 } else {
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 Write-Host "======== $project ========" -ForegroundColor Cyan
 $projectArgs = @("--project-root", (Join-Path $workspaceRoot $project))
 $projectExit = Invoke-DatrixPythonScript -Module $duplicateModule -Arguments ($projectArgs + $commonArgs)
 $results[$project] = ($projectExit -eq 0)
 if ($projectExit -ne 0 -and $StopOnError) {
 Write-Host "Stopping due to -StopOnError" -ForegroundColor Red
 break
 }
 }
 }

 Write-Host ""
 Write-Host "Duplicate-Code Summary" -ForegroundColor Cyan
 foreach ($p in ($results.Keys | Sort-Object)) {
 $status = if ($results[$p]) { "[PASS]" } else { "[FAIL]" }
 $color = if ($results[$p]) { "Green" } else { "Red" }
 Write-Host " $status : $p" -ForegroundColor $color
 }
 $failed = ($results.Values | Where-Object { $_ -eq $false }).Count
 if ($failed -gt 0) { exit 1 }
 exit 0
