#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Find and list top N files by line count for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs lib\large_files.py
 for each project. Walks both src/ and tests/; default is Python files only.
 Reports the largest files by line count in summary or json format.

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common).

.PARAMETER All
 Run for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Top
 Number of largest files to list per project. Default: 20.

.PARAMETER Threshold
 Only show files with at least this many lines (0 = no filter). Default: 0.

.PARAMETER Format
 Output format: summary, json. Default: summary.

.PARAMETER Suffix
 Comma-separated file suffixes to include (default: py). Use "" for all.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from the script.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\large-files.ps1 datrix-common
 List top 20 Python files by line count for datrix-common.

.EXAMPLE
 .\large-files.ps1 datrix-language -Top 30 -Format json
 List top 30 Python files for datrix-language in JSON format.

.EXAMPLE
 .\large-files.ps1 -All -Suffix ""
 List top 20 files (all extensions) for all projects.

.EXAMPLE
 .\large-files.ps1 datrix-language -Threshold 500
 List top 20 Python files with at least 500 lines for datrix-language.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [int]$Top = 20,
 [int]$Threshold = 0,
 [ValidateSet("summary", "json")]
 [string]$Format = "summary",
 [string]$Suffix = "py",
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$workspaceRoot = Get-DatrixWorkspaceRoot
$largeFilesScript = Join-Path $PSScriptRoot "lib\large_files.py"

 $projectsToAnalyze = @()

 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No Datrix projects found in: $workspaceRoot" -ForegroundColor Red
 exit 1
 }
 $thresholdInfo = if ($Threshold -gt 0) { ", threshold=$Threshold" } else { "" }
 Write-Host "Running large-files (top=$Top, format=$Format$thresholdInfo) for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $normalized = $Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }
 $projectsToAnalyze = $normalized | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No valid projects specified (datrix is excluded)." -ForegroundColor Red
 exit 1
 }
 $thresholdInfo = if ($Threshold -gt 0) { ", threshold=$Threshold" } else { "" }
 Write-Host "Running large-files (top=$Top, format=$Format$thresholdInfo) for projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "ERROR: No projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\large-files.ps1 <project-name> [options]" -ForegroundColor Cyan
 Write-Host " .\large-files.ps1 <folder-path> [options]" -ForegroundColor Cyan
 Write-Host " .\large-files.ps1 -All [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\large-files.ps1 datrix-common" -ForegroundColor Cyan
 Write-Host " .\large-files.ps1 datrix-language -Top 30 -Format json" -ForegroundColor Cyan
 Write-Host " .\large-files.ps1 -All -Suffix \"\"" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Parameters:" -ForegroundColor Yellow
 Write-Host " -Top Number of largest files per project (default: 20)" -ForegroundColor Gray
 Write-Host " -Threshold Only show files with at least this many lines (0 = no filter)" -ForegroundColor Gray
 Write-Host " -Format summary | json (default: summary)" -ForegroundColor Gray
 Write-Host " -Suffix Comma-separated suffixes (default: py). Use \"\" for all" -ForegroundColor Gray
 Write-Host " -All Run for all datrix-* projects" -ForegroundColor Gray
 Write-Host " -StopOnError Stop on first project failure" -ForegroundColor Gray
 Write-Host " -VerboseOutput Verbose output from the script" -ForegroundColor Gray
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

 $results = @{}
 $fileCounts = @{}
 $totalProjects = $projectsToAnalyze.Count
 $currentProject = 0

 foreach ($project in $projectsToAnalyze) {
 $currentProject++
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 $runInfo = "top=$Top, format=$Format"; if ($Threshold -gt 0) { $runInfo += ", threshold=$Threshold" }
 Write-Host "[$currentProject/$totalProjects] $project ($runInfo)" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""

 $projectRoot = Join-Path $workspaceRoot $project
 $projectArgs = @(
 "--project-root", $projectRoot,
 "--top", "$Top",
 "--format", $Format,
 "--suffix", $Suffix
 )
 if ($Threshold -gt 0) { $projectArgs += @("--threshold", "$Threshold") }
 if ($VerboseOutput) { $projectArgs += "--verbose" }
 if ($Dbg) { $projectArgs += "--debug" }

 if ($Threshold -gt 0) {
 $out = New-Object System.Collections.Generic.List[string]
 $exitCode = Invoke-DatrixPythonScript -Script $largeFilesScript -Arguments $projectArgs -OutputLines $out
 $out | Write-Host
 $lastLine = if ($out.Count -gt 0) { $out[$out.Count - 1] } else { $null }
 if ($exitCode -eq 0 -and $null -ne $lastLine -and $lastLine -match 'LARGE_FILES_COUNT: (\d+)') {
 $fileCounts[$project] = [int]$Matches[1]
 }
 $results[$project] = ($exitCode -eq 0)
 } else {
 $exitCode = Invoke-DatrixPythonScript -Script $largeFilesScript -Arguments $projectArgs
 $results[$project] = ($exitCode -eq 0)
 }

 if ($exitCode -ne 0) {
 if ($Threshold -gt 0) {
 Write-Host ""
 Write-Host "Error: $project failed (exit code: $exitCode)" -ForegroundColor Red
 } else {
 Write-Host ""
 Write-Host "Error: $project failed (exit code: $exitCode)" -ForegroundColor Red
 }
 if ($StopOnError) {
 Write-Host "Stopping due to -StopOnError flag" -ForegroundColor Red
 break
 }
 }
 }

 if ($Threshold -gt 0) {
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Files with >= $Threshold lines" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 $totalFiles = 0
 foreach ($p in ($projectsToAnalyze | Sort-Object)) {
 $count = $fileCounts[$p]
 if ($null -ne $count) {
 Write-Host " $p : $count files" -ForegroundColor Gray
 $totalFiles += $count
 } else {
 Write-Host " $p : (error)" -ForegroundColor Red
 }
 }
 Write-Host ""
 Write-Host "Total: $totalFiles files above threshold" -ForegroundColor Cyan
 }

 if (($results.Values | Where-Object { $_ -eq $false }).Count -gt 0) { exit 1 }
 exit 0
