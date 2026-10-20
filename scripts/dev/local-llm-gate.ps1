#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the local-model reading tools.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.local_llm_gate, which builds real workspaces in temporary
 directories (framework repositories, a customer-style repository beside them, .tmp and
 .test-output) and checks the reading layer and the MCP server against a real model server on
 loopback: what may be read and what is refused, chunking with original line numbers, log
 reduction, single-request and map-then-merge answers, citation checking, the usage log, and the
 MCP protocol. Nothing contacts the network's model servers. It ends with the gate's verdict line.

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
 .\local-llm-gate.ps1

.EXAMPLE
 .\local-llm-gate.ps1 -Only check_scope
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.local_llm_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
