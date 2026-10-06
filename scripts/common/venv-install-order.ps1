#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Self-test for the derived venv install order (Get-DatrixPackages' topological sort).

.PARAMETER SelfTest
 Run only install_order.py's self-test and exit. Does not scan the real workspace.

.EXAMPLE
 .\venv-install-order.ps1 -SelfTest
 Run only the topological-sort self-test.
#>

[CmdletBinding()]
param(
 [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

if (-not $SelfTest) {
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\venv-install-order.ps1 -SelfTest" -ForegroundColor White
 exit 1
}

. (Join-Path $PSScriptRoot "venv.ps1")

# --self-test needs no venv (no import of any datrix-* package, only stdlib
# tomllib), so this wrapper deliberately does NOT call Ensure-DatrixVenv -- it
# runs against bare `python` on PATH, matching install_order.py's own
# no-venv-required self-test contract. It only needs the shared scripts package
# (common\lib\datrix_scripts) on PYTHONPATH.
Set-DatrixPythonPath
& python -m datrix_scripts.install_order --self-test
exit $LASTEXITCODE
