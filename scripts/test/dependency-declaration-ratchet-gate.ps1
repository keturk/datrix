#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Dependency-declaration-only-path ratchet (W4 / design-principle F5 enforcement).

.DESCRIPTION
 Reports every site in every package implementing each registered language
 (its backend plus each language core the backend requires) that decides a
 dependency package NAME outside the language's own
 generation/dependency_tables.py table, and checks the out-of-table count
 against a decrease-only baseline at
 scripts/config/dependency-declaration-ratchet-baseline.json.

 Runs a built-in non-vacuity self-test on every invocation, including a
 fixture language split into a backend and a core, and a live check that
 every registered language's real catalog covers every package its real
 declared table names. Fails loud (exit 2) if fewer than two languages are
 registered.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER UpdateBaseline
 Write the live out-of-table count as the new baseline.

.EXAMPLE
 .\dependency-declaration-ratchet-gate.ps1
 Run the report over every registered language and check the ratchet.

.EXAMPLE
 .\dependency-declaration-ratchet-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\dependency-declaration-ratchet-gate.ps1 -UpdateBaseline
 Freeze the current live out-of-table count as the new baseline.
#>

[CmdletBinding()]
param(
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
$runnerScript = Join-Path $libraryDir "test\dependency_declaration_ratchet.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: dependency_declaration_ratchet.py not found at: $runnerScript"
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
    if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }

    Write-Host "Running dependency-declaration-only-path ratchet" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Dependency-declaration ratchet failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Dependency-declaration ratchet passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
