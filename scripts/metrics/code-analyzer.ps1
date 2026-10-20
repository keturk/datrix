#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build a Markdown report of Python symbols (classes, methods, functions, constants, type aliases)
    and cross-file duplicate top-level names across Datrix packages.

.DESCRIPTION
    Activates the Datrix virtual environment and runs datrix_scripts.metrics.code_analyzer. The report is written
    under the current working directory by default (inherited cwd), not next to this script.

.PARAMETER Projects
    One or more project names (e.g. datrix-common datrix-language). Positional.

.PARAMETER All
    Run for every datrix-* package under the workspace (same as other metrics scripts).

.PARAMETER Src
    Include each project's src/ tree. Default scan is src-only when -Tests is not used alone.

.PARAMETER Tests
    Include each project's tests/ tree. Use alone for tests-only scan.

.PARAMETER Output
    Optional report path (passed to Python as --output). Relative paths resolve against cwd.

.PARAMETER Dbg
    Log the scan roots at DEBUG level (to stderr).

.PARAMETER LlmReview
    Add an advisory "Duplicate-name triage" section: a local model ranks which duplicate
    top-level names are one concept with two homes. Advisory only; never changes the exit code.

.PARAMETER LlmLimit
    Maximum duplicate groups sent to the local model (default 20).

.PARAMETER LocalMachines
    Machines to search for local model servers, in preference order. Omit to search the
    default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
    Local models to use, best first. Omit for any model already in memory, else the default load.

.PARAMETER LlmTimeout
    Seconds for each request to a ready local model (default 180).

.PARAMETER SelfTest
    Run only the duplicate-triage checks (planted sites, no model server) and the wrapper seam checks, and exit.

.EXAMPLE
    .\code-analyzer.ps1 datrix-common

.EXAMPLE
    .\code-analyzer.ps1 -All

.EXAMPLE
    .\code-analyzer.ps1 datrix-common -Tests

.EXAMPLE
    .\code-analyzer.ps1 -All -Src -Tests -Output reports\structure.md

.EXAMPLE
    .\code-analyzer.ps1 -All -LlmReview -LlmLimit 10
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$Src,

    [switch]$Tests,

    [string]$Output,

    [switch]$Dbg,

    [switch]$LlmReview,
    [int]$LlmLimit = 20,
    [string[]]$LocalMachines = @(),
    [string[]]$LlmModel = @(),
    [int]$LlmTimeout = 180,

    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.code_analyzer" -Parameters $PSBoundParameters
exit $LASTEXITCODE
