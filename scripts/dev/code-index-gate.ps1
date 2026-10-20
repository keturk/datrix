#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the code index and its entry points.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.code_index_gate, which builds real workspaces of git
 repositories in temporary directories and checks the code index over them: extraction,
 incremental refresh, git visibility and excludes, import-resolved references, the logic-map
 rewrite, search, canonical lookup, model summaries (against a real loopback model server), and
 the MCP server over its standard streams. It ends with the gate's verdict line.

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
 Run the harness self-test and the wrapper seam checks only.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\code-index-gate.ps1

.EXAMPLE
 .\code-index-gate.ps1 -Only check_references
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.code_index_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
