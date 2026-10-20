#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Show the git status of every repository under the workspace root.

.DESCRIPTION
 The behaviour is datrix_scripts.git.status. Each directory directly under the workspace root is
 reported on one line: "<name>: clean", "<name>: has changes" or "<name>: not a git repo". With
 -Detailed, a repository with changes also shows its branch, how many commits it is ahead of or
 behind its upstream, and its changed files (git status --short). Every git call only reads.

 Exit codes: 0 = reported (or a passing -SelfTest); 1 = a self-test check failed.

.PARAMETER Detailed
 For a repository with changes: branch, ahead/behind, and the changed files.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Report a temporary workspace of real repositories, run the census that no git script runs
 stash/reset/checkout/revert/restore, and the wrapper seam checks.

.EXAMPLE
 .\git\status.ps1

.EXAMPLE
 .\git\status.ps1 -Detailed
#>
[CmdletBinding()]
param(
 [switch]$Detailed,
 [switch]$Dbg,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.status" -Parameters $PSBoundParameters
exit $LASTEXITCODE
