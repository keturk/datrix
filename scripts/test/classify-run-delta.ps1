#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Classify the delta between two structured test-results runs.
.DESCRIPTION
 Runs datrix_scripts.classify_run_delta (shared with the red-run digest). Compares the failing sets and cluster
 patterns of a previous and a current run of the same project, writes run-delta.json into the CURRENT run
 directory, and reports a verdict (SUCCESS / PARTIAL / NO_CHANGE / REGRESSION). -Previous and -Current are each a
 run directory or its index.json, also accepted positionally in that order. -SelfTest runs only the self-test.
 Exit 0 SUCCESS (or self-test passed), 1 any other verdict (or self-test failed), 2 usage error.
 python -m datrix_scripts.classify_run_delta --help describes every option.
.EXAMPLE
 .\test\classify-run-delta.ps1 <previous-run-dir> <current-run-dir>
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0)][string]$Previous, [Parameter(Position = 1)][string]$Current,
 [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.classify_run_delta" -Parameters $PSBoundParameters
exit $LASTEXITCODE
