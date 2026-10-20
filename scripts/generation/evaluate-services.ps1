#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Runs /evaluate-generated-service prompts in parallel using Claude Code CLI.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.evaluate_services. Finds all service-*.prompt.md
 files in the evaluation folder and runs them through Claude Code in non-interactive mode (-p,
 the prompt on stdin), processing up to 5 services concurrently. Asks "Proceed? (y/N)" first;
 anything but y (or an end of input) aborts with exit 0.

 By default uses the current directory as the evaluation folder. Pass -EvalDir
 to specify a different path.

 Where the claude on PATH is a batch shim (claude.cmd, which cmd.exe runs), a -SourceDir,
 -GeneratedDir or -Model holding a cmd.exe metacharacter is refused (exit 2).

 Exit codes: 0 = every run succeeded (or the run was declined), 1 = a run failed or a
 directory is missing, 2 = usage error.

.PARAMETER SourceDir
 Path to the project source directory (containing .dtrx files).
 Required — this is the directory Claude Code needs read access to.

.PARAMETER GeneratedDir
 Path to the generated output directory.
 Required — this is the directory Claude Code needs read access to.

.PARAMETER Parallel
 Number of parallel Claude Code processes to run (1 or more). Default: 5.

.PARAMETER Model
 Model to use. Default: opus.

.PARAMETER EvalDir
 Path to the evaluation directory containing prompt files.
 If not specified, uses the current directory.

.PARAMETER SelfTest
 Run only the self-test: the local triage's checks (a planted prompt and scan, a model server
 on loopback), this runner's own (prompt discovery, the Claude Code argument vector, batching,
 the confirmation), and the wrapper seam.

.PARAMETER Full
 Skip the local triage: every service goes to Claude Code.

 Without -Full, each service is first triaged by the local model servers
 (datrix_scripts.generation.service_triage): its Phase 3.5 categories (computed fields,
 lifecycle hooks, validation blocks, REST endpoint logic, event handlers) are each judged
 clean, finding or unverifiable, into service-<name>.local-triage.json. A service
 whose categories are all clean gets its report written from the triage into
 evaluated\ (marked "local triage only") and no Claude Code run; any other service
 goes to Claude Code with the triage file appended to its prompt. No local server
 answering makes every category unverifiable, so every service goes to Claude Code.

.EXAMPLE
 cd d:\datrix\eval\2026-05-16-100000-ecommerce
 d:\datrix\datrix\scripts\generation\evaluate-services.ps1 -SourceDir "d:\datrix\datrix\examples\03-domains\ecommerce" -GeneratedDir "d:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce"

.EXAMPLE
 d:\datrix\datrix\scripts\generation\evaluate-services.ps1 -SourceDir "d:\datrix\datrix\examples\03-domains\ecommerce" -GeneratedDir "d:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce" -EvalDir "d:\datrix\eval\2026-05-16-100000-ecommerce" -Parallel 3 -Model sonnet
#>
[CmdletBinding(DefaultParameterSetName = "Evaluate")]
param(
 [Parameter(Mandatory = $true, ParameterSetName = "Evaluate")][string]$SourceDir,
 [Parameter(Mandatory = $true, ParameterSetName = "Evaluate")][string]$GeneratedDir,
 [Parameter(ParameterSetName = "Evaluate")][string]$EvalDir,
 [Parameter(ParameterSetName = "Evaluate")][int]$Parallel,
 [Parameter(ParameterSetName = "Evaluate")][string]$Model,
 [Parameter(ParameterSetName = "Evaluate")][switch]$Full,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.evaluate_services" -Parameters $PSBoundParameters
exit $LASTEXITCODE
