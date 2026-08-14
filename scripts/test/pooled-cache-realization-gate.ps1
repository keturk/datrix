#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Pooled-cache member-slice realization gate.

.DESCRIPTION
 For every registered `datrix.languages` / `datrix.platforms` target, asserts
 that a pooled cache member's declared slice (`PooledMember.slice_index`,
 `datrix_codegen_common.pooling.contract`) actually reaches that target's own
 emitted-output-facing source -- never merely that the shared pooling
 pre-pass computed it. Detection is STATIC: this gate parses each target
 package's own `src/` tree (Python `ast`, never a substring/regex scan) for a
 function that both reads a `.slice_index` attribute and is call-reachable
 from elsewhere in that same tree (declared AND consumed, not dead code). It
 never invokes `generate.ps1` and never generates a project.

 A target that does not yet realize the slice must carry a typed exemption
 (axis + target + reason) in
 `datrix/scripts/config/pooled-cache-realization-exemptions.json`, whose
 `pinned_count` must equal the file's live entry count on every change --
 a target quietly losing its realization fails the gate the same way a
 target that never had one does.

 Derives its target sets from
 `importlib.metadata.entry_points(group="datrix.languages" | "datrix.platforms")`
 at runtime -- never a hardcoded python/typescript/java/dotnet or
 aws/azure/docker literal -- so a future datrix-codegen-<x> package is
 covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: a synthetic declared-and-reachable `.slice_index`
 consumer must classify realized; a synthetic declared-but-dead (never
 called) one must classify NOT realized; a synthetic single-target axis must
 be refused as vacuous. Fails loud (exit 2) if fewer than 2 targets are
 registered on an axis being checked.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Axis
 Which axis to check: "languages" or "platforms". Omit to check BOTH axes
 in one invocation.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\pooled-cache-realization-gate.ps1
 Run the gate for every registered language AND platform target.

.EXAMPLE
 .\pooled-cache-realization-gate.ps1 -Axis platforms
 Run the gate for the platforms axis only.

.EXAMPLE
 .\pooled-cache-realization-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("languages", "platforms")]
    [string]$Axis,

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\pooled_cache_realization_gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: pooled_cache_realization_gate.py not found at: $runnerScript"
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
    if ($Axis) { $pythonArgs += @("--axis", $Axis) }
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    $axisLabel = if ($Axis) { $Axis } else { "languages+platforms" }
    Write-Host "Running pooled-cache member-slice realization gate (axis: $axisLabel)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Pooled-cache realization gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Pooled-cache realization gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
