#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Count files with one or more extensions in subfolders of every datrix directory.

.DESCRIPTION
 Runs datrix_scripts.workspace.file_count in the shared venv.
 Counts the files whose name ends with each given extension under every datrix repository (the datrix
 showcase repo plus every datrix-* package directory in the workspace, discovered from disk), one column
 per extension. A file is counted under an extension only when its name ends with it, so "x.dtrx.false"
 counts as dtrx.false, never as dtrx. Hidden files and folders are left out and no link is entered.

.PARAMETER Extension
 The file extensions to count (without the leading dot), one or more, comma-separated. Defaults to "j2".

.PARAMETER SelfTest
 Run only the module's self-test (a planted workspace) and the wrapper seam checks, and exit.

.EXAMPLE
 .\file-count.ps1
 Count .j2 files in all directories (default).

.EXAMPLE
 .\file-count.ps1 py
 Count .py files in all directories.

.EXAMPLE
 .\file-count.ps1 -Extension dtrx,dtrx.false
 Count .dtrx and .dtrx.false files, one column each.
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0)]
 [string[]]$Extension,

 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.workspace.file_count" -Parameters $PSBoundParameters
exit $LASTEXITCODE
