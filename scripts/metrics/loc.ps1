#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run pygount (lines-of-code counting) for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library loc.py
 for each project. Reports code, documentation, and empty line counts
 per language. Supports summary, cloc-xml, and json output formats.

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run LOC counting for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Format
 Output format: summary, cloc-xml, json. Default: summary.

.PARAMETER Suffix
 Comma-separated file suffixes to include (e.g. py,js). Empty = all.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from the script.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\loc.ps1 datrix-common
 Count lines of code for datrix-common (summary format).

.EXAMPLE
 .\loc.ps1 datrix-common -Format json
 Count lines of code for datrix-common in JSON format.

.EXAMPLE
 .\loc.ps1 -All -Suffix py
 Count only Python lines of code for all projects.

.EXAMPLE
 .\loc.ps1 datrix-common datrix-language -Format cloc-xml
 Count lines for multiple projects in cloc-xml format.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("summary", "cloc-xml", "json")]
 [string]$Format = "summary",
 [string]$Suffix = "",
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get datrix folder (scripts/metrics -> scripts -> datrix)
$datrixCommon = Split-Path -Parent (Split-Path -Parent $scriptDir)
# Get workspace root (parent of datrix)
$datrixRoot = Split-Path -Parent $datrixCommon

$libraryDir = Join-Path $datrixCommon "scripts\library"
$locScript = Join-Path $libraryDir "metrics\loc.py"

$commonDir = Join-Path $datrixCommon "scripts\common"
$venvUtilsScript = Join-Path $commonDir "venv.ps1"

if (-not (Test-Path $venvUtilsScript)) {
 Write-Error "Error: Common venv utilities not found at: $venvUtilsScript"
 exit 1
}
. $venvUtilsScript

if (-not (Test-Path $locScript)) {
 Write-Error "Error: loc.py not found at: $locScript"
 exit 1
}

function Get-DatrixProjects {
 $projects = @()
 if (Test-Path $datrixRoot) {
 Get-ChildItem -Path $datrixRoot -Directory | Where-Object {
 $_.Name -like "datrix-*"
 } | ForEach-Object {
 $projects += $_.Name
 }
 }
 return $projects | Sort-Object
}

function Normalize-ProjectInput {
 param([string]$ProjectInput)
 $trimmedInput = $ProjectInput.Trim()
 $isPath = $trimmedInput -match '^\.|^\.\\|^[A-Za-z]:\\'
 if ($isPath) {
 try {
 $resolvedPath = Resolve-Path -Path $trimmedInput -ErrorAction Stop
 return Split-Path -Leaf $resolvedPath.Path
 } catch {
 $cleaned = $trimmedInput -replace '[\\/]+$', ''
 return Split-Path -Leaf $cleaned
 }
 }
 return $trimmedInput
}

function Deactivate-Venv {
 if ($env:VIRTUAL_ENV) {
 try {
 if (Get-Command deactivate -ErrorAction SilentlyContinue) {
 deactivate
 } else {
 $env:VIRTUAL_ENV = $null
 $env:VIRTUAL_ENV_PROMPT = $null
 if ($env:_OLD_VIRTUAL_PATH) {
 $env:PATH = $env:_OLD_VIRTUAL_PATH
 $env:_OLD_VIRTUAL_PATH = $null
 }
 }
 } catch {
 $env:VIRTUAL_ENV = $null
 $env:VIRTUAL_ENV_PROMPT = $null
 }
 }
}

function Invoke-Cleanup { Deactivate-Venv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $projectsToAnalyze = @()

 if ($All) {
 $projectsToAnalyze = Get-DatrixProjects
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No Datrix projects found in: $datrixRoot" -ForegroundColor Red
 exit 1
 }
 Write-Host "Running LOC (format=$Format) for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $normalized = $Projects | ForEach-Object { Normalize-ProjectInput -ProjectInput $_ }
 $projectsToAnalyze = $normalized | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No valid projects specified (datrix is excluded)." -ForegroundColor Red
 exit 1
 }
 Write-Host "Running LOC (format=$Format) for projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "ERROR: No projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\loc.ps1 <project-name> [options]" -ForegroundColor Cyan
 Write-Host " .\loc.ps1 <folder-path> [options]" -ForegroundColor Cyan
 Write-Host " .\loc.ps1 -All [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\loc.ps1 datrix-common" -ForegroundColor Cyan
 Write-Host " .\loc.ps1 datrix-common -Format json" -ForegroundColor Cyan
 Write-Host " .\loc.ps1 -All -Suffix py" -ForegroundColor Cyan
 Write-Host " .\loc.ps1 datrix-language -Format cloc-xml" -ForegroundColor Cyan
 Write-Host " .\loc.ps1 datrix-common datrix-language -VerboseOutput" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Parameters:" -ForegroundColor Yellow
 Write-Host " -Format summary | cloc-xml | json (default: summary)" -ForegroundColor Gray
 Write-Host " -Suffix Comma-separated suffixes to include (e.g. py,js)" -ForegroundColor Gray
 Write-Host " -All Run for all datrix-* projects" -ForegroundColor Gray
 Write-Host " -StopOnError Stop on first project failure" -ForegroundColor Gray
 Write-Host " -VerboseOutput Verbose output from the check script" -ForegroundColor Gray
 Write-Host " -Dbg Debug output" -ForegroundColor Gray
 Write-Host ""
 $available = Get-DatrixProjects
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

 # Ensure pygount is installed
 $oldErr = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show pygount 2>&1
 $pygountInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErr
 if (-not $pygountInstalled) {
 Write-Host "Installing pygount..." -ForegroundColor Cyan
 & pip install "pygount>=1.8"
 }

 $results = @{}
 $totalProjects = $projectsToAnalyze.Count
 $currentProject = 0

 foreach ($project in $projectsToAnalyze) {
 $currentProject++
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "[$currentProject/$totalProjects] $project (format=$Format)" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""

 $projectRoot = Join-Path $datrixRoot $project
 $projectArgs = @(
 $locScript,
 "--project-root", $projectRoot,
 "--format", $Format
 )
 if ($Suffix) { $projectArgs += @("--suffix", $Suffix) }
 if ($VerboseOutput) { $projectArgs += "--verbose" }
 if ($Dbg) { $projectArgs += "--debug" }

 & python @projectArgs
 $exitCode = $LASTEXITCODE

 if ($exitCode -eq 0) {
 $results[$project] = $true
 Write-Host ""
 Write-Host "[PASS] LOC counting passed for $project" -ForegroundColor Green
 } else {
 $results[$project] = $false
 Write-Host ""
 Write-Host "[FAIL] LOC counting failed for $project (exit code: $exitCode)" -ForegroundColor Red
 if ($StopOnError) {
 Write-Host "Stopping due to -StopOnError flag" -ForegroundColor Red
 break
 }
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "LOC Summary (format=$Format)" -ForegroundColor Cyan
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
