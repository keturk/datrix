#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Scan Datrix Python code for anti-patterns using LibCST.

.DESCRIPTION
    Runs the LibCST anti-pattern scanner, in the shared venv, on one or more
    projects (or the entire monorepo with -All). libcst must be installed in the
    venv; the scanner refuses, naming the install command, when it is not.

    Patterns detected:
    - silent-fallback       : dict.get(key, None)
    - empty-except          : except: pass
    - missing-encoding      : read_text()/write_text()/open() without encoding=
    - banned-test-import    : MagicMock/Mock/patch/SimpleNamespace in tests
    - placeholder-body      : pass / raise NotImplementedError as sole body
    Uses the Python implementation in scripts/scan/lib/libcst_scanner.py.

.PARAMETER Projects
    One or more project names to scan (e.g. datrix-common datrix-language).
    Positional.

.PARAMETER All
    Scan all projects in the monorepo.

.PARAMETER Report
    Write a markdown report to this path (relative to monorepo root).

.EXAMPLE
    .\libcst.ps1 datrix-common
    Scan datrix-common for anti-patterns.

.EXAMPLE
    .\libcst.ps1 -All
    Scan all projects.

.EXAMPLE
    .\libcst.ps1 -All -Report libcst-report.md
    Scan all projects and write a markdown report.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [string]$Report = ""
)

if ($Projects.Count -eq 0 -and -not $All) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\libcst.ps1 <project> [project2 ...]" -ForegroundColor White
    Write-Host "  .\libcst.ps1 -All [-Report <path>]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\libcst.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @(if ($All) { "--all" } else { $Projects })
if ($Report) { $pyArgs += @("--report", $Report) }

# libcst_scanner.py refuses, naming the install command, when libcst is not in the shared venv.
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\libcst_scanner.py") -Arguments $pyArgs)
