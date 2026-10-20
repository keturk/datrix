#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compare .generated vs .generated_saved with content-level feature detection.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.compare_generated. Runs the exhaustive
 content-level comparison and writes a Markdown report. Feature detection is by file content
 (same feature may be in different paths). Relative paths resolve under the workspace root.
 Report default: <workspace>\generated-comparison-report.md.

 Exit codes: 0 = report written, 1 = a generated root is missing, 2 = usage error.

.PARAMETER Current
 Current generated root (default: .generated).

.PARAMETER Saved
 Saved (old) generated root (default: .generated_saved).

.PARAMETER Report
 Output report path under the workspace root (default: generated-comparison-report.md).

.PARAMETER LlmSummary
 Append advisory local LLM summary to the generated comparison report.

.PARAMETER LlmLimit
 Maximum feature/project rows to include in advisory LLM summary. Default: 40.

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
 Run only the module's self-test: two planted trees are compared, a missing root exits 1, and
 the wrapper seam holds.

.EXAMPLE
 .\compare-generated.ps1
 Compare defaults and write report to <workspace>\generated-comparison-report.md.

.EXAMPLE
 .\compare-generated.ps1 -Report my-report.md
 Write report to <workspace>\my-report.md.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][string]$Current,
 [Parameter(ParameterSetName = "Run")][string]$Saved,
 [Parameter(ParameterSetName = "Run")][string]$Report,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.compare_generated" -Parameters $PSBoundParameters
exit $LASTEXITCODE
