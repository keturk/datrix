#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Bandit security scanner for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs lib\bandit_report.py
 for each project. Finds common security issues in Python code.

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run for all Datrix projects.

.PARAMETER Severity
 Minimum severity: low, medium, high. Default: medium.

.PARAMETER Confidence
 Minimum confidence: low, medium, high. Default: medium.

.PARAMETER Format
 Output format: screen, json, csv, html, yaml, sarif. Default: screen.

.PARAMETER StopOnError
 Stop on first project failure.

.PARAMETER VerboseOutput
 Verbose output.

.EXAMPLE
 .\bandit.ps1 datrix-common
 .\bandit.ps1 datrix-common -Severity high
 .\bandit.ps1 -All -Format json
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("low", "medium", "high")]
 [string]$Severity = "medium",
 [ValidateSet("low", "medium", "high")]
 [string]$Confidence = "medium",
 [ValidateSet("screen", "json", "csv", "html", "yaml", "sarif")]
 [string]$Format = "screen",
 [switch]$StopOnError,
 [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$workspaceRoot = Get-DatrixWorkspaceRoot
# bandit must be installed in the shared venv; bandit_report.py refuses, naming the install command, when it is not.
$banditScript = Join-Path $PSScriptRoot "lib\bandit_report.py"

 $projectsToAnalyze = @()
 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No Datrix projects in: $workspaceRoot" -ForegroundColor Red; exit 1 }
 Write-Host "Running Bandit security scan for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $projectsToAnalyze = ($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No valid projects (datrix excluded)." -ForegroundColor Red; exit 1 }
 Write-Host "Running Bandit security scan for: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host "Usage: .\bandit.ps1 <project> [options] or .\bandit.ps1 -All [options]" -ForegroundColor Yellow
 Write-Host " -Severity low|medium|high -Confidence low|medium|high -Format screen|json|csv|html|yaml|sarif" -ForegroundColor Cyan
 exit 1
 }

 $results = @{}
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 Write-Host "======== $project ========" -ForegroundColor Cyan
 $projectRoot = Join-Path $workspaceRoot $project
 $projectArgs = @(
 "--project-root", $projectRoot,
 "--severity", $Severity,
 "--confidence", $Confidence,
 "--format", $Format
 )
 if ($VerboseOutput) { $projectArgs += "--verbose" }

 $projectExit = Invoke-DatrixPythonScript -Script $banditScript -Arguments $projectArgs
 $results[$project] = ($projectExit -eq 0)
 if ($projectExit -ne 0 -and $StopOnError) {
 Write-Host "Stopping due to -StopOnError" -ForegroundColor Red
 break
 }
 }

 Write-Host ""
 Write-Host "Bandit Security Summary" -ForegroundColor Cyan
 foreach ($p in ($results.Keys | Sort-Object)) {
 $status = if ($results[$p]) { "[PASS]" } else { "[FAIL]" }
 $color = if ($results[$p]) { "Green" } else { "Red" }
 Write-Host " $status : $p" -ForegroundColor $color
 }
 $failed = ($results.Values | Where-Object { $_ -eq $false }).Count
 if ($failed -gt 0) { exit 1 }
 exit 0
