#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Third-party dependency parity gate -- declared third-party runtime dependencies equal imported ones.

.DESCRIPTION
 For every datrix-* package with a src/ tree, the third-party distributions its
 [project] dependencies declare must equal the third-party distributions its
 src/ tree imports (ast, nested imports included, mapped to distributions through
 the installed metadata). `imported - declared` is an undeclared dependency that
 works here only because something else installed it; `declared - imported` is a
 dead declaration. Extras other than `dev` are optional runtime surfaces that may
 satisfy a src/ import; the `dev` extra never does. A distribution the package
 invokes as a subprocess rather than imports is a reviewed executable exemption in
 datrix/scripts/config/third-party-dependency-exemptions.json (a stale entry fails
 the gate). The sibling manifest-import-parity-gate.ps1 holds the same invariant for
 the Datrix distributions; this gate covers everything else.

 The self-test runs first on every invocation: a planted dirty package must yield
 exactly its four violations, a planted clean package none, a single-package
 workspace is refused, and the live scan must see a real package both declare and
 import one distribution.

 Exit codes:
   0 = every manifest agrees with its imports, or a successful -SelfTest run
   1 = a violation or a stale exemption was found
   2 = usage error, too few packages, or the self-test failed

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the scanner's self-test and exit, skipping the real scan.

.PARAMETER ShowFiles
 Print each package's declared set as it is scanned.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\third-party-dependency-parity-gate.ps1
 Compare every datrix-* manifest's third-party dependencies against its src/ imports.

.EXAMPLE
 .\third-party-dependency-parity-gate.ps1 -SelfTest
 Prove the scanner reports every planted violation and clears the clean package.
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
$pythonScript = Join-Path $scriptDir "third-party-dependency-parity-gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: third-party-dependency-parity-gate.py not found at: $pythonScript"
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
