#!/usr/bin/env pwsh
<#
.SYNOPSIS
 GenDSL corpus reference-resolution gate (D1/I1).

.DESCRIPTION
 Proves the real, shipped corpus of builder/call/context/appends references
 across every consumer package (datrix-codegen-python, -typescript, -sql,
 -docker, -aws, -azure, -component) is genuinely resolvable. Imports each
 package's genDSL definitions module -- import succeeding IS the assertion;
 a bad reference raises GenDSLReferenceResolutionError at import time.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix). Previously a pytest test inside datrix-codegen-common
 that imported all seven concrete target packages directly, which was both a
 cross-package import boundary violation (datrix_codegen_common must not
 import concrete target packages) and a cross-package test (prohibited
 everywhere in the repo). Moved here as the repo-level proof it always was.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\gendsl-corpus-resolution-gate.ps1
 Run the gate for all seven packages.

.EXAMPLE
 .\gendsl-corpus-resolution-gate.ps1 -Dbg
 Run the gate with debug logging.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\gendsl_corpus_resolution.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: gendsl_corpus_resolution.py not found at: $runnerScript"
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

    Write-Host "Running GenDSL corpus resolution gate (7 packages)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "GenDSL corpus resolution gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "GenDSL corpus resolution gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
