<#
.SYNOPSIS
    Audit generated Python code for placeholders and syntax errors.

.DESCRIPTION
    Scans .generated/python/docker for:
    - Python syntax errors (ast.parse)
    - Placeholder patterns: pass, raise NotImplementedError, "# Test fixtures placeholder"
    Run from repository root (directory containing .generated and datrix).
    When -Report is used, the report is written to the given path under the repository root
    (e.g. examples-generated-audit-report.md -> <repo>\examples-generated-audit-report.md).

.PARAMETER OutputBase
    Output base directory (default: .generated).

.PARAMETER Report
    Write markdown report to this path under repository root (e.g. examples-generated-audit-report.md).
    Script reports the full path where the report was written.

.PARAMETER FailOnSyntax
    Exit with non-zero if any syntax errors are found.

.PARAMETER FailOnPlaceholders
    Exit with non-zero if any placeholder patterns are found (actionable only; allowlisted excluded).

.PARAMETER LlmTriage
    Append advisory local LLM triage for syntax and placeholder findings.

.PARAMETER LlmLimit
    Maximum findings to include in advisory LLM triage. Default: 30.

.PARAMETER LocalMachines
    Machines to search for local model servers, in preference order. Omit to search the
    default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
    Models to use for advisory triage, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    Request timeout in seconds for advisory triage.

.PARAMETER LlmNumPredict
    Max generated tokens for advisory triage.

.PARAMETER LlmTemperature
    Sampling temperature for advisory triage.

.EXAMPLE
    .\audit.ps1 -Report examples-generated-audit-report.md
    Run audit and write markdown report; script prints where the report was written.

.EXAMPLE
    .\audit.ps1 -Report examples-generated-audit-report.md -FailOnSyntax -FailOnPlaceholders
    Run audit, write report, and exit non-zero if syntax errors or actionable placeholders.
#>
[CmdletBinding()]
param(
    [string]$OutputBase = ".generated",
    [string]$Report = "",
    [switch]$FailOnSyntax,
    [switch]$FailOnPlaceholders,
    [switch]$LlmTriage,
    [int]$LlmLimit = 30,
    [string[]]$LocalMachines = @(),
    [string[]]$LlmModel = @(),
    [int]$LlmTimeout = 180,
    [int]$LlmNumPredict = 4096,
    [double]$LlmTemperature = 0.1
)

# Show usage when no parameters provided (mimic compile.ps1)
if ($PSBoundParameters.Count -eq 0) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\audit.ps1 -Report <path>" -ForegroundColor White
    Write-Host "  .\audit.ps1 -Report examples-generated-audit-report.md [-FailOnSyntax] [-FailOnPlaceholders]" -ForegroundColor White
    Write-Host ""
    Write-Host "Report path is under repository root. Use Get-Help .\audit.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @("--output-base", $OutputBase)
if ($Report) { $pyArgs += @("--report", $Report) }
if ($FailOnSyntax) { $pyArgs += "--fail-on-syntax" }
if ($FailOnPlaceholders) { $pyArgs += "--fail-on-placeholders" }
if ($LlmTriage) {
    $pyArgs += @(
        "--llm-triage",
        "--llm-limit", "$LlmLimit",
        "--llm-num-predict", "$LlmNumPredict",
        "--llm-temperature", "$LlmTemperature"
    )
    $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
}

$exitCode = Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\audit_generated.py") -Arguments $pyArgs

if ($Report) {
    $reportFullPath = if ([System.IO.Path]::IsPathRooted($Report)) { $Report } else { Join-Path (Get-DatrixWorkspaceRoot) $Report }
    Write-Host "Report written to: $reportFullPath"
}
exit $exitCode
