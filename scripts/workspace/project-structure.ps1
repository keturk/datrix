#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Generate .project-structure.md files for Datrix projects.

.DESCRIPTION
 Runs datrix_scripts.workspace.project_structure in the shared venv.
 Walks src/, tests/, and templates/ directories of each specified project and
 writes a .project-structure.md file to the project root containing annotated
 ASCII directory trees. The file name is added to the project's .gitignore when missing.

.PARAMETER Projects
 One or more project names (e.g., datrix-codegen-typescript) or paths.

.PARAMETER All
 Generate structure for every datrix project holding src/, tests/ or templates/.

.PARAMETER Depth
 Maximum directory depth to include in trees (default: 4).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the module's self-test (a planted workspace) and the wrapper seam checks, and exit.

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript

.EXAMPLE
 .\project-structure.ps1 -All

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript -Depth 6
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [int]$Depth = 4,
 [switch]$Dbg,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.workspace.project_structure" -Parameters $PSBoundParameters
exit $LASTEXITCODE
