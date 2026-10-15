<#
.SYNOPSIS
 Repo-level gate for task orientation and citation validation (lib\task_orientation_gate.py).

.DESCRIPTION
 Runs lib\task_orientation_gate.py in the shared venv, which builds real
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

.PARAMETER SelfTest
 Run the harness self-test and the gate's checks over planted inputs only.

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
    [Parameter()] [switch]$SelfTest,
    [Parameter()] [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($HarnessSelfTest) { $pythonArgs += "--harness-self-test" }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Only) { $pythonArgs += @("--only", $Only) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\task_orientation_gate.py") -Arguments $pythonArgs -Gate "task-orientation" -ShowCommand:$Dbg)
