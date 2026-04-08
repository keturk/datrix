<#
.SYNOPSIS
    Compare two .dtrx files and report schema changes.

.DESCRIPTION
    Parses two .dtrx source files, produces a structural diff, and outputs
    a report in Markdown or JSON format. Identifies breaking vs non-breaking changes.

.PARAMETER Before
    Path to the earlier .dtrx file (baseline).

.PARAMETER After
    Path to the later .dtrx file (comparison target).

.PARAMETER Format
    Output format: markdown or json (default: markdown).

.PARAMETER Output
    Output file path. If omitted, writes to stdout.

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\schema-diff.ps1 v1\system.dtrx v2\system.dtrx
    Compare two versions and print Markdown diff to stdout.

.EXAMPLE
    .\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Format json -Output changes.json
    Compare and write JSON diff to a file.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$Before,

    [Parameter(Position = 1, Mandatory = $true)]
    [string]$After,

    [ValidateSet("markdown", "json")]
    [string]$Format = "markdown",

    [string]$Output,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $libraryDir "visualize\schema_diff.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "schema_diff.py not found at $pythonScript"
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

    $pyArgs = @("--before", $Before, "--after", $After)
    if ($Format -ne "markdown") {
        $pyArgs += "--format"
        $pyArgs += $Format
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
