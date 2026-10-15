<#
.SYNOPSIS
    Report documentation status for Datrix projects.

.DESCRIPTION
    Scans Datrix project source directories and reports which documentation
    artifacts exist: diagrams, OpenAPI specs, AsyncAPI specs, and snapshots.
    Supports single-file and batch modes.

.PARAMETER Source
    Path to .dtrx file or directory (single project mode).

.PARAMETER All
    Check all projects from test-projects.json.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: all).

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\status-docs.ps1 examples\02-domains\ecommerce\system.dtrx
    Report docs status for the ecommerce example.

.EXAMPLE
    .\status-docs.ps1 -All
    Report docs status for all projects.

#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Domains,
    [string]$TestSet = "all",
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @()
if ($Source) { $pyArgs += @("--source", $Source) }
if ($All) { $pyArgs += "--all" }
if ($Domains) { $pyArgs += "--domains" }
if ($TestSet -ne "all") { $pyArgs += @("--test-set", $TestSet) }
if ($Dbg) { $pyArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\status_docs.py") -Arguments $pyArgs)
