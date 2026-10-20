#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Declarative design-acceptance assertion runner over a file tree.

.DESCRIPTION
 Evaluates a JSON spec of must_contain / must_not_contain / file_exists /
 file_absent / count_equals assertions (regex patterns, text files only) over a
 target tree and writes a per-assertion PASS/FAIL ledger to
 <workspace>\.test-output\conformance\<spec-stem>-ledger.json.
 must_not_contain supports a negative_control tree: the pattern MUST appear
 there or the assertion fails as vacuous. A built-in self-test proving every
 assertion type both detects a violation and passes a satisfied case runs as
 step 1 of every invocation (self-test failure aborts with exit 2).

 The last line is the gate verdict, "[GATE] conformance PASSED|FAILED exit=<n>
 log=<path>"; the log under .test-output\gates\conformance\ holds the whole run.

.PARAMETER Spec
 Path to the conformance spec JSON.

.PARAMETER SelfTest
 Run only the built-in self-test and the wrapper seam check, and exit.

.PARAMETER Output
 Override the ledger path (default:
 <workspace>\.test-output\conformance\<spec-stem>-ledger.json).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\conformance-gate.ps1 my-spec.json

.EXAMPLE
 .\conformance-gate.ps1 -SelfTest
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Spec,

 [Parameter()]
 [switch]$SelfTest,

 [Parameter()]
 [string]$Output,

 [Parameter()]
 [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.realization.conformance_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
