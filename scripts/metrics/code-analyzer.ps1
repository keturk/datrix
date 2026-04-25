#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build a Markdown report of Python symbols (classes, methods, functions, constants, type aliases)
    and cross-file duplicate top-level names across Datrix packages.

.DESCRIPTION
    Activates the Datrix virtual environment and runs code_analyzer.py. The report is written
    under the current working directory by default (inherited cwd), not next to this script.

.PARAMETER Projects
    One or more project names (e.g. datrix-common datrix-language). Positional.

.PARAMETER All
    Run for every datrix-* package under the workspace (same as other metrics scripts).

.PARAMETER Src
    Include each project's src/ tree. Default scan is src-only when -Tests is not used alone.

.PARAMETER Tests
    Include each project's tests/ tree. Use alone for tests-only scan.

.PARAMETER Output
    Optional report path (passed to Python as --output). Relative paths resolve against cwd.

.PARAMETER Dbg
    Pass --debug to Python (prints scan roots to stderr).

.EXAMPLE
    .\code-analyzer.ps1 datrix-common

.EXAMPLE
    .\code-analyzer.ps1 -All

.EXAMPLE
    .\code-analyzer.ps1 datrix-common -Tests

.EXAMPLE
    .\code-analyzer.ps1 -All -Src -Tests -Output reports\structure.md
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$Src,

    [switch]$Tests,

    [string]$Output,

    [switch]$Dbg
)

if ($Projects.Count -eq 0 -and -not $All) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\code-analyzer.ps1 <project> [project2 ...] [-Src] [-Tests] [-Output path] [-Dbg]" -ForegroundColor White
    Write-Host "  .\code-analyzer.ps1 -All [-Src] [-Tests] [-Output path] [-Dbg]" -ForegroundColor White
    Write-Host ""
    Write-Host "Default: src/ only. -Tests alone: tests/ only. -Src and -Tests: both trees." -ForegroundColor Gray
    Write-Host "Report defaults to .\code-structure-report.md (cwd). Use Get-Help for full help." -ForegroundColor Gray
    exit 1
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "metrics\code_analyzer.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "code_analyzer.py not found at: $pythonScript"
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
    $workspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    $pyArgs = @($pythonScript)
    if ($All) {
        $pkgList = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
        if ($pkgList.Count -eq 0) {
            Write-Host "ERROR: No datrix-* packages under: $workspaceRoot" -ForegroundColor Red
            exit 1
        }
        $pyArgs += "--all"
    }
    else {
        $normalized = $Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }
        $filtered = $normalized | Where-Object { $_ -ne "datrix" }
        if ($filtered.Count -eq 0) {
            Write-Host "ERROR: No valid projects (datrix meta folder is excluded)." -ForegroundColor Red
            exit 1
        }
        $pyArgs += $filtered
    }
    if ($Output) {
        $pyArgs += "--output", $Output
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

    Write-Host "Python code structure analyzer (AST)..." -ForegroundColor Cyan
    Write-Host ""

    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonExe @pyArgs
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
