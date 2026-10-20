#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compile Python (syntax + import check) in Datrix projects, or under any path

.DESCRIPTION
 The behaviour is datrix_scripts.scan.compile. Two parameter sets:

 Projects (-All or positional project directories): compiles every Python file of the named
 Datrix projects to find syntax issues, and imports every installable package among them with
 all its submodules to find import issues.

 Path (-Path): checks Python files under any file or directory (a generated service's routes
 folder, say). For each path it finds the containing installable package and runs that
 package's full import check, so a missing import is reported.

 Relative names and paths resolve against the workspace root; a missing one exits 2, as does
 a run with nothing selected (after printing the usage).

.PARAMETER All
 Compile Python in all datrix repositories (the showcase repo and every datrix-* directory).

.PARAMETER ProjectDir
 One or more project directories to check (positional). Can be names (e.g. datrix-common)
 or full paths.

.PARAMETER Path
 One or more files or directories to check, anywhere (e.g. a generated service's folder).
 Comma-separated values are split.

.PARAMETER Dbg
 Print the interpreter and arguments before running, and log at DEBUG level.

.PARAMETER SelfTest
 Run only the module's self-test: planted projects are checked (a syntax error fails, a clean
 project passes), the Path mode finds the containing package, the usage errors are refused,
 and the wrapper seam holds.

.EXAMPLE
 .\compile.ps1 -All
 Check all Python files in all datrix repositories.

.EXAMPLE
 .\compile.ps1 datrix-common datrix-language -Dbg
 Check two projects with debug output.

.EXAMPLE
 .\compile.ps1 -Path D:\datrix\.generated\python\docker\02-features\01-core-data-modeling\rest-api\library_book_service\src\library_book_service\routes
 Check the routes folder; the import check runs for the containing library_book_service package.
#>
[CmdletBinding(DefaultParameterSetName = "Projects")]
param(
 [Parameter(ParameterSetName = "Projects")][switch]$All,
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Projects")][string[]]$ProjectDir,
 [Parameter(Mandatory = $true, ParameterSetName = "Path")][string[]]$Path,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.compile" -Parameters $PSBoundParameters
exit $LASTEXITCODE
