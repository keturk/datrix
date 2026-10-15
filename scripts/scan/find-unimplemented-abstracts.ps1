#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Find classes that inherit abstract methods they never implement.

.DESCRIPTION
 Wraps scan\lib\find_unimplemented_abstracts.py. Imports every module of the selected
 packages (default: every datrix-* package with a src/ tree) and lists every class whose
 __abstractmethods__ is non-empty. A class that subclasses abc.ABC directly, declares an
 abstract method itself, is a typing.Protocol, or is itself subclassed is an intended
 abstract base; every other such class (a leaf meant to be concrete) is INCOMPLETE -- it
 cannot be instantiated, and nothing says so until something tries. Each missing method is printed with the base that declares it abstract.

 Exit codes: 0 = no incomplete class, 1 = incomplete class(es) found,
 2 = a module failed to import (each failure is listed) or a bad argument.

.PARAMETER Package
 Import names to scan (e.g. datrix_codegen_python). Default: every datrix-* package.

.PARAMETER ShowBases
 Also list the intended abstract bases.

.PARAMETER Dbg
 Debug logging (per-package module and class counts).

.EXAMPLE
 .\scan\find-unimplemented-abstracts.ps1
 Every incomplete class in every package.

.EXAMPLE
 .\scan\find-unimplemented-abstracts.ps1 -Package datrix_codegen_python -ShowBases
 One package, with its abstract bases.
#>

[CmdletBinding()]
param(
    [string[]]$Package = @(),
    [switch]$ShowBases,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Package = @($Package | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($name in $Package) { $pythonArgs += @("--package", $name) }
if ($ShowBases) { $pythonArgs += "--show-bases" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\find_unimplemented_abstracts.py") -Arguments $pythonArgs -RequirePackages)
