#!/usr/bin/env pwsh
<#
.SYNOPSIS
 The shared Datrix venv (D:\datrix\.venv): create it, check it, install the datrix-* packages into it.
.DESCRIPTION
 Runs datrix_scripts.venv. Actions run in this order: -Recreate, -Ensure, -InstallPackage <name> [-NoDev],
 -EnsurePackages [-SkipIfInstalled | -Force | -Offline], -TestCommand. Queries run alone: -BaseInterpreter,
 -ListPackages, -SelfTest. DATRIX_OFFLINE=1 runs no pip; DATRIX_VENV_VERBOSE=1 prints each step.
 python -m datrix_scripts.venv --help describes every option.
.EXAMPLE
 .\common\venv.ps1 -Ensure -EnsurePackages -SkipIfInstalled
#>
[CmdletBinding()]
param(
 [switch]$Ensure, [switch]$Recreate, [switch]$EnsurePackages, [switch]$SkipIfInstalled, [switch]$Force, [switch]$Offline,
 [string]$InstallPackage, [switch]$NoDev, [switch]$TestCommand, [switch]$BaseInterpreter, [switch]$ListPackages, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.venv" -Parameters $PSBoundParameters
exit $LASTEXITCODE
