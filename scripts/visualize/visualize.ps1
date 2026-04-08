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

.PARAMETER Tutorial
    Tutorial examples only.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: generate-all).

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

.EXAMPLE
    .\visualize.ps1 -Tutorial -Type service-map -Format mmd
    Generate service map diagrams in raw Mermaid format for tutorials.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Tutorial,
    [switch]$Domains,
    [string]$TestSet = "generate-all",

    [ValidateSet("erd", "service-map", "event-flow", "api-catalog", "cqrs-flow", "inheritance", "infrastructure", "system-context", "all")]
    [string]$Type = "all",

    [string]$Service,

    [ValidateSet("md", "mmd")]
    [string]$Format = "md",

    [string]$Profile = "test",

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $libraryDir "visualize\visualize.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "visualize.py not found at $pythonScript"
    exit 1
}

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    Write-Error "Failed to activate virtual environment"
    exit 1
}

trap {
    if (Get-Command Disable-DatrixVenv -ErrorAction SilentlyContinue) {
        Disable-DatrixVenv
    }
    throw $_
}

try {
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    $pyArgs = @()

    if ($Source) {
        $pyArgs += "--source"
        $pyArgs += $Source
    }
    if ($All) { $pyArgs += "--all" }
    if ($Tutorial) { $pyArgs += "--tutorial" }
    if ($Domains) { $pyArgs += "--domains" }
    if ($TestSet -ne "generate-all") {
        $pyArgs += "--test-set"
        $pyArgs += $TestSet
    }
    if ($Type -ne "all") {
        $pyArgs += "--type"
        $pyArgs += $Type
    }
    if ($Service) {
        $pyArgs += "--service"
        $pyArgs += $Service
    }
    if ($Format -ne "md") {
        $pyArgs += "--format"
        $pyArgs += $Format
    }
    if ($Profile -ne "test") {
        $pyArgs += "--profile"
        $pyArgs += $Profile
    }
    if ($Dbg) { $pyArgs += "--debug" }

    & $pythonExe $pythonScript @pyArgs
    exit $LASTEXITCODE
} finally {
    Disable-DatrixVenv
}
