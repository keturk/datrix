#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run a single test file or pattern quickly for checkpoint-based debugging.

.DESCRIPTION
 Runs datrix_scripts.test.test_single: pytest, in the shared venv, against a specific test file, test class, or
 test function, in the project that owns it. Designed for the fix-one-verify-one workflow where you need fast
 feedback on a single fix. Unlike test.ps1, which orchestrates project test runs, it runs exactly what you
 specify with minimal overhead. python -m datrix_scripts.test.test_single --help describes every option.

 Exit codes:
   0 = tests passed
   1 = tests failed
   2 = usage error

.PARAMETER TestPath
 Path to the test file, or a pytest node ID (file::class::method). Can be:
   - Full path: D:\datrix\datrix-codegen-python\tests\test_entity.py
   - Relative path: tests\test_entity.py (resolved against Project)
   - Node ID: tests/test_entity.py::TestEntityGen::test_basic

.PARAMETER Project
 Project context for resolving relative paths. Defaults to auto-detect from TestPath.

.PARAMETER Keyword
 Pytest -k filter expression (e.g., "test_enum and not test_enum_import").

.PARAMETER Marker
 Pytest -m marker filter (e.g., "not slow").

.PARAMETER VerboseOutput
 Show full pytest output (default: quiet mode with failure details only).

.PARAMETER FailFast
 Stop on first failure (-x flag).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run the module's self-test.

.EXAMPLE
 .\test-single.ps1 "D:\datrix\datrix-codegen-python\tests\generators\test_entity_generator.py"
 Run all tests in a specific file.

.EXAMPLE
 .\test-single.ps1 "tests/generators/test_entity_generator.py::TestEntityGenerator::test_basic" -Project datrix-codegen-python
 Run a single test method.

.EXAMPLE
 .\test-single.ps1 -Project datrix-common -Keyword "test_poly_string"
 Run tests matching a keyword in a project.

.EXAMPLE
 .\test-single.ps1 "tests/test_enum.py" -Project datrix-codegen-typescript -FailFast
 Run tests in a file, stop on first failure.
#>
[CmdletBinding()]
param(
 [Parameter(Position=0)][string]$TestPath, [string]$Project, [string]$Keyword, [string]$Marker,
 [switch]$VerboseOutput, [switch]$FailFast, [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.test_single" -Parameters $PSBoundParameters
exit $LASTEXITCODE
