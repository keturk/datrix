#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Bandit security scanner for one or more Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.metrics.bandit for each project. Finds common security issues in Python code.
 Bandit comes with the shared venv (the scripts dependency group); the module refuses, naming the
 declaring manifest and the venv repair, when it is missing.

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run for all Datrix projects.

.PARAMETER Severity
 Minimum severity: low, medium, high. Default: medium.

.PARAMETER Confidence
 Minimum confidence: low, medium, high. Default: medium.

.PARAMETER Format
 Output format: screen, json, csv, html, yaml, sarif. Default: screen.

.PARAMETER StopOnError
 Stop on first project failure.

.PARAMETER VerboseOutput
 Verbose output: Bandit's own output streamed as it runs.

.PARAMETER SelfTest
 Run only the module's self-test (planted projects, no real workspace) and exit.

.EXAMPLE
 .\bandit.ps1 datrix-common
 .\bandit.ps1 datrix-common -Severity high
 .\bandit.ps1 -All -Format json
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("low", "medium", "high")]
 [string]$Severity = "medium",
 [ValidateSet("low", "medium", "high")]
 [string]$Confidence = "medium",
 [ValidateSet("screen", "json", "csv", "html", "yaml", "sarif")]
 [string]$Format = "screen",
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.bandit" -Parameters $PSBoundParameters
exit $LASTEXITCODE
