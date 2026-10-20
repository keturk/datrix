#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List Datrix projects or full paths to src/tests/docs folders.

.DESCRIPTION
 Runs datrix_scripts.workspace.projects in the shared venv.
 With no parameters, lists all Datrix project directory names (one per line).
 With -Src, prints the full path of each project's src folder (only for projects that have one).
 With -Tests, prints the full path of each project's tests folder (only for projects that have one).
 With -Docs, prints the full path of each project's docs folder (only for projects that have one).

.PARAMETER Src
 Display full paths to the src folder of each project that has one.

.PARAMETER Tests
 Display full paths to the tests folder of each project that has one.

.PARAMETER Docs
 Display full paths to the docs folder of each project that has one.

.PARAMETER SelfTest
 Run only the module's self-test (a planted workspace) and the wrapper seam checks, and exit.

.EXAMPLE
 .\projects.ps1

.EXAMPLE
 .\projects.ps1 -Src
#>
[CmdletBinding()]
param(
 [switch]$Src, [switch]$Tests, [switch]$Docs, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.workspace.projects" -Parameters $PSBoundParameters
exit $LASTEXITCODE
