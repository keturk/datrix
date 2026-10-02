#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Capability gap ledger gate.

.DESCRIPTION
 Censuses every registered target's `capability_gaps` rows (languages, client
 targets and platforms, read off the live declarations), enforces a
 decrease-only two-directional pin on the total and the per-target split
 (`scripts/config/capability-gap-baseline.toml`), and fails when EVERY distinct
 implementation of an axis carries a row for the same surface -- a defect in the
 shared layer, never a per-target gap. A row suppresses nothing elsewhere; this
 gate only counts and bounds the ledger. The row count is printed on every run.

 Derives its target sets from the installed `datrix.languages`,
 `datrix.generators` (client targets) and `datrix.platforms` entry points at
 runtime -- never a hardcoded target literal. Registered names that share one
 on-disk package fold into one implementation.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any
 real census. Fails loud (exit 2) if an axis has fewer than 2 distinct
 implementations or the baseline is unreadable.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Debug logging: prints every censused row (target, surface, detail).

.PARAMETER SelfTest
 Run only the built-in non-vacuity self-test; skip the real census.

.PARAMETER BaselinePath
 Compare against this baseline TOML instead of the committed one (used to prove
 a raised or lowered pin fails).

.EXAMPLE
 .\capability-gap-ledger-gate.ps1
 Run the gate for every registered target.

.EXAMPLE
 .\capability-gap-ledger-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [string]$BaselinePath
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\capability_gap_ledger.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: capability_gap_ledger.py not found at: $runnerScript"
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
    if ($Dbg) {
        $pythonArgs += "--debug"
    }
    if ($SelfTest) {
        $pythonArgs += "--self-test"
    }
    if ($BaselinePath) {
        $pythonArgs += @("--baseline", $BaselinePath)
    }

    Write-Host "Running capability gap ledger gate (all registered languages, client targets and platforms)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Capability gap ledger gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Capability gap ledger gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
