#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Mechanical project-level scan for the /evaluate-generated skill (quick mode).

.DESCRIPTION
 Parses the system.dtrx with the real Datrix pipeline, cross-checks the
 generated project (service directories, manifests, infrastructure files,
 docker-compose entries), rolls up critical blockers and warnings, and writes
 project-scan.json plus one service-*.prompt.md per service into the
 evaluation directory. All detail goes to the output files; the console
 prints a short summary only.

.PARAMETER Source
 Path to the system.dtrx file.

.PARAMETER Generated
 Generated project root directory (as produced by generate.ps1).

.PARAMETER EvalDir
 Evaluation output directory. Default: <workspace>\.tmp\eval\<project-slug>\.

.PARAMETER ConfigProfile
 Config profile the project was generated with (default: test, matching
 generate.ps1's default).

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\evaluate-generated-scan.ps1 -Source examples\01-foundation\system.dtrx -Generated D:\datrix\.generated\python\docker-compose\local\01-foundation
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Source,

 [Parameter(Position=1)]
 [string]$Generated,

 [Parameter()]
 [string]$EvalDir = "",

 [Parameter()]
 [string]$ConfigProfile = "",

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Source) { $pythonArgs += @("--source", $Source) }
if ($Generated) { $pythonArgs += @("--generated", $Generated) }
if ($EvalDir) { $pythonArgs += @("--eval-dir", $EvalDir) }
if ($ConfigProfile) { $pythonArgs += @("--profile", $ConfigProfile) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\evaluate_generated_scan.py") -Arguments $pythonArgs)
