#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Self-test for the [dev] extra specs and dependency-group specs the shared venv installs (datrix_scripts.dev_specs).
.DESCRIPTION
 A package's [dev] extra may name a sibling workspace package by direct URL ("datrix-extensions @ file:../datrix-extensions").
 Installing that URL into the shared venv replaces the sibling's editable install with a frozen copy; dev_specs names
 such a sibling by its bare name instead.
.PARAMETER SelfTest
 Run only dev_specs.py's self-test and exit. Does not read the real workspace.
.EXAMPLE
 .\venv-dev-specs.ps1 -SelfTest
#>
[CmdletBinding()]
param(
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev_specs" -Parameters $PSBoundParameters
exit $LASTEXITCODE
