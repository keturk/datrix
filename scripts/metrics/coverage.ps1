#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run pytest with coverage for one or more Datrix projects and show coverage details.

.DESCRIPTION
 Activates the datrix virtual environment and runs lib\coverage_report.py
 for each project. Runs tests with pytest-cov and displays the coverage report.
 Optionally fails if coverage is below a threshold (-FailUnder).

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run coverage for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Format
 Coverage report format: term, term-missing, html, xml. Default: term-missing.

.PARAMETER FailUnder
 Minimum coverage percentage; exit 1 if total coverage is below this value.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from pytest.

.EXAMPLE
 .\coverage.ps1 datrix-common
 Run tests with coverage for datrix-common (term-missing report).

.EXAMPLE
 .\coverage.ps1 datrix-common -Format html
 Run tests with coverage and generate HTML report.

.EXAMPLE
 .\coverage.ps1 -All -FailUnder 90
 Run coverage for all projects and fail if any project is below 90%.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("term", "term-missing", "html", "xml")]
 [string]$Format = "term-missing",
 [float]$FailUnder = 0,
 [switch]$StopOnError,
 [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$workspaceRoot = Get-DatrixWorkspaceRoot
# pytest-cov comes with each package's dev install in the shared venv.
$coverageScript = Join-Path $PSScriptRoot "lib\coverage_report.py"

 $projectsToAnalyze = @()
 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No Datrix projects in: $workspaceRoot" -ForegroundColor Red; exit 1 }
 Write-Host "Running coverage (format=$Format) for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $projectsToAnalyze = ($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No valid projects (datrix excluded)." -ForegroundColor Red; exit 1 }
 Write-Host "Running coverage (format=$Format) for: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "ERROR: No projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\coverage.ps1 <project-name> [options]" -ForegroundColor Cyan
 Write-Host " .\coverage.ps1 <folder-path> [options]" -ForegroundColor Cyan
 Write-Host " .\coverage.ps1 -All [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\coverage.ps1 datrix-common" -ForegroundColor Cyan
 Write-Host " .\coverage.ps1 datrix-common -Format html" -ForegroundColor Cyan
 Write-Host " .\coverage.ps1 -All -FailUnder 90" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Parameters:" -ForegroundColor Yellow
 Write-Host " -Format term | term-missing | html | xml (default: term-missing)" -ForegroundColor Gray
 Write-Host " -FailUnder Minimum coverage percent; fail if below (e.g. 90)" -ForegroundColor Gray
 Write-Host " -All Run for all datrix-* projects" -ForegroundColor Gray
 Write-Host " -StopOnError Stop on first project failure" -ForegroundColor Gray
 Write-Host " -VerboseOutput Verbose pytest output" -ForegroundColor Gray
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
 $resultDetails = @{}
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 Write-Host "======== $project ========" -ForegroundColor Cyan
 $projectRoot = Join-Path $workspaceRoot $project
 $summaryFile = [System.IO.Path]::GetTempFileName()
 $projectArgs = @(
 "--project-root", $projectRoot,
 "--format", $Format,
 "--summary-file", $summaryFile
 )
 if ($FailUnder -gt 0) { $projectArgs += @("--fail-under", "$FailUnder") }
 if ($VerboseOutput) { $projectArgs += "--verbose" }

 $projectExit = Invoke-DatrixPythonScript -Script $coverageScript -Arguments $projectArgs -RequirePackages
 $results[$project] = ($projectExit -eq 0)
 $detail = $null
 if (Test-Path $summaryFile) {
 $line = Get-Content $summaryFile -Raw -ErrorAction SilentlyContinue
 if ($line) { $resultDetails[$project] = $line.Trim() }
 Remove-Item $summaryFile -Force -ErrorAction SilentlyContinue
 }
 if ($projectExit -ne 0 -and $StopOnError) {
 Write-Host "Stopping due to -StopOnError" -ForegroundColor Red
 break
 }
 }

 Write-Host ""
 Write-Host "Coverage Summary" -ForegroundColor Cyan
 foreach ($p in ($results.Keys | Sort-Object)) {
 $status = if ($results[$p]) { "[PASS]" } else { "[FAIL]" }
 $color = if ($results[$p]) { "Green" } else { "Red" }
 Write-Host " $status : $p" -ForegroundColor $color
 $detail = $resultDetails[$p]
 if ($detail) {
 $parts = $detail -split '\s+'
 if ($parts.Length -ge 3) {
 $pct = $parts[0]; $req = $parts[1]
 if ([double]$req -gt 0) { Write-Host "       $pct% (required $req%)" -ForegroundColor Gray }
 else { Write-Host "       $pct% total" -ForegroundColor Gray }
 }
 }
 }
 $failed = ($results.Values | Where-Object { $_ -eq $false }).Count
 if ($failed -gt 0) { exit 1 }
 exit 0
