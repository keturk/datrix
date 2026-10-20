#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Collect per-cluster failure data from a structured test-results run.
.DESCRIPTION
 Runs datrix_scripts.collect_failure_data: resolves the representative entry of every error/failure cluster in
 the run's index.json (-Path, or the newest run of -Project), embeds the tail of its detail log (-MaxLogLines,
 default 60) and a ready-to-run single-test command, groups clusters into families, and writes failure-data.json
 into the run directory. The first -LlmHintLimit families (default 5) get an advisory local-model hint
 (-NoLlmHints: none; -LocalMachines, -LlmModel, -LlmTimeout seconds, default 120). Exit 0 when done, 2 on a usage
 error. -SelfTest runs the module's self-test. python -m datrix_scripts.collect_failure_data --help describes every option.
.EXAMPLE
 .\test\collect-failure-data.ps1 -Project datrix-codegen-azure
.EXAMPLE
 .\test\collect-failure-data.ps1 D:\datrix\datrix-codegen-aws\.test_results\test-results-20260712-235813
#>
[CmdletBinding()]
param(
 [Parameter(Position=0)][string]$Path, [string]$Project, [int]$MaxLogLines, [switch]$SelfTest, [switch]$NoLlmHints,
 [int]$LlmHintLimit, [string[]]$LocalMachines, [string[]]$LlmModel, [int]$LlmTimeout, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.collect_failure_data" -Parameters $PSBoundParameters
exit $LASTEXITCODE
