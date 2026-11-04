#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Count and cap the .dtrx/.dcfg test fixtures of every Datrix package against a decrease-only baseline.

.DESCRIPTION
 For every datrix-* package with a tests/ tree, counts its fixture files (.dtrx, .dtrx.false, .dcfg,
 .dseed under tests/) and its inline .dtrx/.dcfg string literals in test modules; across all counted
 files, counts the duplicate copies, the fixture names shared by two or more packages, and the total of
 every package's fixtures plus the shared fixtures under datrix-testing/src/datrix_testing/fixtures_data/.
 Each count may only fall below scripts/config/fixture-budget-baseline.json; the shared fixture count
 alone is printed and not pinned.

 Exit codes:
   0 = every pinned count at or below its baseline and every corpus entry read
   1 = a count above its baseline, or a corpus entry no test reads
   2 = usage error, missing baseline, attempted baseline increase, unreadable file, failed self-test

.PARAMETER ShowFiles
 Print every counted file, inline literal site, duplicate group and cross-package name.

.PARAMETER BaseDir
 Workspace root directory (default: auto-detect).

.PARAMETER UpdateBaseline
 Freeze the first baseline, or tighten an existing one. Refused (exit 2) when any count rises.

.PARAMETER SelfTest
 Run only the self-test (the census checks over a planted workspace and the wrapper seam check) and
 exit; reads nothing of the real workspace. The census checks also run before every real scan.

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\fixture-budget-gate.ps1
 Count every package's fixtures and fail on a count above the baseline.

.EXAMPLE
 .\fixture-budget-gate.ps1 -ShowFiles
 Also list every counted file, literal site, duplicate group and shared name.

.EXAMPLE
 .\fixture-budget-gate.ps1 -UpdateBaseline
 Freeze the first baseline, or bank a fall.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$UpdateBaseline,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.ratchet.fixture_budget_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
