#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Format Datrix .dtrx files losslessly, with the same formatter as `datrix format`.

.DESCRIPTION
 Discovers .dtrx files under the given paths and normalizes their whitespace over
 the parse tree (datrix_language.formatting): indentation follows bracket nesting,
 trailing whitespace is removed, and a run of blank lines becomes one. Every token
 and comment is verified identical before anything is written; writes are atomic.
 It writes nothing if any file fails parsing or verification. .dtrx.false fixtures
 are intentionally invalid and are not formatted.

.PARAMETER Path
 One or more file or directory paths to scan.

.PARAMETER All
 Scan all Datrix repository directories.

.PARAMETER Check
 Check formatting without modifying files.

.PARAMETER Diff
 Show unified diffs without modifying files.

.PARAMETER IndentSize
 Number of spaces per indentation level. Defaults to 4.

.PARAMETER Dbg
 Enable debug logging.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Path = @(),

    [Parameter()]
    [switch]$All,

    [Parameter()]
    [switch]$Check,

    [Parameter()]
    [switch]$Diff,

    [Parameter()]
    [ValidateRange(1, 8)]
    [int]$IndentSize = 4,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

if ($All -and $Path.Count -gt 0) {
    Write-Error "Specify either -All or one or more paths, not both."
    exit 1
}

if (-not $All -and $Path.Count -eq 0) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\datrix-format.ps1 -All [-Check] [-Diff] [-IndentSize 4] [-Dbg]" -ForegroundColor White
    Write-Host "  .\datrix-format.ps1 <path> [path2 ...] [-Check] [-Diff] [-IndentSize 4] [-Dbg]" -ForegroundColor White
    exit 1
}

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pathsToCheck = if ($All) { @(Get-DatrixDirectoryPaths | Where-Object { Test-Path $_ }) } else { @($Path) }

$pythonArgs = @($pathsToCheck) + @("--indent-size", "$IndentSize")
if ($Check) { $pythonArgs += "--check" }
if ($Diff) { $pythonArgs += "--diff" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\datrix_format.py") -Arguments $pythonArgs)
