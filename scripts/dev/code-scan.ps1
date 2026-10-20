#!/usr/bin/env pwsh
<#
.SYNOPSIS
    On-demand code-health scan: one ranked digest of dead code, complexity, duplicates and docs drift.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.code_scan. By default scans only the packages whose content
    changed since their last scan (tracked with the code index's file hashes in
    .code-index\scan-state.json); -Package or -All override that. Runs on this machine; changes
    nothing but the digest and the scan state.

    Per package:
      dead code   two-pass Vulture, each finding checked against the code index across the whole
                  workspace (a use in another package refutes it) and dropped if a template, a string
                  (getattr name, dotted resolver path) or a manifest entry point names it
      complexity  cyclomatic and cognitive complexity over the limit
      duplicates  Pylint R0801 groups, largest first
      docs drift  the check-docs lint over the package's docs\

    Every finding is written, by section and then by package, to
    <workspace>\reports\code-scan\code-scan-<timestamp>.md, headed by a per-package count table.
    The console gets one progress line per stage while it runs, then one line: the totals and the
    report's path.

    Exit codes:
      0 = digest written, or nothing changed since the last scan
      1 = the scan could not run (a tool missing, an unknown package, an unreadable scan state)

.PARAMETER Package
    Scan these packages, changed or not (positional). Each is a package name or its folder, in any
    form: datrix-cli, .\datrix-cli\, D:\datrix\datrix-cli, or a path inside it. Comma-separate or list
    several.

.PARAMETER All
    Scan every package with a src\ tree.

.PARAMETER MinConfidence
    Vulture's minimum confidence for a dead-code finding. Default: 60.

.PARAMETER DuplicateMinLines
    Smallest duplicated block Pylint reports. Default: 6.

.PARAMETER SelfTest
    Run only the module's self-test: package names and string-named symbols are read correctly, and
    the wrapper seam holds.

.EXAMPLE
    .\code-scan.ps1
    Scan the packages changed since their last scan.

.EXAMPLE
    .\code-scan.ps1 datrix-codegen-common

.EXAMPLE
    .\code-scan.ps1 .\datrix-cli\ .\datrix-common\
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Package,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][int]$MinConfidence = 60,
 [Parameter(ParameterSetName = "Run")][int]$DuplicateMinLines = 6,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.code_scan" -Parameters $PSBoundParameters
exit $LASTEXITCODE
