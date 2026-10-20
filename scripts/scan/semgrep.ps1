#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run Semgrep with Datrix-specific rules across the monorepo.

.DESCRIPTION
    The behaviour is datrix_scripts.scan.semgrep. Runs individual YAML rules from
    scripts/config/semgrep-rules/, in the shared venv, on one or more projects (or all with
    -All). semgrep is declared in the "scripts" dependency group of datrix/pyproject.toml,
    which the shared venv installs; semgrep ships no Windows ARM64 wheel, so a native Windows
    ARM64 venv lacks it. The scanner refuses when it is missing, naming the platform or the
    install step.

    Each rule is run independently, making it easy to test and debug.
    Use -Rule to run a specific rule, -ListRules to see all available rules. -ListRules wins
    over a scan, and -All over named projects; neither a project nor -All prints the usage and
    exits 1.

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
    using multiple -Rule values).

.PARAMETER SelfTest
    Run only the module's self-test: the rule set lists and resolves, an unknown rule and an
    unknown project are refused, the usage is printed when nothing is selected, and the
    wrapper seam holds. Runs no semgrep process.

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
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Projects,
    [Parameter(ParameterSetName = "Run")][switch]$All,
    [Parameter(ParameterSetName = "Run")][string[]]$Rule,
    [Parameter(ParameterSetName = "Run")][switch]$ListRules,
    [Parameter(ParameterSetName = "Run")][string]$Report,
    [Parameter(ParameterSetName = "Run")][switch]$ShowRaw,
    [Parameter(ParameterSetName = "Run")][switch]$SinglePass,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.semgrep" -Parameters $PSBoundParameters
exit $LASTEXITCODE
