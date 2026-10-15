<#
.SYNOPSIS
    Generate OpenAPI and AsyncAPI specs from .dtrx source files.

.DESCRIPTION
    Parses .dtrx files and produces one OpenAPI 3.1 YAML per service (every
    rest_api block of the service) and one AsyncAPI 3.0 YAML per service (every
    pubsub block of the service). Clears only docs/openapi and docs/asyncapi.
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
    Spec type: openapi, asyncapi, or all (default: all).

.PARAMETER Profile
    Config profile to resolve (default: test).

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\openapi-gen.ps1 examples\02-domains\ecommerce\system.dtrx
    Generate OpenAPI and AsyncAPI specs for the ecommerce example.

.EXAMPLE
    .\openapi-gen.ps1 -All -Type openapi
    Generate only OpenAPI specs for all projects.

.EXAMPLE
    .\openapi-gen.ps1 -Domains -Type asyncapi
    Generate only AsyncAPI specs for domain examples.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Domains,
    [string]$TestSet = "all",

    [ValidateSet("openapi", "asyncapi", "all")]
    [string]$Type = "all",

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
if ($Profile -ne "test") { $pyArgs += @("--profile", $Profile) }
if ($Dbg) { $pyArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\openapi_gen.py") -Arguments $pyArgs)
