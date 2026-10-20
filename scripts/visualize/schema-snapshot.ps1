#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Save .dtrx Application as a JSON snapshot for future diffs.

.DESCRIPTION
 The behaviour is datrix_scripts.visualize.schema_snapshot. Loads .dtrx files the way generation
 does (profile test) and serializes the Application model to JSON. Snapshots can be compared
 with schema-diff.ps1 to detect changes. Supports single-file and batch modes.

 Exit codes: 0 = every snapshot was written; 1 = a project failed, or the batch named no
 project; 2 = neither -Source nor a batch flag.

.PARAMETER Source
 Path to .dtrx file or directory (single mode), relative to the workspace root.

.PARAMETER All
 Snapshot all projects from test-projects.json.

.PARAMETER Domains
 Domain examples only.

.PARAMETER TestSet
 Named test set from test-projects.json (default: all).

.PARAMETER Output
 Explicit output file path (overrides default location).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: a planted example is snapshotted, the refusals, and the
 wrapper seam.

.EXAMPLE
 .\schema-snapshot.ps1 datrix\examples\02-domains\ecommerce\system.dtrx
 Create a snapshot for the ecommerce example.

.EXAMPLE
 .\schema-snapshot.ps1 -All
 Create snapshots for all projects.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0)][string]$Source,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Domains,
 [Parameter(ParameterSetName = "Run")][string]$TestSet,
 [Parameter(ParameterSetName = "Run")][string]$Output,
 [Parameter(ParameterSetName = "Run")][switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.visualize.schema_snapshot" -Parameters $PSBoundParameters
exit $LASTEXITCODE
