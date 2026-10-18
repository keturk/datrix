#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rebuild Tree-sitter Parser for Datrix DSL (PowerShell Wrapper)

.DESCRIPTION
 Runs lib\rebuild_parser.py in the shared venv, which builds through the package's own
 datrix_language.parser.tree_sitter_datrix.build and writes
 tree_sitter_datrix.<platform>.<ext> plus its staleness record into the package's build\.

.PARAMETER Force
 Rebuild even if the parser is fresh

.EXAMPLE
 .\rebuild-parser.ps1
 Rebuild the parser from grammar.js

.EXAMPLE
 .\rebuild-parser.ps1 -Force
 Force rebuild even if grammar hasn't changed
#>

[CmdletBinding()]
param(
 [switch]$Force
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Force) { $pythonArgs += "--force" }
if ($DebugPreference -ne 'SilentlyContinue') { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\rebuild_parser.py") -Arguments $pythonArgs)
