<#
.SYNOPSIS
 Repo-level gate for ineedtoknow (ineedtoknow-gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs ineedtoknow-gate.py, which builds real
 workspaces in temporary directories (framework repositories plus a customer-style repository) with
 real SQLite files and a real model server on loopback, and checks: markdown chunking keeps the
 document's own line numbers, doc sync adds/updates/removes and never reads a customer repository,
 lookup answers only what a chunk covers, learned answers round-trip through their committed text
 files and a second machine converges from them, an answer expires when a cited file changes, and
 a gathered answer is stored only when every citation and quote is in what the model was sent.
 Nothing contacts the network's model servers and nothing touches the machine's own knowledge base.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_gather).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL] (proves the harness
 is not vacuous).

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\ineedtoknow-gate.ps1

.EXAMPLE
 .\ineedtoknow-gate.ps1 -Only check_gather
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$Only = "",
    [Parameter()] [switch]$HarnessSelfTest,
    [Parameter()] [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "ineedtoknow-gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Host "Error: ineedtoknow-gate.py not found at: $pythonScript" -ForegroundColor Red
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
    if ($Only) { $pythonArgs += @("--only", $Only) }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
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
