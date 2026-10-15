#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List Datrix projects or full paths to src/tests/docs folders.

.DESCRIPTION
 With no parameters, lists all Datrix project directory names (one per line).
 With -Src, prints the full path of each project's src folder (only for projects that have one).
 With -Tests, prints the full path of each project's tests folder (only for projects that have one).
 With -Docs, prints the full path of each project's docs folder (only for projects that have one).
 Runs projects.py in the shared venv.

.PARAMETER Src
 Display full paths to the src folder of each project that has one.

.PARAMETER Tests
 Display full paths to the tests folder of each project that has one.

.PARAMETER Docs
 Display full paths to the docs folder of each project that has one.

.EXAMPLE
 .\projects.ps1
 List all Datrix projects.

.EXAMPLE
 .\projects.ps1 -Src
 List full paths to each project's src folder.

.EXAMPLE
 .\projects.ps1 -Tests
 List full paths to each project's tests folder.

.EXAMPLE
 .\projects.ps1 -Docs
 List full paths to each project's docs folder.
#>

[CmdletBinding()]
param(
 [Parameter()]
 [switch]$Src,

 [Parameter()]
 [switch]$Tests,

 [Parameter()]
 [switch]$Docs
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Src) { $pythonArgs += "--src" }
if ($Tests) { $pythonArgs += "--tests" }
if ($Docs) { $pythonArgs += "--docs" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\projects.py") -Arguments $pythonArgs)
