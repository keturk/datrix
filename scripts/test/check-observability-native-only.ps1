#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Observability native-only example-conformance guard (design 019 Phase 4).

.DESCRIPTION
 Scans every datrix/examples/**/config/system.dcfg for a portable
 observability provider (prometheus/datadog metrics, jaeger/zipkin tracing,
 loki logging, grafana visualization, alertmanager alerting) paired with a
 cloud deployment target (provider aws or azure) in the same resolved
 profile. Design 019 D1's native-only platform-boundary rule forbids this
 pairing; this is the retained Phase-4 example-conformance guard.

 Exit codes:
   0 = clean (no violations), or -Warn mode
   1 = at least one violation found
   2 = usage error, missing examples root, or the automatic self-test
       step failing on a normal invocation

.PARAMETER Warn
 Warning mode: report violations but exit 0.

.PARAMETER ExamplesRoot
 Override examples root directory (default: auto-detect datrix/examples).

.PARAMETER SelfTest
 Run only the scanner's own self-test suite and exit.

.PARAMETER ShowFiles
 Print each system.dcfg being scanned (verbose mode).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\check-observability-native-only.ps1
 Scan every example, fail on any cloud+portable-provider pairing.

.EXAMPLE
 .\check-observability-native-only.ps1 -ExamplesRoot D:\datrix\.tmp\obs-guard-selftest\examples
 Scan a scratch examples tree instead of the real datrix/examples.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Warn,

    [Parameter()]
    [string]$ExamplesRoot = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "check-observability-native-only.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: check-observability-native-only.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"

    $pythonArgs = @($pythonScript)
    if ($Warn) { $pythonArgs += "--warn" }
    if ($ExamplesRoot) { $pythonArgs += "--examples-root"; $pythonArgs += $ExamplesRoot }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($ShowFiles) { $pythonArgs += "--verbose" }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
        Write-Host "Arguments: $($pythonArgs -join ' ')" -ForegroundColor Cyan
        Write-Host ""
    }

    & $pythonExe @pythonArgs
    $exitCode = $LASTEXITCODE

    exit $exitCode

} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
