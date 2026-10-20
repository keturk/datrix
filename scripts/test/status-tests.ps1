#!/usr/bin/env pwsh
<#
.SYNOPSIS
 The status of the latest test run of every testable datrix-* package.
.DESCRIPTION
 Runs datrix_scripts.status_tests (shared with the test runner and the tooling gates). Reads each package's
 latest .test_results run and prints one row per package. Exit 1 when any run FAILED, 2 when any is UNKNOWN,
 else 0. -SelfTest runs the module's self-test. python -m datrix_scripts.status_tests --help describes every option.
.EXAMPLE
 .\test\status-tests.ps1
#>
[CmdletBinding()]
param(
 [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.status_tests" -Parameters $PSBoundParameters
exit $LASTEXITCODE
