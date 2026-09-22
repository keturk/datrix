#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Language-axis (and platform-axis, report-only) behaviour-parity gate.

.DESCRIPTION
 Wraps datrix/scripts/library/test/behaviour_parity.py. Groups functions
 across registered target packages into roles (by shared-typed signature or
 normalized name), classifies each into identical / same-behaviour /
 divergent by comparing behaviour skeletons rather than bodies, and fails on
 any role in scope that is not adapter-exempt (identical / same-behaviour)
 or whose members, once every package declaring the construct unsupported
 is set aside, still split into more than one skeleton group (divergent).
 No language is the reference: a divergent role names every skeleton group
 it splits into. The platform axis (-Axis platforms) is report-only and
 never fails.

 Runs a five-bucket non-vacuity self-test on every invocation. Exits 2 if
 fewer than two targets are registered on the chosen axis, or on a
 discovery/parse/self-test failure.

.PARAMETER Axis
 "languages" (default) or "platforms".

.PARAMETER Scope
 Comma-separated or repeated domain ids (plus the literal "undomained") to
 restrict failure to. Overrides
 datrix/scripts/config/behaviour-parity-scope.json when given; when absent,
 the scope file's list applies if it exists, else every domain is in scope.

.PARAMETER Buckets
 Comma-separated or repeated verdict-bucket ids (identical, same-behaviour,
 divergent) to fail across every domain, regardless of -Scope. Overrides
 datrix/scripts/config/behaviour-parity-scope.json's "buckets" list when
 given; when absent, the scope file's "buckets" list applies if it exists,
 else no bucket is gated.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis languages

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis languages -Scope queue,cache

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis languages -Buckets identical

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis platforms -Dbg
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("languages", "platforms")]
    [string]$Axis = "languages",

    [Parameter()]
    [string[]]$Scope,

    [Parameter()]
    [string[]]$Buckets,

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\behaviour_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: behaviour_parity.py not found at: $runnerScript"
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

    $pythonArgs = @($runnerScript, "--axis", $Axis)
    if ($Scope) { $pythonArgs += "--scope"; $pythonArgs += ($Scope -join ",") }
    if ($Buckets) { $pythonArgs += "--buckets"; $pythonArgs += ($Buckets -join ",") }
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    Write-Host "Running behaviour-parity gate on the $Axis axis" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Behaviour-parity gate failed (exit code $exitCode)" -ForegroundColor Red
        exit $exitCode
    }
    exit 0
} finally {
    Invoke-Cleanup
}
