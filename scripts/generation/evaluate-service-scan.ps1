#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Mechanical service-level scan for the /evaluate-generated-service skill.

.DESCRIPTION
 Parses the service DSL with the real Datrix pipeline and cross-checks ONE
 generated service directory: DSL feature inventory, manifest subset with a
 both-direction filesystem diff, directory-name convention check, per-block /
 per-entity expected-artifact existence table, dead-code candidates, env-var
 references, and Dockerfile / migrations existence. Writes service-scan JSON;
 the console prints a short summary only. Semantic verification stays with
 the model (skill Phase 3.5) — this scan checks existence only.

.PARAMETER Source
 Path to the service .dtrx file, or a system.dtrx combined with -Service.

.PARAMETER Service
 Service name (qualified, simple, or kebab-case). Required when Source
 defines more than one service.

.PARAMETER Generated
 Generated SERVICE directory (the service-specific folder, not the project root).

.PARAMETER ProjectGenerated
 Generated PROJECT root holding .datrix\manifests. Auto-detected from the
 parent directories of -Generated when omitted.

.PARAMETER Output
 Output JSON path. Default: <workspace>\.tmp\eval\<project>\service-<name>-scan.json.

.PARAMETER ConfigProfile
 Config profile the project was generated with (default: test, matching
 generate.ps1's default).

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\evaluate-service-scan.ps1 -Source examples\01-foundation\system.dtrx -Service BookService -Generated D:\datrix\.generated\python\docker-compose\local\01-foundation\library_book_service
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Source,

 [Parameter()]
 [string]$Service = "",

 [Parameter(Position=1)]
 [string]$Generated,

 [Parameter()]
 [string]$ProjectGenerated = "",

 [Parameter()]
 [string]$Output = "",

 [Parameter()]
 [string]$ConfigProfile = "",

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Source) { $pythonArgs += @("--source", $Source) }
if ($Service) { $pythonArgs += @("--service", $Service) }
if ($Generated) { $pythonArgs += @("--generated", $Generated) }
if ($ProjectGenerated) { $pythonArgs += @("--project-generated", $ProjectGenerated) }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($ConfigProfile) { $pythonArgs += @("--profile", $ConfigProfile) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\evaluate_service_scan.py") -Arguments $pythonArgs)
