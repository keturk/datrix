#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Format Datrix .dtrx files losslessly, with the same formatter as `datrix format`.

.DESCRIPTION
 The behaviour is datrix_scripts.scan.datrix_format. Discovers .dtrx files under the given paths
 and normalizes their whitespace over the parse tree (datrix_language.formatting): indentation
 follows bracket nesting, trailing whitespace is removed, and a run of blank lines becomes one.
 Every token and comment is verified identical before anything is written; writes are atomic.
 It writes nothing if any file fails parsing or verification. .dtrx.false fixtures are
 intentionally invalid and are not formatted. Pass -All or one or more paths, not both;
 neither prints the usage and exits 1.

.PARAMETER Path
 One or more file or directory paths to scan.

.PARAMETER All
 Scan all Datrix repository directories.

.PARAMETER Check
 Check formatting without modifying files.

.PARAMETER Diff
 Show unified diffs without modifying files.

.PARAMETER IndentSize
 Number of spaces per indentation level (1-8). Defaults to 4.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: a planted badly indented model is reported and left
 unwritten under -Check, the selection rules hold, and the wrapper seam holds.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Path,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Check,
 [Parameter(ParameterSetName = "Run")][switch]$Diff,
 [Parameter(ParameterSetName = "Run")][ValidateRange(1, 8)][int]$IndentSize = 4,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.datrix_format" -Parameters $PSBoundParameters
exit $LASTEXITCODE
