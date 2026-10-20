#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Dump the logic map SQLite database to a readable Markdown report.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.logic_map_report. Refreshes the code index, reads
    .logic-map/markers.db and writes a grouped Markdown file for human review. The report
    includes all markers, rules, anti-patterns, cross-references, and a dependency graph. Not
    intended for agent consumption — use SQLite queries for that.

    Exit codes: 0 = report written, 1 = the index could not be refreshed or a @see names a topic
    no marker declares (the report is still written).

.PARAMETER Output
    Output file path (default: logic-map-report.md in current directory).

.PARAMETER SelfTest
    Run only the module's self-test: a planted database is reported, its dangling @see found,
    and the wrapper seam holds.

.EXAMPLE
    .\logic-map-report.ps1
    Write logic-map-report.md to the current directory.

.EXAMPLE
    .\logic-map-report.ps1 -Output docs\logic-map.md
    Write to a specific path.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string]$Output,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.logic_map_report" -Parameters $PSBoundParameters
exit $LASTEXITCODE
