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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\logic_map_report.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "logic_map_report.py not found at: $pythonScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null
trap {
    Invoke-Cleanup
    exit 130
}

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    Write-Error "Failed to activate virtual environment"
    exit 1
}

try {
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    $pyArgs = @()
    if ($Output) {
        $pyArgs += "--output", $Output
    }

    Write-Host "Generating logic map report..." -ForegroundColor Cyan
    Write-Host ""

    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonExe $pythonScript @pyArgs
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldEAP

    exit $exitCode
}
catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.Exception.InnerException) {
        Write-Host "Inner: $($_.Exception.InnerException.Message)" -ForegroundColor Red
    }
    Write-Host ""
    Invoke-Cleanup
    exit 1
}
finally {
    Invoke-Cleanup
}
