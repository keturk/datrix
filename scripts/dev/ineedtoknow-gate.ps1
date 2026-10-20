#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for ineedtoknow.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.ineedtoknow_gate, which builds real workspaces in temporary
 directories (framework repositories plus a customer-style repository) with real SQLite files and
 a real model server on loopback, and checks: markdown chunking keeps the document's own line
 numbers, doc sync adds/updates/removes and never reads a customer repository, lookup answers only
 what a chunk covers, learned answers round-trip through their committed text files and a second
 machine converges from them, an answer expires when a cited file changes, and a gathered answer
 is stored only when every citation and quote is in what the model was sent. Nothing contacts the
 network's model servers and nothing touches the machine's own knowledge base. It ends with the
 gate's verdict line.

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
 Run the harness self-test and the wrapper seam checks only.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\ineedtoknow-gate.ps1

.EXAMPLE
 .\ineedtoknow-gate.ps1 -Only check_gather
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.ineedtoknow_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
