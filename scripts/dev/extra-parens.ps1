#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Remove extraneous parentheses in Datrix Python code using Ruff (UP034).

.DESCRIPTION
    Activates the Datrix virtual environment, ensures ruff is installed, and runs
    extra_parens.py on one or more projects (or the entire monorepo with -All).

    Uses rule UP034 (pyupgrade extraneous-parentheses) only, so project
    pyproject ignore lists do not need to enable UP for this pass.

.PARAMETER Projects
    One or more project names (e.g. datrix-common datrix-language). Positional.

.PARAMETER All
    Run on every datrix* project that has src/ (and tests/ when present).

.PARAMETER DryRun
    Report violations only; do not modify files.

.PARAMETER Diff
    Print fix diffs to stdout; do not write files.

.EXAMPLE
    .\extra-parens.ps1 -All
    Fix extraneous parentheses across the monorepo.

.EXAMPLE
    .\extra-parens.ps1 datrix-common datrix-language
    Fix only those two projects.

.EXAMPLE
    .\extra-parens.ps1 -All -DryRun
    List UP034 findings without changing files.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$DryRun,

    [switch]$Diff
)

if ($Projects.Count -eq 0 -and -not $All) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\extra-parens.ps1 <project> [project2 ...] [-DryRun] [-Diff]" -ForegroundColor White
    Write-Host "  .\extra-parens.ps1 -All [-DryRun] [-Diff]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\extra-parens.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

if ($DryRun -and $Diff) {
    Write-Error "Specify only one of -DryRun or -Diff."
    exit 1
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\extra_parens.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "extra_parens.py not found at: $pythonScript"
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

    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & $pythonExe -m ruff --version 2>&1
    $ruffOk = $LASTEXITCODE
    $ErrorActionPreference = $oldEAP

    if ($ruffOk -ne 0) {
        if (Test-DatrixOfflineMode) {
            Write-Error "DATRIX_OFFLINE is set: ruff is not installed. Install while online: pip install ruff>=0.1.0"
            exit 1
        }
        Write-Host "Installing ruff..." -ForegroundColor Yellow
        $ErrorActionPreference = "Continue"
        & $pythonExe -m pip install "ruff>=0.1.0"
        $pipExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        if ($pipExit -ne 0) {
            Write-Error "Failed to install ruff. Install manually: pip install ruff>=0.1.0"
            exit 1
        }
        Write-Host "ruff installed successfully" -ForegroundColor Green
    }

    $pyArgs = @()
    if ($All) {
        $pyArgs += "--all"
    } else {
        $pyArgs += $Projects
    }
    if ($DryRun) {
        $pyArgs += "--dry-run"
    }
    if ($Diff) {
        $pyArgs += "--diff"
    }

    Write-Host "Running extraneous-parentheses cleanup (Ruff UP034)..." -ForegroundColor Cyan
    Write-Host ""

    $ErrorActionPreference = "Continue"
    & $pythonExe $pythonScript @pyArgs
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldEAP

    exit $exitCode
} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.Exception.InnerException) {
        Write-Host "Inner: $($_.Exception.InnerException.Message)" -ForegroundColor Red
    }
    Write-Host ""
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
