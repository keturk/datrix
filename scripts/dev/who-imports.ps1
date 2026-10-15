#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Show which runtime import chain first loads a module.

.DESCRIPTION
 Wraps dev\lib\who_imports.py. Imports each -Root module in a fresh interpreter with an
 observer on sys.meta_path; the first time a -Target module (or any submodule of a target
 package) is looked up, it prints the chain of workspace frames that led there -- the
 import statement, function-level ones included, that pulled the target in. The observer
 resolves nothing itself, so imports behave as without it.

 scan\check-import-boundaries.ps1 reports that a forbidden edge exists (statically); this
 shows which chain realizes it at runtime.

 Exit codes: 0 = every root imported (a target that never loaded is listed as such),
 2 = a root failed to import (its error is printed).

.PARAMETER Root
 Modules to import (required, one or more).

.PARAMETER Target
 Modules or packages to watch (required, one or more).

.EXAMPLE
 .\dev\who-imports.ps1 -Root datrix_codegen_kernel.dgen -Target datrix_codegen_common
 Does the kernel's DAL generator load the language layer, and through which import?
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Root,
    [Parameter(Mandatory = $true)]
    [string[]]$Target
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Root = @($Root | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Target = @($Target | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($item in $Root) { $pythonArgs += @("--root", $item) }
foreach ($item in $Target) { $pythonArgs += @("--target", $item) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\who_imports.py") -Arguments $pythonArgs -RequirePackages)
