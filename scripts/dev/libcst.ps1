#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Scan Datrix Python code for anti-patterns using LibCST.

.DESCRIPTION
    Activates the Datrix virtual environment, ensures libcst is installed,
    and runs the LibCST anti-pattern scanner on one or more projects
    (or the entire monorepo with -All).

    Patterns detected:
    - silent-fallback       : dict.get(key, None)
    - empty-except          : except: pass
    - missing-encoding      : read_text()/write_text()/open() without encoding=
    - banned-test-import    : MagicMock/Mock/patch/SimpleNamespace in tests
    - placeholder-body      : pass / raise NotImplementedError as sole body
    Uses the Python implementation in scripts/library/dev/libcst_scanner.py.

.PARAMETER Projects
    One or more project names to scan (e.g. datrix-common datrix-language).
    Positional.

.PARAMETER All
    Scan all projects in the monorepo.

.PARAMETER Report
    Write a markdown report to this path (relative to monorepo root).

.EXAMPLE
    .\libcst.ps1 datrix-common
    Scan datrix-common for anti-patterns.

.EXAMPLE
    .\libcst.ps1 -All
    Scan all projects.

.EXAMPLE
    .\libcst.ps1 -All -Report libcst-report.md
    Scan all projects and write a markdown report.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [string]$Report = ""
)

if ($Projects.Count -eq 0 -and -not $All) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\libcst.ps1 <project> [project2 ...]" -ForegroundColor White
    Write-Host "  .\libcst.ps1 -All [-Report <path>]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\libcst.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\libcst_scanner.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "libcst_scanner.py not found at: $pythonScript"
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

    # Ensure libcst is installed (check via Python import)
    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & $pythonExe -c "import libcst" 2>&1
    $importExitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldEAP

    if ($importExitCode -ne 0) {
        Write-Host "Installing libcst..." -ForegroundColor Yellow
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $pythonExe -m pip install "libcst>=1.0.0"
        $pipExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        if ($pipExit -ne 0) {
            Write-Error "Failed to install libcst. Install manually: pip install libcst>=1.0.0"
            exit 1
        }
        Write-Host "libcst installed successfully" -ForegroundColor Green
    }

    # Build arguments
    $pyArgs = @()
    if ($All) {
        $pyArgs += "--all"
    } else {
        $pyArgs += $Projects
    }
    if ($Report) {
        $pyArgs += "--report"
        $pyArgs += $Report
    }

    Write-Host "Running LibCST anti-pattern scanner..." -ForegroundColor Cyan
    Write-Host ""

    $oldEAP = $ErrorActionPreference
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
