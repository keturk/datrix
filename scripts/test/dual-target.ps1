#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run the same generation test set for every registered language and compare per-project results.
.DESCRIPTION
 Runs datrix_scripts.test.dual_target: for each registered datrix.languages target (in name order, discovered at
 run time) it runs dev\generate.ps1 -TestSet -Language -Platform, or with -Skip4 -Skip5 the complete run with its
 deploy and test steps skipped (-FreshBuild forwarded), then reads the newest generate-results-*.log under
 <workspace>\.generated\.results. Prints a Markdown table with one column per language and a parity column.
 -TestSet defaults to typescript-validation; -Platform (default docker) must be a registered datrix.platforms
 target. -Dbg logs at debug level here and in each child run. Exit 0 when every project succeeded in every
 language, 1 on any failure, missing project, unregistered platform or missing log. -SelfTest runs the module's
 self-test. python -m datrix_scripts.test.dual_target --help describes every option.
.EXAMPLE
 .\test\dual-target.ps1 -TestSet typescript-validation -Platform docker
.EXAMPLE
 .\test\dual-target.ps1 -Skip4 -Skip5 -FreshBuild
#>
[CmdletBinding()]
param(
 [string]$TestSet, [string]$Platform, [switch]$Skip4, [switch]$Skip5, [switch]$FreshBuild,
 [Alias("Dbg")][switch]$DebugLogging, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.dual_target" -Parameters $PSBoundParameters
exit $LASTEXITCODE
