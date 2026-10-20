#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Radon metrics (complexity, raw, Halstead, MI) for one or more Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.metrics.complexity in the shared venv for each project.
 Mode: check (enforce max complexity), cc, raw, halstead, mi.
 In mode=check, two metrics are enforced:
 - Cyclomatic complexity (Radon/McCabe): decision points and paths.
 - Cognitive complexity : understandability, including nesting.
 Both use the same threshold (default 15). CI can still report
 other issues (e.g. string literal duplication S1192).

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run metrics for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Mode
 Metric to run: check (enforce max cyclomatic and cognitive), cc (cyclomatic), raw, halstead, mi.

.PARAMETER Max
 Maximum cyclomatic and cognitive complexity allowed per block (mode=check). Default: 15.

.PARAMETER Files
 Check exactly these .py files (cyclomatic and cognitive, mode=check) instead of whole
 projects -- the check for the functions an edit touches, before it lands. Exit 1 on any
 violation. Not combinable with -Fix/-FixAll or another -Mode.

.PARAMETER Fix
 Fix the worst complexity violation using a local model (mode=check only).
 Sends the offending function to the first local model server that answers
 (datrix_scripts/local_llm.py), validates the result, and overwrites the function if
 the file is unchanged. Exits after first successful fix.
 If a fix fails (syntax error, undefined names, test failure), reverts and tries the next.

.PARAMETER FixAll
 Fix ALL complexity violations (not just the first). Implies -Fix.
 Processes violations from worst to least complex, continuing after each success.
 Use with -Test to verify each fix before moving to the next.

.PARAMETER Test
 Run pytest after fix to verify correctness; revert if tests fail. Use with -Fix/-FixAll.

.PARAMETER MaxRetries
 Maximum number of model attempts per violation (default: 3). Use with -Fix.
 On each retry, the LLM receives feedback about why the previous attempt failed.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order, for -Fix/-FixAll.
 Omit to search the default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER Model
 Models to use for -Fix/-FixAll, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for each refactor attempt. Default: 180.

.PARAMETER LlmNumPredict
 Maximum generated tokens per refactor attempt. Default: 4096.

.PARAMETER LlmTemperature
 Sampling temperature for refactor attempts. Default: 0.1.

.PARAMETER MaxContextChars
 Maximum file-context characters included in each prompt. The target function is always sent in full. Default: 8000.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from the script.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (planted packages) and the wrapper seam checks, and exit.

.EXAMPLE
 .\complexity.ps1 datrix-common
 Check datrix-common with default max complexity 15 (mode=check).

.EXAMPLE
 .\complexity.ps1 datrix-common -Mode raw
 Report raw metrics (SLOC, comment/blank, LOC, LLOC) for datrix-common.

.EXAMPLE
 .\complexity.ps1 -All -Mode halstead
 Report Halstead metrics for all projects.

.EXAMPLE
 .\complexity.ps1 -Files datrix-cli\src\datrix_cli\main.py,datrix-cli\src\datrix_cli\commands\generate.py
 Check just the two files an edit touched.

.EXAMPLE
 .\complexity.ps1 datrix-common -Fix
 Fix the worst complexity violation in datrix-common using a local model.

.EXAMPLE
 .\complexity.ps1 datrix-common -Fix -Test
 Fix with auto-revert if tests fail.

.EXAMPLE
 .\complexity.ps1 datrix-common -FixAll -Test
 Fix all violations, testing after each fix.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("check", "cc", "raw", "halstead", "mi")]
 [string]$Mode = "check",
 [int]$Max = 15,
 [string[]]$Files = @(),
 [switch]$Fix,
 [switch]$FixAll,
 [switch]$Test,
 [int]$MaxRetries = 3,
 [string[]]$LocalMachines = @(),
 [string[]]$Model = @(),
 [int]$LlmTimeout = 180,
 [int]$LlmNumPredict = 4096,
 [double]$LlmTemperature = 0.1,
 [int]$MaxContextChars = 8000,
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$Dbg,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.complexity" -Parameters $PSBoundParameters
exit $LASTEXITCODE
