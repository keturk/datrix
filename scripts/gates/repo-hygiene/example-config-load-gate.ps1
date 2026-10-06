#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Example config load gate: every declared profile of every example .dcfg loads.

.DESCRIPTION
 Every model a ConfigDSL document validates into rejects unknown keys, so a
 key the model does not declare is an error at load time rather than a value
 silently dropped. This gate loads every declared profile of every .dcfg
 under datrix/examples through the real loaders (service, shared, system,
 identity, app, strings, extern) and fails on any error, so a misspelled or
 retired key in the corpus is found here.

 Runs a built-in non-vacuity self-test on every invocation: a planted temp
 .dcfg carrying an unknown nested key must be reported (key named, value not
 echoed) and its clean twin must load. Fails loud (exit 2) if zero .dcfg
 files exist on disk.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real check.

.EXAMPLE
 .\example-config-load-gate.ps1
 Load every declared profile of every example .dcfg.

.EXAMPLE
 .\example-config-load-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $scriptDir "lib\example_config_load.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: example_config_load.py not found at: $runnerScript"
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

    Write-Host "Running example config load gate" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Example config load gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Example config load gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
