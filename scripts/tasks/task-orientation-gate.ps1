<#
.SYNOPSIS
 Repo-level gate for task orientation and citation validation (lib\task_orientation_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\task_orientation_gate.py, which builds real
 workspaces in temporary directories (framework repositories with real Python, task files under
 .tasks/phase-NN) and checks, over the real code index and a real model server on loopback: the
 ## Orientation block (parsed by the one task parser; every malformed entry and every "where is X
 defined / who calls X" question rejected), the resolver (exact facts, stale entries called out,
 explanations marked as leads, no model server leaving the facts intact), the citation checker
 (missing files and out-of-range lines are errors; abbreviated, ambiguous and not-yet-created paths
 are not; names beside a citation that are nowhere near its lines are warnings), and the validator end
 to end with its exit codes. Nothing contacts the network's model servers.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_citations).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL] (proves the harness
 is not vacuous).

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\task-orientation-gate.ps1

.EXAMPLE
 .\task-orientation-gate.ps1 -Only check_citations
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$Only = "",
    [Parameter()] [switch]$HarnessSelfTest,
    [Parameter()] [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\task_orientation_gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Host "Error: task_orientation_gate.py not found at: $pythonScript" -ForegroundColor Red
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
