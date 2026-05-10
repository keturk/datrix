#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run mypy for Datrix projects using mypy.py.

.DESCRIPTION
 Activates the Datrix virtual environment and runs mypy.py for one or more
 projects. Accepts the same parameters as test.ps1 for command-line symmetry.

.PARAMETER Projects
 One or more project names or folder paths to type-check.

.PARAMETER All
 Run mypy for all Datrix projects that have pyproject.toml.

.PARAMETER Coverage
 Accepted for parity with test.ps1; ignored by mypy.py.

.PARAMETER VerboseOutput
 Enable verbose mypy output.

.PARAMETER NoSave
 Don't save mypy output to log files.

.PARAMETER NoAutoInstall
 Accepted for parity with test.ps1; dependency installation is handled by this wrapper.

.PARAMETER SkipInstall
 Skip pip installs; verify monorepo packages and CLI only. Requires a ready .venv.

.PARAMETER Unit
 Accepted for parity with test.ps1; ignored by mypy.py.

.PARAMETER Integration
 Accepted for parity with test.ps1; ignored by mypy.py.

.PARAMETER E2E
 Accepted for parity with test.ps1; ignored by mypy.py.

.PARAMETER Fast
 Accepted for parity with test.ps1; ignored by mypy.py.

.PARAMETER Slow
 Accepted for parity with test.ps1; ignored by mypy.py.

.PARAMETER Specific
 Run mypy against a specific file, directory, or comma-separated targets.

.PARAMETER Keyword
 Accepted for parity with test.ps1; ignored by mypy.py.

.PARAMETER Dbg
 Enable debug logging.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Projects,

 [switch]$All,
 [switch]$Coverage,
 [switch]$VerboseOutput,
 [switch]$NoSave,
 [switch]$NoAutoInstall,
 [switch]$SkipInstall,

 [switch]$Unit,
 [switch]$Integration,
 [switch]$E2E,
 [switch]$Fast,
 [switch]$Slow,

 [string]$Specific,
 [string]$Keyword,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$libraryDir = Join-Path $scriptsDir "library"
$mypyScript = Join-Path $libraryDir "mypy.py"

$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $mypyScript)) {
 Write-Error "Error: mypy.py not found at: $mypyScript"
 exit 1
}

