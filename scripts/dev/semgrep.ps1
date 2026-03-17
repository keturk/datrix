#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run Semgrep with Datrix-specific rules across the monorepo.

.DESCRIPTION
    Activates the Datrix virtual environment, ensures semgrep is installed,
    and runs individual YAML rules from scripts/config/semgrep-rules/ on one
    or more projects (or all with -All).

    Each rule is run independently, making it easy to test and debug.
    Use -Rule to run a specific rule, -ListRules to see all available rules.

    Uses the Python implementation in scripts/library/dev/semgrep_scanner.py.

.PARAMETER Projects
    One or more project names to scan (e.g. datrix-common datrix-language).
    Positional.

.PARAMETER All
    Scan all projects in the monorepo.

.PARAMETER Rule
    Run only this rule (repeatable). Name matches the YAML filename without
    extension (e.g. empty-except-pass, return-none-lookup).

.PARAMETER ListRules
    List all available rules and exit.

.PARAMETER Report
    Write a markdown report to this path (relative to monorepo root).

.PARAMETER ShowRaw
    Show raw semgrep output for each rule.

.EXAMPLE
    .\semgrep.ps1 -All
    Scan all projects with all rules.

.EXAMPLE
    .\semgrep.ps1 -All -Rule missing-encoding-read
    Scan all projects with only the missing-encoding-read rule.

.EXAMPLE
    .\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup
    Scan all projects with two specific rules.

.EXAMPLE
    .\semgrep.ps1 -ListRules
    List all available semgrep rules.

.EXAMPLE
    .\semgrep.ps1 datrix-common -Report semgrep-report.md
    Scan one project and write a report.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [string[]]$Rule = @(),

    [switch]$ListRules,

    [string]$Report = "",

    [switch]$ShowRaw
)

if ($Projects.Count -eq 0 -and -not $All -and -not $ListRules) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\semgrep.ps1 <project> [project2 ...]" -ForegroundColor White
    Write-Host "  .\semgrep.ps1 -All [-Rule <name>] [-Report <path>]" -ForegroundColor White
    Write-Host "  .\semgrep.ps1 -ListRules" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\semgrep.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\semgrep_scanner.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "semgrep_scanner.py not found at: $pythonScript"
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

    # Check if semgrep is available
    $semgrepAvailable = $null -ne (Get-Command semgrep -ErrorAction SilentlyContinue)

    if (-not $semgrepAvailable -and -not $ListRules) {
        Write-Host "Installing semgrep..." -ForegroundColor Yellow
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $pythonExe -m pip install semgrep
        $pipExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        if ($pipExit -ne 0) {
            Write-Error "Failed to install semgrep. Install manually: pip install semgrep"
            exit 1
        }
        Write-Host "semgrep installed successfully" -ForegroundColor Green
    }

    # Build arguments
    $pyArgs = @()
    if ($ListRules) {
        $pyArgs += "--list-rules"
    } elseif ($All) {
        $pyArgs += "--all"
    } else {
        $pyArgs += $Projects
    }
    foreach ($r in $Rule) {
        $pyArgs += "--rule"
        $pyArgs += $r
    }
    if ($Report) {
        $pyArgs += "--report"
        $pyArgs += $Report
    }
    if ($ShowRaw) {
        $pyArgs += "--verbose"
    }

    if (-not $ListRules) {
        Write-Host "Running Semgrep anti-pattern scanner..." -ForegroundColor Cyan
        Write-Host ""
    }

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
