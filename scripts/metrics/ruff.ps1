#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Ruff (lint/format) for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs lib\ruff_report.py
 for each project. Modes: check (lint), format. Supports output-format,
 fix, diff, statistics for check; check (dry run), diff for format.
 Console output is written to a timestamped log under the workspace-level
 .test-output\ruff\<project>\ folder
 (e.g. D:\datrix\.test-output\ruff\datrix-common\ruff-20260207-143022.log).
 The logs live OUTSIDE every package repo on purpose: each datrix-* package
 is its own git repository, so a log folder created inside one is committed
 and pushed unless a human notices.

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

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$workspaceRoot = Get-DatrixWorkspaceRoot
# Ruff comes with the shared venv's dev install.
$ruffScript = Join-Path $PSScriptRoot "lib\ruff_report.py"

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

 # Run logs go to the workspace-level output tree, never inside a package repo:
 # every datrix-* package is its own git repository, and anything dropped in one
 # is committed and pushed unless a human notices. See repo-boundaries in the
 # agent rules; the ignored-source gate fails on any such stray output.
 $RUFF_LOG_ROOT = Join-Path $workspaceRoot ".test-output\ruff"
 $results = @{}
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 $targetLabel = if ($Test) { "tests" } else { "src" }
 Write-Host "======== $project (mode=$Mode, $targetLabel) ========" -ForegroundColor Cyan
 $projectRoot = Join-Path $workspaceRoot $project
 $ruffLogDir = Join-Path $RUFF_LOG_ROOT $project
 if (-not (Test-Path $ruffLogDir)) {
 New-Item -Path $ruffLogDir -ItemType Directory -Force | Out-Null
 }
 $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
 $logFileName = "ruff-$timestamp.log"
 $logFile = Join-Path $ruffLogDir $logFileName
 Write-Host "Log file: $logFile" -ForegroundColor Gray

 $projectArgs = @(
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

 $ruffExitCode = Invoke-DatrixPythonScript -Script $ruffScript -Arguments $projectArgs -TeePath $logFile
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