function Invoke-Cleanup {
 Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $projectsToCheck = @()

 if ($All) {
 $projectsToCheck = Get-DatrixPackageNamesGlobWithPyProject -WorkspaceRoot $datrixWorkspaceRoot
 if ($projectsToCheck.Count -eq 0) {
 Write-Host "ERROR: No Datrix projects with pyproject.toml found in: $datrixWorkspaceRoot" -ForegroundColor Red
 exit 1
 }
 Write-Host "Running mypy for all projects: $($projectsToCheck -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $normalizedProjects = $Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }
 $allProjects = Get-DatrixPackageNamesGlobWithPyProject -WorkspaceRoot $datrixWorkspaceRoot
 $projectsToCheck = $normalizedProjects | Where-Object { $allProjects -contains $_ }

 if ($projectsToCheck.Count -eq 0) {
 Write-Host "ERROR: No valid projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Available projects:" -ForegroundColor Yellow
 foreach ($project in $allProjects) {
 Write-Host " - $project" -ForegroundColor Cyan
 }
 exit 1
 }
 Write-Host "Running mypy for projects: $($projectsToCheck -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "ERROR: No projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\mypy.ps1 <project-name> [options]" -ForegroundColor Cyan
 Write-Host " .\mypy.ps1 <folder-path> [options]" -ForegroundColor Cyan
 Write-Host " .\mypy.ps1 -All [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\mypy.ps1 datrix-common" -ForegroundColor Cyan
 Write-Host " .\mypy.ps1 .\datrix-common\" -ForegroundColor Cyan
 Write-Host " .\mypy.ps1 datrix-common datrix-language" -ForegroundColor Cyan
 Write-Host " .\mypy.ps1 datrix-common -Specific `"src\datrix_common\builtins`"" -ForegroundColor Cyan
 Write-Host " .\mypy.ps1 -All" -ForegroundColor Cyan
 Write-Host ""
 $availableProjects = Get-DatrixPackageNamesGlobWithPyProject -WorkspaceRoot $datrixWorkspaceRoot
 if ($availableProjects.Count -gt 0) {
 Write-Host "Available projects:" -ForegroundColor Yellow
 foreach ($project in $availableProjects) {
 Write-Host " - $project" -ForegroundColor Cyan
 }
 Write-Host ""
 Write-Host "Total: $($availableProjects.Count) projects" -ForegroundColor Cyan
 }
 exit 1
 }

 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Host ""
 Write-Host "ERROR: Failed to activate virtual environment!" -ForegroundColor Red
 Write-Error "ERROR: No virtual environment is currently active."
 exit 1
 }

 if (-not $SkipInstall) {
 $packagesInstalled = Ensure-DatrixPackagesInstalled -SkipIfInstalled
 if (-not $packagesInstalled) {
 Write-Host ""
 Write-Host "ERROR: Failed to install or update packages!" -ForegroundColor Red
 Write-Error "Failed to install or update packages"
 exit 1
 }
 } else {
 $packagesInstalled = Ensure-DatrixPackagesInstalled -Offline
 if (-not $packagesInstalled) {
 Write-Host ""
 Write-Host "ERROR: Offline/skip-install verification failed (packages or CLI not ready)." -ForegroundColor Red
 Write-Error "Failed offline package verification"
 exit 1
 }
 }

 $mypyArgs = @()
 if ($Coverage) { $mypyArgs += "--coverage" }
 if ($VerboseOutput) { $mypyArgs += "--verbose" }
 if ($NoSave) { $mypyArgs += "--no-save" }
 if ($NoAutoInstall) { $mypyArgs += "--no-auto-install" }
 if ($Unit) { $mypyArgs += "--unit" }
 if ($Integration) { $mypyArgs += "--integration" }
 if ($E2E) { $mypyArgs += "--e2e" }
 if ($Fast) { $mypyArgs += "--fast" }
 if ($Slow) { $mypyArgs += "--slow" }
 if ($Specific) {
 $mypyArgs += "--specific"
 $mypyArgs += $Specific
 }
 if ($Keyword) {
 $mypyArgs += "-k"
 $mypyArgs += $Keyword
 }
 if ($Dbg) { $mypyArgs += "--debug" }

 $results = @{}
 $totalProjects = $projectsToCheck.Count
 $currentProject = 0

 foreach ($project in $projectsToCheck) {
 $currentProject++
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "[$currentProject/$totalProjects] Mypy: $project" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""

 & python $mypyScript @mypyArgs $project
 $exitCode = $LASTEXITCODE
 $results[$project] = @{ success = ($exitCode -eq 0); exitCode = $exitCode }

 if ($exitCode -eq 0) {
 Write-Host ""
 Write-Host "[PASS] Mypy passed for $project" -ForegroundColor Green
 } else {
 Write-Host ""
 Write-Host "[FAIL] Mypy failed for $project (exit code: $exitCode)" -ForegroundColor Red
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Mypy Summary" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan

 $passed = ($results.Keys | Where-Object { $results[$_].success -eq $true }).Count
 $failed = ($results.Keys | Where-Object { $results[$_].success -eq $false }).Count

 foreach ($project in ($results.Keys | Sort-Object)) {
 $result = $results[$project]
 $status = if ($result.success) { "[PASS]" } else { "[FAIL]" }
 $color = if ($result.success) { "Green" } else { "Red" }
 Write-Host " $status : $project" -ForegroundColor $color
 }

 Write-Host ""
 Write-Host "Total: $totalProjects | Passed: $passed | Failed: $failed" -ForegroundColor Cyan

 if ($failed -gt 0) {
 exit 1
 }
 exit 0
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
