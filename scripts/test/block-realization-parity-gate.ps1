#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-platform capability-declaration parity gate.

.DESCRIPTION
 Proves every installed `datrix.platforms` plugin realizes every CAPABILITY
 any installed platform realizes, across seven surfaces: block types (a
 platform realizes each block type by at least one flavor), observability
 categories (at least one native provider per category), a supported-runtime
 floor, identity features (offered through at least one provider), static web
 hosting origin and custom-domain surfaces (each platform against its OWN
 edge: `domain` and both surfaces when the edge binds custom domains,
 `loopback_port` and neither otherwise), and model realizations (at least one
 provider with a flavor cell). Compares capabilities, never implementations:
 a platform that lacks one flavor, vendor product or provider another has is
 not a gap. A capability a platform realizes by no implementation is a
 `<kind>:<id>` row in that platform's own `capability_gaps`, which accounts
 for the violation here and suppresses nothing elsewhere. There is no
 exemption file.

 Declarations are read through one extractor (presence only) and compared as
 plain facts. Secret backends, deployable constructs, the set-shaped optional
 fields and the presence-shaped topology fields are not compared across
 platforms (product vocabulary / per-platform topology); a field partition
 guard still forces every present and future declaration field, required or
 optional, into a named bucket.

 Derives its target platform set from
 `importlib.metadata.entry_points(group="datrix.platforms")` at runtime --
 never a hardcoded aws/azure/docker/local literal -- so a future
 datrix-codegen-<platform> package is covered automatically with no edit
 to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: planted facts for a clean pair must report zero gaps,
 each planted divergence must be detected as exactly one violation, and a
 merely different vocabulary must not. Fails loud (exit 2) if fewer than 2
 platforms are registered or a live surface unions over nothing.

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

    Write-Host "Running block-realization capability parity gate (all registered platforms, seven surfaces)" -ForegroundColor Cyan
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
