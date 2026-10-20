#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compare two .dtrx files and report schema changes.

.DESCRIPTION
 The behaviour is datrix_scripts.visualize.schema_diff. Loads two .dtrx applications the way
 generation does (profile test), produces a structural diff, and outputs a report in Markdown or
 JSON format. Identifies breaking vs non-breaking changes. Relative paths are taken from the
 workspace root.

 Exit codes: 0 = the report was produced; 1 = an input is missing or failed to load.

.PARAMETER Before
 Path to the earlier .dtrx file (baseline).

.PARAMETER After
 Path to the later .dtrx file (comparison target).

.PARAMETER Format
 Output format: markdown or json (default: markdown).

.PARAMETER Output
 Output file path. If omitted, writes to stdout.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: a planted example diffed with itself, the refusals, and the
 wrapper seam.

.EXAMPLE
 .\schema-diff.ps1 v1\system.dtrx v2\system.dtrx
 Compare two versions and print Markdown diff to stdout.

.EXAMPLE
 .\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Format json -Output changes.json
 Compare and write JSON diff to a file.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0, Mandatory = $true)][string]$Before,
 [Parameter(ParameterSetName = "Run", Position = 1, Mandatory = $true)][string]$After,
 [Parameter(ParameterSetName = "Run")][ValidateSet("markdown", "json")][string]$Format,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.visualize.schema_diff" -Parameters $PSBoundParameters
exit $LASTEXITCODE
