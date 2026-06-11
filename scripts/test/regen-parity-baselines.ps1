#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Regenerate the stored reference-example parity baselines.

.DESCRIPTION
    For every example system.dtrx under datrix/examples/ x each discovered language
    generator, generates output in-process and writes a deterministic per-file sha256
    manifest to datrix-codegen-common/tests/parity/baselines/<example_id>/<language>.sha256.

    This is the ONLY sanctioned way to update baselines. The pytest gate
    (test_reference_example_parity.py) never writes baselines. Run this script
    deliberately after an intentional, reviewed change to generated output.

.PARAMETER Example
    Path relative to datrix/examples/ for a single example
    (e.g. "01-foundation" or "02-features/01-core-data-modeling/entities").
    When omitted, ALL examples are regenerated.

.PARAMETER Language
    Single language name (python or typescript).
    When omitted, ALL discovered languages are regenerated.

.PARAMETER Dbg
    Enable DEBUG-level logging.

.EXAMPLE
    .\regen-parity-baselines.ps1
    Rewrite every example x language baseline.

.EXAMPLE
    .\regen-parity-baselines.ps1 -Example "01-foundation"
    Rewrite baselines for the foundation example only.

.EXAMPLE
    .\regen-parity-baselines.ps1 -Language python
    Rewrite only the Python baselines for all examples.

.EXAMPLE
    .\regen-parity-baselines.ps1 -Example "02-features/01-core-data-modeling/entities" -Language typescript
    Rewrite the TypeScript baseline for the entities example.

.EXAMPLE
    .\regen-parity-baselines.ps1 -Dbg
    Rewrite all baselines with debug logging.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Example,

    [Parameter()]
    [string]$Language,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Script directory and derived paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"

Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

# Python regen entry point lives in the datrix-codegen-common tests package
$regenScript = Join-Path $datrixRoot "datrix-codegen-common\tests\parity\regen.py"

if (-not (Test-Path $regenScript)) {
    Write-Error "Regen script not found at: $regenScript"
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

    # Build Python arguments
    $pythonArgs = @($regenScript)

    if ($Example) {
        $pythonArgs += "--example"
        $pythonArgs += $Example
    }

    if ($Language) {
        $pythonArgs += "--language"
        $pythonArgs += $Language
    }

    if ($Dbg) {
        $pythonArgs += "--debug"
    }

    $modeDesc = if ($Example -and $Language) {
        "example=$Example language=$Language"
    } elseif ($Example) {
        "example=$Example (all languages)"
    } elseif ($Language) {
        "language=$Language (all examples)"
    } else {
        "all examples x all languages"
    }

    Write-Host "Regenerating parity baselines: $modeDesc" -ForegroundColor Cyan
    Write-Host "Script: $regenScript" -ForegroundColor DarkGray
    Write-Host ""

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host ""
        Write-Host "Parity baseline regeneration FAILED (exit code $exitCode)." -ForegroundColor Red
        Write-Host "Review the errors above and fix generation failures before retrying." -ForegroundColor Red
        exit $exitCode
    }

    Write-Host ""
    Write-Host "Parity baselines regenerated successfully." -ForegroundColor Green
    Write-Host "IMPORTANT: Review the baseline diff before committing." -ForegroundColor Yellow
    Write-Host "An unexpected change signals real cross-language divergence." -ForegroundColor Yellow
    exit 0

} finally {
    Invoke-Cleanup
}
