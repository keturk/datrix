#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Lint documentation for common drift patterns.

.DESCRIPTION
    Checks Datrix monorepo docs for:
      1. Deprecated CLI flags in examples
      2. Fixed phase-count language
      3. CDX design doc filename validation
      4. CDX design doc structure validation
      5. Missing capability status labels

    Exit codes:
      0 = all checks passed
      1 = lint issues detected

.PARAMETER DocsDir
    One or more documentation directories to scan (positional).
    Defaults to all docs/ directories in the monorepo.

.PARAMETER Check
    Run only the specified check(s). Can be repeated.
    Available: deprecated-cli-flags, fixed-phase-count, cdx-filenames,
    cdx-structure, capability-status-labels

.PARAMETER Detailed
    Show detailed output including content and suggestions.

.PARAMETER Dbg
    Enable debug logging.

.PARAMETER LlmSuggest
    Append advisory local LLM replacement suggestions for deterministic findings.

.PARAMETER LlmLimit
    Maximum findings to include in advisory LLM suggestions. Default: 25.

.PARAMETER LocalMachines
    Machines to search for local model servers, in preference order. Omit to search the
    default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
    Models to use for advisory suggestions, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    Request timeout in seconds for advisory suggestions.

.PARAMETER LlmNumPredict
    Max generated tokens for advisory suggestions.

.PARAMETER LlmTemperature
    Sampling temperature for advisory suggestions.

.EXAMPLE
    .\check-docs.ps1
    Run all checks on all docs directories.

.EXAMPLE
    .\check-docs.ps1 -Check cdx-filenames -Check cdx-structure
    Run only CDX-related checks.

.EXAMPLE
    .\check-docs.ps1 -Detailed
    Show detailed output for all findings.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$DocsDir = @(),

    [Parameter()]
    [string[]]$Check = @(),

    [Parameter()]
    [switch]$Detailed,

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$LlmSuggest,

    [Parameter()]
    [int]$LlmLimit = 25,

    [Parameter()]
    [string[]]$LocalMachines = @(),

    [Parameter()]
    [string[]]$LlmModel = @(),

    [Parameter()]
    [int]$LlmTimeout = 180,

    [Parameter()]
    [int]$LlmNumPredict = 4096,

    [Parameter()]
    [double]$LlmTemperature = 0.1
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @($DocsDir)
foreach ($c in $Check) {
    # Handle comma-separated values (e.g., -Check cdx-filenames,cdx-structure)
    foreach ($item in ($c -split ',')) {
        $trimmed = $item.Trim()
        if ($trimmed) { $pyArgs += @("--check", $trimmed) }
    }
}
if ($Detailed) { $pyArgs += "--verbose" }
if ($Dbg) { $pyArgs += "--debug" }
if ($LlmSuggest) {
    $pyArgs += @(
        "--llm-suggest",
        "--llm-limit", "$LlmLimit",
        "--llm-num-predict", "$LlmNumPredict",
        "--llm-temperature", "$LlmTemperature"
    )
    $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
}

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\check_docs.py") -Arguments $pyArgs)
