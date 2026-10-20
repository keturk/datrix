#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Generate Mermaid and SVG diagrams from .dtrx source files.

.DESCRIPTION
 The behaviour is datrix_scripts.visualize.visualize. Parses .dtrx files and produces diagrams
 (ERD, service map, event flow, API catalog, CQRS flow, inheritance tree, infrastructure
 topology, system context) into <project>\docs\diagrams\. Supports single-file and batch modes.

 Exit codes: 0 = every project loaded; 1 = a project failed to load, or the batch named no
 project; 2 = neither -Source nor a batch flag.

.PARAMETER Source
 Path to .dtrx file or directory (single mode), relative to the current directory.

.PARAMETER All
 Generate for all projects from test-projects.json.

.PARAMETER Domains
 Domain examples only.

.PARAMETER TestSet
 Named test set from test-projects.json (default: all).

.PARAMETER Type
 Diagram type: erd, service-map, event-flow, api-catalog, cqrs-flow,
 inheritance, infrastructure, system-context, or all (default: all).

.PARAMETER Service
 Scope to a single service name.

.PARAMETER Format
 Output format: md or mmd (default: md).

.PARAMETER Profile
 Config profile to resolve (default: test).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: diagrams of a planted example, the refusals, and the wrapper
 seam.

.EXAMPLE
 .\visualize.ps1 examples\02-domains\ecommerce\system.dtrx -Type all
 Generate all diagram types for the ecommerce example.

.EXAMPLE
 .\visualize.ps1 -All -Type erd
 Generate ERD diagrams for all projects.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0)][string]$Source,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Domains,
 [Parameter(ParameterSetName = "Run")][string]$TestSet,
 [Parameter(ParameterSetName = "Run")][ValidateSet("erd", "service-map", "event-flow", "api-catalog", "cqrs-flow", "inheritance", "infrastructure", "system-context", "all")][string]$Type,
 [Parameter(ParameterSetName = "Run")][string]$Service,
 [Parameter(ParameterSetName = "Run")][ValidateSet("md", "mmd")][string]$Format,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.visualize.visualize" -Parameters $PSBoundParameters
exit $LASTEXITCODE
