#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate absorbing the shared-library test coverage orphaned by the
 datrix showcase repo's no-pytest-suite boundary.

.DESCRIPTION
 Runs shared-library-gate.py, which re-expresses every distinct behavior class
 from the 8 orphaned pytest files under scripts/library/shared/tests/ as plain
 Python checks (no pytest, no mocks, real tempfile.TemporaryDirectory()
 fixtures). See the .py file's module docstring for the full list of modules
 covered.

 Exit codes:
   0 = every check passed
   1 = at least one check failed
   2 = usage error

.PARAMETER HarnessSelfTest
 Run only the harness self-test: register one deliberately-failing dummy
 check and confirm the harness reports it FAILED with a nonzero exit. Proves
 the pass/fail mechanism itself cannot swallow a failure.

.PARAMETER Dbg
 Enable debug logging (prints the python executable, script path, and arguments).

.EXAMPLE
 .\shared-library-gate.ps1
 Run every shared-library behavior check; exit 0 only if all pass.

.EXAMPLE
 .\shared-library-gate.ps1 -HarnessSelfTest
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
$pythonScript = Join-Path $scriptDir "shared-library-gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: shared-library-gate.py not found at: $pythonScript"
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
