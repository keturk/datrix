#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Lint Datrix .dtrx specification files using semantic analysis.

.DESCRIPTION
 Discovers system.dtrx entry points under the given paths and runs the full
 Datrix semantic analysis pipeline on each one. Reports all diagnostics
 (errors and warnings) with error codes, severities, messages, and source
 locations.

 Exit codes:
   0  No issues found
   1  One or more errors found (or warnings in -Strict mode)

.PARAMETER Path
 One or more file or directory paths to scan (positional, variadic).
 Each may be a directory (scanned recursively for system.dtrx) or a direct
 path to a system.dtrx file.

.PARAMETER All
 Scan all subdirectories in the monorepo root for system.dtrx projects.
 Mutually exclusive with Path.

.PARAMETER Strict
 Treat warnings as errors. Exits with code 1 if any warnings are found.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER Profile
 Config profile used when resolving service/shared .dcfg files.
 Defaults to 'development'.

.PARAMETER ResolveConfigs
 Enable service/shared .dcfg resolution before semantic checks.
 Disabled by default.

.EXAMPLE
 .\datrix-linter.ps1 examples\01-foundation
 Lint the 01-foundation example project.

.EXAMPLE
 .\datrix-linter.ps1 -All
 Lint all Datrix projects in the monorepo.

.EXAMPLE
 .\datrix-linter.ps1 -All -Strict
 Lint all projects and fail on warnings too.

.EXAMPLE
 .\datrix-linter.ps1 datrix\examples\03-domains\ecommerce\system.dtrx
 Lint a specific system.dtrx file directly.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Path = @(),

    [Parameter()]
    [switch]$All,

    [Parameter()]
    [switch]$Strict,

    [Parameter()]
    [switch]$Dbg

    ,
    [Parameter()]
    [switch]$ResolveConfigs

    ,
    [Parameter()]
    [string]$Profile = "development"
)

$ErrorActionPreference = "Stop"

if ($All -and $Path.Count -gt 0) {
    Write-Error "Specify either -All or one or more paths, not both."
    exit 1
}

if (-not $All -and $Path.Count -eq 0) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\datrix-linter.ps1 -All [-Strict] [-Dbg]" -ForegroundColor White
    Write-Host "  .\datrix-linter.ps1 <path> [path2 ...] [-Strict] [-Dbg]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\datrix-linter.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @(if ($All) { "--all" } else { $Path })
if ($Strict) { $pythonArgs += "--strict" }
if ($Dbg) { $pythonArgs += "--debug" }
if ($ResolveConfigs) { $pythonArgs += "--resolve-configs" }
if ($ResolveConfigs -and $Profile) { $pythonArgs += @("--profile", $Profile) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\datrix_linter.py") -Arguments $pythonArgs)

