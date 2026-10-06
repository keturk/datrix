#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Problem-type parity gate -- every registered language answers errors with
 RFC 7807 type URNs from datrix-common's registry and is obligated to every
 framework family; unspelled (language, family) cells are held to a
 two-directional pin.

.DESCRIPTION
 A generated service's error body carries a `type` member naming the error
 class; a client keyed on it must see one vocabulary whichever language
 served the request. The vocabulary has one home,
 datrix_common.datrix_model.problem_types (urn:datrix:error:<slug>). This gate
 censuses the .py and .j2 sources under every registered language package
 and holds each language to:

   * REFERENCE, NEVER LITERAL -- no source spells a urn:datrix:error:<slug>
     literal at all (registered or private slug alike, no exemption path);
     a language renders a problem type from the registry;
   * REALIZATION -- every registered language is obligated to realize every
     registered family: a .j2 source references its PROBLEM_<FAMILY> template
     global (or renders the GENERIC_PROBLEM_FAMILY_BY_STATUS table), or a .py
     source calls problem_type_for("<family>"). A (language, family) cell a
     language does not realize
     is counted (printed as PINNED GAP language=<l> family=<f>) against the
     language's pin in scripts/config/problem-type-parity-baseline.toml: a
     count above the pin fails (EXCEED), a count below it fails until the pin
     is lowered in the same change (BELOW), and a language absent from the
     table is pinned at zero. No declaration excuses a cell. A family no
     language spells is a dead registry entry and fails outright.

 Language set from the installed datrix.languages entry points at runtime;
 registry read from the packages -- never a table here. The pin is seeded
 from a live run and lowered by hand; no script writes it.
 Runs a built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (per-language spelling counts).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.EXAMPLE
 .\problem-type-parity-gate.ps1

.EXAMPLE
 .\problem-type-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $scriptDir "lib\problem_type_parity.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: problem_type_parity.py not found at: $runnerScript"
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

    Write-Host "Running problem-type parity gate (every registered language)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Problem-type parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Problem-type parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
