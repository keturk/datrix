#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Collapsibility-classification enforcement gate (W1).

.DESCRIPTION
 Asserts that every name the parallel-implementation drift scanner reports
 DRIFTED, on either axis, carries a schema-valid `collapsibility` field in that
 axis's classification file: entry count == live drifted count (hard, once the
 file exists), every entry carries `status` (hard), and a decrease-only ratchet on
 the count of entries whose `collapsibility.mechanism` is missing, invalid, or (for
 mechanism 'none') carries no reason distinct from the entry's legitimacy reason.

 Runs a built-in plant/observe/revert non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest suite
 lives in datrix).

.PARAMETER Axis
 Which classification file to check: "languages" (default) or "platforms".

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real check.

.PARAMETER UpdateBaseline
 Write the live unclassified-collapsibility count as the new baseline for the
 invoked axis only.

.EXAMPLE
 .\collapsibility-classification-gate.ps1
 Check the language-axis classification file.

.EXAMPLE
 .\collapsibility-classification-gate.ps1 -Axis platforms -UpdateBaseline
 Freeze the current live platform-axis unclassified count as the new baseline.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("languages", "platforms")]
    [string]$Axis = "languages",

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$UpdateBaseline
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\collapsibility_classification.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: collapsibility_classification.py not found at: $runnerScript"
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
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }

    Write-Host "Running collapsibility-classification gate on the $Axis axis" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Collapsibility-classification gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Collapsibility-classification gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
