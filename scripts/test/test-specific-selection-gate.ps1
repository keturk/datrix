#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Prove that `test.ps1 <package> -Specific <file>` runs ONLY that file's tests.
.DESCRIPTION
 Runs datrix_scripts.test.test_specific_selection_gate. A -Specific run that reports PASSED while its own
 index.json / JUnit XML describe a different file's tests is a silent false green (two same-second test.ps1 runs
 once shared one run directory). Checks: 1 non-vacuity (a wrong-file run directory is rejected, a correct one
 accepted), 2 a real -Specific <FileA> run names only FileA, 3 a two-file run names only those files, 4 run-
 directory exclusivity under a pinned timestamp, 5 two concurrent -Specific runs get distinct directories.
 -Package (default datrix-codegen-python), -FileA, -FileB (package-relative) choose the files. -SelfTest runs only
 the non-vacuity proof and the wrapper seam checks (no test.ps1 run); -HarnessSelfTest runs only the harness
 self-test. Exit 0 pass, 1 a check failed, 2 usage error (test.ps1 or a named file not found). The last line is
 "[GATE] test-specific-selection PASSED|FAILED exit=<n> log=<path>".
 python -m datrix_scripts.test.test_specific_selection_gate --help describes every option.
.EXAMPLE
 .\test\test-specific-selection-gate.ps1 -SelfTest
#>
[CmdletBinding()]
param(
 [string]$Package, [string]$FileA, [string]$FileB, [switch]$SelfTest, [switch]$HarnessSelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.test_specific_selection_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
