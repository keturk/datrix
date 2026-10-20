#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run ast-grep structural searches across Datrix Python code.

.DESCRIPTION
    The behaviour is datrix_scripts.scan.ast_grep. Runs, in the shared venv, either saved YAML
    rules from scripts/config/ast-grep-rules/ or a one-off Python pattern across one or more
    projects (or all with -All). The ast-grep CLI must be on PATH (npm install -g @ast-grep/cli;
    AST_GREP_BIN overrides it); the scanner refuses when it is not.

    -ListRules wins over a scan, and -All over named projects; neither a project nor -All prints
    the usage and exits 1. -Pattern together with -Rule is refused (exit 1). Exit codes: 0 no
    finding, 1 a finding or a refusal, 2 an ast-grep error.

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

.PARAMETER SelfTest
    Run only the module's self-test: a saved rule finds a planted violation and passes a clean
    file, the rule set resolves, an unknown rule and -Pattern with -Rule are refused, the usage
    is printed when nothing is selected, and the wrapper seam holds.

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
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Projects,
    [Parameter(ParameterSetName = "Run")][switch]$All,
    [Parameter(ParameterSetName = "Run")][string]$Pattern,
    [Parameter(ParameterSetName = "Run")][string[]]$Rule,
    [Parameter(ParameterSetName = "Run")][switch]$ListRules,
    [Parameter(ParameterSetName = "Run")][string]$Report,
    [Parameter(ParameterSetName = "Run")][switch]$ShowRaw,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.ast_grep" -Parameters $PSBoundParameters
exit $LASTEXITCODE
