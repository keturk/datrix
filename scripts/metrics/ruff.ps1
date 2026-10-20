#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run Ruff (lint/format) for one or more Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.metrics.ruff for each project. Modes: check (lint), format. Supports
 output-format, fix, diff, statistics for check; check (dry run), diff for format.
 Console output is written to a timestamped log under the workspace-level
 .test-output\ruff\<project>\ folder
 (e.g. D:\datrix\.test-output\ruff\datrix-common\ruff-20260207-143022.log).
 The logs live OUTSIDE every package repo on purpose: each datrix-* package
 is its own git repository, so a log folder created inside one is committed
 and pushed unless a human notices.

.PARAMETER Projects
 One or more project names or folder paths.

.PARAMETER All
 Run Ruff for all Datrix projects.

.PARAMETER Mode
 check (lint) or format. Default: check.

.PARAMETER OutputFormat
 For mode=check: full, concise, json, json-lines, junit, grouped, github, etc.

.PARAMETER Fix
 Apply fixes (mode=check).

.PARAMETER Diff
 Show diff only (check: fix diff; format: format diff).

.PARAMETER Statistics
 Show rule counts (mode=check).

.PARAMETER Check
 Dry run for format: exit non-zero if changes needed.

.PARAMETER Test
 Run Ruff on each project's tests/ folder instead of src/.

.PARAMETER StopOnError
 Stop on first project failure.

.PARAMETER VerboseOutput
 Verbose output (Ruff's -v).

.PARAMETER SelfTest
 Run only the module's self-test (planted projects, no real workspace) and exit.

.EXAMPLE
 .\ruff.ps1 datrix-common
 .\ruff.ps1 datrix-common -Mode format -Diff
 .\ruff.ps1 -All -Mode check -OutputFormat json -Statistics
 .\ruff.ps1 -All -Test
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("check", "format")]
 [string]$Mode = "check",
 [string]$OutputFormat = "full",
 [switch]$Fix,
 [switch]$Diff,
 [switch]$Statistics,
 [switch]$Check,
 [switch]$Test,
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.ruff" -Parameters $PSBoundParameters
exit $LASTEXITCODE
