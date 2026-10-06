#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Review task files with the Task Review System (lib\review.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\review.py: Tier 1 on a local
 model server, optional Tier 2 (Codex) per review/config.toml. Every argument is
 passed through unchanged, so the flags are review.py's own (--task, --phase,
 --verify, --codex, --codex-on-threshold, --codex-phase-gate, --config,
 --local-machine, --local-model). See quick-reference.md for the exit codes.

.EXAMPLE
 .\review.ps1 --phase <NN> --codex-phase-gate

.EXAMPLE
 .\review.ps1 --task <path to one task file>
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ReviewArguments
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\review.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: review.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"

    & $pythonExe $pythonScript @ReviewArguments
    exit $LASTEXITCODE
} catch {
    Write-Error "Error: $_"
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
