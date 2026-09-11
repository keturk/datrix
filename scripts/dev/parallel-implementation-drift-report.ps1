#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Parallel-implementation drift report.

.DESCRIPTION
 Reports every function/method name defined in two or more registered
 target packages' src/ trees (datrix.languages by default, datrix.platforms
 with -Axis platforms), and nowhere else in the monorepo -- a candidate that
 was never hoisted to datrix-codegen-common, or was hoisted with one copy
 left behind. Each name is IDENTICAL (every definition byte-for-byte equal)
 or DRIFTED (at least one differs).

 This is a REPORT, not a gate: it carries no baseline and never fails on the
 count. A name-keyed scan cannot tell an intentional per-language emission
 difference from an unreconciled divergence, so the list is for reading when
 a hoist is being considered, never for ratcheting.

 Runs a built-in non-vacuity self-test on every invocation. Exits 2 if fewer
 than two targets are registered on the chosen axis.

.PARAMETER Axis
 "languages" (default) or "platforms".

.PARAMETER Dbg
 Enable debug logging (also lists every IDENTICAL group).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real report.

.EXAMPLE
 .\parallel-implementation-drift-report.ps1
 List drifted names across every registered language package.

.EXAMPLE
 .\parallel-implementation-drift-report.ps1 -Axis platforms -Dbg
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("languages", "platforms")]
    [string]$Axis = "languages",

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\parallel_implementation_drift.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: parallel_implementation_drift.py not found at: $runnerScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

trap {
    Invoke-Cleanup
    break
}

Ensure-DatrixVenv

try {
    Ensure-DatrixPackagesInstalled

    $pythonArgs = @($runnerScript, "--axis", $Axis)
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    Write-Host "Running parallel-implementation drift report on the $Axis axis" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Parallel-implementation drift report could not run (exit code $exitCode)" -ForegroundColor Red
        exit $exitCode
    }
    exit 0
} finally {
    Invoke-Cleanup
}
