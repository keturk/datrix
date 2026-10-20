#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Prove two concurrent runs can never be handed the same run-log file.
.DESCRIPTION
 Runs datrix_scripts.test.run_log_exclusivity_gate. A run log named from a second-granularity timestamp plus labels
 is one name for every run agreeing on them (two generate.ps1 runs once truncated and interleaved one log), so
 uniqueness comes from claiming the name: DatrixRunLog.psm1's New-DatrixRunLogFile and its Python twin
 datrix_scripts.run_log, both atomic create-or-fail. The gate holds both to it: 1 non-vacuity (a forced collision is
 seen, no false one, and both composers agree name for name), 2 sequential and 3 concurrent exclusivity (-Racers
 claims on one pinned name, default 8, 2..64), 4 label containment, 5 the wiring of datrix_scripts.dev.generate
 (the module behind generate.ps1) to claim_run_log_file. -SelfTest runs step 1
 and the wrapper seam checks and claims no file. Exit 0 every run gets its own log, 1 a check failed, 2 usage
 error. The last line is "[GATE] run-log-exclusivity PASSED|FAILED exit=<n> log=<path>".
 python -m datrix_scripts.test.run_log_exclusivity_gate --help describes every option.
.EXAMPLE
 .\test\run-log-exclusivity-gate.ps1 -SelfTest
#>
[CmdletBinding()]
param(
 [int]$Racers, [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.run_log_exclusivity_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
