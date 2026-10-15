#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report function bodies duplicated anywhere across the Datrix package source trees.

.DESCRIPTION
 Wraps scan\lib\find_duplicate_bodies.py. Walks every module-level function and class
 method in every datrix-* package's src/ tree, keeps those at or above the body floor
 (8 lines, 40 AST nodes) and groups them two ways:

   exact       identical bodies, every name and constant kept (a straight copy)
   normalized  identical once parameters/locals become positional tokens and constants
               collapse to their type (a renamed copy)

 This is the discovery side of gates\parity\shared-home-body-gate.ps1, which uses the
 same normalization (datrix_scripts.body_digest) but only pins copies of a PUBLIC
 shared-home function. This report also shows copies where neither side lives in a
 shared home: the hoist candidates. Report only; exit 0 unless the scan fails
 (2 = a source file did not parse, or a bad argument).

.PARAMETER CrossPackage
 Show only groups spanning two or more packages.

.PARAMETER Package
 Show only groups with a member in these packages (import names, e.g. datrix_codegen_python).

.PARAMETER Limit
 Number of groups to print (0 = all). Default: 25.

.PARAMETER JsonOut
 Also write every selected group to this JSON file. Keep it outside the package repos
 (for example under D:\datrix\.tmp\).

.PARAMETER Dbg
 Debug logging (per-package function counts).

.EXAMPLE
 .\scan\find-duplicate-bodies.ps1 -CrossPackage
 The largest cross-package duplicate groups.

.EXAMPLE
 .\scan\find-duplicate-bodies.ps1 -Package datrix_codegen_python -Limit 0
 Every group with a member in datrix-codegen-python.

.EXAMPLE
 .\scan\find-duplicate-bodies.ps1 -Limit 0 -JsonOut D:\datrix\.tmp\duplicate-bodies.json
 Every group, also as JSON.
#>

[CmdletBinding()]
param(
    [switch]$CrossPackage,
    [string[]]$Package = @(),
    [ValidateRange(0, [int]::MaxValue)]
    [int]$Limit = 25,
    [string]$JsonOut = "",
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Package = @($Package | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @("--limit", "$Limit")
if ($CrossPackage) { $pythonArgs += "--cross-package" }
foreach ($name in $Package) { $pythonArgs += @("--package", $name) }
if ($JsonOut) { $pythonArgs += @("--json-out", $JsonOut) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\find_duplicate_bodies.py") -Arguments $pythonArgs -RequirePackages)
