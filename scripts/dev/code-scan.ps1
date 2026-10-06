#!/usr/bin/env pwsh
<#
.SYNOPSIS
    On-demand code-health scan: one ranked digest of dead code, complexity, duplicates and docs drift.

.DESCRIPTION
    Wraps scripts\dev\lib\code_scan.py. By default scans only the packages whose content changed
    since their last scan (tracked with the code index's file hashes in .code-index\scan-state.json);
    -Package or -All override that. Runs on this machine; changes nothing but the digest and the scan
    state.

    Per package:
      dead code   two-pass Vulture, each finding checked against the code index across the whole
                  workspace (a use in another package refutes it) and dropped if a template, a string
                  (getattr name, dotted resolver path) or a manifest entry point names it
      complexity  cyclomatic and cognitive complexity over the limit
      duplicates  Pylint R0801 groups, largest first
      docs drift  the check-docs lint over the package's docs\

    Every finding is written, by section and then by package, to
    <workspace>\reports\code-scan\code-scan-<timestamp>.md, headed by a per-package count table.
    The console gets one progress line per stage while it runs, then one line: the totals and the
    report's path.

    Exit codes:
      0 = digest written, or nothing changed since the last scan
      1 = the scan could not run (a tool missing, an unknown package, an unreadable scan state)

.PARAMETER Package
    Scan these packages, changed or not (positional). Each is a package name or its folder, in any
    form: datrix-cli, .\datrix-cli\, D:\datrix\datrix-cli, or a path inside it. Comma-separate or list
    several.

.PARAMETER All
    Scan every package with a src\ tree.

.PARAMETER MinConfidence
    Vulture's minimum confidence for a dead-code finding. Default: 60.

.PARAMETER DuplicateMinLines
    Smallest duplicated block Pylint reports. Default: 6.

.EXAMPLE
    .\code-scan.ps1
    Scan the packages changed since their last scan.

.EXAMPLE
    .\code-scan.ps1 datrix-codegen-common

.EXAMPLE
    .\code-scan.ps1 .\datrix-cli\ .\datrix-common\
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)] [string[]]$Package = @(),
    [Parameter()] [switch]$All,
    [Parameter()] [int]$MinConfidence = 60,
    [Parameter()] [int]$DuplicateMinLines = 6
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$pythonScript = Join-Path $scriptDir "lib\code_scan.py"
$commonDir = Join-Path $scriptsDir "common"
. (Join-Path $commonDir "venv.ps1")
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

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

    $pyArgs = @("--min-confidence", $MinConfidence, "--duplicate-min-lines", $DuplicateMinLines)
    foreach ($entry in $Package) {
        foreach ($name in ($entry -split ',')) {
            if ($name.Trim()) { $pyArgs += @("--package", $name.Trim()) }
        }
    }
    if ($All) { $pyArgs += "--all" }

    & $pythonExe $pythonScript @pyArgs
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
}
finally {
    Invoke-Cleanup
}
