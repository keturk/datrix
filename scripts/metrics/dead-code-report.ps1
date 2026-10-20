#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Dead-code report: never referenced vs only referenced by tests (two-pass Vulture).

.DESCRIPTION
 Runs datrix_scripts.metrics.dead_code_report with two-pass Vulture in the shared venv.
Reports dead code in src/ only, classified as "never referenced" or "only referenced by tests".
With -MakeWhitelist it writes Vulture's whitelist candidates per package instead of the report.

.PARAMETER Projects
 One or more project names or folder paths (e.g. datrix-common, .\datrix-codegen-aws\). If omitted, scans
every datrix-* package discovered on disk with a pyproject.toml (except datrix) -- the same set as -All.

.PARAMETER All
 Scan all datrix-* projects (except datrix). Same discovered set as the no-argument default.

.PARAMETER MinConfidence
 Vulture min confidence 60-100. Default: 60 (include functions/classes).

.PARAMETER SortBySize
 List the largest unused functions and classes first (Vulture's --sort-by-size); each line carries
 the definition's size.

.PARAMETER MakeWhitelist
 Instead of the report, write Vulture's --make-whitelist candidates for each package to
 D:\datrix\.test-output\vulture\<package>-whitelist-candidates.py -- never into a package. Review a
 candidate before merging it into the package's vulture_whitelist.py.

.PARAMETER Output
 Report format: text or json. Default: text.

.PARAMETER OutputPath
 Optional file path to write the report to (the report alone; progress stays on the console). The
 report is still printed unless -Quiet.

.PARAMETER VerboseOutput
 Verbose progress to stderr.

.PARAMETER Raw
 Disable false-positive filters (show all Vulture findings).

.PARAMETER LlmReview
 Add an advisory local LLM review for the top deterministic findings.

.PARAMETER LlmLimit
 Maximum findings to include in the advisory LLM review. Default: 30.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
 Models to use for advisory review, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for advisory review.

.PARAMETER LlmNumPredict
 Max generated tokens for advisory review.

.PARAMETER LlmTemperature
 Sampling temperature for advisory review.

.PARAMETER Quiet
 Only write to -OutputPath (if set); do not print the report to the console.

.PARAMETER SelfTest
 Run only the self-test over planted packages (Vulture runs for real), then exit.

.EXAMPLE
  .\dead-code-report.ps1
  .\dead-code-report.ps1 -All -Output json -OutputPath D:\datrix\.test-output\dead-code.json
  .\dead-code-report.ps1 datrix-common .\datrix-language\ -MinConfidence 100 -OutputPath dead-code.md
  .\dead-code-report.ps1 datrix-common -MinConfidence 80 -SortBySize
  .\dead-code-report.ps1 datrix-cli -MakeWhitelist
  .\dead-code-report.ps1 -All -Raw
  .\dead-code-report.ps1 datrix-cli -LlmReview -LlmLimit 20
  .\dead-code-report.ps1 -SelfTest
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [int]$MinConfidence = 60,
 [switch]$SortBySize,
 [switch]$MakeWhitelist,
 [ValidateSet("text", "json")]
 [string]$Output = "text",
 [string]$OutputPath,
 [switch]$VerboseOutput,
 [switch]$Raw,
 [switch]$LlmReview,
 [int]$LlmLimit = 30,
 [string[]]$LocalMachines = @(),
 [string[]]$LlmModel = @(),
 [int]$LlmTimeout = 180,
 [int]$LlmNumPredict = 4096,
 [double]$LlmTemperature = 0.1,
 [switch]$Quiet,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.dead_code_report" -Parameters $PSBoundParameters
exit $LASTEXITCODE
