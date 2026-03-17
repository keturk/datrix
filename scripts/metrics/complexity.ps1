#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Radon metrics (complexity, raw, Halstead, MI) for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library complexity.py
 for each project. Mode: check (enforce max complexity), cc, raw, halstead, mi.
 Ensures virtual environment is deactivated on exit.

 In mode=check, two metrics are enforced:
 - Cyclomatic complexity (Radon/McCabe): decision points and paths.
 - Cognitive complexity : understandability, including nesting.
 Both use the same threshold (default 15). CI can still report
 other issues (e.g. string literal duplication S1192).

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run metrics for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Mode
 Metric to run: check (enforce max cyclomatic and cognitive), cc (cyclomatic), raw, halstead, mi.

.PARAMETER Max
 Maximum cyclomatic and cognitive complexity allowed per block (mode=check). Default: 15.

.PARAMETER Fix
 Fix the worst complexity violation using local Ollama (mode=check only).
 Sends the offending function to Ollama for refactoring, validates the result,
 and overwrites the function if the file is unchanged. Exits after first successful fix.
 If a fix fails (syntax error, undefined names, test failure), reverts and tries the next.

.PARAMETER Test
 Run pytest after fix to verify correctness; revert if tests fail. Use with -Fix.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from the script.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\complexity.ps1 datrix-common
 Check datrix-common with default max complexity 15 (mode=check).

.EXAMPLE
 .\complexity.ps1 datrix-common -Mode raw
 Report raw metrics (SLOC, comment/blank, LOC, LLOC) for datrix-common.

.EXAMPLE
 .\complexity.ps1 -All -Mode halstead
 Report Halstead metrics for all projects.

.EXAMPLE
 .\complexity.ps1 datrix-common -Fix
 Fix the worst complexity violation in datrix-common using Ollama.

.EXAMPLE
 .\complexity.ps1 datrix-common -Fix -Test
 Fix with auto-revert if tests fail.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("check", "cc", "raw", "halstead", "mi")]
 [string]$Mode = "check",
 [Parameter()]
 [int]$Max = 15,
 [switch]$Fix,
 [switch]$Test,
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
$complexityScript = Join-Path $libraryDir "metrics\complexity.py"

$commonDir = Join-Path $datrixCommon "scripts\common"
$venvUtilsScript = Join-Path $commonDir "venv.ps1"

if (-not (Test-Path $venvUtilsScript)) {
 Write-Error "Error: Common venv utilities not found at: $venvUtilsScript"
 exit 1
}
. $venvUtilsScript

if (-not (Test-Path $complexityScript)) {
 Write-Error "Error: complexity.py not found at: $complexityScript"
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

if ($Fix -and $Mode -ne "check") {
 Write-Host "ERROR: -Fix can only be used with -Mode check (the default)." -ForegroundColor Red
 exit 1
}
if ($Test -and -not $Fix) {
 Write-Host "ERROR: -Test can only be used with -Fix." -ForegroundColor Red
 exit 1
}

try {
 $projectsToAnalyze = @()

 if ($All) {
 $projectsToAnalyze = Get-DatrixProjects
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No Datrix projects found in: $datrixRoot" -ForegroundColor Red
 exit 1
 }
 Write-Host "Running complexity (mode=$Mode) for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $normalized = $Projects | ForEach-Object { Normalize-ProjectInput -ProjectInput $_ }
 $projectsToAnalyze = $normalized | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) {
 Write-Host "ERROR: No valid projects specified (datrix is excluded)." -ForegroundColor Red
 exit 1
 }
 Write-Host "Running complexity (mode=$Mode) for projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "ERROR: No projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\complexity.ps1 <project-name> [options]" -ForegroundColor Cyan
 Write-Host " .\complexity.ps1 <folder-path> [options]" -ForegroundColor Cyan
 Write-Host " .\complexity.ps1 -All [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\complexity.ps1 datrix-common" -ForegroundColor Cyan
 Write-Host " .\complexity.ps1 datrix-common -Mode raw" -ForegroundColor Cyan
 Write-Host " .\complexity.ps1 -All -Mode halstead" -ForegroundColor Cyan
 Write-Host " .\complexity.ps1 datrix-language -Mode check -Max 10" -ForegroundColor Cyan
 Write-Host " .\complexity.ps1 datrix-common -Mode mi -VerboseOutput" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Parameters:" -ForegroundColor Yellow
 Write-Host " -Mode check | cc | raw | halstead | mi (default: check)" -ForegroundColor Gray
 Write-Host " -Max Max cyclomatic and cognitive complexity for mode=check (default: 15)" -ForegroundColor Gray
 Write-Host " -Fix Fix worst violation via Ollama (mode=check only)" -ForegroundColor Gray
 Write-Host " -Test Run pytest after fix; revert if tests fail (use with -Fix)" -ForegroundColor Gray
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

 # Ensure radon is installed
 $oldErr = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show radon 2>$null
 $radonInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErr
 if (-not $radonInstalled) {
 Write-Host "Installing radon..." -ForegroundColor Cyan
 & pip install "radon>=6.0" 2>$null
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to install radon. Run: pip install radon>=6.0"
 exit 1
 }
 }

 # For mode=check, ensure cognitive_complexity is installed (for cognitive complexity)
 if ($Mode -eq "check") {
 $null = & pip show cognitive_complexity 2>$null
 $cogInstalled = $LASTEXITCODE -eq 0
 if (-not $cogInstalled) {
 Write-Host "Installing cognitive_complexity (for cognitive complexity check)..." -ForegroundColor Cyan
 & pip install cognitive_complexity 2>$null
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to install cognitive_complexity. Run: pip install cognitive_complexity"
 exit 1
 }
 }
 }

 $results = @{}
 $totalProjects = $projectsToAnalyze.Count
 $currentProject = 0

 foreach ($project in $projectsToAnalyze) {
 $currentProject++
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "[$currentProject/$totalProjects] $project (mode=$Mode)" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""

 $projectRoot = Join-Path $datrixRoot $project
 $projectArgs = @(
 $complexityScript,
 "--project-root", $projectRoot,
 "--mode", $Mode,
 "--max", $Max
 )
 if ($project -eq "datrix-common") {
   $projectArgs += "--ignore-path-contains", "builtins,objects"
 }
 if ($VerboseOutput) { $projectArgs += "--verbose" }
 if ($Dbg) { $projectArgs += "--debug" }
 if ($Fix) { $projectArgs += "--fix" }
 if ($Test) { $projectArgs += "--test" }

 & python @projectArgs
 $exitCode = $LASTEXITCODE

 if ($exitCode -eq 0) {
 $results[$project] = $true
 Write-Host ""
 Write-Host "[PASS] Complexity ($Mode) passed for $project" -ForegroundColor Green
 } else {
 $results[$project] = $false
 Write-Host ""
 Write-Host "[FAIL] Complexity ($Mode) failed for $project (exit code: $exitCode)" -ForegroundColor Red
 if ($StopOnError) {
 Write-Host "Stopping due to -StopOnError flag" -ForegroundColor Red
 break
 }
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Complexity Summary (mode=$Mode)" -ForegroundColor Cyan
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
