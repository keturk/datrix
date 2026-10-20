#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Syntax Checker for Datrix .dtrx Files

.DESCRIPTION
 The behaviour is datrix_scripts.scan.syntax_checker. Validates the syntax of .dtrx files using
 the tree-sitter parser (no ERROR or MISSING node, plus the contextual-keyword check), in the
 shared venv where datrix-language and tree-sitter are installed. .dtrx.false files
 (intentionally invalid fixtures) are skipped. Exit 0 when every file is valid, 1 otherwise.

.PARAMETER Path
 File or directory to check (default: all datrix repositories).

.PARAMETER Dbg
 Print each file checked, and log at DEBUG level.

.PARAMETER SelfTest
 Run only the module's self-test: a planted valid model passes, a planted broken one fails, a
 .dtrx.false fixture is skipped, and the wrapper seam holds.

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
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string]$Path,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.syntax_checker" -Parameters $PSBoundParameters
exit $LASTEXITCODE
