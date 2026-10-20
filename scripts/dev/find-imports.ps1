#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List every place that imports names from given modules: the worklist before a move or rename.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.find_imports. AST-parses every .py file under each datrix-*
 repository's src/ and tests/ trees, its root-level *.py files, the scripts tree and the Claude
 Code hooks, and prints path:line for:

   [from-import]    from M import N            (relative imports in src/ resolved first)
   [import]         import M / import M as m   (only without -Name)
   [module-import]  from P import M            (only without -Name)
   [attribute]      m.N on a name bound to M   (only with -Name)

 The code index's find_references resolves symbols; this answers the different question
 "which import statements name this module path", and it needs no index. A file that does
 not parse is printed as UNPARSEABLE and counted. Report only: exit 0.

.PARAMETER Module
 Dotted target modules (required, one or more; comma-separated or repeated).

.PARAMETER Name
 Narrow to these imported names.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: a planted import is found, and the wrapper seam holds.

.EXAMPLE
 .\dev\find-imports.ps1 -Module datrix_common.errors.plugin -Name PluginError
 Every import of PluginError from datrix_common.errors.plugin, and every errors_plugin.PluginError read.

.EXAMPLE
 .\dev\find-imports.ps1 -Module datrix_codegen_common.transpiler.base
 Everything imported from the module, and every place that imports the module itself.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, ParameterSetName = "Run")][string[]]$Module,
 [Parameter(ParameterSetName = "Run")][string[]]$Name,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.find_imports" -Parameters $PSBoundParameters
exit $LASTEXITCODE
