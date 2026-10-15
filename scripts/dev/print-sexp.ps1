#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Print the tree-sitter parse tree of Datrix source as a corpus-style S-expression.

.DESCRIPTION
 Wraps dev\lib\print_sexp.py. Parses with the built Datrix grammar (the same compiled parser
 datrix-language loads; the native tree-sitter CLI cannot load that library on every host)
 and prints the tree in tree-sitter corpus layout -- two-space indent, closing parentheses on
 the last child's line -- ready to paste into a corpus test as the expected tree.

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

.EXAMPLE
 .\dev\print-sexp.ps1 examples\01-foundation\system.dtrx

.EXAMPLE
 .\dev\print-sexp.ps1 -Text 'enum Status { Active, Inactive }' -All
#>

[CmdletBinding(DefaultParameterSetName = "File")]
param(
    [Parameter(ParameterSetName = "File", Position = 0, Mandatory = $true)]
    [string]$Path,
    [Parameter(ParameterSetName = "Text", Mandatory = $true)]
    [string]$Text,
    [switch]$All
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = if ($PSCmdlet.ParameterSetName -eq "Text") { @("--text", $Text) } else { @($Path) }
if ($All) { $pythonArgs += "--all" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\print_sexp.py") -Arguments $pythonArgs -RequirePackages)
