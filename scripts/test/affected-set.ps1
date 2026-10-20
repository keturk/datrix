#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Derive the reverse-dependency closure of Datrix packages from actual imports.
.DESCRIPTION
 Runs datrix_scripts.affected_set (shared with the suite stamp and the affected gate). Discovers every datrix-*
 package from disk, builds the import graph from each package's src/, tests/ and root conftest.py plus its declared
 pyproject.toml dependencies, and prints the reverse-dependency closure of each package named (-Projects) or of
 every package (-All). Writes affected-set.json to <workspace>\.tmp\test\ unless -Output names a path. The
 scanner's self-test runs first on every invocation; -SelfTest runs only it. Exit 0 done, 1 self-check failed,
 2 usage error. python -m datrix_scripts.affected_set --help describes every option.
.EXAMPLE
 .\test\affected-set.ps1 -Projects datrix-language
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$Projects,
 [switch]$All, [string]$Output, [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.affected_set" -Parameters $PSBoundParameters
exit $LASTEXITCODE
