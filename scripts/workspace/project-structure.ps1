#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Generate .project-structure.md files for Datrix projects.

.DESCRIPTION
 Walks src/, tests/, and templates/ directories of each specified project and
 writes a .project-structure.md file to the project root containing annotated
 ASCII directory trees. Runs project_structure.py in the shared venv.

.PARAMETER Projects
 One or more project names (e.g., datrix-codegen-typescript) or paths.

.PARAMETER All
 Generate structure for all discoverable datrix-* projects.

.PARAMETER Depth
 Maximum directory depth to include in trees (default: 4).

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript
 Generate structure file for the TypeScript codegen project.

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript datrix-codegen-python
 Generate structure files for multiple projects.

.EXAMPLE
 .\project-structure.ps1 -All
 Generate structure files for all discoverable projects.

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript -Depth 6
 Generate with deeper directory traversal.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Projects = @(),

 [Parameter()]
 [switch]$All,

 [Parameter()]
 [int]$Depth = 4,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = if ($All) { @("--all") } else { @($Projects) }
$pythonArgs += @("--depth", "$Depth")
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\project_structure.py") -Arguments $pythonArgs)
