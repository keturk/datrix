#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List or delete the empty folders at and below a path.

.DESCRIPTION
 Runs datrix_scripts.workspace.empty_folders in the shared venv.
 A folder is empty when it holds no entry at all, hidden ones included. The search starts at -Path (the
 current directory by default; listed too when empty) and never enters a hidden folder or a symbolic link
 or junction. Folders are listed deepest first. -Force deletes them after a yes/no confirmation (an end of
 input deletes nothing), checking each again before removing it; nothing outside -Path is touched.
 Exit 0 when listed, deleted or cancelled; 1 when -Path does not exist, is not a directory or is a link.

.PARAMETER Path
 The folder to search. Default: the current directory.

.PARAMETER Force
 Delete the listed folders after confirmation.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (planted trees, links included) and the wrapper seam checks, and exit.

.EXAMPLE
 .\empty-folders.ps1 -Path D:\datrix

.EXAMPLE
 .\empty-folders.ps1 -Path D:\datrix -Force
#>
[CmdletBinding()]
param(
 [string]$Path, [switch]$Force, [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.workspace.empty_folders" -Parameters $PSBoundParameters
exit $LASTEXITCODE
