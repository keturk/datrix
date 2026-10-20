#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Scan Datrix Python code for anti-patterns using LibCST.

.DESCRIPTION
    The behaviour is datrix_scripts.scan.libcst. Runs the LibCST anti-pattern scanner, in the
    shared venv, on one or more projects (or the entire monorepo with -All). libcst must be
    installed in the venv; the scanner refuses, naming the install command, when it is not.
    Neither a project nor -All prints the usage and exits 1; with both, -All wins.

    Patterns detected:
    - silent-fallback       : dict.get(key, None)
    - empty-except          : except: pass
    - missing-encoding      : read_text()/write_text()/open() without encoding=
    - banned-test-import    : MagicMock/Mock/patch/SimpleNamespace in tests
    - placeholder-body      : pass / raise NotImplementedError as sole body

.PARAMETER Projects
    One or more project names to scan (e.g. datrix-common datrix-language).
    Positional.

.PARAMETER All
    Scan all projects in the monorepo.

.PARAMETER Report
    Write a markdown report to this path (relative to monorepo root).

.PARAMETER SelfTest
    Run only the module's self-test: planted anti-patterns are found, a clean project passes,
    the usage is printed when nothing is selected, and the wrapper seam holds.

.EXAMPLE
    .\libcst.ps1 datrix-common
    Scan datrix-common for anti-patterns.

.EXAMPLE
    .\libcst.ps1 -All
    Scan all projects.

.EXAMPLE
    .\libcst.ps1 -All -Report libcst-report.md
    Scan all projects and write a markdown report.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Projects,
    [Parameter(ParameterSetName = "Run")][switch]$All,
    [Parameter(ParameterSetName = "Run")][string]$Report,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.libcst" -Parameters $PSBoundParameters
exit $LASTEXITCODE
