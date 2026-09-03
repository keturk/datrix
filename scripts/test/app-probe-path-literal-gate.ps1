#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Hard-zero gate: no platform package may hardcode a language's probe route.

.DESCRIPTION
 Scans every datrix.platforms package's src/ tree (Python string constants via
 ast, docstrings excluded; quoted literals in .j2 templates, comment lines
 excluded) for a string literal equal to any route a registered language
 declares on its LanguageRuntimeSpec -- readiness_probe_path() or
 app_service_liveness_probe_path(). A platform that spells one of those routes
 itself has assumed a route on the language's behalf: that is how one
 registered language, whose controller never mounted the "/ready" every
 platform assumed, was probed at a 404 on Compose, ECS and App Runner.

 Platform packages are discovered from disk (each datrix-*/pyproject.toml
 registering datrix.platforms); the declared routes come from the INSTALLED
 datrix.languages plugins. Hits are compared against the reviewed exemptions in
 datrix/scripts/config/app-probe-path-exemptions.json (file + exact snippet +
 reason, expected_count pinned); a stale exemption fails the gate too.

 The self-test runs first on every invocation: a planted platform package must
 yield exactly its code-line hits (docstrings and template comments excluded), a
 clean one none, a single-package workspace is refused, and the live scan of the
 language packages' own src/ trees must find every declared route -- so the
 matcher is proven against real literals, never only fixtures.

 Exit codes:
   0 = clean, or a successful -SelfTest run
   1 = an unexempted hit or a stale exemption was found
   2 = usage error, too few packages/languages, or the self-test failed

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the scanner's self-test and exit, skipping the real scan.

.PARAMETER ShowFiles
 Print each file as it is scanned.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\app-probe-path-literal-gate.ps1
 Scan every platform package, fail on any unexempted probe-route literal.

.EXAMPLE
 .\app-probe-path-literal-gate.ps1 -SelfTest
 Prove the scanner detects planted literals and clears docstrings/comments.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "app-probe-path-literal-gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: app-probe-path-literal-gate.py not found at: $pythonScript"
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
    if ($BaseDir) { $pythonArgs += "--base-dir"; $pythonArgs += $BaseDir }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($ShowFiles) { $pythonArgs += "--verbose" }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
    }

    & $pythonExe @pythonArgs
    $exitCode = $LASTEXITCODE
    Invoke-Cleanup
    exit $exitCode
}
catch {
    Write-Error $_
    Invoke-Cleanup
    exit 2
}
