#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate documentation fragments from source code.

.DESCRIPTION
    Extracts documentation from source-of-truth code locations and writes
    markdown fragment files to datrix/docs/generated/.

    Two fragment types are supported:
    - semantic-pipeline: Ordered list of semantic analyzer phases
    - cli-help: Full `datrix generate --help` output

    Supports --Check mode for CI verification.

.PARAMETER Fragment
    Which fragment to generate: semantic-pipeline, cli-help, or all (default: all).

.PARAMETER Check
    Verify mode: check that existing fragments are up-to-date.
    Exits with non-zero status if any fragment is stale.

.PARAMETER Dbg
    Print detailed output during generation.

.EXAMPLE
    .\generate-doc-fragments.ps1
    # Generate all fragments

.EXAMPLE
    .\generate-doc-fragments.ps1 -Fragment semantic-pipeline
    # Generate only the semantic pipeline fragment

.EXAMPLE
    .\generate-doc-fragments.ps1 -Check
    # Verify all fragments are up-to-date
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "semantic-pipeline", "cli-help")]
    [string]$Fragment = "all",

    [switch]$Check,

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\generate_doc_fragments.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "generate_doc_fragments.py not found at: $pythonScript"
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

    if ($Fragment -ne "all") {
        $pyArgs += "--fragment", $Fragment
    }
    if ($Check) {
        $pyArgs += "--check"
    }
    if ($Dbg) {
        $pyArgs += "--verbose"
    }

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
