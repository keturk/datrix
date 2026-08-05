#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-target observability-AXIS parity gate.

.DESCRIPTION
 Proves the language/platform split for observability provider realization
 is consistent across every registered target -- the invariant whose absence
 let two generation-breaking defects ship with every per-package suite green:

   1. A language declared it realized providers in a category only the
      PLATFORM can realize, so the SAME config generated cleanly on one
      language and failed generation outright on another.
   2. The language-axis validator policed a platform-only category, so a
      provider the resolved platform natively realizes (and provisions) was
      rejected for every project using that language.

 Both are CROSS-TARGET consistency defects. Per-package conformance suites
 cannot detect either by construction -- each package validates its own
 declaration in isolation, so all of them can be internally green while
 disagreeing about the same portable field. This gate compares targets.

 Two legs, target sets derived from the installed entry points at runtime
 (`datrix.languages` / `datrix.platforms`) -- never a hardcoded language or
 provider literal, so a future package is covered with no edit here:

   Leg 1 (declaration identity): every registered language must declare the
   empty set for every category in PLATFORM_ONLY_OBSERVABILITY_CATEGORIES.

   Leg 2 (validator agreement): for each platform-only category, a provider
   at least one registered PLATFORM declares native must validate cleanly
   against every registered language.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison. Leg 1's comparator must detect a synthetic language
 claiming a platform-only provider and must not fire on a clean one. Leg 2's
 check must still see the validator REJECT an unrealized provider in a
 language-realizable category -- otherwise a neutered validator would make
 leg 2 pass vacuously.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\observability-axis-parity-gate.ps1
 Run the gate for every registered language and platform.

.EXAMPLE
 .\observability-axis-parity-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\observability_axis_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: observability_axis_parity.py not found at: $runnerScript"
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

    Write-Host "Running observability-axis parity gate (all registered languages/platforms)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Observability-axis parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Observability-axis parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
