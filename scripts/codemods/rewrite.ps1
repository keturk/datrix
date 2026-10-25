#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rewrite one or more Datrix projects to newer, faster Python idioms with Ruff (UP, FURB, PERF).

.DESCRIPTION
 Runs datrix_scripts.codemods.rewrite for each project. For every project it runs
 "ruff check --select UP,FURB,PERF --preview" over src/ and tests/ from the project root, so the project's
 own line-length, target-version, excludes and per-file ignores apply, while its own rule selection is
 replaced for the run. Only Ruff's safe fixes are applied; a fix Ruff marks unsafe is never written.
 The default is a preview (the diff) that writes nothing; -Apply writes the fixes. A finding Ruff cannot
 fix is reported, not failed on: a project fails only when Ruff could not run on it.
 Run the project's tests afterwards (test.ps1 <pkg> -Specific / -Tag).

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Rewrite every datrix-* project that has a src/ or tests/ tree.

.PARAMETER Apply
 Write the fixes. Without it, the diff is shown and nothing is written.

.PARAMETER Exclude
 A path or glob, relative to the project root, to leave out of the run; one or more. Use it for a tree
 generated from a template and compared byte for byte against its regeneration.

.PARAMETER StopOnError
 Stop on the first project failure.

.PARAMETER SelfTest
 Run only the module's self-test (planted projects, no real workspace) and exit.

.EXAMPLE
 .\rewrite.ps1 datrix-common
 Preview the rewrites in datrix-common.

.EXAMPLE
 .\rewrite.ps1 datrix-common datrix-cli -Apply
 Write the rewrites in two projects.

.EXAMPLE
 .\rewrite.ps1 datrix-common -Apply -Exclude "src/datrix_common/datrix_model/*"
 Write the rewrites, leaving the generated model classes alone.
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [switch]$Apply,
 [string[]]$Exclude,
 [switch]$StopOnError,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.codemods.rewrite" -Parameters $PSBoundParameters
exit $LASTEXITCODE
