#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Lint and format config documents (.dcfg).

.DESCRIPTION
 The behaviour is datrix_scripts.scan.config_linter. Discovers .dcfg files and applies
 deterministic formatting. Also reports syntax errors and simple style warnings. A file whose
 formatting would drop a comment is left unchanged, with a warning. Pass -All or one or more
 paths, not both; neither prints the usage and exits 1.

.PARAMETER Path
 File or directory paths to scan.

.PARAMETER All
 Scan all datrix repositories.

.PARAMETER Check
 Check mode only. Reports issues and needed formatting without writing files.

.PARAMETER SelfTest
 Run only the module's self-test (round-trip fidelity fixture: service-wildcard rendering,
 replace/inheriting-base preservation, idempotence, comment fail-safe; the selection rules; the
 wrapper seam) and exit. Does not require -All or a path, and does not scan or format any real
 .dcfg file.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\config-linter.ps1 -All
 Format all .dcfg files under all datrix repositories.

.EXAMPLE
 .\config-linter.ps1 -All -Check
 Check all .dcfg files without modifying files.

.EXAMPLE
 .\config-linter.ps1 examples\01-foundation\config
 Format .dcfg files only in the provided folder.

.EXAMPLE
 .\config-linter.ps1 -SelfTest
 Run only the formatter self-test.
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$Path,
 [switch]$All,
 [switch]$Check,
 [switch]$SelfTest,
 [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.config_linter" -Parameters $PSBoundParameters
exit $LASTEXITCODE
