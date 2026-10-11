#!/usr/bin/env pwsh
<#
.SYNOPSIS
 DAL generator corpus reference-resolution gate.

.DESCRIPTION
 Proves the real, shipped corpus of builder/call/context/appends references
 across every DISCOVERED DAL generator target -- derived from
 datrix.dgen_generator_targets + datrix.platforms entry-point discovery,
 never a hardcoded package list -- is genuinely resolvable. Imports each
 target's DAL generator definitions module -- import succeeding IS the assertion;
 a bad reference raises DalReferenceError at import time.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix). Previously a pytest test inside datrix-codegen-common
 that imported all seven concrete target packages directly, which was both a
 cross-package import boundary violation (datrix_codegen_common must not
 import concrete target packages) and a cross-package test (prohibited
 everywhere in the repo). Moved here as the repo-level proof it always was.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\dgen-corpus-resolution-gate.ps1
 Run the gate for every discovered DAL generator target.

.EXAMPLE
 .\dgen-corpus-resolution-gate.ps1 -Dbg
 Run the gate with debug logging.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = Join-Path $scriptDir "lib\dgen_corpus_resolution.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: dgen_corpus_resolution.py not found at: $runnerScript"
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

    Write-Host "Running DAL generator corpus resolution gate (all discovered targets)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "DAL generator corpus resolution gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "DAL generator corpus resolution gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
