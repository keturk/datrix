#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List or delete the temporary cache folders and files of the workspace.

.DESCRIPTION
 Runs datrix_scripts.workspace.cleanup_temps in the shared venv.
 Lists cache folders and files directly under -BaseDir (the workspace root by default) and at any depth
 below every datrix* project in it. Folders: .hypothesis, .ruff_cache, .ruff_check, .mypy_cache,
 .pytest_cache, htmlcov, .benchmarks, __pycache__, .tox, .nox, .cache, .pyre, .pytype, cython_debug.
 Files: .coverage, .coverage.*, coverage.xml, .dmypy.json, dmypy.json. The walk skips .git, .venv, venv,
 env, node_modules and .generated, never touches .test_results or .tasks, and never enters or deletes a
 symbolic link or junction. -Force deletes the items after a yes/no confirmation (an end of input deletes
 nothing) and removes the parents a deleted folder left empty, never at or above -BaseDir.
 Exit 0 when listed, deleted or cancelled; 1 when -BaseDir is not a directory; 2 on a usage error.

.PARAMETER BaseDir
 The directory holding the datrix* projects. Default: the workspace root.

.PARAMETER Force
 Delete the listed items after confirmation.

.PARAMETER AdditionalFolders
 More cache folder names to take. Each must be one plain name (no path separator, not . or ..).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (a planted workspace, links included) and the wrapper seam checks, and exit.

.EXAMPLE
 .\cleanup-temps.ps1

.EXAMPLE
 .\cleanup-temps.ps1 -Force -AdditionalFolders .scratch_cache
#>
[CmdletBinding()]
param(
 [string]$BaseDir, [switch]$Force, [string[]]$AdditionalFolders, [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.workspace.cleanup_temps" -Parameters $PSBoundParameters
exit $LASTEXITCODE
