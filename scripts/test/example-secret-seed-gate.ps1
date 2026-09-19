#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Example secret-seed gate: every example's deploy test can start its stack.

.DESCRIPTION
 A handle a service declares in its secrets { } table is mounted into the
 container as a file, and the generated deployment script refuses to start
 the stack while that file is absent -- with nothing written in its place,
 because an operator-provisioned value is a credential the deployment does
 not hold. On a local secret profile the generator writes the file only
 from the handle's localDefault.

 The example corpus is deploy-tested on the 'test' profile by an unattended
 harness, so for every example, on that profile, every required
 operator-provisioned handle must carry a localDefault -- or no full-corpus
 run can ever bring the example up, and the deploy log is where anyone
 finds out. Three examples shipped that way the day secret delivery moved
 to compose file secrets.

 Runs a built-in non-vacuity self-test on every invocation (the pure
 comparator over synthetic handles, no file I/O). Fails loud (exit 2) if
 zero examples or zero service configs exist on disk.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real check.

.EXAMPLE
 .\example-secret-seed-gate.ps1
 Run the gate against the real examples tree.

.EXAMPLE
 .\example-secret-seed-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\example_secret_seed.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: example_secret_seed.py not found at: $runnerScript"
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

    Write-Host "Running example secret-seed gate" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Example secret-seed gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Example secret-seed gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
