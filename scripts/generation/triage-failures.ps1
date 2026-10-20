#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Parse test or generation logs and group failures by root cause.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.triage_failures. Reads a test output log or
 generation results file and groups failures by likely root cause. Produces a summary table
 suitable for driving checkpoint-based debugging sessions.

 Supports:
   - pytest output logs (from test.ps1 or test-single.ps1)
   - Generation result logs (from generate.ps1)
   - Deploy test logs (from deploy tests)

 The triage output is designed to feed directly into /fix-tests or /checkpoint-debug
 skills as input.

 Exit codes:
   0 = log parsed successfully (failures may or may not exist)
   1 = parse error or file not found
   2 = usage error

.PARAMETER LogPath
 Path to the log file to parse. Accepts:
   - .log files (generation results, deploy tests)
   - .txt files (captured pytest output)

.PARAMETER Format
 Force a specific parser. Auto-detected from file content if not specified.
 Valid: pytest, generate, deploy

.PARAMETER OutputFile
 Write triage report to a file instead of stdout. Produces Markdown.

.PARAMETER Dbg
 Show the auto-detected format.

.PARAMETER LlmSummary
 Append an advisory local LLM triage summary.

.PARAMETER LlmLimit
 Maximum failure groups to include in the advisory LLM summary. Default: 10.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
 Models to use for advisory summary, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for advisory summary. Default: 180.

.PARAMETER LlmNumPredict
 Max generated tokens for advisory summary. Default: 4096.

.PARAMETER LlmTemperature
 Sampling temperature for advisory summary. Default: 0.1.

.PARAMETER SelfTest
 Run only the module's self-test: a planted generation log is triaged, a missing log exits 1,
 and the wrapper seam holds.

.EXAMPLE
 .\triage-failures.ps1 "D:\datrix\.generated\.results\generate-results-20260503-172334.log"
 Parse generation log and group failures.

.EXAMPLE
 .\triage-failures.ps1 "D:\datrix\datrix-codegen-python\.test_results\test-output.log"
 Parse pytest output log.

.EXAMPLE
 .\triage-failures.ps1 "D:\datrix\.generated\.results\generate-results-20260503-172334.log" -OutputFile "D:\datrix\.tmp\triage.md"
 Write triage report to a Markdown file.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0, Mandatory = $true)][string]$LogPath,
 [Parameter(ParameterSetName = "Run")][ValidateSet("pytest", "generate", "deploy", "")][string]$Format,
 [Parameter(ParameterSetName = "Run")][string]$OutputFile,
 [Parameter(ParameterSetName = "Run")][switch]$Dbg,
 [Parameter(ParameterSetName = "Run")][switch]$LlmSummary,
 [Parameter(ParameterSetName = "Run")][int]$LlmLimit,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName = "Run")][int]$LlmTimeout,
 [Parameter(ParameterSetName = "Run")][int]$LlmNumPredict,
 [Parameter(ParameterSetName = "Run")][double]$LlmTemperature,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.triage_failures" -Parameters $PSBoundParameters
exit $LASTEXITCODE
