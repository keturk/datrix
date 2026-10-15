#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Prove that `test.ps1 <package> -Specific <file>` runs ONLY that file's tests.

.DESCRIPTION
 A `-Specific` run that reports PASSED while its own index.json / JUnit XML
 describe a DIFFERENT file's tests is a silent false green: the caller "proves"
 a fix that never ran. That was a real, observed defect -- TeeLogger named its
 run directory to the second and created it with mkdir(exist_ok=True), so two
 test.ps1 invocations against one package that started in the same second shared
 one run directory and overwrote each other's artifacts, each still printing its
 own PASSED.

 This gate checks, on every run:
   1. NON-VACUITY -- the comparator is fed a deliberately WRONG-file run directory
      and must reject it (and fed a correct one, which it must accept). A gate that
      cannot fail is not a gate, so this runs FIRST and its failure fails the gate.
   2. POSITIVE -- a real `-Specific <fileA>` run's own artifacts name only fileA.
   3. RUN-DIRECTORY EXCLUSIVITY -- TeeLogger's timestamp format is pinned to a
      literal so every racer wants the SAME directory name (a guaranteed collision,
      not a hoped-for one); each must still get a directory of its own, both
      sequentially and concurrently. This is the root-cause invariant and it is
      deterministic: it fails 8/8 against the old mkdir(exist_ok=True).
   4. CONCURRENCY -- two concurrent `-Specific` runs against the same package but
      different files must get distinct run directories, each naming only its own
      file. This reproduces the original defect end-to-end.

 Repo-level validation SCRIPT, not a pytest suite (per the datrix showcase
 boundary -- datrix hosts no test suite of any kind).

 Exit codes:
   0 = -Specific selects only the requested file, and the check is non-vacuous
   1 = a check failed (wrong-file selection, shared run directory, or vacuous gate)
   2 = usage error (test.ps1 or the named test files not found)

.PARAMETER Package
 Package to exercise (default: datrix-codegen-python).

.PARAMETER FileA
 First test file, relative to the package root. Default is the file from the
 original report.

.PARAMETER FileB
 Second test file, relative to the package root. Used as the concurrent run's
 target; it must be a DIFFERENT file from FileA for the concurrency check to mean
 anything.

.PARAMETER SelfTest
 Run only the non-vacuity self-test (the comparator rejects a planted wrong-file
 run directory and accepts a correct one) and run no suite.

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\test-specific-selection-gate.ps1
 Run the gate against the default package/file pair.

.EXAMPLE
 .\test-specific-selection-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\test-specific-selection-gate.ps1 -Package datrix-common -FileA "tests/unit/datrix_model/test_seal.py" -FileB "tests/unit/datrix_model/test_traits.py"
 Run the gate against a different package and file pair.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Package = "",

    [Parameter()]
    [string]$FileA = "",

    [Parameter()]
    [string]$FileB = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Package) { $pythonArgs += @("--package", $Package) }
if ($FileA) { $pythonArgs += @("--file-a", $FileA) }
if ($FileB) { $pythonArgs += @("--file-b", $FileB) }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\test_specific_selection_gate.py") -Arguments $pythonArgs -Gate "test-specific-selection" -ShowCommand:$Dbg)
