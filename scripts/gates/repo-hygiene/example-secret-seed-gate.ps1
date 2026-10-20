#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Example secret-seed gate: every example's deploy test can start its stack.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.example_secret_seed_gate in the shared venv.

 A handle a service declares in its secrets { } table is mounted into the
 container as a file, and the generated deployment script refuses to start
 the stack while that file is absent -- with nothing written in its place,
 because an operator-provisioned value is a credential the deployment does
 not hold. On a local secret profile the generator writes the file only
 from the handle's localDefault.

 The example corpus is deploy-tested on the 'test' profile by an unattended
 harness, so for every example, on that profile, every required
 operator-provisioned handle must carry a localDefault -- or no full-corpus
 run can ever bring the example up, and the deploy log is where anyone
 finds out. Three examples shipped that way the day secret delivery moved
 to compose file secrets.

 Runs a built-in non-vacuity self-test on every invocation (the pure
 comparator over synthetic handles, no file I/O). Fails loud (exit 2) if
 zero examples or zero service configs exist on disk.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable DEBUG logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real check.

.EXAMPLE
 .\example-secret-seed-gate.ps1
 Run the gate against the real examples tree.

.EXAMPLE
 .\example-secret-seed-gate.ps1 -SelfTest
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.example_secret_seed_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
