#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Author a package's diagnostics fixtures from the diagnostic catalog (draft, plan, scaffold, verify).

.DESCRIPTION
 The behaviour is datrix_scripts.dev.fixture_author.cli.

 diagnostics loads the package's case session, reads the
 catalog variants its diagnostics fixtures must provoke (the target-check variants for the package that
 registers the target checks, every other variant for the rest, less those its census proves by a code
 test), and plans one area project per code family (<family>-halt for a code that ends analysis, a seeded
 <area>/ directory for a code read off seed documents, one targets area for target checks, declaring
 // @analysis targets and naming no language: it is one input per registered backend language, and a
 variant must fire under each). With no action switch it drafts each planned area not on disk: a local model writes
 one fragment per variant, the area is analyzed once per round, a cascade or a variant not provoked goes
 back to the model, at most 4 rounds; a variant still failing is written to
 .tmp\fixture-author\queue\<area>.md for a person to finish. A draft holding a secret-looking literal is
 queued and never written. -Verify analyzes each area as its whole-analysis case does and prints what it
 reports and does not annotate (a cascade) and what it annotates and does not report.

 Exit of diagnostics: 0 done (every drafted variant landed; every verified area reports exactly what it
 annotates), 1 a variant was queued, an area failed or the package's state refuses the run, 2 usage
 error, 3 no local model can draft (nothing is written).

.PARAMETER Kind
 diagnostics (author the diagnostics fixtures).

.PARAMETER Package
 The package directory name, e.g. datrix-semantic. Required.

.PARAMETER Area
 One planned area; default every planned area (diagnostics only).

.PARAMETER Plan
 Print the needs and the planned areas (with -Area, that area's variants).

.PARAMETER Scaffold
 Copy the corpus system configuration and datasource templates into each project root lacking them.

.PARAMETER Verify
 Compare each area's reported variants with its annotated ones.

.PARAMETER LocalMachines
 Machines (host name or IP) whose Ollama server drafts or reads, in preference order.

.PARAMETER LlmModel
 Use only these models, best first. Default: any model already in memory.

.PARAMETER LlmTimeout
 Timeout in seconds for each request to a ready model. Default: 300.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: needs, area plan, scaffold, verification, and drafting over a loopback model server.

.EXAMPLE
 .\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Area svc
 Draft the area svc with a local model and queue what still fails.

.EXAMPLE
 .\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Plan
 Print the needs and every planned area.

.EXAMPLE
 .\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Area svc -Verify
 Verify the area project svc.dtrx.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Run")][ValidateSet("diagnostics")][string]$Kind,
 [Parameter(ParameterSetName = "Run")][string]$Package,
 [Parameter(ParameterSetName = "Run")][string]$Area,
 [Parameter(ParameterSetName = "Run")][switch]$Plan,
 [Parameter(ParameterSetName = "Run")][switch]$Scaffold,
 [Parameter(ParameterSetName = "Run")][switch]$Verify,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName = "Run")][int]$LlmTimeout,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.fixture_author.cli" -Parameters $PSBoundParameters
exit $LASTEXITCODE
