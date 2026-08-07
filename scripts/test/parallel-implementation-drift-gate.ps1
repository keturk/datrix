#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Parallel-implementation drift report (D10.1).

.DESCRIPTION
 Reports every function/method name defined in two or more registered
 datrix.languages packages' src/ trees, and nowhere else in the monorepo --
 a candidate that was never hoisted to datrix-codegen-common (or was hoisted
 and one copy left behind). Classifies each such name as IDENTICAL (every
 definition's source text is byte-for-byte equal) or DRIFTED (at least one
 definition differs), and checks the DRIFTED count against a decrease-only
 baseline at scripts/config/parallel-implementation-drift-baseline.json.

 This is a REPORT with a count ratchet, not a pass/fail gate on individual
 names -- a name-keyed check cannot distinguish an intentional per-language
 emission difference from a genuine unreconciled divergence.

 Runs a built-in non-vacuity self-test on every invocation. Fails loud
 (exit 2) if fewer than two languages are registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real report.

.PARAMETER UpdateBaseline
 Write the live drifted-group count as the new baseline.

.EXAMPLE
 .\parallel-implementation-drift-gate.ps1
 Run the report over every registered language and check the drift ratchet.

.EXAMPLE
 .\parallel-implementation-drift-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\parallel-implementation-drift-gate.ps1 -UpdateBaseline
 Freeze the current live drifted-group count as the new baseline.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$UpdateBaseline
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

    $pythonArgs = @($runnerScript)
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }

    Write-Host "Running parallel-implementation drift report (D10.1)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Parallel-implementation drift report failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Parallel-implementation drift report passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
