<#
.SYNOPSIS
 Repo-level gate for ineedtoknow (lib\ineedtoknow_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\ineedtoknow_gate.py, which builds real
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

.PARAMETER SelfTest
 Run the harness self-test and the gate's checks over planted inputs only.

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
    [Parameter()] [switch]$SelfTest,
    [Parameter()] [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($HarnessSelfTest) { $pythonArgs += "--harness-self-test" }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Only) { $pythonArgs += @("--only", $Only) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\ineedtoknow_gate.py") -Arguments $pythonArgs -Gate "ineedtoknow" -ShowCommand:$Dbg)
