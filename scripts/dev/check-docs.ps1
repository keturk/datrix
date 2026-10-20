#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Lint documentation for common drift patterns.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.check_docs. Checks Datrix monorepo docs for:
      1. Deprecated CLI flags in examples
      2. Fixed phase-count language
      3. CDX design doc filename validation
      4. CDX design doc structure validation
      5. Missing capability status labels

    Exit codes:
      0 = all checks passed
      1 = lint issues detected
      2 = an unknown check was named

.PARAMETER DocsDir
    One or more documentation directories to scan (positional).
    Defaults to all docs/ directories in the monorepo.

.PARAMETER Check
    Run only the specified check(s). Can be repeated or comma-separated.
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
    Request timeout in seconds for advisory suggestions. Default: 180.

.PARAMETER LlmNumPredict
    Max generated tokens for advisory suggestions. Default: 4096.

.PARAMETER LlmTemperature
    Sampling temperature for advisory suggestions. Default: 0.1.

.PARAMETER SelfTest
    Run only the module's self-test: a planted doc is linted, an unknown check is refused, and
    the wrapper seam holds.

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
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$DocsDir,
 [Parameter(ParameterSetName = "Run")][string[]]$Check,
 [Parameter(ParameterSetName = "Run")][switch]$Detailed,
 [switch]$Dbg,
 [Parameter(ParameterSetName = "Run")][switch]$LlmSuggest,
 [Parameter(ParameterSetName = "Run")][int]$LlmLimit = 25,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName = "Run")][int]$LlmTimeout = 180,
 [Parameter(ParameterSetName = "Run")][int]$LlmNumPredict = 4096,
 [Parameter(ParameterSetName = "Run")][double]$LlmTemperature = 0.1,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.check_docs" -Parameters $PSBoundParameters
exit $LASTEXITCODE
