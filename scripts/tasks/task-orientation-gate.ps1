#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for task orientation and citation validation.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.task_orientation_gate, which builds real workspaces in
 temporary directories (framework repositories with real Python, task files under .tasks/phase-NN)
 and checks, over the real code index and a real model server on loopback: the ## Orientation block
 (parsed by the one task parser; every malformed entry and every "where is X defined / who calls X"
 question rejected), the resolver (exact facts, stale entries called out, explanations marked as
 leads, no model server leaving the facts intact), the citation checker (missing files and
 out-of-range lines are errors; abbreviated, ambiguous and not-yet-created paths are not; names beside
 a citation that are nowhere near its lines are warnings), the validator end to end with its exit
 codes, and the orientation retrofit. Nothing contacts the network's model servers. It ends with the
 gate's verdict line.

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
 Run the harness self-test and the wrapper seam checks only.

.PARAMETER Dbg
 Debug logging.

.EXAMPLE
 .\tasks\task-orientation-gate.ps1

.EXAMPLE
 .\tasks\task-orientation-gate.ps1 -Only check_citations
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.task_orientation_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
