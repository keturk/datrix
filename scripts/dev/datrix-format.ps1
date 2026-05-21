#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Format Datrix .dtrx files without re-rendering the AST.

.DESCRIPTION
 Discovers .dtrx and .dtrx.false files under the given paths and applies a
 conservative text formatter. It adjusts leading indentation and inserts one
 empty line after a standalone closing brace when followed by another content
 line. It refuses to write if the ordered nonblank source lines change.

.PARAMETER Path
 One or more file or directory paths to scan.

.PARAMETER All
 Scan all Datrix repository directories.

.PARAMETER Check
 Check formatting without modifying files.

.PARAMETER Diff
 Show unified diffs without modifying files.

.PARAMETER IndentSize
 Number of spaces per indentation level. Defaults to 4.

.PARAMETER Dbg
 Enable debug logging.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Path = @(),

    [Parameter()]
    [switch]$All,

    [Parameter()]
    [switch]$Check,

    [Parameter()]
    [switch]$Diff,

    [Parameter()]
    [ValidateRange(1, 8)]
    [int]$IndentSize = 4,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

if ($All -and $Path.Count -gt 0) {
    Write-Error "Specify either -All or one or more paths, not both."
    exit 1
}

if (-not $All -and $Path.Count -eq 0) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\datrix-format.ps1 -All [-Check] [-Diff] [-IndentSize 4] [-Dbg]" -ForegroundColor White
    Write-Host "  .\datrix-format.ps1 <path> [path2 ...] [-Check] [-Diff] [-IndentSize 4] [-Dbg]" -ForegroundColor White
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\datrix_format.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: datrix_format.py not found at: $pythonScript"
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

    if ($All) {
        $pathsToCheck = @()
        $directories = Get-DatrixDirectoryPaths
        foreach ($dirPath in $directories) {
            if (Test-Path $dirPath) {
                $pathsToCheck += $dirPath
            }
        }
    } else {
        $pathsToCheck = $Path
    }

    $pythonArgs = @($pythonScript) + $pathsToCheck + @("--indent-size", $IndentSize)
    if ($Check) {
        $pythonArgs += "--check"
    }
    if ($Diff) {
        $pythonArgs += "--diff"
    }
    if ($Dbg) {
        $pythonArgs += "--debug"
    }

    Write-Host "Running Datrix formatter..." -ForegroundColor Cyan
    Write-Host ""

    & $pythonExe @pythonArgs
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
