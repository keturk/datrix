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

.PARAMETER Tutorial
    Tutorial examples only.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: generate-all).

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\status-docs.ps1 examples\02-domains\ecommerce\system.dtrx
    Report docs status for the ecommerce example.

.EXAMPLE
    .\status-docs.ps1 -All
    Report docs status for all projects.

.EXAMPLE
    .\status-docs.ps1 -Tutorial
    Report docs status for tutorial examples.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Tutorial,
    [switch]$Domains,
    [string]$TestSet = "generate-all",
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $libraryDir "visualize\status_docs.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "status_docs.py not found at $pythonScript"
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
    if ($Dbg) { $pyArgs += "--debug" }

    & $pythonExe $pythonScript @pyArgs
    exit $LASTEXITCODE
} finally {
    Disable-DatrixVenv
}
