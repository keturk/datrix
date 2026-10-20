#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the shared scripts package and the scripts-tree contracts.
.DESCRIPTION
 Runs datrix_scripts.test.shared_library_gate, which checks the shared scripts package (common/lib/datrix_scripts),
 the scripts-tree layout and the scripts-tree censuses as plain Python checks (no pytest, no mocks, real temporary
 directories); the module docstring lists every module covered. -Only runs the checks whose name starts with a
 prefix (e.g. check_local_llm), for a change confined to one shared module. -SelfTest runs only the non-vacuity
 proof over planted inputs (the harness reports a deliberate failure, each scripts-tree census reports a planted
 copy, and the wrapper seam is checked), reading nothing of the real tree; -HarnessSelfTest runs only the harness
 self-test. Exit 0 every check passed, 1 a check failed, 2 usage error. The last line is
 "[GATE] shared-library PASSED|FAILED exit=<n> log=<path>".
 python -m datrix_scripts.test.shared_library_gate --help describes every option.
.EXAMPLE
 .\test\shared-library-gate.ps1 -Only check_scripts_tree
#>
[CmdletBinding()]
param(
 [switch]$SelfTest, [switch]$HarnessSelfTest, [string]$Only
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.shared_library_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
