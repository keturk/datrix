#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Ruff Checker for Jinja2 Templates

.DESCRIPTION
 Finds Jinja templates under -TemplatesDir (default: the current directory), renders them with
 mock values in a temp folder, runs ruff check on the generated files, and saves the findings to
 D:\datrix\.test-output\ruff-checker\ruff-report-<yyyyMMdd-HHmmss>.txt -- never into the scanned
 folder, so a run inside a package leaves nothing to commit.

.PARAMETER TemplatesDir
 Directory searched (recursively) for .j2 templates. Default: the current directory.

.PARAMETER Dbg
 Log at DEBUG level and print the python invocation before running.

.EXAMPLE
 .\ruff-checker.ps1
 Check all .j2 templates in the current directory and subfolders.

.EXAMPLE
 .\ruff-checker.ps1 -TemplatesDir D:\datrix\datrix-codegen-python\src\datrix_codegen_python\templates
 Check one package's templates without changing directory.
#>

[CmdletBinding()]
param(
 [string]$TemplatesDir = "",
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$searched = if ($TemplatesDir) { $TemplatesDir } else { (Get-Location).Path }
Write-Host "Running ruff template checker..." -ForegroundColor Cyan
Write-Host "Checking templates in: $searched" -ForegroundColor Cyan
Write-Host ""

$pythonArgs = @("--templates-dir", $searched)
if ($Dbg) {
 $pythonArgs += "--debug"
}
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\ruff_checker.py") -Arguments $pythonArgs -ShowCommand:$Dbg)
