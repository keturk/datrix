#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Enforce the I5 docs-conformance gate across Datrix architecture docs.

.DESCRIPTION
 Extracts repo-relative path references and Python module references from the
 curated 37-file architecture-doc set and fails if any reference does not
 resolve to a real file/directory/module in the tree, unless it is recorded
 in the committed exceptions baseline at
 scripts/config/docs-conformance-exceptions.json.

 Exit codes:
   0 = clean (no unresolved references), or -Warn mode
   1 = at least one unresolved, non-excepted reference found
   2 = usage error, missing exceptions baseline, or a doc in
       ARCHITECTURE_DOC_FILES that no longer exists

.PARAMETER Warn
 Warning mode: report unresolved references but exit 0.

.PARAMETER ShowFiles
 Print each architecture doc file being scanned (verbose mode).

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the self-test suite (plain-Python edge-case checks on the scanner's
 own functions) and exit -- skips the real docs scan. The same self-test also
 runs automatically, unconditionally, as step 1 of every normal invocation
 (with or without this switch).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\check-docs-conformance.ps1
 Scan all 37 architecture docs, fail on unresolved references (self-test runs first, automatically).

.EXAMPLE
 .\check-docs-conformance.ps1 -SelfTest
 Run only the scanner's own self-test suite.

.EXAMPLE
 .\check-docs-conformance.ps1 -Warn
 Report unresolved references but exit 0.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Warn,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "check-docs-conformance.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: check-docs-conformance.py not found at: $pythonScript"
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
    if ($ShowFiles) { $pythonArgs += "--verbose" }
    if ($BaseDir) { $pythonArgs += "--base-dir"; $pythonArgs += $BaseDir }
    if ($SelfTest) { $pythonArgs += "--self-test" }

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
