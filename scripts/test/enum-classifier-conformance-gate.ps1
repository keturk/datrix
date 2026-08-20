#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-target enum-classifier conformance gate (G10).

.DESCRIPTION
 Proves every registered `datrix.languages` plugin that emits enum types realizes
 `equalsKeyword`/`containsKeyword` identically for a fixture keyword-bearing enum: hit, miss
 (throws the declared exception with a message naming only the enum type), and miss-with-fallback
 all behave the same way across every target.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime -- never a hardcoded
 language literal -- so a future `datrix-codegen-<lang>` package is covered automatically with no
 edit to this gate.

 These classifiers are deliberately NOT `BUILTIN_REGISTRY` entries (the registry is keyed by
 fixed category names and a user enum is never one of those categories), so this gate is the
 coverage the closed registry would otherwise provide.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any real comparison:
 feeds the comparator a synthetic fully-conformant pair (must report zero violations) and a
 synthetic partially-broken pair (must report exactly the broken language). Fails loud (exit 2) if
 fewer than 2 enum-emitting languages are registered -- a cross-language comparison over 0 or 1
 language is vacuous.

 Repo-level validation script (per the datrix showcase boundary -- no pytest suite lives in
 datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\enum-classifier-conformance-gate.ps1
 Run the gate for every registered enum-emitting language.

.EXAMPLE
 .\enum-classifier-conformance-gate.ps1 -Dbg
 Run the gate with debug logging.

.EXAMPLE
 .\enum-classifier-conformance-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\enum_classifier_conformance.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: enum_classifier_conformance.py not found at: $runnerScript"
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

    Write-Host "Running enum-classifier cross-target conformance gate (all registered enum-emitting languages, G10)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Enum-classifier conformance gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Enum-classifier conformance gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
