#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the review library.

.DESCRIPTION
 The behaviour is datrix_scripts.review.review_library_gate: plain-Python checks of the review
 library (review_schema, canonical_modules, escalation, review_reply parsing, the review
 orchestrator and Tier 2, the last against a model server on loopback; nothing contacts the
 network's model servers). It ends with the gate's verdict line.

 Exit codes:
   0 = every check passed
   1 = at least one check (or the harness self-test) failed
   2 = usage error

.PARAMETER Only
 Run only the checks whose name starts with this prefix (e.g. extract).

.PARAMETER HarnessSelfTest
 Demonstration mode: run one intentionally-failing dummy check through the harness
 and confirm it reports [FAIL] and exits 1 (proves the harness is not vacuous).

.PARAMETER SelfTest
 Run the harness self-test and the wrapper seam checks only.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\review-library-gate.ps1
 Run every check.

.EXAMPLE
 .\review-library-gate.ps1 -HarnessSelfTest
 Prove the harness detects a forced failure.
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.review.review_library_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
