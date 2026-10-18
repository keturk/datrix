<#
.SYNOPSIS
 Repo-level gate for line-addressed editing (lib\line_edit_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\line_edit_gate.py, which builds real files in a
 temporary workspace and reads and edits them through datrix_scripts.line_edits and the datrix-edit MCP
 server: hash-checked replaces and inserts, a whole call refused when one hash is wrong, line numbers that
 refer to the file before the call, kept line endings, byte-order mark and final newline, the reply a
 follow-up edit uses, the workspace and UTF-8 limits, the span the edit guards are shown, and the MCP
 protocol. Nothing outside the temporary directory is touched.

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
 .\line-edit-gate.ps1

.EXAMPLE
 .\line-edit-gate.ps1 -Only check_mcp
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\line_edit_gate.py") -Arguments $pythonArgs -Gate "line-edit" -ShowCommand:$Dbg)
