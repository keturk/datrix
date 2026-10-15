#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the first-pass pre-review (lib\pre_review_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\pre_review_gate.py, which builds real git
 repositories in temporary directories and checks scripts/git/lib/pre_review.py over them:
 the diff parser, every definite rule firing on added lines only (with Protocol/ABC exemptions
 and planted old violations as the non-vacuity control), pending changes read from git, model
 findings dropped unless grounded, and the model review staying advisory and off test files
 (against a real loopback model server).

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose function name starts with this prefix (e.g. check_model).

.PARAMETER HarnessSelfTest
 Run one intentionally-failing dummy check and confirm it is reported [FAIL].

.PARAMETER SelfTest
 Run the harness self-test and the gate's checks over planted inputs only.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\pre-review-gate.ps1
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\pre_review_gate.py") -Arguments $pythonArgs -Gate "pre-review" -ShowCommand:$Dbg)
