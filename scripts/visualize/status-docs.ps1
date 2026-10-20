#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report documentation status for Datrix projects.

.DESCRIPTION
 The behaviour is datrix_scripts.visualize.status_docs. Scans Datrix project source directories
 and reports which documentation artifacts exist: diagrams, OpenAPI specs and AsyncAPI specs.
 Supports single-file and batch modes.

 Exit codes: 0 = reported; 1 = the batch named no project; 2 = neither -Source nor a batch flag.

.PARAMETER Source
 Path to .dtrx file or directory (single project mode), relative to the workspace root.

.PARAMETER All
 Check all projects from test-projects.json.

.PARAMETER Domains
 Domain examples only.

.PARAMETER TestSet
 Named test set from test-projects.json (default: all).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: a planted project's docs are reported, the refusals, and the
 wrapper seam.

.EXAMPLE
 .\status-docs.ps1 datrix\examples\02-domains\ecommerce\system.dtrx
 Report docs status for the ecommerce example.

.EXAMPLE
 .\status-docs.ps1 -All
 Report docs status for all projects.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0)][string]$Source,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Domains,
 [Parameter(ParameterSetName = "Run")][string]$TestSet,
 [Parameter(ParameterSetName = "Run")][switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.visualize.status_docs" -Parameters $PSBoundParameters
exit $LASTEXITCODE
