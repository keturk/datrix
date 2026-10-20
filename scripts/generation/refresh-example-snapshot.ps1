#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Refresh one committed example snapshot with one command.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.refresh_example_snapshot. Generates ONE example in
 ONE registered language (generate.ps1's module in single-project mode; never -All, -Domains or
 -TestSet) into D:\datrix\.tmp\example-snapshots\<example>\<language>-<platform>\, then replaces
 <example>\generated\<language>-<platform>\ with that output minus every path git
 ignores there (the repository's .datrix\ rule and the generated project's own
 .gitignore: build output, per-service secrets\). The ignore set is asked of git,
 never restated.

 <platform> is a registered datrix.platforms name taken from the example's
 resolved deployment (default profile 'test'): the provider-owned platform when
 the provider owns one (aws), otherwise the platform that emits the runtime's
 container scaffolding (docker for docker-compose). -Platform overrides it.

 Exit 2 for a refused request: a language or platform that is not registered, a
 missing source, or a deployment that resolves to no single platform.

.PARAMETER Source
 Path to the example's system.dtrx.

.PARAMETER Language
 A registered datrix.languages name.

.PARAMETER Platform
 Optional registered datrix.platforms name overriding the derived one.

.PARAMETER ConfigProfile
 Config profile that selects the deployment (default: test).

.PARAMETER SelfTest
 Run only the self-test: a fixture project with secrets\ and .datrix\ copies neither, and the
 wrapper seam holds.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\refresh-example-snapshot.ps1 -Source d:\datrix\datrix\examples\03-domains\ecommerce\system.dtrx -Language python
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][string]$Source,
 [Parameter(ParameterSetName = "Run")][string]$Language,
 [Parameter(ParameterSetName = "Run")][string]$Platform,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.refresh_example_snapshot" -Parameters $PSBoundParameters
exit $LASTEXITCODE
