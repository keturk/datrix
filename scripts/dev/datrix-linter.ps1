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

.PARAMETER Format
 Format each discovered system.dtrx in place before linting.

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
 .\datrix-linter.ps1 datrix-projects\curvaero\datrix-app\system.dtrx
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
    [switch]$Format

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

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\datrix_linter.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: datrix_linter.py not found at: $pythonScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    if (Get-Command Disable-DatrixVenv -ErrorAction SilentlyContinue) {
        Disable-DatrixVenv
    }
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath  = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"

    # Build the list of paths to pass to the Python script
    $pathsToCheck = @()
    if ($All) {
        $pythonArgs = @($pythonScript, "--all")
    } else {
        $pythonArgs = @($pythonScript) + $Path
    }

    if ($Strict) {
        $pythonArgs += "--strict"
    }
    if ($Dbg) {
        $pythonArgs += "--debug"
    }
    if ($Format) {
        $pythonArgs += "--format"
    }
    if ($ResolveConfigs) {
        $pythonArgs += "--resolve-configs"
    }
    if ($ResolveConfigs -and $Profile) {
        $pythonArgs += @("--profile", $Profile)
    }

    Write-Host "Running Datrix linter..." -ForegroundColor Cyan
    Write-Host ""

    & $pythonExe @pythonArgs
    $exitCode = $LASTEXITCODE

    exit $exitCode

} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    if ($_.Exception.InnerException) {
        Write-Host "Inner exception:" -ForegroundColor Red
        Write-Host $_.Exception.InnerException.Message -ForegroundColor Red
        Write-Host ""
    }
    if (Get-Command Disable-DatrixVenv -ErrorAction SilentlyContinue) {
        Disable-DatrixVenv
    }
    exit 1
} finally {
    if (Get-Command Disable-DatrixVenv -ErrorAction SilentlyContinue) {
        Disable-DatrixVenv
    }
}

