#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rename feature tags across every tag carrier of the package test trees, from a mapping file.

.DESCRIPTION
 Runs datrix_scripts.test.retag in the shared venv. Carriers: pytest tag(...) calls (located with
 ast and rewritten at the exact literal) and fixture "@tags" header lines (.dtrx, .dcfg, .dseed).
 A rule may be scoped to named files; a tag with only scoped rules must name every file it is
 used in, or the run is refused. When the new tag is already present in the same call or header
 line, the old one is removed instead of duplicated. Preview by default (a unified diff is
 written to <workspace>\.tmp\retag\retag.diff); -Apply writes. A self-test runs first.

.PARAMETER Mapping
 The mapping JSON: {"retags": [{"from": "...", "to": "...", "paths": ["datrix-x/tests/a.py"]}]}.

.PARAMETER Apply
 Write the files. Without it, only preview.

.PARAMETER SelfTest
 Run only the self-test and the wrapper seam checks.

.EXAMPLE
 .\retag.ps1 -Mapping D:\datrix\.tmp\retags.json

.EXAMPLE
 .\retag.ps1 -Mapping D:\datrix\.tmp\retags.json -Apply
#>
[CmdletBinding()]
param(
 [string]$Mapping, [switch]$Apply, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.retag" -Parameters $PSBoundParameters
exit $LASTEXITCODE
