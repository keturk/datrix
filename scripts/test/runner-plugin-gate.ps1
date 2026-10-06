#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the test runner's pytest plugin (datrix_scripts.runner_plugin).

.DESCRIPTION
 Runs lib\runner_plugin_gate.py, which spawns real, separate pytest sessions
 (python -m pytest -p datrix_scripts.runner_plugin ...) against temporary fixture
 suites and checks the record files each writes: records never leak file
 contents, environment values or arguments; they hold exactly the observed,
 deselected and timing facts the session produced; a missing or malformed
 required environment variable is a usage error that names it; records are named
 for their worker and are never overwritten. See the .py file's module docstring
 for the full list.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed

.PARAMETER HarnessSelfTest
 Run only the harness self-test: register one deliberately-failing dummy
 check and confirm the harness reports it FAILED with a nonzero exit.

.PARAMETER Dbg
 Print the python executable, script path, and arguments before running.

.EXAMPLE
 .\runner-plugin-gate.ps1
 Run every runner-plugin behavior check; exit 0 only if all pass.

.EXAMPLE
 .\runner-plugin-gate.ps1 -HarnessSelfTest
 Prove the pass/fail harness itself can detect and report a failure.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$HarnessSelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\runner_plugin_gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: runner_plugin_gate.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"

    $pythonArgs = @($pythonScript)
    if ($HarnessSelfTest) { $pythonArgs += "--harness-self-test" }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
        Write-Host "Arguments: $($pythonArgs -join ' ')" -ForegroundColor Cyan
        Write-Host ""
    }

    & $pythonExe @pythonArgs
    exit $LASTEXITCODE

} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
