#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Lint and format config documents (.dcfg).

.DESCRIPTION
 Discovers .dcfg files and applies deterministic formatting.
 Also reports syntax errors and simple style warnings.

.PARAMETER Path
 File or directory paths to scan.

.PARAMETER All
 Scan all datrix repositories.

.PARAMETER Check
 Check mode only. Reports issues and needed formatting without writing files.

.PARAMETER SelfTest
 Run only the formatter self-test (round-trip fidelity fixture: service-wildcard
 rendering, replace/inheriting-base preservation, idempotence, comment fail-safe)
 and exit. Does not require -All or a path, and does not scan or format any real
 .dcfg file.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\config-linter.ps1 -All
 Format all .dcfg files under all datrix repositories.

.EXAMPLE
 .\config-linter.ps1 -All -Check
 Check all .dcfg files without modifying files.

.EXAMPLE
 .\config-linter.ps1 examples\01-foundation\config
 Format .dcfg files only in the provided folder.

.EXAMPLE
 .\config-linter.ps1 -SelfTest
 Run only the formatter self-test.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Path = @(),

 [Parameter()]
 [switch]$All,

 [Parameter()]
 [switch]$Check,

 [Parameter()]
 [switch]$SelfTest,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

if (-not $SelfTest) {
 if ($All -and $Path.Count -gt 0) {
  Write-Error "Specify either -All or one or more paths, not both."
  exit 1
 }

 if (-not $All -and $Path.Count -eq 0) {
  Write-Host "Usage:" -ForegroundColor Yellow
  Write-Host "  .\config-linter.ps1 -All [-Check] [-Dbg]" -ForegroundColor White
  Write-Host "  .\config-linter.ps1 <path> [path2 ...] [-Check] [-Dbg]" -ForegroundColor White
  Write-Host "  .\config-linter.ps1 -SelfTest" -ForegroundColor White
  Write-Host ""
  Write-Host "Use Get-Help .\config-linter.ps1 -Full for detailed help." -ForegroundColor Yellow
  exit 1
 }
}

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pathsToCheck = if ($All) { @(Get-DatrixDirectoryPaths | Where-Object { Test-Path $_ }) } else { $Path }

$pythonArgs = @($pathsToCheck)
if ($Check) { $pythonArgs += "--check" }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\config_linter.py") -Arguments $pythonArgs)

