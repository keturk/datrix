#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Audit generated Python code for placeholders and syntax errors.

.DESCRIPTION
    The behaviour is datrix_scripts.scan.audit. Scans <OutputBase>\python\docker under the
    workspace root for:
    - Python syntax errors (ast.parse)
    - Placeholder patterns: pass, raise NotImplementedError, "# Test fixtures placeholder"
    When -Report is used, the report is written to the given path under the workspace root
    (e.g. examples-generated-audit-report.md -> <workspace>\examples-generated-audit-report.md),
    and its full path is printed. With no parameter at all the usage is printed (exit 1).

    Exit codes: 0, 1 the generated root is missing, 2 a syntax error under -FailOnSyntax, 3 an
    actionable placeholder under -FailOnPlaceholders.

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
    Request timeout in seconds for advisory triage. Default: 180.

.PARAMETER LlmNumPredict
    Max generated tokens for advisory triage. Default: 4096.

.PARAMETER LlmTemperature
    Sampling temperature for advisory triage. Default: 0.1.

.PARAMETER SelfTest
    Run only the module's self-test: a planted syntax error and placeholder set exit 2 / 3, an
    allowlisted placeholder is not actionable, the report is written, a missing generated root is
    refused, the usage is printed with no parameter, and the wrapper seam holds.

.EXAMPLE
    .\audit.ps1 -Report examples-generated-audit-report.md
    Run audit and write markdown report; script prints where the report was written.

.EXAMPLE
    .\audit.ps1 -Report examples-generated-audit-report.md -FailOnSyntax -FailOnPlaceholders
    Run audit, write report, and exit non-zero if syntax errors or actionable placeholders.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(ParameterSetName = "Run")][string]$OutputBase,
    [Parameter(ParameterSetName = "Run")][string]$Report,
    [Parameter(ParameterSetName = "Run")][switch]$FailOnSyntax,
    [Parameter(ParameterSetName = "Run")][switch]$FailOnPlaceholders,
    [Parameter(ParameterSetName = "Run")][switch]$LlmTriage,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.audit" -Parameters $PSBoundParameters
exit $LASTEXITCODE
