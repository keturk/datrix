#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Extract @canonical, @pattern, @boundary, @invariant, @consumes markers from Python source
    into a SQLite database for agent-assisted development.

.DESCRIPTION
    Scans Python files for specially formatted comment markers and builds a queryable SQLite
    database at .logic-map/markers.db (under the workspace root). The database lets AI agents
    quickly look up canonical implementations, approved patterns, system boundaries, invariants,
    and dependency relationships — preventing logic duplication across sessions.

    Activates the Datrix virtual environment and runs logic_map.py.

.PARAMETER Projects
    One or more project names (e.g. datrix-common datrix-language). Positional.

.PARAMETER All
    Scan every datrix* project (scan roots depend on -Src / -Tests; default is both).

.PARAMETER Src
    Scan only each project's src tree. Combine with -Tests to scan both (default).

.PARAMETER Tests
    Scan only each project's tests tree. Combine with -Src to scan both (default).

.PARAMETER Dbg
    Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
    .\logic-map.ps1 -All
    Rebuild the logic map from all datrix projects (src + tests).

.EXAMPLE
    .\logic-map.ps1 datrix-common datrix-language
    Rebuild the logic map from two projects.

.EXAMPLE
    .\logic-map.ps1 -All -Src
    Scan only src trees across all projects.

.EXAMPLE
    .\logic-map.ps1 -All -Tests
    Scan only test trees across all projects.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$Src,

    [switch]$Tests,

    [switch]$Dbg
)

if ($Projects.Count -eq 0 -and -not $All) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\logic-map.ps1 -All [-Src] [-Tests] [-Dbg]" -ForegroundColor White
    Write-Host "  .\logic-map.ps1 <project> [project2 ...] [-Src] [-Tests] [-Dbg]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\logic-map.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\logic_map.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "logic_map.py not found at: $pythonScript"
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
    if ($All) {
        $pyArgs += "--all"
    }
    else {
        $pyArgs += $Projects
    }
    if ($Src) {
        $pyArgs += "--src"
    }
    if ($Tests) {
        $pyArgs += "--tests"
    }
    if ($Dbg) {
        $pyArgs += "--debug"
    }

    Write-Host "Building logic map..." -ForegroundColor Cyan
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
