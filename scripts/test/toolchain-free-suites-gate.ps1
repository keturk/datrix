#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a framework test suite compiles or executes generated output.
.DESCRIPTION
 Runs datrix_scripts.test.toolchain_free_suites. A datrix-*/tests/ suite proves that the generator emits the right
 thing; whether the emitted output compiles and runs belongs to the generated project's own tests and the deploy
 tests. Four shapes fail: a toolchain subprocess (javac, dotnet, tsc, npm, node, docker, az, ...), in-process
 execution of a rendered template (exec(compile(...)), runpy, importlib exec_module), a nested pytest session over a
 repo test path, and a subprocess running a datrix/scripts/ script. pytester synthetic suites, linters over generated
 text and runs of datrix itself stay allowed. Every run first proves the detector non-vacuous.
 -Suites (comma-separated tests/ directories; default every package suite) and -Shapes (comma-separated kinds;
 default all) narrow the scan; a path that is not a directory or an unknown kind is a usage error. -SelfTest runs
 only the detector proof and the wrapper seam checks. Exit 0 pass, 1 violations, 2 usage error. The last line is
 "[GATE] toolchain-free-suites PASSED|FAILED exit=<n> log=<path>".
 python -m datrix_scripts.test.toolchain_free_suites --help describes every option.
.EXAMPLE
 .\test\toolchain-free-suites-gate.ps1 -Shapes suite-in-suite-pytest,suite-in-suite-script
#>
[CmdletBinding()]
param(
 [string]$Suites, [string]$Shapes, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.toolchain_free_suites" -Parameters $PSBoundParameters
exit $LASTEXITCODE
