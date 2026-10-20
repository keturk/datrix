#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a generator holds run state: an attribute assigned after construction,
 or a constructor that takes the run context.

.DESCRIPTION
 A generator is a function of (Application, CodegenContext, output_dir). This
 gate parses every `src/` tree of every `datrix-*` package on disk (with `ast`),
 finds every `Generator` subclass from the class graph (bases resolved through
 imports and re-exports), and fails on:

 - an assignment to an attribute of `self` (or `cls`) in any method of such a
   class other than `__init__` (plain, augmented, annotated, `for`/`with`
   targets, unpacking, `setattr`, `self.__dict__[...]`);
 - an assignment to an attribute of a name typed as such a class (a parameter
   or variable annotation, or a `for` target iterating one), anywhere;
 - a parameter of such a class's `__init__` typed `CodegenContext`.

 The terminal state is zero: there is no baseline and no allowlist. The
 non-vacuity self-test runs on every invocation before the real scan; -SelfTest
 runs only that leg.

.PARAMETER Roots
 Comma-separated source trees to scan. When omitted, scans every `datrix-*/src`
 tree on disk. The kernel's `src` must be among them, or no generator is found.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\stateless-generator-gate.ps1
 Scan every datrix-*/src tree.

.EXAMPLE
 .\stateless-generator-gate.ps1 -SelfTest
 Prove the scanner reports every planted run-state shape and nothing else.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Roots = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) {
    $pythonArgs += "--self-test"
}
elseif (-not [string]::IsNullOrWhiteSpace($Roots)) {
    $pythonArgs += "--roots"
    foreach ($item in $Roots.Split(",")) {
        $trimmed = $item.Trim()
        if (-not [string]::IsNullOrWhiteSpace($trimmed)) { $pythonArgs += $trimmed }
    }
}

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\stateless_generator.py") -Arguments $pythonArgs -Gate "stateless-generator" -ShowCommand:$Dbg)
