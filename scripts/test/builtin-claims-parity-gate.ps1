#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language builtin-claims parity gate (D2).

.DESCRIPTION
 Proves every registered `datrix.languages` plugin's declared
 `builtin_group_stances` are sound, over two surfaces, neither with a
 reviewed-gap path (a divergence here is always a real defect):

 1. Stance key-set identity -- every language declares a stance for exactly
    the same set of `BuiltinGroup` names. A non-vacuity proof:
    `register_builtin_capability`'s per-language completeness check already
    enforces this
    at plugin import, so this repo-level check exists to catch a future
    decoupling, not because it can fail against an installed set.
 2. Per-group stance-vs-mapper coherence -- every group has a declared
    stance, and every group a language declares `supported` has every one
    of its `BUILTIN_REGISTRY` rows actually mapped by that language's
    profile. Re-derives, as an independent belt-and-suspenders backstop,
    the same judgment `register_builtin_capability` enforces at each
    language's own plugin import.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language literal -- so a future `datrix-codegen-<lang>`
 package is covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: feeds both comparators a synthetic matching pair (must
 report zero divergence) and a synthetic forced-mismatch pair (must report
 the planted gap). Fails loud (exit 2) if fewer than 2 languages are
 registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\builtin-claims-parity-gate.ps1
 Run the gate for every registered language.

.EXAMPLE
 .\builtin-claims-parity-gate.ps1 -Dbg
 Run the gate with debug logging.

.EXAMPLE
 .\builtin-claims-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\builtin_claims_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: builtin_claims_parity.py not found at: $runnerScript"
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

    Write-Host "Running builtin-claims parity gate (all registered languages, D2)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Builtin-claims parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Builtin-claims parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
