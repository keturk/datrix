#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Committed example-snapshot gate.

.DESCRIPTION
 Every directory directly under any datrix/examples/**/generated/ must be named
 <language>-<platform> with both halves registered (datrix.languages /
 datrix.platforms entry points), and each example must carry one snapshot per
 registered language for every platform it carries. Every dotted datrix_*
 reference in every snapshot text file and in every datrix-*/src .j2 template
 must resolve through importlib.

 Targets come from the registered entry points at run time, never from a
 hand-written list. Refuses (exit 2) with fewer than two registered languages,
 with no snapshot on disk, or when no template reference is found.

 Runs a built-in non-vacuity self-test on every invocation. Does not
 regenerate: refresh a snapshot with dev\refresh-example-snapshot.ps1.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\example-snapshot-gate.ps1
 Run the gate against the real tree.

.EXAMPLE
 .\example-snapshot-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\example_snapshots.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: example_snapshots.py not found at: $runnerScript"
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
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    Write-Host "Running example-snapshot gate" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Example-snapshot gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Example-snapshot gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
