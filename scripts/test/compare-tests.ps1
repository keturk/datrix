#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compare timestamped test results inside one .test_results folder.
.DESCRIPTION
 Runs datrix_scripts.test.compare_tests against a single project .test_results directory (-TestResults, alias
 -Path, also the first positional argument). Unit test runs are compared only with other unit-test timestamps,
 and deploy test runs only with other deploy-test timestamps. -Report also writes a Markdown report. -SelfTest
 runs only the self-test. Exit 0 runs compared, 1 not a .test_results folder (or self-test failed), 2 no runs
 found or usage error. python -m datrix_scripts.test.compare_tests --help describes every option.
.EXAMPLE
 .\test\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, Mandatory = $true, ParameterSetName = "Run")][Alias("Path")][string]$TestResults,
 [Parameter(ParameterSetName = "Run")][string]$Report, [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.compare_tests" -Parameters $PSBoundParameters
exit $LASTEXITCODE
