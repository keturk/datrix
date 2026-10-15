<#
.SYNOPSIS
    Generate Mermaid diagrams from .dtrx source files.

.DESCRIPTION
    Parses .dtrx files and produces Mermaid diagrams (ERD, service map, event flow,
    API catalog, CQRS flow, inheritance tree, infrastructure topology, system context).
    Supports single-file and batch modes.

.PARAMETER Source
    Path to .dtrx file or directory (single mode).

.PARAMETER All
    Generate for all projects from test-projects.json.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: all).

.PARAMETER Type
    Diagram type: erd, service-map, event-flow, api-catalog, cqrs-flow,
    inheritance, infrastructure, system-context, or all (default: all).

.PARAMETER Service
    Scope to a single service name.

.PARAMETER Format
    Output format: md or mmd (default: md).

.PARAMETER Profile
    Config profile to resolve (default: test).

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\visualize.ps1 examples\02-domains\ecommerce\system.dtrx -Type all
    Generate all diagram types for the ecommerce example.

.EXAMPLE
    .\visualize.ps1 -All -Type erd
    Generate ERD diagrams for all projects.

#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Domains,
    [string]$TestSet = "all",

    [ValidateSet("erd", "service-map", "event-flow", "api-catalog", "cqrs-flow", "inheritance", "infrastructure", "system-context", "all")]
    [string]$Type = "all",

    [string]$Service,

    [ValidateSet("md", "mmd")]
    [string]$Format = "md",

    [string]$Profile = "test",

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @()
if ($Source) { $pyArgs += @("--source", $Source) }
if ($All) { $pyArgs += "--all" }
if ($Domains) { $pyArgs += "--domains" }
if ($TestSet -ne "all") { $pyArgs += @("--test-set", $TestSet) }
if ($Type -ne "all") { $pyArgs += @("--type", $Type) }
if ($Service) { $pyArgs += @("--service", $Service) }
if ($Format -ne "md") { $pyArgs += @("--format", $Format) }
if ($Profile -ne "test") { $pyArgs += @("--profile", $Profile) }
if ($Dbg) { $pyArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\visualize.py") -Arguments $pyArgs)
