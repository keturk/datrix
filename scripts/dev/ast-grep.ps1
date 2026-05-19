#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run ast-grep structural searches across Datrix Python code.

.DESCRIPTION
    Activates the Datrix virtual environment, ensures the ast-grep CLI is
    available, and runs either saved YAML rules from
    scripts/config/ast-grep-rules/ or a one-off Python pattern across one or
    more projects (or all with -All).

    Uses the Python implementation in scripts/library/dev/ast_grep.py.

.PARAMETER Projects
    One or more project names to scan (e.g. datrix-common datrix-language).
    Positional.

.PARAMETER All
    Scan all projects in the monorepo.

.PARAMETER Pattern
    Run a one-off ast-grep pattern against Python files.

.PARAMETER Rule
    Run only this saved rule (repeatable). Name matches the YAML filename
    without extension.

.PARAMETER ListRules
    List all available ast-grep rules and exit.

.PARAMETER Report
    Write a markdown report to this path (relative to monorepo root).

.PARAMETER ShowRaw
    Show raw ast-grep output for each invocation.

.EXAMPLE
    .\ast-grep.ps1 -All -Pattern "raise Exception($MSG)"
    Search all projects for a structural Python pattern.

.EXAMPLE
    .\ast-grep.ps1 datrix-common -Rule broad-exception
    Scan datrix-common with one saved ast-grep rule.

.EXAMPLE
    .\ast-grep.ps1 -ListRules
    List all available ast-grep rules.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [string]$Pattern = "",

    [string[]]$Rule = @(),

    [switch]$ListRules,

    [string]$Report = "",

    [switch]$ShowRaw
)

if ($Projects.Count -eq 0 -and -not $All -and -not $ListRules) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\ast-grep.ps1 <project> [project2 ...] -Pattern <pattern>" -ForegroundColor White
    Write-Host "  .\ast-grep.ps1 -All -Pattern <pattern> [-Report <path>]" -ForegroundColor White
    Write-Host "  .\ast-grep.ps1 -All [-Rule <name>] [-Report <path>]" -ForegroundColor White
    Write-Host "  .\ast-grep.ps1 -ListRules" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\ast-grep.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\ast_grep.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "ast_grep.py not found at: $pythonScript"
    exit 1
}

function Get-AstGrepCommand {
    $commands = @()
    $commands += Get-Command sg.cmd -ErrorAction SilentlyContinue
    $commands += Get-Command ast-grep.cmd -ErrorAction SilentlyContinue
    $commands += Get-Command sg.exe -ErrorAction SilentlyContinue
    $commands += Get-Command ast-grep.exe -ErrorAction SilentlyContinue
    $commands += Get-Command sg -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq "Application" }
    $commands += Get-Command ast-grep -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq "Application" }
    return $commands | Where-Object { $null -ne $_ } | Select-Object -First 1
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

    $astGrepCommand = Get-AstGrepCommand

    if ($null -eq $astGrepCommand -and -not $ListRules) {
        if (Test-DatrixOfflineMode) {
            Write-Error "DATRIX_OFFLINE is set: ast-grep is not on PATH. Install while online: npm install -g @ast-grep/cli"
            exit 1
        }

        $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
        if ($null -eq $npmCommand) {
            Write-Error "ast-grep is not on PATH and npm is unavailable. Install manually: npm install -g @ast-grep/cli"
            exit 1
        }

        Write-Host "Installing ast-grep..." -ForegroundColor Yellow
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & npm install -g "@ast-grep/cli"
        $npmExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        if ($npmExit -ne 0) {
            Write-Error "Failed to install ast-grep. Install manually: npm install -g @ast-grep/cli"
            exit 1
        }

        $astGrepCommand = Get-AstGrepCommand
        if ($null -eq $astGrepCommand) {
            Write-Error "ast-grep installation completed, but sg/ast-grep is still not on PATH"
            exit 1
        }
        Write-Host "ast-grep installed successfully" -ForegroundColor Green
    }

    if ($null -ne $astGrepCommand) {
        $env:AST_GREP_BIN = $astGrepCommand.Source
    }

    $pyArgs = @()
    if ($ListRules) {
        $pyArgs += "--list-rules"
    } elseif ($All) {
        $pyArgs += "--all"
    } else {
        $pyArgs += $Projects
    }
    if ($Pattern) {
        $pyArgs += "--pattern"
        $pyArgs += $Pattern
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
        Write-Host "Running ast-grep structural scanner..." -ForegroundColor Cyan
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
