<#
.SYNOPSIS
    Save .dtrx Application as a JSON snapshot for future diffs.

.DESCRIPTION
    Parses .dtrx files and serializes the Application model to JSON.
    Snapshots can be compared with schema-diff.ps1 to detect changes.
    Supports single-file and batch modes.

.PARAMETER Source
    Path to .dtrx file or directory (single mode).

.PARAMETER All
    Snapshot all projects from test-projects.json.

.PARAMETER Tutorial
    Tutorial examples only.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: all).

.PARAMETER Output
    Explicit output file path (overrides default location).

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\schema-snapshot.ps1 examples\02-domains\ecommerce\system.dtrx
    Create a snapshot for the ecommerce example.

.EXAMPLE
    .\schema-snapshot.ps1 -All
    Create snapshots for all projects.

.EXAMPLE
    .\schema-snapshot.ps1 -Tutorial -OutputBase .snapshots-tutorial
    Snapshot tutorial examples to a custom directory.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Tutorial,
    [switch]$Domains,
    [string]$TestSet = "all",

    [string]$Output,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $libraryDir "visualize\schema_snapshot.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "schema_snapshot.py not found at $pythonScript"
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
    if ($Output) {
        $pyArgs += "--output"
        $pyArgs += $Output
    }
    if ($Dbg) { $pyArgs += "--debug" }

    & $pythonExe $pythonScript @pyArgs
    exit $LASTEXITCODE
} finally {
    Disable-DatrixVenv
}
