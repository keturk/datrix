#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate @test-rule conformance annotations for test functions using a local LLM.

.DESCRIPTION
    Walks each package's tests/ tree, finds un-annotated test functions, and asks a
    local Ollama model whether each test encodes a cross-target conformance rule. In the
    default (propose) mode it writes reviewable proposals under
    .test-output/test-rules/<package>.json (+ a .md preview) and touches no source. Re-run
    with -Apply to insert the reviewed @test-rule markers above the test functions.

    The markers feed the logic-map Rule Matrix (logic-map.ps1 / logic-map-report.ps1).
    Runs are resumable: already-annotated functions and already-proposed functions are
    skipped, so you can build the map incrementally.

    Activates the Datrix virtual environment and runs generate_test_rules.py.

.PARAMETER Projects
    One or more package names (e.g. datrix-codegen-python). Positional.

.PARAMETER All
    Scan every datrix* package's tests tree.

.PARAMETER Apply
    Insert reviewed proposals into the test files (default: propose only).

.PARAMETER Model
    Ollama model name (default: exaone-deep:32b).

.PARAMETER Endpoint
    Ollama base URL (default: http://10.94.0.100:11434).

.PARAMETER Parallel
    Concurrent LLM calls (default: 4).

.PARAMETER Limit
    Max test functions per package this run (0 = no limit). Useful for a sample pass.

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\generate-test-rules.ps1 datrix-codegen-python -Limit 20
    Propose annotations for up to 20 test functions in one package.

.EXAMPLE
    .\generate-test-rules.ps1 -All
    Propose annotations across every package's tests.

.EXAMPLE
    .\generate-test-rules.ps1 datrix-codegen-python -Apply
    Insert the reviewed proposals for one package.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$Apply,

    [switch]$Review,

    [string]$Model,

    [string]$Endpoint,

    [int]$Parallel,

    [int]$Limit,

    [string[]]$Path,

    [switch]$NoSeed,

    [switch]$NoConsolidate,

    [switch]$IncludeE2e,

    [switch]$IncludeIntegration,

    [switch]$Dbg
)

if ($Projects.Count -eq 0 -and -not $All -and -not $Path) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\generate-test-rules.ps1 -All [-Apply] [-Model <name>] [-NoSeed] [-Parallel <n>] [-Limit <n>] [-Dbg]" -ForegroundColor White
    Write-Host "  .\generate-test-rules.ps1 <project> [project2 ...] [-Apply] [-NoSeed] [-Limit <n>] [-Dbg]" -ForegroundColor White
    Write-Host "  .\generate-test-rules.ps1 -Path <file-or-dir> [-NoSeed] [-Limit <n>] [-Dbg]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\generate-test-rules.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\generate_test_rules.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "generate_test_rules.py not found at: $pythonScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null
trap {
    Invoke-Cleanup
    exit 130
}

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    Write-Error "Failed to activate virtual environment"
    exit 1
}

try {
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    $pyArgs = @()
    if ($All) {
        $pyArgs += "--all"
    }
    else {
        $pyArgs += $Projects
    }
    if ($Apply) {
        $pyArgs += "--apply"
    }
    if ($Review) {
        $pyArgs += "--review"
    }
    if ($Model) {
        $pyArgs += "--model", $Model
    }
    if ($Endpoint) {
        $pyArgs += "--endpoint", $Endpoint
    }
    if ($PSBoundParameters.ContainsKey('Parallel')) {
        $pyArgs += "--parallel", $Parallel
    }
    if ($PSBoundParameters.ContainsKey('Limit')) {
        $pyArgs += "--limit", $Limit
    }
    if ($NoSeed) {
        $pyArgs += "--no-seed"
    }
    if ($Path) {
        foreach ($p in $Path) {
            $pyArgs += "--path", $p
        }
    }
    if ($NoConsolidate) {
        $pyArgs += "--no-consolidate"
    }
    if ($IncludeE2e) {
        $pyArgs += "--include-e2e"
    }
    if ($IncludeIntegration) {
        $pyArgs += "--include-integration"
    }
    if ($Dbg) {
        $pyArgs += "--debug"
    }

    Write-Host "Generating test-rule annotations..." -ForegroundColor Cyan
    Write-Host ""

    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonExe $pythonScript @pyArgs
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldEAP

    exit $exitCode
}
catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.Exception.InnerException) {
        Write-Host "Inner: $($_.Exception.InnerException.Message)" -ForegroundColor Red
    }
    Write-Host ""
    Invoke-Cleanup
    exit 1
}
finally {
    Invoke-Cleanup
}
