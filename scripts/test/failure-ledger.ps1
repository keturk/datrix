#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Store a fix job's starting index.json runs, then list which of their failing test ids are still open.

.DESCRIPTION
 The behaviour is datrix_scripts.test.failure_ledger. -Runs stores the starting runs. -Status replays every
 later run of each package, in time order, and reports per test id the last verdict: FAILING (the last run that
 covered its file failed it), NOT-RERUN (no run since has covered its file) or NEW (it failed in a later run
 and in no starting run). A run covers a file when it is a full run or a -Specific selection names the file or
 its directory; a -Tag or -Keyword selection covers nothing here. The job is finished at zero open ids.

 Exit: 0 no open id (or the runs stored), 1 open ids, 2 usage error.

.PARAMETER Runs
 The starting index.json paths (comma-separated or repeated). Stores them, replacing any earlier ledger.

.PARAMETER Status
 Check the stored runs against every run since.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test over planted runs.

.EXAMPLE
 .\test\failure-ledger.ps1 -Runs d:\datrix\datrix-common\.test_results\test-results-20261024-214941\index.json,d:\datrix\datrix-language\.test_results\test-results-20261024-215111\index.json
 Store the job's starting runs.

.EXAMPLE
 .\test\failure-ledger.ps1 -Status
 List the ids still open after every run since.
#>
[CmdletBinding(DefaultParameterSetName = "Status")]
param(
 [Parameter(Mandatory = $true, ParameterSetName = "Store")][string[]]$Runs,
 [Parameter(ParameterSetName = "Status")][switch]$Status,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.failure_ledger" -Parameters $PSBoundParameters
exit $LASTEXITCODE
