#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run a Bowler codemod on the Datrix codebase.

.DESCRIPTION
 Activates the Datrix virtual environment and runs the specified codemod script
 from scripts/dev/codemods. All arguments after the codemod name are passed
 through to the codemod (e.g. OLD_NAME NEW_NAME, or path list).
 Bowler comes from the "scripts" dependency group of datrix/pyproject.toml,
 which the shared venv installs; never pip-install it by hand.

.PARAMETER CodemodName
 Name of the codemod script without .py (e.g. 01_rename_function, 02_rename_class).
 Positional.

.PARAMETER CodemodArgs
 Remaining arguments passed to the codemod (e.g. old name, new name, paths).
 ValueFromRemainingArguments.

.EXAMPLE
 .\run-codemod.ps1 01_rename_function parse_file parse_path
 Preview: rename function parse_file to parse_path (diff only).

.EXAMPLE
 .\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src
 Preview: rename class in given path.

.EXAMPLE
 .\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src
 Update imports when a module is renamed.
#>

[CmdletBinding()]
param(
 [Parameter(Mandatory = $true, Position = 0)]
 [string]$CodemodName,

 [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
 [string[]]$CodemodArgs = @()
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\run_codemod.py") -Arguments (@($CodemodName) + $CodemodArgs))
