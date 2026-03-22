#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Vulture (dead-code detection) across one or more Datrix projects.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library vulture.py
with a single combined invocation across selected projects' src trees.
This enables cross-project reference detection while excluding test code.
Finds unused imports, variables, functions, classes. Supports
--min-confidence, --sort-by-size, --make-whitelist.

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run Vulture for all Datrix projects.

.PARAMETER MinConfidence
 Minimum confidence 60-100. Default: 80.

.PARAMETER SortBySize
 Sort unused classes/functions by size.

.PARAMETER MakeWhitelist
 Output whitelist of false positives (pipe to file).

.PARAMETER StopOnError
 Deprecated for combined mode (retained for compatibility).

.PARAMETER VerboseOutput
 Verbose output.

.EXAMPLE
 .\vulture.ps1 datrix-common
 .\vulture.ps1 datrix-common -MinConfidence 100
 .\vulture.ps1 -All -SortBySize
 .\vulture.ps1 datrix-common -MakeWhitelist | Out-File whitelist.py
.\vulture.ps1 datrix-common datrix-language datrix-common -VerboseOutput
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [int]$MinConfidence = 80,
 [switch]$SortBySize,
 [switch]$MakeWhitelist,
 [switch]$StopOnError,
 [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$venvUtilsScript = Join-Path $commonDir "venv.ps1"
$defaultExcludePattern = "*\tests\*,*\test\*,*__pycache__*,*.git*"

if (-not (Test-Path $venvUtilsScript)) {
 Write-Error "Error: Common venv utilities not found at: $venvUtilsScript"
 exit 1
}
. $venvUtilsScript

$workspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $projectsToAnalyze = @()
 if ($All) {
 $projectsToAnalyze = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No Datrix projects in: $workspaceRoot" -ForegroundColor Red; exit 1 }
 Write-Host "Running combined Vulture scan for all projects: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $projectsToAnalyze = ($Projects | ForEach-Object { Normalize-DatrixProjectInput -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($projectsToAnalyze.Count -eq 0) { Write-Host "ERROR: No valid projects (datrix excluded)." -ForegroundColor Red; exit 1 }
 $projectsToAnalyze = $projectsToAnalyze | Select-Object -Unique
 Write-Host "Running combined Vulture scan for: $($projectsToAnalyze -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host "Usage: .\vulture.ps1 <project> [options] or .\vulture.ps1 -All [options]" -ForegroundColor Yellow
 Write-Host " -MinConfidence 60-100 -SortBySize -MakeWhitelist" -ForegroundColor Cyan
 exit 1
 }

 if (-not (Ensure-DatrixVenv)) { Write-Error "Failed to ensure venv"; exit 1 }

 $oldErr = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $null = & pip show vulture 2>$null
 $vultureInstalled = $LASTEXITCODE -eq 0
 $ErrorActionPreference = $oldErr
 if (-not $vultureInstalled) {
 Write-Host "Installing vulture..." -ForegroundColor Cyan
 & pip install "vulture>=2.0" 2>$null
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to install vulture. Run: pip install vulture>=2.0"
 exit 1
 }
 }

 if ($StopOnError) {
 Write-Host "Warning: -StopOnError is ignored in combined mode." -ForegroundColor Yellow
 }

 $scanPaths = @()
 foreach ($project in $projectsToAnalyze) {
 $projectRoot = Join-Path $workspaceRoot $project
 if (-not (Test-Path $projectRoot)) {
 Write-Host "Warning: Project not found, skipping: $project" -ForegroundColor Yellow
 continue
 }

 $srcRoot = Join-Path $projectRoot "src"
 if (-not (Test-Path $srcRoot)) {
 Write-Host "Warning: Project has no src directory, skipping: $project" -ForegroundColor Yellow
 continue
 }
 $scanPaths += $srcRoot

 $whitelistPath = Join-Path $projectRoot "vulture_whitelist.py"
 if (Test-Path $whitelistPath) {
 $scanPaths += $whitelistPath
 }
 }

 if ($scanPaths.Count -eq 0) {
 Write-Host "ERROR: No valid src directories found to scan." -ForegroundColor Red
 exit 1
 }

 $scanPaths = $scanPaths | Select-Object -Unique
 Write-Host ""
 Write-Host "Combined scan paths:" -ForegroundColor Cyan
 foreach ($path in $scanPaths) {
 Write-Host " - $path"
 }

 $vultureArgs = @(
 "-m", "vulture",
 "--min-confidence", $MinConfidence,
 "--exclude", $defaultExcludePattern
 )
 if ($SortBySize) { $vultureArgs += "--sort-by-size" }
 if ($MakeWhitelist) { $vultureArgs += "--make-whitelist" }
 $vultureArgs += $scanPaths

 if ($VerboseOutput) {
 Write-Host ""
 Write-Host "Command: python $($vultureArgs -join ' ')" -ForegroundColor DarkGray
 }

 Write-Host ""
 & python @vultureArgs
 $exitCode = $LASTEXITCODE

 if ($exitCode -eq 0) {
 Write-Host "Vulture scan completed: no dead code found above threshold." -ForegroundColor Green
 } else {
 Write-Host "Vulture scan found potential dead code (exit code: $exitCode)." -ForegroundColor Yellow
 }

 exit $exitCode
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
