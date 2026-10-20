#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report dependency relationships between Datrix packages.

.DESCRIPTION
 Runs datrix_scripts.metrics.dependency to report which datrix-* packages depend on which
 (from pyproject.toml).
 Modes: tree (default), list, json, third-party (every non-datrix runtime dependency
 with each declaring package and its spec; SPEC DRIFT marks differing specifiers).

.PARAMETER Projects
 Optional. Restrict output to these package names (e.g. datrix-common, datrix-language).

.PARAMETER All
 Include all datrix-* packages (default when no -Projects).

.PARAMETER Mode
 Output mode: tree, list, json, third-party. Default: tree.

.PARAMETER VerboseOutput
 Debug logging: names the packages discovered.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (planted packages, no real workspace) and exit.

.EXAMPLE
 .\dependency.ps1 -All
 Show dependency tree for all Datrix packages.

.EXAMPLE
 .\dependency.ps1 -All -Mode list
 Show edges (package -> dependency) for all packages.

.EXAMPLE
 .\dependency.ps1 -All -Mode third-party
 Every third-party runtime dependency, who declares it, and where the specifiers drift.

.EXAMPLE
 .\dependency.ps1 datrix-common datrix-language -Mode json
 Show JSON for datrix-common and datrix-language only.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("tree", "list", "json", "third-party")]
 [string]$Mode = "tree",
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.dependency" -Parameters $PSBoundParameters
exit $LASTEXITCODE
