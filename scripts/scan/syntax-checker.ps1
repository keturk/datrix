#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Syntax Checker for Datrix .dtrx Files

.DESCRIPTION
 Validates the syntax of .dtrx files using the tree-sitter parser.
 Activates the datrix virtual environment, installs required dependencies,
 and runs syntax_checker.py. Ensures virtual environment is deactivated even
 if the script is interrupted (Ctrl-C).

.PARAMETER Path
 File or directory to check (default: all datrix repositories).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\syntax-checker.ps1
 Check all .dtrx files in all datrix repositories.

.EXAMPLE
 .\syntax-checker.ps1 path/to/file.dtrx
 Check a single file.

.EXAMPLE
 .\syntax-checker.ps1 examples/
 Check all .dtrx files in examples directory.

.EXAMPLE
 .\syntax-checker.ps1 . -Dbg
 Check with debug logging enabled.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Path = "",

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

# Default: check all datrix repositories. tree-sitter comes with the installed datrix-language package.
$pathsToCheck = if ([string]::IsNullOrEmpty($Path)) { @(Get-DatrixDirectoryPaths | Where-Object { Test-Path $_ }) } else { @($Path) }

$pythonArgs = @($pathsToCheck)
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\syntax_checker.py") -Arguments $pythonArgs)
