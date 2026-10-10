#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Hard-zero gate: every Jinja template a framework package ships is named by
 something that can render it.

.DESCRIPTION
 Discovers every .j2 file below a templates/ directory of every datrix-*/src
 tree on disk and fails on any that nothing names: no Python string constant,
 f-string or concatenation in any framework package's src/ (docstrings
 excluded), no static Jinja include/import/from/extends, and no compiled genDSL
 FileDefinition template name of any registered generator target. A genDSL
 template name that matches no template on disk fails the gate too.

 A template nothing names is dead output: reviewed, kept in sync and shipped,
 yet never rendered. Two cache-access templates once sat beside the live one
 that way.

 The self-test runs first on every invocation: a planted workspace must yield
 exactly its docstring-only and unnamed templates, and the live genDSL walk must
 find template names -- so the matcher is proven, never vacuous.

 An unnamed template a declared contract requires to exist is listed, with a
 written reason, in datrix/scripts/config/template-reachability-exemptions.json;
 an entry whose template is named or gone is stale and fails the gate.

 Exit codes:
   0 = every template is named, or a successful -SelfTest run
   1 = an unnamed template, a dangling genDSL template name or a stale exemption
   2 = usage error, a template that does not parse, a malformed exemptions file,
       or the self-test failed

.PARAMETER BaseDir
 Workspace root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the self-test and exit, skipping the real scan.

.PARAMETER Dbg
 Print the python invocation.

.EXAMPLE
 .\template-reachability-gate.ps1
 Scan every framework package, fail on any template nothing names.

.EXAMPLE
 .\template-reachability-gate.ps1 -SelfTest
 Prove the matcher on a planted workspace and the genDSL walk on the real one.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\template_reachability.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: template_reachability.py not found at: $pythonScript"
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
