#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Self-test for the derived venv install order (datrix_scripts.install_order's topological sort).
.PARAMETER SelfTest
 Run only install_order.py's self-test and exit. Does not scan the real workspace.
.EXAMPLE
 .\venv-install-order.ps1 -SelfTest
#>
[CmdletBinding()]
param(
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.install_order" -Parameters $PSBoundParameters
exit $LASTEXITCODE
