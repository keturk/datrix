#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Thin-entrypoint gate: every scripts .ps1 is the wrapper template rendered, with its .sh twin.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.thin_entrypoint_gate in the shared venv.

 Checks every .ps1 under datrix\scripts (the template itself excepted) against four rules, read
 with PowerShell's own parser: at most 40 lines of code (comment-based help does not count); the
 wrapper and its twin are common\templates\entrypoint.ps1 and entrypoint.sh rendered with its
 parameter block and module; a .sh twin sits beside it; PowerShell parses it. No baseline: one hit fails.

 Prints one verdict line last: [GATE] thin-entrypoint PASSED|FAILED exit=<n> log=<path>.

.PARAMETER SelfTest
 Run only the gate's checks over planted trees (one defect of every rule, and a clean twin).

.PARAMETER Only
 Run only the checks whose name starts with this prefix.

.PARAMETER Dbg
 Log at DEBUG level and print the python invocation.

.EXAMPLE
 .\thin-entrypoint-gate.ps1

.EXAMPLE
 .\thin-entrypoint-gate.ps1 -SelfTest
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.thin_entrypoint_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
