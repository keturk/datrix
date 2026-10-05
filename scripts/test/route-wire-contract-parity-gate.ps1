#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language route wire-contract parity gate.

.DESCRIPTION
 Proves every registered `datrix.languages` plugin answers the same route
 identically on the wire: for each example project (a resource CRUD API and the
 CQRS example) it generates the project once per registered language, reads
 every API route's contract -- verb, full path, success status, success-body
 envelope (none / object / list / page / binary) and media type -- out of the
 generated source through that language's own conformance probe
 (`LanguageConformanceProbes.route_wire_contracts`), and compares the languages
 route by route. A route one language registers and another does not, a status
 that differs, a body envelope that differs and a media type that differs each
 fail by name.

 Static by construction: no backend is booted, no request is made, no toolchain
 runs. A report carries declared coordinates only (example, verb, path, the
 per-language values) and never a generated file or source text.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime -- never
 a hardcoded language literal -- so a future `datrix-codegen-<lang>` package is
 covered automatically once its probe implements `route_wire_contracts`.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any
 real comparison: identical contracts must report nothing; a planted status,
 envelope, media-type, route-set and duplicate-route divergence must each be
 reported by name; a report must never name a generated file; a probe that finds
 no route must fail; a plugin with no probe must be refused; and fewer than two
 registered languages must refuse to run (exit 2).

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip real generation entirely.

.EXAMPLE
 .\route-wire-contract-parity-gate.ps1
 Run the gate for every registered language.

.EXAMPLE
 .\route-wire-contract-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\route_wire_contract_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: route_wire_contract_parity.py not found at: $runnerScript"
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

    Write-Host "Running route wire-contract parity gate (all registered languages)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Route wire-contract parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Route wire-contract parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
