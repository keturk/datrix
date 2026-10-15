#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Dump the logic map SQLite database to a readable Markdown report.

.DESCRIPTION
    Reads .logic-map/markers.db and writes a grouped Markdown file for human review.
    The report includes all markers, rules, anti-patterns, cross-references, and a
    dependency graph. Not intended for agent consumption — use SQLite queries for that.

.PARAMETER Output
    Output file path (default: logic-map-report.md in current directory).

.EXAMPLE
    .\logic-map-report.ps1
    Write logic-map-report.md to the current directory.

.EXAMPLE
    .\logic-map-report.ps1 -Output docs\logic-map.md
    Write to a specific path.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Output
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @()
if ($Output) { $pyArgs += @("--output", $Output) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\logic_map_report.py") -Arguments $pyArgs)
