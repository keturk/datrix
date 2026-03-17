#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Pylint duplicate-code detection (R0801) for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library duplicate.py
 for each project. Finds similar/duplicated code blocks across files.

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run for all Datrix projects.

.PARAMETER Mono
 Run duplicate detection across the full monorepo (datrix + all datrix-* packages). Mutually exclusive with -All.

.PARAMETER MinLines
 Minimum similar lines to report. Default: 4.

.PARAMETER Tests
 Also include tests/ in duplicate-code detection.

.PARAMETER StopOnError
 Stop on first project failure.

.PARAMETER VerboseOutput
 Verbose output.

.EXAMPLE
 .\duplicate.ps1 datrix-common
 .\duplicate.ps1 datrix-common -MinLines 6
 .\duplicate.ps1 datrix-common -Tests
 .\duplicate.ps1 -All
 .\duplicate.ps1 -Mono
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [switch]$Mono,
 [int]$MinLines = 4,
 [switch]$Tests,
 [switch]$StopOnError,
 [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datrixCommon = Split-Path -Parent (Split-Path -Parent $scriptDir)
$datrixRoot = Split-Path -Parent $datrixCommon

$libraryDir = Join-Path $datrixCommon "scripts\library"
$duplicateScript = Join-Path $libraryDir "metrics\duplicate.py"
$commonDir = Join-Path $datrixCommon "scripts\common"
$venvUtilsScript = Join-Path $commonDir "venv.ps1"

if (-not (Test-Path $venvUtilsScript)) {
 Write-Error "Error: Common venv utilities not found at: $venvUtilsScript"
 exit 1
}
. $venvUtilsScript

if (-not (Test-Path $duplicateScript)) {
 Write-Error "Error: duplicate.py not found at: $duplicateScript"
 exit 1
}

function Get-DatrixProjects {
 $projects = @()
 if (Test-Path $datrixRoot) {
 Get-ChildItem -Path $datrixRoot -Directory | Where-Object { $_.Name -like "datrix-*" } | ForEach-Object { $projects += $_.Name }
 }
 return $projects | Sort-Object
}

function Normalize-ProjectInput {
 param([string]$ProjectInput)
 $trimmed = $ProjectInput.Trim()
 if ($trimmed -match '^\.|^\.\\|^[A-Za-z]:\\') {
 try {
 $resolved = Resolve-Path -Path $trimmed -ErrorAction Stop
 return Split-Path -Leaf $resolved.Path
 } catch {
 return Split-Path -Leaf ($trimmed -replace '[\\/]+$', '')
 }
 }
 return $trimmed
}

function Deactivate-Venv {
 if ($env:VIRTUAL_ENV) {
 try {
 if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
 else {
 $env:VIRTUAL_ENV = $null
 $env:VIRTUAL_ENV_PROMPT = $null
 if ($env:_OLD_VIRTUAL_PATH) { $env:PATH = $env:_OLD_VIRTUAL_PATH; $env:_OLD_VIRTUAL_PATH = $null }
 }
 } catch { $env:VIRTUAL_ENV = $null; $env:VIRTUAL_ENV_PROMPT = $null }
 }
}
function Invoke-Cleanup { Deactivate-Venv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

if ($All -and $Mono) {
 Write-Error "Parameters -All and -Mono are mutually exclusive. Use one or the other."
 exit 1
}

try {
 $projectsToAnalyze = @()
 $isMonoRun = $false
 if ($All) {
 $projectsToAnalyze = Get-DatrixProjects
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No Datrix projects in: $datrixRoot" -ForegroundColor Red; exit 1 }
 Write-Host "Running duplicate-code detection for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Mono) {
 $monoProjectNames = @(
 "datrix", "datrix-cli", "datrix-common", "datrix-codegen-aws", "datrix-codegen-azure",
 "datrix-codegen-component", "datrix-codegen-docker", "datrix-codegen-k8s", "datrix-codegen-python",
 "datrix-codegen-sql", "datrix-codegen-typescript", "datrix-language"
 )
 $projectsToAnalyze = $monoProjectNames | Where-Object { Test-Path (Join-Path $datrixRoot $_) }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No mono project directories found under: $datrixRoot" -ForegroundColor Red; exit 1 }
 $isMonoRun = $true
 Write-Host "Running duplicate-code detection across monorepo (Mono): $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $projectsToAnalyze = ($Projects | ForEach-Object { Normalize-ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No valid projects (datrix excluded)." -ForegroundColor Red; exit 1 }
 Write-Host "Running duplicate-code detection for: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host "Usage: .\duplicate.ps1 <project> [options] or .\duplicate.ps1 -All [options] or .\duplicate.ps1 -Mono [options]" -ForegroundColor Yellow
 Write-Host " -MinLines N -Tests -StopOnError -VerboseOutput" -ForegroundColor Cyan
 exit 1
 }

 if (-not (Ensure-DatrixVenv)) { Write-Error "Failed to ensure venv"; exit 1 }

 $oldErr = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show pylint 2>&1
 $pylintInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErr
 if (-not $pylintInstalled) {
 Write-Host "Installing pylint..." -ForegroundColor Cyan
 & pip install "pylint>=3.0"
 }

 $results = @{}
 if ($isMonoRun) {
 Write-Host ""
 Write-Host "======== mono (all projects) ========" -ForegroundColor Cyan
 $projectArgs = @($duplicateScript)
 foreach ($project in $projectsToAnalyze) {
 $projectRoot = Join-Path $datrixRoot $project
 $projectArgs += "--project-root"
 $projectArgs += $projectRoot
 }
 $projectArgs += "--min-lines"
 $projectArgs += $MinLines
 if ($Tests) { $projectArgs += "--tests" }
 if ($VerboseOutput) { $projectArgs += "--verbose" }

 & python @projectArgs
 $results["mono"] = ($LASTEXITCODE -eq 0)
 } else {
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 Write-Host "======== $project ========" -ForegroundColor Cyan
 $projectRoot = Join-Path $datrixRoot $project
 $projectArgs = @(
 $duplicateScript,
 "--project-root", $projectRoot,
 "--min-lines", $MinLines
 )
 if ($Tests) { $projectArgs += "--tests" }
 if ($VerboseOutput) { $projectArgs += "--verbose" }

 & python @projectArgs
 $results[$project] = ($LASTEXITCODE -eq 0)
 if ($LASTEXITCODE -ne 0 -and $StopOnError) {
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
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
