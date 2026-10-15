#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Source comment-reference gate.

.DESCRIPTION
 Every module a comment or docstring in a framework package's src/ tree cites
 must exist. Dotted datrix_* references resolve through importlib. A bare or
 relative file citation (foo.py, a/b/foo.py) must name a .py file of the citing
 package or of a package in its runtime dependency closure, or a file the
 generators emit; a module of any other package is cited by its anchored path
 (datrix-<package>/src/...) or dotted import path, which must resolve.

 Packages, dependencies and emitted file names are read from disk at run time,
 never from a hand-written list. No baseline and no exemption file: the
 terminal state is zero.

 Runs a built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\source-comment-reference-gate.ps1
 Scan every framework package's src/ comments and docstrings.

.EXAMPLE
 .\source-comment-reference-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\source_comment_references.py") -Arguments $pythonArgs -RequirePackages -Gate "source-comment-reference")
