#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Mechanical service-level scan for the /evaluate-generated-service skill.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.evaluate_service_scan. Parses the service DSL with
 the real Datrix pipeline and cross-checks ONE generated service directory: DSL feature
 inventory, manifest subset with a both-direction filesystem diff, directory-name convention
 check, per-block / per-entity expected-artifact existence table, dead-code candidates,
 env-var references, and Dockerfile / migrations existence. Writes service-scan JSON; the
 console prints a short summary only. Semantic verification stays with the model (skill
 Phase 3.5) — this scan checks existence only.

 Exit codes: 0 = scanned, 2 = bad input.

.PARAMETER Source
 Path to the service .dtrx file, or a system.dtrx combined with -Service.

.PARAMETER Service
 Service name (qualified, simple, or kebab-case). Required when Source
 defines more than one service.

.PARAMETER Generated
 Generated SERVICE directory (the service-specific folder, not the project root).

.PARAMETER ProjectGenerated
 Generated PROJECT root holding .datrix\manifests. Auto-detected from the
 parent directories of -Generated when omitted.

.PARAMETER Output
 Output JSON path. Default: <workspace>\.tmp\eval\<project>\service-<name>-scan.json.

.PARAMETER ConfigProfile
 Config profile the project was generated with (default: test, matching
 generate.ps1's default).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: the project root is found or refused, caches are not
 indexed, and the wrapper seam holds.

.EXAMPLE
 .\evaluate-service-scan.ps1 -Source examples\01-foundation\system.dtrx -Service BookService -Generated D:\datrix\.generated\python\docker-compose\local\01-foundation\library_book_service
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0)][string]$Source,
 [Parameter(ParameterSetName = "Run")][string]$Service,
 [Parameter(ParameterSetName = "Run", Position = 1)][string]$Generated,
 [Parameter(ParameterSetName = "Run")][string]$ProjectGenerated,
 [Parameter(ParameterSetName = "Run")][string]$Output,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.evaluate_service_scan" -Parameters $PSBoundParameters
exit $LASTEXITCODE
