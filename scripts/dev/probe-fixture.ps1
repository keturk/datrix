#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Analyze a fixture project and print what the production front half makes of it, before a test run depends on it.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.probe_fixture. For each requested config profile it runs
 datrix_testing.project.analyzed_project on the project (parse, config resolution, semantic analysis, the
 same front half the tests and the CLI run) and prints either the error text, or each service with the
 datasource blocks, queues, serverless blocks and integrations it holds. It then writes a stamp under
 <workspace>\.tmp\fixture-probes\; the Claude Code hook guard-test-run-discipline.py refuses a test run that
 follows an edit of a tests\fixtures\[projects\]<name>\ project with no stamp newer than the edit.

 Exit: 0 every profile analyzed, 1 a profile failed, 2 usage error.

.PARAMETER Path
 The fixture project's .dtrx file, or its directory (which must hold system.dtrx).

.PARAMETER ConfigProfile
 Config profile(s) to analyze (comma-separated or repeated). Default test.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: a planted project analyzes, a broken one reports its error, the stamp is keyed.

.EXAMPLE
 .\dev\probe-fixture.ps1 -Path d:\datrix\datrix-codegen-azure\tests\fixtures\projects\data-plane\system.dtrx
 Analyze the project under the test profile.

.EXAMPLE
 .\dev\probe-fixture.ps1 -Path d:\datrix\datrix-codegen-azure\tests\fixtures\projects\pooled-queue-consumers -ConfigProfile production,ungrouped
 Analyze the project under two profiles.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, ParameterSetName = "Run")][string]$Path,
 [Parameter(ParameterSetName = "Run")][string[]]$ConfigProfile,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.probe_fixture" -Parameters $PSBoundParameters
exit $LASTEXITCODE
