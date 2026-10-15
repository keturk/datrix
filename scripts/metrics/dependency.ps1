#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report dependency relationships between Datrix packages.

.DESCRIPTION
 Activates the datrix virtual environment and runs lib\dependency.py
 to report which datrix-* packages depend on which (from pyproject.toml).
 Modes: tree (default), list, json, third-party (every non-datrix runtime dependency
 with each declaring package and its spec; SPEC DRIFT marks differing specifiers).

.PARAMETER Projects
 Optional. Restrict output to these package names (e.g. datrix-common, datrix-language).

.PARAMETER All
 Include all datrix-* packages (default when no -Projects).

.PARAMETER Mode
 Output mode: tree, list, json, third-party. Default: tree.

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
 .\dependency.ps1 -All -Mode third-party
 Every third-party runtime dependency, who declares it, and where the specifiers drift.

.EXAMPLE
 .\dependency.ps1 datrix-common datrix-language -Mode json
 Show JSON for datrix-common and datrix-language only.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("tree", "list", "json", "third-party")]
 [string]$Mode = "tree",
 [switch]$VerboseOutput,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$workspaceRoot = Get-DatrixWorkspaceRoot

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
 Write-Host " -Mode tree | list | json | third-party (default: tree)" -ForegroundColor Gray
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

 $projectArgs = @("--workspace-root", $workspaceRoot, "--mode", $Mode)
 if ($packageFilter.Count -gt 0) { $projectArgs += @("--packages") + @($packageFilter) }
 if ($VerboseOutput) { $projectArgs += "--verbose" }
 if ($Dbg) { $projectArgs += "--debug" }

 exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\dependency.py") -Arguments $projectArgs)
