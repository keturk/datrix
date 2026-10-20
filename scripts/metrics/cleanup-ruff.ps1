#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List, and with -Force delete, the Ruff run logs metrics\ruff.ps1 writes.

.DESCRIPTION
 Runs datrix_scripts.metrics.cleanup_ruff. Lists every log file under the workspace-level
 .test-output\ruff\<project>\ folders, newest first per project ([LATEST] marks each project's newest).
 Those logs live outside every package repo on purpose: each datrix-* package is its own git
 repository, so run output created inside one is committed and pushed unless a human notices.
 With -Force it asks for a typed "yes" (end of input answers no), deletes those files and removes
 each per-project folder left empty. It runs no Ruff. Always exits 0.

.PARAMETER BaseDir
 The folder holding .test-output\ruff. Default: the workspace root.

.PARAMETER Force
 Delete the listed log files after confirmation.

.PARAMETER KeepLatest
 With -Force: keep the latest log of each project.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (planted logs, no real workspace) and exit.

.EXAMPLE
 .\scripts\metrics\cleanup-ruff.ps1
 List the logs.

.EXAMPLE
 .\scripts\metrics\cleanup-ruff.ps1 -Force -KeepLatest
 Delete every log but each project's newest.
#>

[CmdletBinding()]
param(
 [string]$BaseDir,
 [switch]$Force,
 [switch]$KeepLatest,
 [switch]$Dbg,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.cleanup_ruff" -Parameters $PSBoundParameters
exit $LASTEXITCODE
