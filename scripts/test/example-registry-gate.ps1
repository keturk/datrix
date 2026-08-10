#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Example-universe consistency and layout gate (D9).

.DESCRIPTION
 Every system.dtrx under datrix/examples/ must appear in >= 1 named test set
 of datrix/scripts/config/test-projects.json, or carry a reviewed entry in
 datrix/scripts/config/test-set-exclusions.json. An unregistered example is
 never built by generate.ps1 -All / run-complete.ps1 -All, which select
 their corpus FROM test-projects.json's test sets -- exactly how the
 config-store and replayable-ingestion whole-example parked defects went
 unnoticed for a full generation cycle.

 Also enforces the examples tree's layout contract, since an example's
 identity IS its directory: no example may live inside another example, and
 no .dtrx/.dcfg may belong to two examples or to none.

 Runs a built-in non-vacuity self-test on every invocation (a pure
 comparator proof against synthetic ids and paths, no file I/O). Fails loud
 (exit 2) if zero examples exist on disk.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\example-registry-gate.ps1
 Run the gate against the real tree.

.EXAMPLE
 .\example-registry-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\example_registry_consistency.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: example_registry_consistency.py not found at: $runnerScript"
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

    Write-Host "Running example-registry consistency gate (D9)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Example-registry consistency gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Example-registry consistency gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
