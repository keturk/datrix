#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Language-axis and platform-axis behaviour-parity gate.

.DESCRIPTION
 Wraps datrix/scripts/gates/parity/lib/behaviour_parity.py. Groups functions
 across registered target packages into roles (on the platform axis, first by
 the block type a platform's own realization table registers the function a
 plan builder for; then by shared-typed signature or normalized name),
 classifies each into identical / same-behaviour /
 divergent by comparing behaviour skeletons rather than bodies. A role fails
 when it is not adapter-exempt (identical / same-behaviour) or when its
 member packages still split into more than one skeleton group (divergent);
 no capability declaration or gap row sets a package aside. No language is
 the reference: a divergent role names every skeleton group it splits into.

 Every role is in scope -- every bucket, every domain, an `undomained` role
 included. The verdict is the count of failing roles compared in BOTH
 directions with the pin in
 datrix/scripts/config/behaviour-parity-baseline.toml: more failing roles
 than the pin fails (a regression), fewer fails too unless the pin is
 lowered in the same change (an improvement must be banked). Both axes gate,
 each against its own section ([languages], [platforms]) of that file.

 Runs a non-vacuity self-test on every invocation -- the five-bucket role
 grouping/classification cases, and the fingerprint pass's own non-vacuity
 (a planted renamed pair is reported; a covered, under-size, no-model-read
 or single-package pair is not). Exits 2 if fewer than two targets are
 registered on the chosen axis, or on a discovery/parse/self-test failure.

.PARAMETER Axis
 "languages" (default) or "platforms".

.PARAMETER Scope
 Comma-separated or repeated domain ids (plus the literal "undomained")
 whose role lines the report prints. A report filter only: it never changes
 the failing-role count or the exit code.

.PARAMETER Buckets
 Comma-separated or repeated verdict-bucket ids (identical, same-behaviour,
 divergent) whose role lines the report prints; with -Scope, a role prints
 when it satisfies both. A report filter only: it never changes the
 failing-role count or the exit code.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Fingerprint
 Also run the report-only skeleton-fingerprint grouping pass: cross-package
 groups of functions no name/signature role covers, judged by the same
 verdict rules. Never changes the exit code.

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis languages

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis languages -Dbg -Scope queue,cache   # print only those domains' role lines

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis languages -Dbg -Buckets identical   # print only the identical-verdict role lines

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Axis platforms -Dbg

.EXAMPLE
 .\behaviour-parity-gate.ps1 -Fingerprint
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
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Fingerprint
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = Join-Path $scriptDir "lib\behaviour_parity.py"

$commonDir = Join-Path $scriptDir "..\..\common"
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
    if ($Fingerprint) { $pythonArgs += "--fingerprint" }

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
