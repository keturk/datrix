#!/usr/bin/env pwsh
<#
.SYNOPSIS
 D14 gate: no package's tests resolve a path inside another package's
 tests/ directory.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.check_cross_package_fixture_reads in the shared
 venv, which AST-scans every .py file under every discovered datrix* package's tests/
 tree and statically evaluates the pathlib expressions test fixtures use to
 locate .dtrx/.dcfg/.json files (Path(__file__), .resolve(), .parent,
 .parents[N], "/" joins, and "from tests.<module> import NAME" -- always the
 same package's own tests/ namespace). Reports two things:

   (a) a resolved directory constant that points inside ANOTHER package's
       own tests/ tree (the D14 violation itself, regardless of whether the
       file it names still exists there);
   (b) a statically-resolved fixture path that does not exist on disk.

 This is exactly the shape that turned datrix-common commit 0badd1c's
 fixture cleanup into a red datrix-codegen-typescript suite:
 COMMON_FIXTURES_DIR / "system-with-jobs.dtrx" pointed at a file
 datrix-common's own tests no longer read, so nothing there knew to keep it.

 Packages are discovered from disk (any datrix* directory with a tests/
 tree) -- never a hardcoded list. Runs a built-in non-vacuity self-test on
 every invocation, which also plants both defect shapes in a temp tree and
 proves the scanner both finds and does not falsely find them, before
 checking a live read against the real workspace.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the scanner's self-test and exit, skipping the real workspace scan.

.PARAMETER ShowFiles
 Print each file as it is scanned.

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\check-cross-package-fixture-reads.ps1
 Scan every package, fail on any cross-package reference or missing fixture.

.EXAMPLE
 .\check-cross-package-fixture-reads.ps1 -SelfTest
 Prove the scanner detects both defect shapes and clears the clean case.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.check_cross_package_fixture_reads" -Parameters $PSBoundParameters
exit $LASTEXITCODE
