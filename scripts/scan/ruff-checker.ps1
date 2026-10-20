#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Ruff Checker for Jinja2 Templates

.DESCRIPTION
 The behaviour is datrix_scripts.scan.ruff_checker. Finds Jinja templates under -TemplatesDir
 (default: the current directory), renders them with mock values in a temp folder, runs ruff
 check on the generated files, and saves the findings to
 D:\datrix\.test-output\ruff-checker\ruff-report-<yyyyMMdd-HHmmss>.txt -- never into the scanned
 folder, so a run inside a package leaves nothing to commit.

 Exit codes: 0 clean, 1 a render error or a ruff finding, 2 ruff missing or a -TemplatesDir that
 is not a directory.

.PARAMETER TemplatesDir
 Directory searched (recursively) for .j2 templates. Default: the current directory.

.PARAMETER Dbg
 Log at DEBUG level and print the python invocation before running.

.PARAMETER SelfTest
 Run only the module's self-test: a planted template whose output ruff flags fails the check, a
 clean one passes, a folder that is not a directory is refused, and the wrapper seam holds.

.EXAMPLE
 .\ruff-checker.ps1
 Check all .j2 templates in the current directory and subfolders.

.EXAMPLE
 .\ruff-checker.ps1 -TemplatesDir D:\datrix\datrix-codegen-python\src\datrix_codegen_python\templates
 Check one package's templates without changing directory.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(ParameterSetName = "Run")][string]$TemplatesDir,
    [Parameter(ParameterSetName = "Run")][switch]$Dbg,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.ruff_checker" -Parameters $PSBoundParameters
exit $LASTEXITCODE
