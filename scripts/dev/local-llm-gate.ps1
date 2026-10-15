<#
.SYNOPSIS
 Repo-level gate for the local-model reading tools (lib\local_llm_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\local_llm_gate.py, which builds real workspaces
 in temporary directories (framework repositories, a customer-style repository beside them, .tmp
 and .test-output) and checks the reading layer and the MCP server against a real model server on
 loopback: what may be read and what is refused, chunking with original line numbers, log
 reduction, single-request and map-then-merge answers, citation checking, the usage log, and the
 MCP protocol. Nothing contacts the network's model servers.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_mcp).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL] (proves the harness
 is not vacuous).

.PARAMETER SelfTest
 Run the harness self-test and the gate's checks over planted inputs only.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\local-llm-gate.ps1

.EXAMPLE
 .\local-llm-gate.ps1 -Only check_scope
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\local_llm_gate.py") -Arguments $pythonArgs -Gate "local-llm" -ShowCommand:$Dbg)
