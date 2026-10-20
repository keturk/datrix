#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List, delete or trim the .test_results folders of the workspace.
.DESCRIPTION
 Runs datrix_scripts.test.cleanup: lists each .test_results folder under every datrix* package, under .generated
 (a pruned walk that stops at each generated project) and under .projects (any depth), with its contents. -Force
 deletes them all after a yes/no confirmation and removes the parents left empty below -BaseDir (default: the
 workspace root); -Force -Trim keeps the 10 newest top-level items in each folder instead. An end of input at
 the confirmation deletes nothing. Exit 0 when done or cancelled, 1 when -BaseDir is not a directory.
 -SelfTest runs the module's self-test. python -m datrix_scripts.test.cleanup --help describes every option.
.EXAMPLE
 .\test\cleanup.ps1
.EXAMPLE
 .\test\cleanup.ps1 -Force -Trim
#>
[CmdletBinding()]
param(
 [string]$BaseDir, [switch]$Force, [switch]$Trim, [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.cleanup" -Parameters $PSBoundParameters
exit $LASTEXITCODE
