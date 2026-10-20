#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Print the tree-sitter parse tree of Datrix source as a corpus-style S-expression.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.print_sexp. Parses with the built Datrix grammar (the same
 compiled parser datrix-language loads; the native tree-sitter CLI cannot load that library on
 every host) and prints the tree in tree-sitter corpus layout -- two-space indent, closing
 parentheses on the last child's line -- ready to paste into a corpus test as the expected tree.
 The editable installs are checked first.

 Named nodes only by default; -All also prints anonymous nodes (keywords, punctuation) as
 quoted text. MISSING nodes print as (MISSING <type>).

 Exit codes: 0 = no error in the tree, 1 = ERROR or MISSING nodes present (tree still
 printed), 2 = the input could not be read.

.PARAMETER Path
 A .dtrx file.

.PARAMETER Text
 Datrix source given inline instead of a file.

.PARAMETER All
 Also print anonymous nodes.

.PARAMETER SelfTest
 Run only the module's self-test: a parse error and an unreadable file exit as documented, and the
 wrapper seam holds.

.EXAMPLE
 .\dev\print-sexp.ps1 examples\01-foundation\system.dtrx

.EXAMPLE
 .\dev\print-sexp.ps1 -Text 'enum Status { Active, Inactive }' -All
#>
[CmdletBinding(DefaultParameterSetName = "File")]
param(
 [Parameter(ParameterSetName = "File", Position = 0, Mandatory = $true)][string]$Path,
 [Parameter(ParameterSetName = "Text", Mandatory = $true)][string]$Text,
 [Parameter(ParameterSetName = "File")][Parameter(ParameterSetName = "Text")][switch]$All,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.print_sexp" -Parameters $PSBoundParameters
exit $LASTEXITCODE
