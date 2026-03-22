#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Bandit security scanner for one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library bandit.py
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
$banditScript = Join-Path $libraryDir "metrics\bandit.py"

if (-not (Test-Path $banditScript)) {
 Write-Error "Error: bandit.py not found at: $banditScript"
 exit 1
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $projectsToAnalyze = @()
 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No Datrix projects in: $workspaceRoot" -ForegroundColor Red; exit 1 }
 Write-Host "Running Bandit security scan for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $projectsToAnalyze = ($Projects | ForEach-Object { Normalize-DatrixProjectInput -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No valid projects (datrix excluded)." -ForegroundColor Red; exit 1 }
 Write-Host "Running Bandit security scan for: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host "Usage: .\bandit.ps1 <project> [options] or .\bandit.ps1 -All [options]" -ForegroundColor Yellow
 Write-Host " -Severity low|medium|high -Confidence low|medium|high -Format screen|json|csv|html|yaml|sarif" -ForegroundColor Cyan
 exit 1
 }

 if (-not (Ensure-DatrixVenv)) { Write-Error "Failed to ensure venv"; exit 1 }

 $oldErr = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show bandit 2>&1
 $banditInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErr
 if (-not $banditInstalled) {
 Write-Host "Installing bandit..." -ForegroundColor Cyan
 & pip install "bandit>=1.7"
 }

 $results = @{}
 foreach ($project in $projectsToAnalyze) {
 Write-Host ""
 Write-Host "======== $project ========" -ForegroundColor Cyan
 $projectRoot = Join-Path $workspaceRoot $project
 $projectArgs = @(
 $banditScript,
 "--project-root", $projectRoot,
 "--severity", $Severity,
 "--confidence", $Confidence,
 "--format", $Format
 )
 if ($VerboseOutput) { $projectArgs += "--verbose" }

 & python @projectArgs
 $results[$project] = ($LASTEXITCODE -eq 0)
 if ($LASTEXITCODE -ne 0 -and $StopOnError) {
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
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
