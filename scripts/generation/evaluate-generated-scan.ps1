#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Mechanical project-level scan for the /evaluate-generated skill (quick mode).

.DESCRIPTION
 The behaviour is datrix_scripts.generation.evaluate_generated_scan. Parses the system.dtrx
 with the real Datrix pipeline, cross-checks the generated project (service directories,
 manifests, infrastructure files, docker-compose entries), rolls up critical blockers and
 warnings, and writes project-scan.json plus one service-*.prompt.md per service into the
 evaluation directory. All detail goes to the output files; the console prints a short
 summary only.

 Exit codes: 0 = scanned, 2 = bad input (missing source or generated root, a source that
 does not analyze).

.PARAMETER Source
 Path to the system.dtrx file.

.PARAMETER Generated
 Generated project root directory (as produced by generate.ps1).

.PARAMETER EvalDir
 Evaluation output directory. Default: <workspace>\.tmp\eval\<project-slug>\.

.PARAMETER ConfigProfile
 Config profile the project was generated with (default: test, matching
 generate.ps1's default).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: bad inputs are refused, planted outputs are read, and the
 wrapper seam holds.

.EXAMPLE
 .\evaluate-generated-scan.ps1 -Source examples\01-foundation\system.dtrx -Generated D:\datrix\.generated\python\docker-compose\local\01-foundation
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0)][string]$Source,
 [Parameter(ParameterSetName = "Run", Position = 1)][string]$Generated,
 [Parameter(ParameterSetName = "Run")][string]$EvalDir,
 [Parameter(ParameterSetName = "Run")][string]$ConfigProfile,
 [Parameter(ParameterSetName = "Run")][switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.evaluate_generated_scan" -Parameters $PSBoundParameters
exit $LASTEXITCODE
