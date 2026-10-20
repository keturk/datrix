#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate for the test runner's pytest plugin (datrix_scripts.runner_plugin).
.DESCRIPTION
 Runs datrix_scripts.test.runner_plugin_gate, which spawns real, separate pytest sessions
 (python -m pytest -p datrix_scripts.runner_plugin ...) against temporary fixture suites and checks the record
 files each writes: records never leak file contents, environment values or arguments; they hold exactly the
 observed, deselected and timing facts the session produced; a missing or malformed required environment
 variable is a usage error that names it; records are named for their worker and are never overwritten.
 -Only runs the checks whose name starts with a prefix. -HarnessSelfTest proves the pass/fail harness reports a
 deliberately failing check; -SelfTest runs it and the wrapper seam checks. Exit 0 every check passed, 1 a check
 failed, 2 usage error. The last line is "[GATE] runner-plugin PASSED|FAILED exit=<n> log=<path>".
 python -m datrix_scripts.test.runner_plugin_gate --help describes every option.
.EXAMPLE
 .\test\runner-plugin-gate.ps1 -HarnessSelfTest
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.runner_plugin_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
