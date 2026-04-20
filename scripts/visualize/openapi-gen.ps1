<#
.SYNOPSIS
    Generate OpenAPI and AsyncAPI specs from .dtrx source files.

.DESCRIPTION
    Parses .dtrx files and produces OpenAPI 3.1 YAML per REST API and
    AsyncAPI 3.0 YAML per PubSub block. Supports single-file and batch modes.

.PARAMETER Source
    Path to .dtrx file or directory (single mode).

.PARAMETER All
    Generate for all projects from test-projects.json.

.PARAMETER Tutorial
    Tutorial examples only.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: all).

.PARAMETER Type
    Spec type: openapi, asyncapi, or all (default: all).

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
    [switch]$Tutorial,
    [switch]$Domains,
    [string]$TestSet = "all",

    [ValidateSet("openapi", "asyncapi", "all")]
    [string]$Type = "all",

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $libraryDir "visualize\openapi_gen.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "openapi_gen.py not found at $pythonScript"
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
    if ($TestSet -ne "all") {
        $pyArgs += "--test-set"
        $pyArgs += $TestSet
    }
    if ($Type -ne "all") {
        $pyArgs += "--type"
        $pyArgs += $Type
    }
    if ($Dbg) { $pyArgs += "--debug" }

    & $pythonExe $pythonScript @pyArgs
    exit $LASTEXITCODE
} finally {
    Disable-DatrixVenv
}
