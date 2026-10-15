#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run ast-grep structural searches across Datrix Python code.

.DESCRIPTION
    Runs, in the shared venv, either saved YAML rules from
    scripts/config/ast-grep-rules/ or a one-off Python pattern across one or
    more projects (or all with -All). The ast-grep CLI must be on PATH
    (npm install -g @ast-grep/cli); the scanner refuses when it is not.

    Uses the Python implementation in scripts/scan/lib/ast_grep.py.

.PARAMETER Projects
    One or more project names to scan (e.g. datrix-common datrix-language).
    Positional.

.PARAMETER All
    Scan all projects in the monorepo.

.PARAMETER Pattern
    Run a one-off ast-grep pattern against Python files.

.PARAMETER Rule
    Run only this saved rule (repeatable). Name matches the YAML filename
    without extension.

.PARAMETER ListRules
    List all available ast-grep rules and exit.

.PARAMETER Report
    Write a markdown report to this path (relative to monorepo root).

.PARAMETER ShowRaw
    Show raw ast-grep output for each invocation.

.EXAMPLE
    .\ast-grep.ps1 -All -Pattern "raise Exception($MSG)"
    Search all projects for a structural Python pattern.

.EXAMPLE
    .\ast-grep.ps1 datrix-common -Rule broad-exception
    Scan datrix-common with one saved ast-grep rule.

.EXAMPLE
    .\ast-grep.ps1 -ListRules
    List all available ast-grep rules.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [string]$Pattern = "",

    [string[]]$Rule = @(),

    [switch]$ListRules,

    [string]$Report = "",

    [switch]$ShowRaw
)

if ($Projects.Count -eq 0 -and -not $All -and -not $ListRules) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\ast-grep.ps1 <project> [project2 ...] -Pattern <pattern>" -ForegroundColor White
    Write-Host "  .\ast-grep.ps1 -All -Pattern <pattern> [-Report <path>]" -ForegroundColor White
    Write-Host "  .\ast-grep.ps1 -All [-Rule <name>] [-Report <path>]" -ForegroundColor White
    Write-Host "  .\ast-grep.ps1 -ListRules" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\ast-grep.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = if ($ListRules) { @("--list-rules") } elseif ($All) { @("--all") } else { @($Projects) }
if ($Pattern) { $pyArgs += @("--pattern", $Pattern) }
foreach ($r in $Rule) { $pyArgs += @("--rule", $r) }
if ($Report) { $pyArgs += @("--report", $Report) }
if ($ShowRaw) { $pyArgs += "--verbose" }

# ast_grep.py finds the ast-grep binary on PATH (AST_GREP_BIN overrides it) and refuses,
# naming the install command, when there is none.
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\ast_grep.py") -Arguments $pyArgs)
