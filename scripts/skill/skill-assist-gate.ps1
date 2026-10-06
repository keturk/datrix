<#
.SYNOPSIS
 Repo-level gate for the skill assists (lib\skill_assist_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\skill_assist_gate.py, which builds real workspaces
 in temporary directories (git repositories, task files under .tasks/phase-NN, a findings folder, a
 design folder) and checks, over the real code index and a real model server on loopback: the
 shared-context digest (touched directories, module descriptions, not-yet-created files), the
 readiness evidence (missing dependency edges and unresolvable names exactly; already-satisfied leads
 with their citations checked), the findings index (citation tails mapped, invented and unassigned
 citations reported, registered customer terms never sent) and the no-loss check, the checklist draft
 (quotes verified, uncovered requirement lines listed), the absorb reference search and transfer
 verdicts, the bug Resolution builder (a non-framework diff never sent, a second Resolution refused),
 the evaluation report renderers, and the command line's exit code when no model answers. Nothing
 contacts the network's model servers.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_findings).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL] (proves the harness
 is not vacuous).

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\skill-assist-gate.ps1

.EXAMPLE
 .\skill-assist-gate.ps1 -Only check_findings
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$Only = "",
    [Parameter()] [switch]$HarnessSelfTest,
    [Parameter()] [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\skill_assist_gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Host "Error: skill_assist_gate.py not found at: $pythonScript" -ForegroundColor Red
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
