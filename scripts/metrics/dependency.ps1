#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report dependency relationships between Datrix packages.

.DESCRIPTION
 Activates the datrix virtual environment and runs the library dependency.py
 to report which datrix-* packages depend on which (from pyproject.toml).
 Modes: tree (default), list, json.

.PARAMETER Projects
 Optional. Restrict output to these package names (e.g. datrix-common, datrix-language).

.PARAMETER All
 Include all datrix-* packages (default when no -Projects).

.PARAMETER Mode
 Output mode: tree, list, json. Default: tree.

.PARAMETER VerboseOutput
 Verbose output.

.PARAMETER Dbg
 Debug output.

.EXAMPLE
 .\dependency.ps1 -All
 Show dependency tree for all Datrix packages.

.EXAMPLE
 .\dependency.ps1 -All -Mode list
 Show edges (package -> dependency) for all packages.

.EXAMPLE
 .\dependency.ps1 datrix-common datrix-language -Mode json
 Show JSON for datrix-common and datrix-language only.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("tree", "list", "json")]
 [string]$Mode = "tree",
 [switch]$VerboseOutput,
 [switch]$Dbg
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
$dependencyScript = Join-Path $libraryDir "metrics\dependency.py"

if (-not (Test-Path $dependencyScript)) {
 Write-Error "Error: dependency.py not found at: $dependencyScript"
 exit 1
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $useAll = $false
 $packageFilter = @()

 if ($All) {
 $useAll = $true
 Write-Host "Dependency (mode=$Mode) for all Datrix packages" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 $packageFilter = ($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
 if ($packageFilter.Count -eq 0) {
 Write-Host "ERROR: No valid projects specified (datrix is excluded)." -ForegroundColor Red
 exit 1
 }
 Write-Host "Dependency (mode=$Mode) for: $($packageFilter -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\dependency.ps1 -All [options]" -ForegroundColor Cyan
 Write-Host " .\dependency.ps1 <package> [package ...] [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\dependency.ps1 -All" -ForegroundColor Cyan
 Write-Host " .\dependency.ps1 -All -Mode list" -ForegroundColor Cyan
 Write-Host " .\dependency.ps1 -All -Mode json" -ForegroundColor Cyan
 Write-Host " .\dependency.ps1 datrix-common datrix-language -Mode tree" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Parameters:" -ForegroundColor Yellow
 Write-Host " -Mode tree | list | json (default: tree)" -ForegroundColor Gray
 Write-Host " -All Include all datrix-* packages" -ForegroundColor Gray
 Write-Host " -VerboseOutput Verbose output" -ForegroundColor Gray
 Write-Host " -Dbg Debug output" -ForegroundColor Gray
 Write-Host ""
 $available = Get-DatrixPackageNamesGlobWithPyProject -WorkspaceRoot $workspaceRoot
 if ($available.Count -gt 0) {
 Write-Host "Available packages:" -ForegroundColor Yellow
 foreach ($p in $available) { Write-Host " - $p" -ForegroundColor Cyan }
 }
 Write-Host ""
 exit 1
 }

 if (-not (Ensure-DatrixVenv)) {
 Write-Error "Failed to ensure virtual environment is ready"
 exit 1
 }

 $projectArgs = @(
 $dependencyScript,
 "--workspace-root", $workspaceRoot,
 "--mode", $Mode
 )
 if ($packageFilter.Count -gt 0) {
 $projectArgs += "--packages"
 $projectArgs += $packageFilter
 }
 if ($VerboseOutput) { $projectArgs += "--verbose" }
 if ($Dbg) { $projectArgs += "--debug" }

 & python @projectArgs
 $exitCode = $LASTEXITCODE

 if ($exitCode -eq 0) {
 Write-Host ""
 Write-Host "[OK] Dependency report completed" -ForegroundColor Green
 } else {
 Write-Host ""
 Write-Host "[FAIL] Dependency script exited with code $exitCode" -ForegroundColor Red
 }
 exit $exitCode
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
