#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Give tasks without an ## Orientation block one, deterministically (no writer, no model).

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.retrofit_orientation: review-list Python files the task does not
 edit become exact outline: entries, and unique cited functions become symbol: entries, each only when it
 resolves in the code index; the rewrite is written only if it parses and every entry resolves. A quality
 gate, a task that already has a block, and a task with no review list are left alone. Dry run unless
 -Apply, which copies each original to <workspace>\.tmp\retrofit-orientation\<stamp>\ first.

 Exit codes:
   0 = done
   1 = a self-test check failed
   2 = usage error (no task file, or the code index could not be opened)

.PARAMETER Task
 Task files to retrofit.

.PARAMETER Phase
 Retrofit every task of this phase, in every repository.

.PARAMETER Apply
 Write the rewritten tasks (default: a dry run).

.PARAMETER BaseDir
 The workspace root (default: this checkout's).

.PARAMETER SelfTest
 Run only the module's self-test and the wrapper seam checks.

.EXAMPLE
 .\tasks\retrofit-orientation.ps1 -Phase 61
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string[]]$Task,
 [Parameter(Position = 1, ParameterSetName = "Run")][int]$Phase,
 [Parameter(ParameterSetName = "Run")][switch]$Apply,
 [Parameter(Position = 2, ParameterSetName = "Run")][string]$BaseDir,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.retrofit_orientation" -Parameters $PSBoundParameters
exit $LASTEXITCODE
