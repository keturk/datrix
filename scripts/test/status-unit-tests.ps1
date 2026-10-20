#!/usr/bin/env pwsh
<#
.SYNOPSIS
 The status of the latest unit-test run of every generated project under <workspace>\.generated.
.DESCRIPTION
 Runs datrix_scripts.test.status_unit_tests. -Language narrows the report to <.generated>\<language>, validated
 against the language folders present (never a hardcoded list). -SelfTest runs the module's self-test.
 python -m datrix_scripts.test.status_unit_tests --help describes every option.
.EXAMPLE
 .\test\status-unit-tests.ps1 -L python
#>
[CmdletBinding()]
param(
 [Alias("L")][string]$Language, [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.status_unit_tests" -Parameters $PSBoundParameters
exit $LASTEXITCODE
