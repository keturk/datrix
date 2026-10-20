#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Census every whole-suite test.ps1/affected-gate.ps1 form in agent-facing instruction documents.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.instruction_surface_gate in the shared venv.

 Scans
 claude-config/.claude/CLAUDE.md, rules/*.md and skills/**/*.md for a bare
 test.ps1 form (no -Specific/-Keyword), -All, -Rerun, or an unqualified tier
 switch, outside a <!-- forbidden-example --> context. A plain-Python self-test
 suite runs automatically, unconditionally, as step 1 of every invocation.

.PARAMETER SelfTest
 Run only the scanner's own self-test suite and exit -- skips the real census.

.PARAMETER Dbg
 Enable DEBUG logging.

.EXAMPLE
 .\instruction-surface-gate.ps1

.EXAMPLE
 .\instruction-surface-gate.ps1 -SelfTest
#>

[CmdletBinding()]
param(
    [switch]$SelfTest,
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.instruction_surface_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
