#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Split a large module into sibling modules and point every importer at the new homes.

.DESCRIPTION
 The behaviour is datrix_scripts.codemods.split_module. Top-level definitions move VERBATIM
 (with the comments above them) into the new sibling modules a JSON plan names:

   {
     "_plan_sizing": {"doc": "App Service Plan SKU policy.", "range": ["SKU_MAP", "derive_size"]},
     "_plan_checks": {"doc": "SKU validation.", "names": ["validate_sku", "_tier_of"]}
   }

 "range" claims a contiguous run in source order, "names" an explicit list; "doc" is the new
 module's docstring (required, so no module inherits the original's). Each new module gets
 the original's imports, the imports of what it uses from its siblings and from the original,
 and the original's module-level pytestmark. Unclaimed definitions stay in the original.

 The original does NOT re-export what moved (one import path per symbol): every
 `from <original> import <moved>` across the workspace is rewritten to the new home. The
 split refuses, writing nothing, on a double claim, an unknown name, an import cycle among
 the new modules and the original (named with the names on each edge), an __all__ naming a moved name, or a
 reference the rewrite cannot reach (a module-object attribute read, an import sharing its
 line, or the dotted path written as text in a source or pyproject.toml file). ruff
 (F401, I001) then tidies the imports of the new modules and the original.

 Exit codes: 0 = split done (or a clean -DryRun), 1 = refused (every reason printed), 2 = usage.

.PARAMETER Module
 The .py file to split.

.PARAMETER Plan
 The JSON plan file (keep it outside the package repos, e.g. under D:\datrix\.tmp\).

.PARAMETER PackageModule
 Dotted package of the module when it is not under a src/ tree (e.g. a test module:
 tests.unit.generators).

.PARAMETER DryRun
 Print the new modules, the remainder and every importer rewrite; write nothing.

.PARAMETER SelfTest
 Run only the module's self-test: a planted module is split (dry run, then for real) with its
 importer rewritten, moved code imports what stays while a cycle is refused, a bad plan is
 refused with nothing written, and the wrapper seam.

.EXAMPLE
 .\codemods\split-module.ps1 -Module D:\datrix\datrix-codegen-azure\src\datrix_codegen_azure\generators\resource_mapping\_gateway_app_service.py -Plan D:\datrix\.tmp\split-plan.json -DryRun
 Preview the split and every import it would rewrite.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Mandatory = $true)][string]$Module,
 [Parameter(ParameterSetName = "Run", Mandatory = $true)][string]$Plan,
 [Parameter(ParameterSetName = "Run")][string]$PackageModule,
 [Parameter(ParameterSetName = "Run")][switch]$DryRun,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.codemods.split_module" -Parameters $PSBoundParameters
exit $LASTEXITCODE
