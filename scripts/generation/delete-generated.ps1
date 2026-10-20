#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rename .generated and delete the renamed tree (in a background process by default).

.DESCRIPTION
 The behaviour is datrix_scripts.generation.delete_generated. Renames <BaseDir>\.generated to
 .generated_old, or .generated_old_01 through .generated_old_99 if those names already exist, then
 removes the renamed folder. By default the removal runs in a detached process that outlives this
 session (its output in <workspace>\.tmp\delete-generated\), so the script returns right after the
 rename; use -Wait for synchronous deletion.

 Only a real directory <BaseDir>\.generated is renamed (a link or junction is refused, never
 followed), and only a real directory directly under <BaseDir> named .generated_old[_NN] is
 removed.

 Exit codes: 0 = removed, started, previewed, or nothing to do; 1 = refused by the containment
 check, no free name, or the removal failed.

.PARAMETER BaseDir
 Directory holding .generated (default: the workspace root).

.PARAMETER Wait
 Remove the renamed folder before returning.

.PARAMETER DryRun
 Print the rename and the removal; change nothing.

.PARAMETER SelfTest
 Run only the module's self-test: deletion, dry run and every containment refusal on planted
 trees, and the wrapper seam.

.EXAMPLE
 .\delete-generated.ps1

.EXAMPLE
 .\delete-generated.ps1 -Wait

.EXAMPLE
 .\delete-generated.ps1 -BaseDir D:\other\repo -DryRun
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][string]$BaseDir,
 [Parameter(ParameterSetName = "Run")][switch]$Wait,
 [Parameter(ParameterSetName = "Run")][switch]$DryRun,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.delete_generated" -Parameters $PSBoundParameters
exit $LASTEXITCODE
