#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run a Bowler codemod on the Datrix codebase.

.DESCRIPTION
 The behaviour is datrix_scripts.codemods.run_codemod. Runs the specified numbered codemod
 recipe from scripts/codemods/lib in the shared venv. All arguments after the codemod name are
 passed through to the codemod (e.g. OLD_NAME NEW_NAME, or path list). Bowler comes from the
 "scripts" dependency group of datrix/pyproject.toml, which the shared venv installs; never
 pip-install it by hand. Only a numbered recipe in that folder runs: a name holding a path is
 refused. A recipe prints its rewrite as a diff; -Write writes it to the files instead.

 Exit codes: Bowler's own; 1 = no such recipe.

.PARAMETER CodemodName
 Name of the codemod script without .py (e.g. 01_rename_function, 02_rename_class).
 Positional.

.PARAMETER CodemodArgs
 Remaining arguments passed to the codemod (e.g. old name, new name, paths).
 ValueFromRemainingArguments.

.PARAMETER Write
 Write the rewrite to the files instead of printing its diff. Preview first.

.PARAMETER SelfTest
 Run only the module's self-test: a recipe previews and writes a planted rename, the refusals,
 and the wrapper seam.

.EXAMPLE
 .\run-codemod.ps1 01_rename_function parse_file parse_path
 Preview: rename function parse_file to parse_path (diff only).

.EXAMPLE
 .\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src
 Preview: rename class in given path.

.EXAMPLE
 .\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src
 Preview the import updates when a module is renamed.

.EXAMPLE
 .\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src -Write
 Write those import updates.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0, Mandatory = $true)][string]$CodemodName,
 [Parameter(ParameterSetName = "Run", Position = 1, ValueFromRemainingArguments = $true)][string[]]$CodemodArgs,
 [Parameter(ParameterSetName = "Run")][switch]$Write,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.codemods.run_codemod" -Parameters $PSBoundParameters
exit $LASTEXITCODE
