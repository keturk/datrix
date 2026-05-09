#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Lint documentation for common drift patterns.

.DESCRIPTION
    Checks Datrix monorepo docs for:
      1. Deprecated CLI flags in examples
      2. Fixed phase-count language
      3. CDX design doc filename validation
      4. CDX design doc structure validation
      5. Missing capability status labels

    Exit codes:
      0 = all checks passed
      1 = lint issues detected

.PARAMETER DocsDir
    One or more documentation directories to scan (positional).
    Defaults to all docs/ directories in the monorepo.

.PARAMETER Check
    Run only the specified check(s). Can be repeated.
    Available: deprecated-cli-flags, fixed-phase-count, cdx-filenames,
    cdx-structure, capability-status-labels

.PARAMETER Detailed
    Show detailed output including content and suggestions.

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\check-docs.ps1
    Run all checks on all docs directories.

.EXAMPLE
    .\check-docs.ps1 -Check cdx-filenames -Check cdx-structure
    Run only CDX-related checks.

.EXAMPLE
    .\check-docs.ps1 -Detailed
    Show detailed output for all findings.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$DocsDir = @(),

    [Parameter()]
    [string[]]$Check = @(),

    [Parameter()]
    [switch]$Detailed,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\check_docs.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "check_docs.py not found at $pythonScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    $pyArgs = @()

    foreach ($d in $DocsDir) {
        $pyArgs += $d
    }
    foreach ($c in $Check) {
        # Handle comma-separated values (e.g., -Check cdx-filenames,cdx-structure)
        foreach ($item in ($c -split ',')) {
            $trimmed = $item.Trim()
            if ($trimmed) {
                $pyArgs += "--check"
                $pyArgs += $trimmed
            }
        }
    }
    if ($Detailed) { $pyArgs += "--verbose" }
    if ($Dbg) { $pyArgs += "--debug" }

    & $pythonExe $pythonScript @pyArgs
    exit $LASTEXITCODE
} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
