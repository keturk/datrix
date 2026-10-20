#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Validate task files against the tree as it is now, before they are dispatched.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.validate_task: the ## Orientation block parses and every entry
 resolves (a symbol or refs the code index finds, an outline of a file that exists, an explain over
 files a local model may read), the task is not oversized, and every path:line citation still points
 at a file that exists and lines that are in it, with the identifiers quoted beside it near those lines.

 Exit codes:
   0 = no errors (and, with -Strict, no warnings)
   1 = errors found (or a self-test check failed)
   2 = usage error (no task file)

.PARAMETER Task
 Task files to validate.

.PARAMETER Phase
 Validate every task of this phase, in every repository.

.PARAMETER Strict
 Warnings (moved lines) fail the run too.

.PARAMETER RequireOrientation
 A task with no ## Orientation block is an error.

.PARAMETER BaseDir
 The workspace root (default: this checkout's).

.PARAMETER SelfTest
 Run only the module's self-test and the wrapper seam checks.

.EXAMPLE
 .\tasks\validate-task.ps1 -Phase 61 -RequireOrientation
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string[]]$Task,
 [Parameter(Position = 1, ParameterSetName = "Run")][int]$Phase,
 [Parameter(ParameterSetName = "Run")][switch]$Strict,
 [Parameter(ParameterSetName = "Run")][switch]$RequireOrientation,
 [Parameter(Position = 2, ParameterSetName = "Run")][string]$BaseDir,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.validate_task" -Parameters $PSBoundParameters
exit $LASTEXITCODE
