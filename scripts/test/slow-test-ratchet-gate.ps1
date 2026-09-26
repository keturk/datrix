#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail when a package's newest full-run timings show an un-baselined slow
 test or a fixture rebuilt on more than one xdist worker.

.DESCRIPTION
 Reads datrix/scripts/config/slow-test-baseline.json (decrease-only, checked
 against the baseline committed at git HEAD in every mode) and the newest
 FULL run's merged timings.json for every testable package (discovered the
 same way test.ps1/status-tests.ps1 do -- a package carrying a tests/
 directory or a package.json declaring a test script, never a hardcoded
 list). Fails on (i) any call exceeding 30s, (ii) any session/package/module
 fixture set up on more than one DISTINCT xdist worker with setup exceeding
 5s on at least one of them, unless baselined; also fails on a stale baseline
 entry (no longer an offender -- except a toolchain-compile entry, which is
 permanently exempt) and on a package with no v2 full run recorded at all.

 A Node package (datrix-vscode) carries no fixture-timing dimension; its
 merged JUnit XML's own per-testcase time is the only call-duration signal.

 The non-vacuity self-test runs on EVERY invocation before the real scan.

 This wrapper activates the venv but does NOT run
 Ensure-DatrixPackagesInstalled: the underlying Python module imports only
 the standard library and datrix/scripts/library, so it never needs the
 installed editable package set, and skipping the check avoids taking the
 workspace-wide package lock for nothing.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Seed
 Write the baseline from current offenders. Refused (exit 2) if it would
 grow the baseline committed at git HEAD.

.PARAMETER Dbg
 Print the resolved workspace root and package list to stderr.

.EXAMPLE
 .\slow-test-ratchet-gate.ps1
 Check every package's newest full run against the baseline.

.EXAMPLE
 .\slow-test-ratchet-gate.ps1 -SelfTest

.EXAMPLE
 .\slow-test-ratchet-gate.ps1 -Seed
 Seed the baseline from the current offenders (run once, at the phase
 boundary, after the boundary sweep -- then hand-edit every class/reason).
#>

[CmdletBinding()]
param(
    [switch]$SelfTest,
    [switch]$Seed,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\slow_test_ratchet.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: slow_test_ratchet.py not found at: $runnerScript"
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
    # No Ensure-DatrixPackagesInstalled here: the Python module below imports
    # only the stdlib and datrix/scripts/library, so it never needs the
    # installed editable package set.

    $pythonArgs = @($runnerScript)
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($Seed) { $pythonArgs += "--seed" }
    if ($Dbg) { $pythonArgs += "--dbg" }

    $targetLabel = if ($SelfTest) { "self-test only" } elseif ($Seed) { "seed baseline" } else { "check baseline" }
    Write-Host "Running slow-test ratchet gate: $targetLabel" -ForegroundColor Cyan

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Slow-test ratchet gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Slow-test ratchet gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
