#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Find classes that inherit abstract methods they never implement.

.DESCRIPTION
 The behaviour is datrix_scripts.scan.find_unimplemented_abstracts; the editable installs
 are checked first. Imports every module of the selected packages (default: every datrix-*
 package with a src/ tree) and lists every class whose __abstractmethods__ is non-empty. A
 class that subclasses abc.ABC directly, declares an abstract method itself, is a
 typing.Protocol, or is itself subclassed is an intended abstract base; every other such
 class (a leaf meant to be concrete) is INCOMPLETE -- it cannot be instantiated, and nothing
 says so until something tries. Each missing method is printed with the base that declares
 it abstract.

 Exit codes: 0 = no incomplete class, 1 = incomplete class(es) found or the package install
 check failed, 2 = a module failed to import (each failure is listed) or a bad argument.

.PARAMETER Package
 Import names to scan (e.g. datrix_codegen_python). A list or one comma-separated value.
 Default: every datrix-* package.

.PARAMETER ShowBases
 Also list the intended abstract bases.

.PARAMETER Dbg
 Debug logging (per-package module and class counts).

.PARAMETER SelfTest
 Run only the module's self-test (a planted incomplete leaf exits 1 while its bases are
 intended, a planted import failure exits 2, an unknown package is refused, the wrapper
 seam holds).

.EXAMPLE
 .\scan\find-unimplemented-abstracts.ps1
 Every incomplete class in every package.

.EXAMPLE
 .\scan\find-unimplemented-abstracts.ps1 -Package datrix_codegen_python -ShowBases
 One package, with its abstract bases.

.EXAMPLE
 .\scan\find-unimplemented-abstracts.ps1 -SelfTest
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(ParameterSetName = "Run")][string[]]$Package,
    [Parameter(ParameterSetName = "Run")][switch]$ShowBases,
    [Parameter(ParameterSetName = "Run")][switch]$Dbg,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.find_unimplemented_abstracts" -Parameters $PSBoundParameters
exit $LASTEXITCODE
