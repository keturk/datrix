#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Docs fence gate: every datrix fence under datrix/docs states a fact that holds.

.DESCRIPTION
 The showcase repo hosts no test suite, so its docs tree is checked here through
 the same collector, stages and comparison a package's case runner applies to
 its own docs/ tree: an example parses, a context= fragment parses in its
 construct, a whole application analyzes clean or to exactly the codes its
 expect= names, and rejected syntax stays rejected. A refused fence (an unknown
 info string, a datrix-grammar fence with no placeholder, a string that looks
 like a raw secret) fails the gate too.

 Runs a built-in non-vacuity self-test on every invocation: a planted fence that
 does not parse must be reported and its fixed twin must pass.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real check.

.EXAMPLE
 .\docs-fence-gate.ps1
 Check every datrix fence under datrix/docs.

.EXAMPLE
 .\docs-fence-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\docs_fence_gate.py") -Arguments $pythonArgs -RequirePackages -Gate "docs-fence")
