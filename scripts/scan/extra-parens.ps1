#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Remove extraneous parentheses in Datrix Python code using Ruff (UP034).

.DESCRIPTION
    The behaviour is datrix_scripts.scan.extra_parens, run in the shared venv (ruff comes with
    its dev install) on one or more projects (or the entire monorepo with -All).

    Uses rule UP034 (pyupgrade extraneous-parentheses) only, so project
    pyproject ignore lists do not need to enable UP for this pass.

    -All wins over named projects; neither prints the usage and exits 1, and -DryRun with -Diff
    is refused (exit 1). Otherwise the exit code is Ruff's.

.PARAMETER Projects
    One or more project names (e.g. datrix-common datrix-language). Positional.

.PARAMETER All
    Run on every datrix* project that has src/ (and tests/ when present).

.PARAMETER DryRun
    Report violations only; do not modify files.

.PARAMETER Diff
    Print fix diffs to stdout; do not write files.

.PARAMETER SelfTest
    Run only the module's self-test: the usage and the -DryRun/-Diff refusal, each mode's Ruff
    command, a planted UP034 violation reported by a dry run, and the wrapper seam.

.EXAMPLE
    .\extra-parens.ps1 -All
    Fix extraneous parentheses across the monorepo.

.EXAMPLE
    .\extra-parens.ps1 datrix-common datrix-language
    Fix only those two projects.

.EXAMPLE
    .\extra-parens.ps1 -All -DryRun
    List UP034 findings without changing files.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Projects,
    [Parameter(ParameterSetName = "Run")][switch]$All,
    [Parameter(ParameterSetName = "Run")][switch]$DryRun,
    [Parameter(ParameterSetName = "Run")][switch]$Diff,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.extra_parens" -Parameters $PSBoundParameters
exit $LASTEXITCODE
