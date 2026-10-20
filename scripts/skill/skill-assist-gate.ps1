#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the skill assists.

.DESCRIPTION
 The behaviour is datrix_scripts.skill.skill_assist_gate, which builds real workspaces in temporary
 directories (git repositories, task files under .tasks/phase-NN, a findings folder, a design folder)
 and checks, over the real code index and a real model server on loopback: the shared-context digest
 (touched directories, module descriptions, not-yet-created files), the readiness evidence (missing
 dependency edges and unresolvable names exactly; already-satisfied leads with their citations
 checked), the findings index (citation tails mapped, invented and unassigned citations reported,
 registered customer terms never sent) and the no-loss check, the checklist draft (quotes verified,
 uncovered requirement lines listed), the absorb reference search and transfer verdicts, the bug
 Resolution builder (a non-framework diff never sent, a second Resolution refused), the evaluation
 report renderers, and the command line's exit code when no model answers. Nothing contacts the
 network's model servers. It ends with the gate's verdict line.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_findings).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL] (proves the harness
 is not vacuous).

.PARAMETER SelfTest
 Run the harness self-test and the wrapper seam checks only.

.PARAMETER Dbg
 Debug logging.

.EXAMPLE
 .\skill\skill-assist-gate.ps1

.EXAMPLE
 .\skill\skill-assist-gate.ps1 -Only check_findings
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.skill.skill_assist_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
