#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Java/Python SUPPORTED-and-shared-39 parity gate (design 036 G3, task 40-51).

.DESCRIPTION
 Proves java's and python's derived SUPPORTED domain sets, restricted to the
 seven rich cross-language domains (design 025 D4/D9) that are also
 shared-39 members, are identical -- zero symmetric difference. Imports both
 datrix_codegen_java.language_plugin.JavaLanguagePlugin and
 datrix_codegen_python.language_plugin.PythonLanguagePlugin and compares
 their `.domain_declarations`.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix). Previously two pytest tests inside
 datrix-codegen-java/tests/support/ (test_shared39_progression.py and its
 shared39_progression.py helper) that imported datrix_codegen_python
 directly from java's own test suite -- a cross-package test (prohibited
 everywhere in the repo, not only in the showcase package: "A test that
 imports two generator packages ... does not belong in datrix -- or
 anywhere"). The proof is inherently repo-level, so it was relocated here
 (deleting the pytest tests) rather than allowlisting the violation.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\shared39-supported-parity-gate.ps1
 Run the gate for java and python.

.EXAMPLE
 .\shared39-supported-parity-gate.ps1 -Dbg
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
$runnerScript = Join-Path $libraryDir "test\shared39_supported_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: shared39_supported_parity.py not found at: $runnerScript"
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

    Write-Host "Running shared-39 SUPPORTED parity gate (java vs python, design 036 G3)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Shared-39 SUPPORTED parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Shared-39 SUPPORTED parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
