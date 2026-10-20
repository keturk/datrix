#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run error message quality detection and scoring for one or more Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.metrics.error_messages for each project. Modes: check (enforce minimum
 quality score), report (list all sites).

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run metrics for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Mode
 Mode to run: check (enforce min score) or report (list all sites). Default: check.

.PARAMETER MinScore
 Minimum quality score for check mode (0-4). Default: 2.

.PARAMETER Fix
 Fix the worst error-message violation using a local model (check mode only).

.PARAMETER FixAll
 Fix ALL violations, not just the worst. Implies -Fix.

.PARAMETER Test
 Run pytest after each fix to verify; revert if tests fail (-Fix/-FixAll only).

.PARAMETER MaxRetries
 Max model attempts per violation. Default: 3.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order, for -Fix/-FixAll.
 Omit to search the default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER Model
 Models to use for -Fix/-FixAll, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for each fix attempt. Default: 300.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Also list the error sites the exclusion list skips.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (planted projects; no model is asked) and exit.

.EXAMPLE
 .\error-messages.ps1 datrix-common
 Check error message quality in datrix-common with default min-score 2.

.EXAMPLE
 .\error-messages.ps1 datrix-common -Mode report
 Report all error sites with scores for datrix-common.

.EXAMPLE
 .\error-messages.ps1 -All
 Check all projects with default settings.

.EXAMPLE
 .\error-messages.ps1 -All -MinScore 3
 Enforce minimum score 3 across all projects.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("check", "report")]
 [string]$Mode = "check",
 [Parameter()]
 [int]$MinScore = 2,
 [switch]$Fix,
 [switch]$FixAll,
 [switch]$Test,
 [int]$MaxRetries = 3,
 [string[]]$LocalMachines = @(),
 [string[]]$Model = @(),
 [int]$LlmTimeout = 300,
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$Dbg,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.error_messages" -Parameters $PSBoundParameters
exit $LASTEXITCODE
