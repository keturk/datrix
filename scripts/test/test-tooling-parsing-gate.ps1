#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the test tooling's result parsing.
.DESCRIPTION
 Runs datrix_scripts.test.test_tooling_parsing_gate, a plain-Python check harness (no pytest) over the result
 parsing of datrix_scripts.test.compare_tests, datrix_scripts.status_tests, run_complete's summary-line parsing,
 the node test runner's JUnit merge and post_process_test_results' index.json. -Only <prefix> runs only the checks
 whose name starts with it. -SelfTest runs the harness self-test and the wrapper seam checks; -HarnessSelfTest runs
 only the harness self-test. Exit 0 pass, 1 a check failed, 2 usage error. The last line is
 "[GATE] test-tooling-parsing PASSED|FAILED exit=<n> log=<path>".
 python -m datrix_scripts.test.test_tooling_parsing_gate --help describes every option.
.EXAMPLE
 .\test\test-tooling-parsing-gate.ps1 -HarnessSelfTest
#>
[CmdletBinding()]
param(
 [string]$Only, [switch]$SelfTest, [switch]$HarnessSelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.test_tooling_parsing_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
