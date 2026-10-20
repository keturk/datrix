#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run coverage-driven test generation for one or more Datrix projects.
.DESCRIPTION
 Runs datrix_scripts.metrics.test_gen for each project: the project's tests under coverage,
 then the uncovered functions ranked by priority.
 Modes:
 - report       : list uncovered functions ranked by priority
 - generate     : generate test for top-ranked (or target) function
 - generate-all : generate tests for all ranked candidates
.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).
.PARAMETER All
 Run for all Datrix projects (datrix-* folders, excluding datrix).
.PARAMETER Mode
 report | generate | generate-all (default: report).
.PARAMETER Generate
 Shortcut for -Mode generate.
.PARAMETER GenerateAll
 Shortcut for -Mode generate-all.
.PARAMETER TargetFunction
 Optional function name to target in generate mode.
.PARAMETER MaxRetries
 Maximum generation retries per function (default: 3).
.PARAMETER MinUncoveredRatio
Include only functions where uncovered/total lines > ratio (default: 0.5).
.PARAMETER MaxPromptTokens
 Approximate prompt token budget before warnings are emitted (default: 6000).
.PARAMETER VerbosePrompts
 Print generated prompts for debugging.
.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.
.PARAMETER Model
 Models to use for generation, best first. Omit to use any model already in memory.
.PARAMETER LlmTimeout
 Request timeout in seconds for each generation attempt (default: 300).
.PARAMETER StopOnError
Stop after first project failure.
.PARAMETER VerboseOutput
 Number the per-project lines ([i/n]).
.PARAMETER SelfTest
 Run only the module's self-test (planted projects; no test is run, no model is asked) and exit.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,
 [switch]$All,
 [ValidateSet("report", "generate", "generate-all")]
 [string]$Mode = "report",
 [switch]$Generate,
 [switch]$GenerateAll,
 [string]$TargetFunction,
 [int]$MaxRetries = 3,
 [double]$MinUncoveredRatio = 0.5,
 [int]$MaxPromptTokens = 6000,
 [switch]$VerbosePrompts,
 [string[]]$LocalMachines = @(),
 [string[]]$Model = @(),
 [int]$LlmTimeout = 300,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.test_gen" -Parameters $PSBoundParameters
exit $LASTEXITCODE
