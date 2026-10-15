<#
.SYNOPSIS
    Compare .generated vs .generated_saved with content-level feature detection.

.DESCRIPTION
    Runs the exhaustive content-level comparison script and writes a Markdown report.
    Feature detection is by file content (same feature may be in different paths).
    Report default: <datrix_root>\generated-comparison-report.md.

.PARAMETER Current
    Current generated root (default: .generated).

.PARAMETER Saved
    Saved (old) generated root (default: .generated_saved).

.PARAMETER Report
    Output report path under datrix root (default: generated-comparison-report.md).

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
    Request timeout in seconds for advisory summary.

.PARAMETER LlmNumPredict
    Max generated tokens for advisory summary.

.PARAMETER LlmTemperature
    Sampling temperature for advisory summary.

.EXAMPLE
    .\compare-generated.ps1
    Compare defaults and write report to datrix_root\generated-comparison-report.md.

.EXAMPLE
    .\compare-generated.ps1 -Report my-report.md
    Write report to datrix_root\my-report.md.
#>
[CmdletBinding()]
param(
    [string]$Current = ".generated",
    [string]$Saved = ".generated_saved",
    [string]$Report = "generated-comparison-report.md",
    [switch]$LlmSummary,
    [int]$LlmLimit = 40,
    [string[]]$LocalMachines = @(),
    [string[]]$LlmModel = @(),
    [int]$LlmTimeout = 180,
    [int]$LlmNumPredict = 4096,
    [double]$LlmTemperature = 0.1
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @("--current", $Current, "--saved", $Saved, "--report", $Report)
if ($LlmSummary) {
    $pyArgs += @(
        "--llm-summary",
        "--llm-limit", "$LlmLimit",
        "--llm-num-predict", "$LlmNumPredict",
        "--llm-temperature", "$LlmTemperature"
    )
    $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
}

$exitCode = Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\compare_generated.py") -Arguments $pyArgs

if ($exitCode -eq 0 -and $Report) {
    $reportFullPath = if ([System.IO.Path]::IsPathRooted($Report)) { $Report } else { Join-Path (Get-DatrixWorkspaceRoot) $Report }
    Write-Host "Report written to: $reportFullPath"
}
exit $exitCode
