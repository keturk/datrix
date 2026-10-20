#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run pygount (lines-of-code counting) for one or more Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.metrics.loc in the shared venv for each project.
 Reports code, documentation, and empty line counts per language.
 Supports summary, cloc-xml, and json output formats. A report only: no count fails the run.

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run LOC counting for all Datrix projects (datrix-* folders, excluding datrix).
 When -All is used, a second JSON pass per successful project aggregates a workspace-wide LOC total (code, documentation, empty lines, files, and per-language sums).

.PARAMETER Format
 Output format: summary, cloc-xml, json. Default: summary.

.PARAMETER Suffix
 Comma-separated file suffixes to include (e.g. py,js). Empty = all.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from the script.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (planted packages) and the wrapper seam checks, and exit.

.EXAMPLE
 .\loc.ps1 datrix-common
 Count lines of code for datrix-common (summary format).

.EXAMPLE
 .\loc.ps1 datrix-common -Format json
 Count lines of code for datrix-common in JSON format.

.EXAMPLE
 .\loc.ps1 -All -Suffix py
 Count only Python lines of code for all projects; includes a total LOC rollup across projects.

.EXAMPLE
 .\loc.ps1 datrix-common datrix-language -Format cloc-xml
 Count lines for multiple projects in cloc-xml format.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("summary", "cloc-xml", "json")]
 [string]$Format = "summary",
 [string]$Suffix = "",
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.loc" -Parameters $PSBoundParameters
exit $LASTEXITCODE
