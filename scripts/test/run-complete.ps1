#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Complete workflow runner: syntax check, generation, unit tests and deployment tests of the generated projects.
.DESCRIPTION
 Runs datrix_scripts.test.run_complete for one example (-ExamplePath, optional -OutputPath derived from
 test-projects.json) or a test set (-All, -Domains, -TestSet), or with -Rerun only for the projects of the set
 whose latest results did not pass. -Language (-L, required) is any installed datrix.languages target;
 -Platform (-P, default docker-compose) the runtime segment of the output path; -Hosting (-H) overrides hosting.
 -Skip1..-Skip5 skip steps; -VerboseOutput, -FreshBuild (deploy builds with --no-cache), -DebugLogging (-Dbg).
 -LlmSummary prints an advisory local-model summary (-LlmLimit 12, -LocalMachines, -LlmModel, -LlmTimeout 180,
 -LlmNumPredict 4096, -LlmTemperature 0.1). Exit 0 when every step not skipped passed, 1 on a failed step or an
 invalid request, 2 on a usage error, 130 when interrupted. -SelfTest runs the module's self-test.
 python -m datrix_scripts.test.run_complete --help describes every option.
.EXAMPLE
 .\test\run-complete.ps1 "examples/02-features/01-core-data-modeling/entities/system.dtrx" -L python
.EXAMPLE
 .\test\run-complete.ps1 -Rerun -Domains -L python -Skip2
#>
[CmdletBinding()]
param(
 [Parameter(Position=0)][string]$ExamplePath, [Parameter(Position=1)][string]$OutputPath, [switch]$All, [switch]$Domains,
 [Alias("L")][string]$Language, [Alias("P")][string]$Platform, [Alias("H")][string]$Hosting, [string]$TestSet,
 [switch]$Rerun, [switch]$VerboseOutput, [switch]$Skip1, [switch]$Skip2, [switch]$Skip3, [switch]$Skip4, [switch]$Skip5,
 [switch]$FreshBuild, [Alias("Dbg")][switch]$DebugLogging, [switch]$LlmSummary, [int]$LlmLimit, [string[]]$LocalMachines,
 [string[]]$LlmModel, [int]$LlmTimeout, [int]$LlmNumPredict, [double]$LlmTemperature, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.run_complete" -Parameters $PSBoundParameters
exit $LASTEXITCODE
