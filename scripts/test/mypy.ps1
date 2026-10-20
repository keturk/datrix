#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run mypy for Datrix projects.
.DESCRIPTION
 Runs datrix_scripts.test.mypy_check for the projects named (-Projects, names or folder paths) or every datrix-*
 package with a pyproject.toml (-All); the datrix showcase repo may be named but is never swept. -Specific names
 files, directories or comma-separated targets; -VerboseOutput shows error context; -NoSave writes no log. The
 test.ps1 switches (-Coverage, -NoAutoInstall, -Unit, -Integration, -E2E, -Fast, -Slow, -Keyword) are accepted
 for symmetry and ignored. mypy's cache goes under <workspace>\.tmp\mypy-cache, never into a package repository.

 A human-only tool: no skill, hook, orchestrator or other script invokes it (its only caller is affected-gate's
 opt-in -Mypy switch), and the agent contract forbids agents to run any standalone type-checker. That is
 enforced: guard-forbidden-commands.py refuses this wrapper, its .sh twin, the module, the mypy/dmypy/pyright
 binaries, `python -m mypy` and affected-gate -Mypy from any agent tool call, except -SelfTest, which installs,
 launches and caches nothing. The package test suites are the declared gate for type correctness.
 Exit 0 passed or skipped, 1 a project failed (or selection/install/self-test failure), 2 usage error.
 python -m datrix_scripts.test.mypy_check --help describes every option.
.EXAMPLE
 .\test\mypy.ps1 datrix-common -Specific "src\datrix_common\builtins"
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$Projects,
 [switch]$All, [switch]$Coverage, [switch]$VerboseOutput, [switch]$NoSave, [switch]$NoAutoInstall,
 [switch]$Unit, [switch]$Integration, [switch]$E2E, [switch]$Fast, [switch]$Slow,
 [string]$Specific, [string]$Keyword, [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.mypy_check" -Parameters $PSBoundParameters
exit $LASTEXITCODE
