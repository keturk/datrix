#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language domain-universe closure and declaration-presence gate.

.DESCRIPTION
 Proves two properties for every registered `datrix.languages` plugin, over
 the full shared domain universe:

 1. Domain-universe closure -- the union of every registered language's
    COMPILED GenDSL IR domain ids equals the shared registry
    (`SHARED_CONTEXT_TYPES`) exactly. A domain id some language's compiled
    IR declares but the registry omits, or a registry id no registered
    language's compiled IR declares (a dead entry), fails loud and
    short-circuits before anything downstream runs.
 2. Per-language declaration presence -- every registered language declares
    every STRUCTURAL domain id (the kernel's structural-domain-id tuple;
    `discovery` and `resilience` keep their GenDSL registration but carry no
    structural-pattern obligation, so no language is required to declare
    either and a language that does is not reported), and declares nothing
    outside the full registration universe. An undeclared structural id or an
    out-of-universe declaration is a fail-loud `DECLARATION PRESENCE
    VIOLATION` naming the language and the id. This is a presence check,
    never an agreement check: languages may emit a domain to different
    globs. A domain a language does not realize is counted here, never
    excused.

 On success, prints, for every structural domain id, each registered
 language's declared structural pattern (or `no structural pattern`), plus a
 divergence block listing the languages that declare a structural id with no
 structural pattern or do not declare it -- diagnostic only, never itself a
 failure condition.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language literal -- so a future `datrix-codegen-<lang>`
 package is covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: feeds the declaration-presence comparator a complete
 synthetic table over the structural ids (must report zero findings), a
 synthetic language omitting one structural id (must be reported, naming the
 language and id), a synthetic language declaring an out-of-universe id (must
 be reported), and a synthetic language declaring the non-structural id (must
 be neither reported nor required); and feeds the
 closure comparator a synthetic matching pair (must report zero
 divergence), a synthetic compiled id absent from the registry (must be
 reported), and a synthetic dead registry entry (must be reported). Fails
 loud (exit 2) if fewer than 2 languages are registered -- a cross-language
 comparison over 0 or 1 language is vacuous.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\supported-domain-parity-gate.ps1
 Run the gate for every registered language.

.EXAMPLE
 .\supported-domain-parity-gate.ps1 -Dbg
 Run the gate with debug logging.

.EXAMPLE
 .\supported-domain-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $scriptDir "lib\supported_domain_parity.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: supported_domain_parity.py not found at: $runnerScript"
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

    Write-Host "Running domain-universe closure + declaration-presence gate (all registered languages)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Supported-domain parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Supported-domain parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
