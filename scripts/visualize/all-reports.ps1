#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run all visualization and documentation scripts for a project.

.DESCRIPTION
 The behaviour is datrix_scripts.visualize.all_reports. Orchestrates the full visualization
 pipeline for one or more .dtrx projects:
   1. Mermaid and SVG diagrams (visualize)
   2. OpenAPI / AsyncAPI specs (openapi-gen)
   3. Documentation status report (status-docs)

 All output is written next to the .dtrx source files (language-agnostic). Each step runs as its
 own process: a failure in one step is reported but does not block subsequent steps.

 Exit codes: 0 = every step passed; 1 = a step failed, or neither -Source nor a batch flag.

.PARAMETER Source
 Path to .dtrx file or directory (single project mode).

.PARAMETER All
 Process all projects from test-projects.json.

.PARAMETER Domains
 Domain examples only.

.PARAMETER TestSet
 Named test set from test-projects.json (default: all).

.PARAMETER Profile
 Config profile the diagram and spec steps resolve (default: test).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: every step runs with its options, a failing step fails the
 run, and the wrapper seam.

.EXAMPLE
 .\all-reports.ps1 datrix\examples\02-domains\ecommerce\system.dtrx
 Run all reports for the ecommerce example.

.EXAMPLE
 .\all-reports.ps1 -All -Dbg
 Run all reports for every project with debug logging.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0)][string]$Source,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Domains,
 [Parameter(ParameterSetName = "Run")][string]$TestSet,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.visualize.all_reports" -Parameters $PSBoundParameters
exit $LASTEXITCODE
