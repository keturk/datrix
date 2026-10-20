#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Show which runtime import chain first loads a module.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.who_imports. Imports each -Root module in a fresh
 interpreter with an observer on sys.meta_path; the first time a -Target module (or any
 submodule of a target package) is looked up, it prints the chain of workspace frames that led
 there -- the import statement, function-level ones included, that pulled the target in. The
 observer resolves nothing itself, so imports behave as without it. The editable installs are
 checked first.

 scan\check-import-boundaries.ps1 reports that a forbidden edge exists (statically); this
 shows which chain realizes it at runtime.

 Exit codes: 0 = every root imported (a target that never loaded is listed as such),
 1 = the package install check failed, 2 = a root failed to import (its error is printed).

.PARAMETER Root
 Modules to import (required, one or more; comma-separated or repeated).

.PARAMETER Target
 Modules or packages to watch (required, one or more; comma-separated or repeated).

.PARAMETER SelfTest
 Run only the module's self-test: a planted chain is traced, and the wrapper seam holds.

.EXAMPLE
 .\dev\who-imports.ps1 -Root datrix_codegen_kernel.dgen -Target datrix_codegen_common
 Does the kernel's DAL generator load the language layer, and through which import?
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, ParameterSetName = "Run")][string[]]$Root,
 [Parameter(Mandatory = $true, ParameterSetName = "Run")][string[]]$Target,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.who_imports" -Parameters $PSBoundParameters
exit $LASTEXITCODE
