#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Find string literals in Datrix Python projects and write a grouped Markdown report.

.DESCRIPTION
    Activates the Datrix virtual environment and runs datrix_scripts.metrics.find_constants on one or more
    projects (or the entire monorepo with -All). The report is written to the current
    working directory by default (inherited cwd), matching where you invoke this script.

.PARAMETER Projects
    One or more project names (e.g. datrix-common datrix-language). Positional.

.PARAMETER All
    Run on every datrix* project (scan roots depend on -Src / -Tests; default is both).

.PARAMETER Src
    Scan only each project src tree. Combine with -Tests to scan both (default).

.PARAMETER Tests
    Scan only each project tests tree. Combine with -Src to scan both (default).

.PARAMETER Output
    Optional report file path (passed to Python as --output). When omitted, the report
    is string-constants-report.md under the current directory.

.PARAMETER IncludeDocstrings
    Include module/class/function docstrings in the report.

.PARAMETER MinLength
    Minimum string length to include (default 1).

.PARAMETER MaxValueChars
    Max characters from each value shown in section headings (default 120).

.PARAMETER SelfTest
    Run only the module's self-test (planted projects, no real workspace) and exit.

.EXAMPLE
    .\find-constants.ps1 -All

.EXAMPLE
    .\find-constants.ps1 datrix-common datrix-language

.EXAMPLE
    .\find-constants.ps1 datrix-common -Output reports\strings.md

.EXAMPLE
    .\find-constants.ps1 -All -Tests
    String literals under tests only, all projects.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$Src,

    [switch]$Tests,

    [string]$Output,

    [switch]$IncludeDocstrings,

    [int]$MinLength = 1,

    [int]$MaxValueChars = 120,

    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.find_constants" -Parameters $PSBoundParameters
exit $LASTEXITCODE
