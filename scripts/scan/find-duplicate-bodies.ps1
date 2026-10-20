#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report function bodies duplicated anywhere across the Datrix package source trees.

.DESCRIPTION
 The behaviour is datrix_scripts.scan.find_duplicate_bodies; the editable installs are
 checked first. Walks every module-level function and class method in every datrix-*
 package's src/ tree, keeps those at or above the body floor (8 lines, 40 AST nodes) and
 groups them two ways:

   exact       identical bodies, every name and constant kept (a straight copy)
   normalized  identical once parameters/locals become positional tokens and constants
               collapse to their type (a renamed copy)

 This is the discovery side of gates\parity\shared-home-body-gate.ps1, which uses the
 same normalization (datrix_scripts.body_digest) but only pins copies of a PUBLIC
 shared-home function. This report also shows copies where neither side lives in a
 shared home: the hoist candidates. Report only; exit 0 unless the scan fails
 (2 = a source file did not parse, or a bad argument; 1 = the package install check failed).

.PARAMETER CrossPackage
 Show only groups spanning two or more packages.

.PARAMETER Package
 Show only groups with a member in these packages (import names, e.g. datrix_codegen_python).
 A list or one comma-separated value.

.PARAMETER Limit
 Number of groups to print (0 = all). Default: 25.

.PARAMETER JsonOut
 Also write every selected group to this JSON file. Keep it outside the package repos
 (for example under D:\datrix\.tmp\).

.PARAMETER Dbg
 Debug logging (per-package function counts).

.PARAMETER SelfTest
 Run only the module's self-test (a planted copy and a planted renamed copy are grouped,
 -Package and -CrossPackage select, a negative -Limit is refused, the wrapper seam holds).

.EXAMPLE
 .\scan\find-duplicate-bodies.ps1 -CrossPackage
 The largest cross-package duplicate groups.

.EXAMPLE
 .\scan\find-duplicate-bodies.ps1 -Package datrix_codegen_python -Limit 0
 Every group with a member in datrix-codegen-python.

.EXAMPLE
 .\scan\find-duplicate-bodies.ps1 -Limit 0 -JsonOut D:\datrix\.tmp\duplicate-bodies.json
 Every group, also as JSON.

.EXAMPLE
 .\scan\find-duplicate-bodies.ps1 -SelfTest
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(ParameterSetName = "Run")][switch]$CrossPackage,
    [Parameter(ParameterSetName = "Run")][string[]]$Package,
    [Parameter(ParameterSetName = "Run")][ValidateRange(0, [int]::MaxValue)][int]$Limit,
    [Parameter(ParameterSetName = "Run")][string]$JsonOut,
    [Parameter(ParameterSetName = "Run")][switch]$Dbg,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.find_duplicate_bodies" -Parameters $PSBoundParameters
exit $LASTEXITCODE
