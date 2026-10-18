#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Remove extraneous parentheses in Datrix Python code using Ruff (UP034).

.DESCRIPTION
    Activates the Datrix virtual environment, ensures ruff is installed, and runs
    extra_parens.py on one or more projects (or the entire monorepo with -All).

    Uses rule UP034 (pyupgrade extraneous-parentheses) only, so project
    pyproject ignore lists do not need to enable UP for this pass.

.PARAMETER Projects
    One or more project names (e.g. datrix-common datrix-language). Positional.

.PARAMETER All
    Run on every datrix* project that has src/ (and tests/ when present).

.PARAMETER DryRun
    Report violations only; do not modify files.

.PARAMETER Diff
    Print fix diffs to stdout; do not write files.

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

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$DryRun,

    [switch]$Diff
)

if ($Projects.Count -eq 0 -and -not $All) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\extra-parens.ps1 <project> [project2 ...] [-DryRun] [-Diff]" -ForegroundColor White
    Write-Host "  .\extra-parens.ps1 -All [-DryRun] [-Diff]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\extra-parens.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

if ($DryRun -and $Diff) {
    Write-Error "Specify only one of -DryRun or -Diff."
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @(if ($All) { "--all" } else { $Projects })
if ($DryRun) { $pyArgs += "--dry-run" }
if ($Diff) { $pyArgs += "--diff" }

# Ruff comes with the shared venv's dev install.
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\extra_parens.py") -Arguments $pyArgs)
