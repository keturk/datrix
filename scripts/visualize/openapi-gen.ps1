#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Generate OpenAPI and AsyncAPI specs from .dtrx source files.

.DESCRIPTION
 The behaviour is datrix_scripts.visualize.openapi_gen. Parses .dtrx files and produces one
 OpenAPI 3.1 YAML per service (every rest_api block of the service) and one AsyncAPI 3.0 YAML per
 service (every pubsub block of the service). Clears only docs/openapi and docs/asyncapi.
 Supports single-file and batch modes.

 Exit codes: 0 = every project's specs were built; 1 = a project failed, or the batch named no
 project; 2 = neither -Source nor a batch flag.

.PARAMETER Source
 Path to .dtrx file or directory (single mode), relative to the workspace root.

.PARAMETER All
 Generate for all projects from test-projects.json.

.PARAMETER Domains
 Domain examples only.

.PARAMETER TestSet
 Named test set from test-projects.json (default: all).

.PARAMETER Type
 Spec type: openapi, asyncapi, or all (default: all).

.PARAMETER Profile
 Config profile to resolve (default: test).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: specs of a planted example, the refusals, and the wrapper seam.

.EXAMPLE
 .\openapi-gen.ps1 datrix\examples\02-domains\ecommerce\system.dtrx
 Generate OpenAPI and AsyncAPI specs for the ecommerce example.

.EXAMPLE
 .\openapi-gen.ps1 -All -Type openapi
 Generate only OpenAPI specs for all projects.

.EXAMPLE
 .\openapi-gen.ps1 -Domains -Type asyncapi
 Generate only AsyncAPI specs for domain examples.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0)][string]$Source,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Domains,
 [Parameter(ParameterSetName = "Run")][string]$TestSet,
 [Parameter(ParameterSetName = "Run")][ValidateSet("openapi", "asyncapi", "all")][string]$Type,
 [Parameter(ParameterSetName = "Run")][string]$Profile,
 [Parameter(ParameterSetName = "Run")][switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.visualize.openapi_gen" -Parameters $PSBoundParameters
exit $LASTEXITCODE
