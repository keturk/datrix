#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the review library (lib\review_library_gate.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\review_library_gate.py, which
 re-expresses the distinct behavioral classes of the review library's 5 former pytest files
 (test_review_schema.py, test_canonical_modules_cache.py, test_escalation.py,
 test_model_parsing.py, test_orchestrator_core.py) as a plain-Python check harness against
 lib\review_schema.py, lib\canonical_modules.py, lib\escalation.py, and lib\review.py.

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
 .\review-library-gate.ps1
 Run every absorbed check.

.EXAMPLE
 .\review-library-gate.ps1 -HarnessSelfTest
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\review_library_gate.py") -Arguments $pythonArgs -Gate "review-library" -ShowCommand:$Dbg)
