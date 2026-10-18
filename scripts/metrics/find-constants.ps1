#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Find string literals in Datrix Python projects and write a grouped Markdown report.

.DESCRIPTION
    Activates the Datrix virtual environment and runs find_constants.py on one or more
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

    [int]$MaxValueChars = 120
)

if ($Projects.Count -eq 0 -and -not $All) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\find-constants.ps1 <project> [project2 ...] [-Src] [-Tests] [-Output path] [-IncludeDocstrings] [-MinLength N] [-MaxValueChars N]" -ForegroundColor White
    Write-Host "  .\find-constants.ps1 -All [-Src] [-Tests] [-Output path] [-IncludeDocstrings] [-MinLength N] [-MaxValueChars N]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\find-constants.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @(if ($All) { "--all" } else { $Projects })
if ($Output) { $pyArgs += @("--output", $Output) }
if ($IncludeDocstrings) { $pyArgs += "--include-docstrings" }
if ($MinLength -ne 1) { $pyArgs += @("--min-length", "$MinLength") }
if ($MaxValueChars -ne 120) { $pyArgs += @("--max-value-chars", "$MaxValueChars") }
if ($Src) { $pyArgs += "--src" }
if ($Tests) { $pyArgs += "--tests" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\find_constants.py") -Arguments $pyArgs)
