#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Aggregate a GREEN/RED test gate verdict across Datrix packages.
.DESCRIPTION
 Runs datrix_scripts.test.gate_verdict in gate mode: for each project named (or every testable package with -All)
 it reads the newest test-results run and reports a per-project GREEN/RED verdict and an overall one, writing
 gate-verdict.json to <workspace>\.tmp\test\ unless -Output names a path. Exit 0 only when every project is GREEN,
 1 when any is RED, 2 on a usage error. -SelfTest judges planted green, red and index-less runs (GREEN, RED, RED)
 and reads no real run. python -m datrix_scripts.test.gate_verdict --help describes every option.
.EXAMPLE
 .\test\gate-verdict.ps1 -Projects datrix-codegen-azure,datrix-language
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$Projects,
 [switch]$All, [string]$Output, [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.gate_verdict" -Parameters $PSBoundParameters
exit $LASTEXITCODE
