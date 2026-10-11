#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Self-test for the [dev] extra specs the shared venv installs (datrix_scripts.dev_specs).

.DESCRIPTION
 A package's [dev] extra may name a sibling workspace package by direct URL
 ("datrix-extensions @ file:../datrix-extensions"). Installing that URL into the
 shared venv replaces the sibling's editable install with a frozen copy;
 dev_specs names such a sibling by its bare name instead.

.PARAMETER SelfTest
 Run only dev_specs.py's self-test and exit. Does not read the real workspace.

.EXAMPLE
 .\venv-dev-specs.ps1 -SelfTest
 Run the dev-spec rewrite self-test.
#>

[CmdletBinding()]
param(
 [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

if (-not $SelfTest) {
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\venv-dev-specs.ps1 -SelfTest" -ForegroundColor White
 exit 1
}

. (Join-Path $PSScriptRoot "venv.ps1")

# --self-test imports no datrix-* package (stdlib tomllib only), so this wrapper
# needs only the shared scripts package on PYTHONPATH, not the venv.
Set-DatrixPythonPath
& python -m datrix_scripts.dev_specs --self-test
exit $LASTEXITCODE
