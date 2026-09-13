#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Model-realization capability-declaration parity gate (Decision 46 invariant 6).

.DESCRIPTION
 Proves every installed `datrix.platforms` plugin declares a well-formed
 `model_realizations` mapping on its `PlatformCapabilityDeclaration` -- one
 `ModelRealization` per model provider (API family) the platform realizes,
 each cell's `flavors` drawn from the closed placement domain
 `container | external | managed | direct`. The field is REQUIRED with no
 default: a platform realizing zero providers must still declare an
 explicit empty mapping, so a missing declaration is a construction error
 rather than a silently-absent capability.

 Scoped to that single field -- it never compares provider sets across
 platforms (a platform realizing zero providers is conforming, never a
 gap); the cross-platform union comparison over every OTHER capability
 surface is `block-realization-parity-gate.ps1`'s job.

 Derives its target platform set from
 `importlib.metadata.entry_points(group="datrix.platforms")` at runtime --
 never a hardcoded aws/azure/docker/local literal -- so a future
 datrix-codegen-<platform> package is covered automatically with no edit
 to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: a synthetic matching declaration pair must report
 zero violations; a synthetic pair with one planted out-of-domain flavor
 must be detected exactly once. Fails loud (exit 2) if fewer than 2
 platforms are registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\model-realization-parity-gate.ps1
 Run the gate for every registered platform.

.EXAMPLE
 .\model-realization-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\model_realization_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: model_realization_parity.py not found at: $runnerScript"
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

    Write-Host "Running model-realization capability parity gate (all registered platforms, invariant 6)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Model-realization parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Model-realization parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
