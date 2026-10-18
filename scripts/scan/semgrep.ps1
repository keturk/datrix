#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run Semgrep with Datrix-specific rules across the monorepo.

.DESCRIPTION
    Runs individual YAML rules from scripts/config/semgrep-rules/, in the shared
    venv, on one or more projects (or all with -All). semgrep is declared in the
    "scripts" dependency group of datrix/pyproject.toml, which the shared venv
    installs; semgrep ships no Windows ARM64 wheel, so a native Windows ARM64 venv
    lacks it. The scanner refuses when it is missing, naming the platform or the
    install step.

    Each rule is run independently, making it easy to test and debug.
    Use -Rule to run a specific rule, -ListRules to see all available rules.

    Uses the Python implementation in scripts/scan/lib/semgrep_scanner.py.

.PARAMETER Projects
    One or more project names to scan (e.g. datrix-common datrix-language).
    Positional.

.PARAMETER All
    Scan all projects in the monorepo.

.PARAMETER Rule
    Run only this rule (repeatable). Name matches the YAML filename without
    extension (e.g. empty-except-pass, return-none-lookup).

.PARAMETER ListRules
    List all available rules and exit.

.PARAMETER Report
    Write a markdown report to this path (relative to monorepo root).

.PARAMETER ShowRaw
    Show raw semgrep output for each rule.

.PARAMETER SinglePass
    Run all selected rules in one semgrep process per file batch (faster when
    using multiple -Rule values). Forwarded as --single-pass to semgrep_scanner.py.

.EXAMPLE
    .\semgrep.ps1 -All
    Scan all projects with all rules.

.EXAMPLE
    .\semgrep.ps1 -All -Rule missing-encoding-read
    Scan all projects with only the missing-encoding-read rule.

.EXAMPLE
    .\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup
    Scan all projects with two specific rules.

.EXAMPLE
    .\semgrep.ps1 -ListRules
    List all available semgrep rules.

.EXAMPLE
    .\semgrep.ps1 datrix-common -Report semgrep-report.md
    Scan one project and write a report.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [string[]]$Rule = @(),

    [switch]$ListRules,

    [string]$Report = "",

    [switch]$ShowRaw,

    [switch]$SinglePass
)

if ($Projects.Count -eq 0 -and -not $All -and -not $ListRules) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\semgrep.ps1 <project> [project2 ...]" -ForegroundColor White
    Write-Host "  .\semgrep.ps1 -All [-Rule <name>] [-Report <path>]" -ForegroundColor White
    Write-Host "  .\semgrep.ps1 -ListRules" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\semgrep.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

# @(...) around the whole expression: an if-expression yielding one element unwraps it to a scalar
# string, and "+=" would then concatenate "--rule <name>" onto the project name.
$pyArgs = @(if ($ListRules) { "--list-rules" } elseif ($All) { "--all" } else { $Projects })
foreach ($r in $Rule) { $pyArgs += @("--rule", $r) }
if ($Report) { $pyArgs += @("--report", $Report) }
if ($ShowRaw) { $pyArgs += "--verbose" }
if ($SinglePass) { $pyArgs += "--single-pass" }

# semgrep_scanner.py refuses, naming the platform or the install step, when semgrep is not in the shared venv.
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\semgrep_scanner.py") -Arguments $pyArgs)
