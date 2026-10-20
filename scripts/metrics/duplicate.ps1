#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Pylint duplicate-code detection (R0801) for one or more Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.metrics.duplicate in the shared venv for each project.
 Finds similar/duplicated code blocks across files.

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run for all Datrix projects.

.PARAMETER Mono
 Run duplicate detection across the full monorepo (datrix + all datrix-* packages). Mutually exclusive with -All.

.PARAMETER MinLines
 Minimum similar lines to report. Default: 4 for a single project, 30 for a
 multi-root (-Mono) run, unless explicitly overridden.

.PARAMETER Tests
 Also include tests/ in duplicate-code detection.

.PARAMETER StopOnError
 Stop on first project failure.

.PARAMETER VerboseOutput
 Verbose output.

.PARAMETER LlmRefactorPlan
 Add an advisory local LLM refactor plan for duplicate-code groups.

.PARAMETER LlmLimit
 Maximum duplicate groups to include in the advisory LLM refactor plan. Default: 20.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
 Models to use for advisory refactor plan, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for advisory refactor plan.

.PARAMETER LlmNumPredict
 Max generated tokens for advisory refactor plan.

.PARAMETER LlmTemperature
 Sampling temperature for advisory refactor plan.

.PARAMETER SelfTest
 Run only the module's self-test (planted packages) and the wrapper seam checks, and exit.

.EXAMPLE
 .\duplicate.ps1 datrix-common
 .\duplicate.ps1 datrix-common -MinLines 6
 .\duplicate.ps1 datrix-common -Tests
 .\duplicate.ps1 -All
 .\duplicate.ps1 -Mono
 .\duplicate.ps1 -Mono -LlmRefactorPlan -LlmLimit 10
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [switch]$Mono,
 [int]$MinLines,
 [switch]$Tests,
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$LlmRefactorPlan,
 [int]$LlmLimit = 20,
 [string[]]$LocalMachines = @(),
 [string[]]$LlmModel = @(),
 [int]$LlmTimeout = 180,
 [int]$LlmNumPredict = 4096,
 [double]$LlmTemperature = 0.1,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.duplicate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
