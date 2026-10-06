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

 No language and no response surface can be set aside: every in-population
 field that diverges fails the gate. (A dependency-response model decodes an
 upstream service's wire, so that schema kind is outside the population for
 every language alike, and the files it excludes are counted.)

 A second census covers a transform applied AFTER serialization, which the
 comparison above cannot see: each registered language declares the regular
 expressions that spell a response-body transform in its framework
 (LanguageCapabilityDeclaration.response_body_transform_idioms), the gate
 greps the same generated tree for them, and every hit must be a typed
 `transform_exemptions` entry in
 datrix/scripts/config/body-wire-naming-exemptions.json (language, path
 suffix, matched text, reason). An unreviewed hit, a stale entry and a
 language with no declaration each fail by name, and the file is refused if
 it carries any key other than _comment and transform_exemptions.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language literal -- so a future `datrix-codegen-<lang>`
 package is covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: a synthetic conformant field (must report zero
 divergence), a synthetic forced-divergent field (must report it), a
 single-word-field case matching a real no-alias-generator template's shape
 (must NOT report it), the transform census over a planted tree, and a
 review file carrying a per-schema-kind `exemptions` list (must be refused).
 Fails loud (exit 2) if fewer than 2 languages are registered.

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
$runnerScript = Join-Path $scriptDir "lib\body_wire_naming_conformance.py"

$commonDir = Join-Path $scriptDir "..\..\common"
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
