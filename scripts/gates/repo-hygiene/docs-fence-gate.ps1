#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Docs fence gate: every datrix fence under datrix/docs states a fact that holds.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.docs_fence_gate in the shared venv.

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
 Enable DEBUG logging.

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
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.docs_fence_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
