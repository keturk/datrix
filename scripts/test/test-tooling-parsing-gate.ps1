#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the test tooling's result parsing (lib\test_tooling_parsing_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\test_tooling_parsing_gate.py, a
 plain-Python check harness (no pytest) over the result parsing of test/lib/compare_tests.py,
 the shared datrix_scripts.status_tests, and run_complete's summary-line parsing.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER HarnessSelfTest
 Demonstration mode: run one intentionally-failing dummy check through the harness
 and confirm it reports [FAIL] and exits 1 (proves the harness is not vacuous).

.PARAMETER SelfTest
 Run the harness self-test and the gate's checks over planted inputs only.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\test-tooling-parsing-gate.ps1
 Run every absorbed check.

.EXAMPLE
 .\test-tooling-parsing-gate.ps1 -HarnessSelfTest
 Prove the harness detects a forced failure.
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\test_tooling_parsing_gate.py") -Arguments $pythonArgs -Gate "test-tooling-parsing" -ShowCommand:$Dbg)
