#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build a Markdown report of Python symbols (classes, methods, functions, constants, type aliases)
    and cross-file duplicate top-level names across Datrix packages.

.DESCRIPTION
    Activates the Datrix virtual environment and runs code_analyzer.py. The report is written
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
    Pass --debug to Python (prints scan roots to stderr).

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
    Run only the duplicate-triage checks (planted sites, no model server) and exit.

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

if ($Projects.Count -eq 0 -and -not $All -and -not $SelfTest) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\code-analyzer.ps1 <project> [project2 ...] [-Src] [-Tests] [-Output path] [-Dbg]" -ForegroundColor White
    Write-Host "  .\code-analyzer.ps1 -All [-Src] [-Tests] [-Output path] [-Dbg]" -ForegroundColor White
    Write-Host ""
    Write-Host "Default: src/ only. -Tests alone: tests/ only. -Src and -Tests: both trees." -ForegroundColor Gray
    Write-Host "Report defaults to .\code-structure-report.md (cwd). Use Get-Help for full help." -ForegroundColor Gray
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
$pythonScript = Join-Path $PSScriptRoot "lib\code_analyzer.py"

if ($SelfTest) {
    exit (Invoke-DatrixPythonScript -Script $pythonScript -Arguments @("--self-test"))
}

$pythonArgs = @()
if ($All) {
    $pythonArgs += "--all"
}
else {
    $filtered = @($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ } | Where-Object { $_ -ne "datrix" })
    if ($filtered.Count -eq 0) {
        Write-Host "ERROR: No valid projects (datrix meta folder is excluded)." -ForegroundColor Red
        exit 1
    }
    $pythonArgs += $filtered
}
if ($Output) {
    $pythonArgs += @("--output", $Output)
}
if ($Src) {
    $pythonArgs += "--src"
}
if ($Tests) {
    $pythonArgs += "--tests"
}
if ($Dbg) {
    $pythonArgs += "--debug"
}
if ($LlmReview) {
    $pythonArgs += @("--llm-review", "--llm-limit", $LlmLimit)
    $pythonArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
}

Write-Host "Python code structure analyzer (AST)..." -ForegroundColor Cyan
Write-Host ""
exit (Invoke-DatrixPythonScript -Script $pythonScript -Arguments $pythonArgs -ShowCommand:$Dbg)
