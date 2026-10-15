#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the shared scripts package and the scripts-tree contracts.

.DESCRIPTION
 Runs lib\shared_library_gate.py, which checks the shared scripts package
 (common/lib/datrix_scripts), the scripts-tree layout and the scripts-tree censuses as plain
 Python checks (no pytest, no mocks, real tempfile.TemporaryDirectory() fixtures). See the .py
 file's module docstring for the full list of modules covered.

 Exit codes:
   0 = every check passed
   1 = at least one check failed
   2 = usage error

.PARAMETER SelfTest
 Run only the gate's non-vacuity proof over planted inputs: the harness reports a deliberate
 failure, and each scripts-tree census reports a planted copy. Reads nothing of the real tree.

.PARAMETER HarnessSelfTest
 Run only the harness self-test: one deliberately-failing check must be reported FAILED.

.PARAMETER Only
 Run only the checks whose name starts with this prefix (e.g. check_local_llm),
 for a change confined to one shared module.

.EXAMPLE
 .\shared-library-gate.ps1
 Run every shared-library behavior check; exit 0 only if all pass.

.EXAMPLE
 .\shared-library-gate.ps1 -SelfTest
 Prove each census and the pass/fail harness can detect and report a failure.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$HarnessSelfTest,

    [Parameter()]
    [string]$Only = ""
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($HarnessSelfTest) { $pythonArgs += "--harness-self-test" }
if ($Only) { $pythonArgs += @("--only", $Only) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\shared_library_gate.py") -Arguments $pythonArgs -Gate "shared-library")
