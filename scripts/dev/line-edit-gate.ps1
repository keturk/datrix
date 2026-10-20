#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for line-addressed editing.

.DESCRIPTION
 Runs datrix_scripts.dev.line_edit_gate in the shared venv. It builds real files in a temporary
 workspace and reads and edits them through datrix_scripts.line_edits and the datrix-edit MCP
 server (datrix_scripts.dev.line_edit_mcp): hash-checked replaces and inserts, a whole call refused
 when one hash is wrong, line numbers that refer to the file before the call, kept line endings,
 byte-order mark and final newline, the reply a follow-up edit uses, the workspace and UTF-8
 limits, the span the edit guards are shown, and the MCP protocol. Nothing outside the temporary
 directory is touched.

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
 Run the harness self-test and the wrapper seam checks.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\line-edit-gate.ps1

.EXAMPLE
 .\line-edit-gate.ps1 -Only check_mcp
#>
[CmdletBinding()]
param(
 [string]$Only, [switch]$HarnessSelfTest, [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.line_edit_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
