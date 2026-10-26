#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the pull-over-local-work script.

.DESCRIPTION
 The behaviour is datrix_scripts.git.resolve_pull_gate, which builds an origin repository and a
 clone of it in temporary directories and runs datrix_scripts.git.resolve_pull over the clone: the
 clean reapply shelving only the overlap, a conflict left with its packet, the finish refusing
 markers and dropped local lines, a set-aside untracked file, a line-ending-only overlap, the diff3
 parser, and the merge draft checked against both sides (against a real loopback model server). No
 real checkout is touched. It ends with the gate's verdict line.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_conflict).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL].

.PARAMETER SelfTest
 Run the harness self-test and the wrapper seam checks only.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\git\resolve-pull-gate.ps1

.EXAMPLE
 .\git\resolve-pull-gate.ps1 -Only check_conflict
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.resolve_pull_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
