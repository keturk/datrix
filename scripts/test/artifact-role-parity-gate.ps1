#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language artifact-role parity gate (D7).

.DESCRIPTION
 For every example with >= 2 blessed language baselines under
 datrix/scripts/config/parity-baselines/, classifies each blessed manifest's
 paths by domain role (via each language's own derived
 DomainDeclaration.structural_pattern) and asserts the set of roles with
 >= 1 matching file is identical across that example's blessed languages.

 Generates NOTHING -- reads the blessed .sha256 manifests
 reference-example-parity-gate.ps1 already writes. Replaces nothing: the
 byte gate still pins CONTENT per (example, language) pair; this gate pins
 PRESENCE across languages. Coverage grows automatically as later phases
 bless more of the matrix.

 Runs a built-in non-vacuity self-test on every invocation. Fails loud
 (exit 2) if zero examples have >= 2 blessed language baselines.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\artifact-role-parity-gate.ps1
 Run the gate for every example with >= 2 blessed language baselines.

.EXAMPLE
 .\artifact-role-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\artifact_role_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: artifact_role_parity.py not found at: $runnerScript"
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

    Write-Host "Running artifact-role parity gate (D7, blessed baselines only)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Artifact-role parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Artifact-role parity gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
