#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the first-pass pre-review.

.DESCRIPTION
 The behaviour is datrix_scripts.git.pre_review_gate, which builds real git repositories in
 temporary directories and checks datrix_scripts.git.pre_review over them: the diff parser, every
 definite rule firing on added lines only (with Protocol/ABC exemptions and planted old violations
 as the non-vacuity control), pending changes read from git, model findings dropped unless grounded,
 and the model review staying advisory and off test files (against a real loopback model server).
 It ends with the gate's verdict line.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_model).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL].

.PARAMETER SelfTest
 Run the harness self-test and the wrapper seam checks only.

.PARAMETER Dbg
 Debug logging.

.EXAMPLE
 .\git\pre-review-gate.ps1

.EXAMPLE
 .\git\pre-review-gate.ps1 -Only check_model
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.pre_review_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
