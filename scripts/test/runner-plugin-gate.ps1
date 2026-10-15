#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the test runner's pytest plugin (datrix_scripts.runner_plugin).

.DESCRIPTION
 Runs lib\runner_plugin_gate.py, which spawns real, separate pytest sessions
 (python -m pytest -p datrix_scripts.runner_plugin ...) against temporary fixture
 suites and checks the record files each writes: records never leak file
 contents, environment values or arguments; they hold exactly the observed,
 deselected and timing facts the session produced; a missing or malformed
 required environment variable is a usage error that names it; records are named
 for their worker and are never overwritten. See the .py file's module docstring
 for the full list.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed

.PARAMETER HarnessSelfTest
 Run only the harness self-test: register one deliberately-failing dummy
 check and confirm the harness reports it FAILED with a nonzero exit.

.PARAMETER SelfTest
 Run the harness self-test and the gate's checks over planted inputs only.

.PARAMETER Dbg
 Print the python executable and arguments before running.

.EXAMPLE
 .\runner-plugin-gate.ps1
 Run every runner-plugin behavior check; exit 0 only if all pass.

.EXAMPLE
 .\runner-plugin-gate.ps1 -HarnessSelfTest
 Prove the pass/fail harness itself can detect and report a failure.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$HarnessSelfTest,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($HarnessSelfTest) { $pythonArgs += "--harness-self-test" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\runner_plugin_gate.py") -Arguments $pythonArgs -Gate "runner-plugin" -ShowCommand:$Dbg)
