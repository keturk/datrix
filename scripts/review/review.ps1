#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Review task files with the Task Review System.

.DESCRIPTION
 The behaviour is datrix_scripts.review.review: Tier 1 (one task at a time) and, per
 review/config.toml, Tier 2 (the whole phase), both on local model servers. Every argument is
 passed through unchanged, so the flags are the review's own (--task, --phase, --verify, --tier2,
 --tier2-on-threshold, --tier2-phase-gate, --config, --local-machine, --local-model; --help
 lists them). See quick-reference.md for the exit codes.

.PARAMETER ReviewArguments
 The review's arguments, passed through in order. ValueFromRemainingArguments.

.PARAMETER SelfTest
 Run only the module's self-test: both argument forms reach the review options, a review with
 neither --task nor --phase is refused, and the wrapper seam.

.EXAMPLE
 .\review.ps1 --phase <NN> --tier2-phase-gate

.EXAMPLE
 .\review.ps1 --task <path to one task file>
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", ValueFromRemainingArguments = $true)][string[]]$ReviewArguments,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.review.review" -Parameters $PSBoundParameters
exit $LASTEXITCODE
