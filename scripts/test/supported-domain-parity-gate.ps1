#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language SUPPORTED-domain-set parity gate (G3 final).

.DESCRIPTION
 Proves every registered `datrix.languages` plugin's derived SUPPORTED
 domain set -- the FULL set (every domain a plugin declares
 `status == "supported"`), not pre-filtered to any subset -- is identical
 across ALL registered languages, zero symmetric difference.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language literal -- so a future `datrix-codegen-<lang>`
 package is covered automatically with no edit to this gate.

 Supersedes `shared39-supported-parity-gate.ps1` (java<->python only,
 restricted to the seven rich cross-language domains that are also
 shared-39 members): this gate's FULL-set identity comparison strictly
 implies that narrower restricted comparison (a subset of an identical set
 is itself identical), and the old gate's second check (8 infra-family
 `_test` domains excluded from the restricted set) was already vacuous by
 construction -- those 8 domains are provably disjoint from the seven rich
 domains, so they could never appear in the restricted set regardless of
 what either language declares. `shared39_supported_parity.py` and this
 gate's predecessor `.ps1` were deleted as superseded rather than kept as a
 redundant, narrower gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: feeds the comparator a synthetic matching pair (must
 report zero divergence) and a synthetic forced-mismatch pair (must report
 the missing domain). Fails loud (exit 2) if fewer than 2 languages are
 registered -- a cross-language comparison over 0 or 1 language is vacuous.

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
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\supported_domain_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
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

    Write-Host "Running supported-domain SUPPORTED parity gate (all registered languages, G3 final)" -ForegroundColor Cyan
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
