#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate absorbing 2 orphaned test/tests/*.py pytest files (test-tooling-parsing-gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs test-tooling-parsing-gate.py, which
 re-expresses the distinct behavioral classes of 2 orphaned pytest files under
 scripts/library/test/tests/ (test_compare_tests.py, test_status_tests_index.py) as a
 plain-Python check harness against test/compare_tests.py and test/status_tests.py.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER HarnessSelfTest
 Demonstration mode: run one intentionally-failing dummy check through the harness
 and confirm it reports [FAIL] and exits 1 (proves the harness is not vacuous).

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\test-tooling-parsing-gate.ps1
 Run every absorbed check.

.EXAMPLE
 .\test-tooling-parsing-gate.ps1 -HarnessSelfTest
 Prove the harness detects a forced failure.
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
$pythonScript = Join-Path $scriptDir "test-tooling-parsing-gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: test-tooling-parsing-gate.py not found at: $pythonScript"
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
    $exitCode = $LASTEXITCODE

    exit $exitCode

} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
