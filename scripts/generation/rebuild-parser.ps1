#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rebuild the Tree-sitter parser for the Datrix DSL.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.rebuild_parser, which builds through the package's own
 datrix_language.parser.tree_sitter_datrix.build and writes tree_sitter_datrix.<platform>.<ext> plus
 its staleness record into the package's build\.

.PARAMETER Force
 Rebuild even if the parser is fresh.

.PARAMETER SelfTest
 Run only the module's self-test: a grammar directory without grammar.js fails the build, and the
 wrapper seam holds.

.EXAMPLE
 .\rebuild-parser.ps1
 Rebuild the parser from grammar.js when it is stale.

.EXAMPLE
 .\rebuild-parser.ps1 -Force
 Force a rebuild even if the grammar has not changed.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][switch]$Force,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.rebuild_parser" -Parameters $PSBoundParameters
exit $LASTEXITCODE
