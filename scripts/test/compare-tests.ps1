#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compare timestamped test results inside one .test_results folder.

.DESCRIPTION
 Runs compare_tests.py in the shared venv against a
 single project .test_results directory. Unit test runs are compared only with
 other unit-test timestamps, and deploy test runs are compared only with other
 deploy-test timestamps.

.PARAMETER TestResults
 Path to a single .test_results folder.

.PARAMETER Report
 Optional Markdown report path.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results

.EXAMPLE
 .\compare-tests.ps1 D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce\python\.test_results -Report D:\datrix\ecommerce-test-comparison.md
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$true)]
 [Alias("Path")]
 [string]$TestResults,

 [string]$Report,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

if (-not (Test-Path -LiteralPath $TestResults -PathType Container)) {
 Write-Host "Error: test results path is not a directory: $TestResults. Expected a project's .test_results folder." -ForegroundColor Red
 exit 1
}
$resolvedTestResultsPath = (Resolve-Path -LiteralPath $TestResults).Path
if ((Split-Path -Leaf $resolvedTestResultsPath) -ne ".test_results") {
 Write-Host "Error: expected a .test_results folder, got: $resolvedTestResultsPath" -ForegroundColor Red
 exit 1
}

$pythonArgs = @("--test-results", $resolvedTestResultsPath)
if ($Report) { $pythonArgs += @("--report", $Report) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\compare_tests.py") -Arguments $pythonArgs)
