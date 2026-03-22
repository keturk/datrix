#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run pytest with coverage for one or more Datrix projects and show coverage details.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library coverage.py
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
$coverageScript = Join-Path $libraryDir "metrics\coverage.py"

if (-not (Test-Path $coverageScript)) {
 Write-Error "Error: coverage.py not found at: $coverageScript"
 exit 1
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
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

 if (-not (Ensure-DatrixVenv)) { Write-Error "Failed to ensure venv"; exit 1 }

 $oldErr = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show pytest-cov 2>&1
 $pytestCovInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErr
 if (-not $pytestCovInstalled) {
 Write-Host "Installing pytest-cov..." -ForegroundColor Cyan
 & pip install "pytest-cov>=4.0"
 }

 $results = @{}
 $resultDetails = @{}
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 Write-Host "======== $project ========" -ForegroundColor Cyan
 $projectRoot = Join-Path $workspaceRoot $project
 $summaryFile = [System.IO.Path]::GetTempFileName()
 $projectArgs = @(
 $coverageScript,
 "--project-root", $projectRoot,
 "--format", $Format,
 "--summary-file", $summaryFile
 )
 if ($FailUnder -gt 0) { $projectArgs += "--fail-under", $FailUnder }
 if ($VerboseOutput) { $projectArgs += "--verbose" }

 & python @projectArgs
 $results[$project] = ($LASTEXITCODE -eq 0)
 $detail = $null
 if (Test-Path $summaryFile) {
 $line = Get-Content $summaryFile -Raw -ErrorAction SilentlyContinue
 if ($line) { $resultDetails[$project] = $line.Trim() }
 Remove-Item $summaryFile -Force -ErrorAction SilentlyContinue
 }
 if ($LASTEXITCODE -ne 0 -and $StopOnError) {
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
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
