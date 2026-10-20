#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Script catalogue gate: each scripts folder's quick-reference documents its scripts and flags.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.script_catalogue_gate in the shared venv.

 Checks datrix\scripts against four rules, read from Markdown's token stream
 and from PowerShell's own parser: every .ps1 in a folder with a quick-reference.md is a ##/###
 heading of it; every -Flag written after a script's name in a code span or code line is a
 parameter (or alias) the script declares; no folder holds both a quick-reference.md and a
 README.md; every relative link in a quick-reference.md or README.md resolves.

 Prints one verdict line last: [GATE] script-catalogue PASSED|FAILED exit=<n> log=<path>.

.PARAMETER SelfTest
 Run only the gate's checks over planted folders (one defect of every rule, and a clean twin).

.PARAMETER Only
 Run only the checks whose name starts with this prefix.

.PARAMETER Dbg
 Log at DEBUG level and print the python invocation.

.EXAMPLE
 .\script-catalogue-gate.ps1

.EXAMPLE
 .\script-catalogue-gate.ps1 -SelfTest
#>

[CmdletBinding()]
param(
 [switch]$SelfTest,
 [string]$Only = "",
 [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.script_catalogue_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
