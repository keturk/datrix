#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language response-body wire-naming conformance gate.

.DESCRIPTION
 Proves every registered `datrix.languages` plugin serializes response-body
 fields under ONE declared rule -- camelCase wire keys -- by generating a
 real example project (the CQRS example under
 datrix/examples/02-features/03-infrastructure-blocks/cqrs/) once per
 registered language and comparing each language's OWN emitted response
 classes' EFFECTIVE wire names (never the mere presence of a wire-renaming
 mechanism) against the camelCase form of the declared field name.

 A language target that cannot support a given response surface declares it
 unsupported with a reason via the typed, counted exemption file at
 datrix/scripts/config/body-wire-naming-exemptions.json (coordinates +
 reason + pinned expected_count).

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language literal -- so a future `datrix-codegen-<lang>`
 package is covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: a synthetic conformant field (must report zero
 divergence), a synthetic forced-divergent field with no exemption (must
 report it), a synthetic forced-divergent field COVERED by an exemption
 (must NOT report it), a single-word-field case matching a real
 no-alias-generator template's shape (must NOT report it), and a real
 Pydantic model whose field carries only `Field(serialization_alias=...)`
 (must read the serialization alias, never the raw attribute name). Fails
 loud (exit 2) if fewer than 2 languages are registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison (skips
 real generation entirely).

.EXAMPLE
 .\body-wire-naming-conformance-gate.ps1
 Run the gate for every registered language.

.EXAMPLE
 .\body-wire-naming-conformance-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\body_wire_naming_conformance.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: body_wire_naming_conformance.py not found at: $runnerScript"
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

    Write-Host "Running body wire-naming conformance gate (all registered languages)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Body wire-naming conformance gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Body wire-naming conformance gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
