#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-platform capability-declaration parity gate (D1).

.DESCRIPTION
 Proves every installed `datrix.platforms` plugin's declared
 PlatformCapabilityDeclaration is complete relative to the union of
 capability coordinates every installed platform declares, across seven
 surfaces: block-realization (block_type, flavor) cells, supported secret
 backends, native observability providers (per category), supported
 deployment runtimes, identity (provider_type, feature) cells, every
 remaining optional scalar/mapping capability field, and
 unrealizable_surfaces. A coordinate present on one platform and entirely
 undeclared (never an explicit supported=False/reason or truthy value) on
 another fails the gate, unless a reviewed entry exists in
 `datrix/scripts/config/platform-capability-holes.json`.

 Derives its target platform set from
 `importlib.metadata.entry_points(group="datrix.platforms")` at runtime --
 never a hardcoded aws/azure/docker/local literal -- so a future
 datrix-codegen-<platform> package is covered automatically with no edit
 to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: a synthetic matching declaration pair must report
 zero gaps; a synthetic pair with one planted missing union cell must be
 detected. Fails loud (exit 2) if fewer than 2 platforms are registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\block-realization-parity-gate.ps1
 Run the gate for every registered platform.

.EXAMPLE
 .\block-realization-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\block_realization_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: block_realization_parity.py not found at: $runnerScript"
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

    Write-Host "Running block-realization capability parity gate (all registered platforms, D1)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Block-realization parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Block-realization parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
