#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List every place that imports names from given modules: the worklist before a move or rename.

.DESCRIPTION
 Wraps dev\lib\find_imports.py. AST-parses every .py file under each datrix-* repository's
 src/ and tests/ trees, its root-level *.py files, the scripts tree and the Claude Code hooks,
 and prints path:line for:

   [from-import]    from M import N            (relative imports in src/ resolved first)
   [import]         import M / import M as m   (only without -Name)
   [module-import]  from P import M            (only without -Name)
   [attribute]      m.N on a name bound to M   (only with -Name)

 The code index's find_references resolves symbols; this answers the different question
 "which import statements name this module path", and it needs no index. A file that does
 not parse is printed as UNPARSEABLE and counted. Report only: exit 0.

.PARAMETER Module
 Dotted target modules (required, one or more).

.PARAMETER Name
 Narrow to these imported names.

.PARAMETER Dbg
 Debug logging.

.EXAMPLE
 .\dev\find-imports.ps1 -Module datrix_common.errors.plugin -Name PluginError
 Every import of PluginError from datrix_common.errors.plugin, and every errors_plugin.PluginError read.

.EXAMPLE
 .\dev\find-imports.ps1 -Module datrix_codegen_common.transpiler.base
 Everything imported from the module, and every place that imports the module itself.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Module,
    [string[]]$Name = @(),
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Module = @($Module | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Name = @($Name | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($item in $Module) { $pythonArgs += @("--module", $item) }
foreach ($item in $Name) { $pythonArgs += @("--name", $item) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\find_imports.py") -Arguments $pythonArgs)
