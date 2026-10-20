#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Find and list top N files by line count for one or more Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.metrics.large_files in the shared venv for each project.
 Walks both src/ and tests/; default is Python files only.
 Reports the largest files by line count in summary or json format. A report only:
 no line count fails the run.

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common).

.PARAMETER All
 Run for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Top
 Number of largest files to list per project. Default: 20.

.PARAMETER Threshold
 Only show files with at least this many lines (0 = no filter). Default: 0.

.PARAMETER Format
 Output format: summary, json. Default: summary.

.PARAMETER Suffix
 Comma-separated file suffixes to include (default: py). Use "" for all.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from the script.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (planted packages) and the wrapper seam checks, and exit.

.EXAMPLE
 .\large-files.ps1 datrix-common
 List top 20 Python files by line count for datrix-common.

.EXAMPLE
 .\large-files.ps1 datrix-language -Top 30 -Format json
 List top 30 Python files for datrix-language in JSON format.

.EXAMPLE
 .\large-files.ps1 -All -Suffix ""
 List top 20 files (all extensions) for all projects.

.EXAMPLE
 .\large-files.ps1 datrix-language -Threshold 500
 List top 20 Python files with at least 500 lines for datrix-language.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [int]$Top = 20,
 [int]$Threshold = 0,
 [ValidateSet("summary", "json")]
 [string]$Format = "summary",
 [string]$Suffix = "py",
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.large_files" -Parameters $PSBoundParameters
exit $LASTEXITCODE
