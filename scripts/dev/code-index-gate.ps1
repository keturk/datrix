#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the code index and its entry points (lib\code_index_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\code_index_gate.py, which builds real
 workspaces of git repositories in temporary directories and checks the code index over them:
 extraction, incremental refresh, git visibility and excludes, import-resolved references,
 the logic-map rewrite, search, canonical lookup, model summaries (against a real loopback
 model server), and the MCP server over its standard streams.

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
 .\code-index-gate.ps1

.EXAMPLE
 .\code-index-gate.ps1 -Only check_references
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\code_index_gate.py") -Arguments $pythonArgs -Gate "code-index" -ShowCommand:$Dbg)
