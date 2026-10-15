#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Split a large module into sibling modules and point every importer at the new homes.

.DESCRIPTION
 Wraps codemods\lib\split_module.py. Top-level definitions move VERBATIM (with the comments
 above them) into the new sibling modules a JSON plan names:

   {
     "_plan_sizing": {"doc": "App Service Plan SKU policy.", "range": ["SKU_MAP", "derive_size"]},
     "_plan_checks": {"doc": "SKU validation.", "names": ["validate_sku", "_tier_of"]}
   }

 "range" claims a contiguous run in source order, "names" an explicit list; "doc" is the new
 module's docstring (required, so no module inherits the original's). Each new module gets
 the original's imports, the imports of what it uses from its siblings and the original's
 module-level pytestmark. Unclaimed definitions stay in the original.

 The original does NOT re-export what moved (one import path per symbol): every
 `from <original> import <moved>` across the workspace is rewritten to the new home. The
 split refuses, writing nothing, on a double claim, an unknown name, an import cycle between
 the new modules, moved code using a name left behind, an __all__ naming a moved name, or a
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

.EXAMPLE
 .\codemods\split-module.ps1 -Module D:\datrix\datrix-codegen-azure\src\datrix_codegen_azure\generators\resource_mapping\_gateway_app_service.py -Plan D:\datrix\.tmp\split-plan.json -DryRun
 Preview the split and every import it would rewrite.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Module,
    [Parameter(Mandatory = $true)]
    [string]$Plan,
    [string]$PackageModule = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @("--module", $Module, "--plan", $Plan)
if ($PackageModule) { $pythonArgs += @("--package-module", $PackageModule) }
if ($DryRun) { $pythonArgs += "--dry-run" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\split_module.py") -Arguments $pythonArgs)
