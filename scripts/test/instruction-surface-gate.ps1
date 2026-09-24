#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Census every whole-suite test.ps1/affected-gate.ps1 form in agent-facing instruction documents.

.DESCRIPTION
 Activates the Datrix virtual environment and runs instruction_surface.py. Scans
 claude-config/.claude/CLAUDE.md, rules/*.md and skills/**/*.md for a bare
 test.ps1 form (no -Specific/-Keyword), -All, -Rerun, or an unqualified tier
 switch, outside a <!-- forbidden-example --> context. A plain-Python self-test
 suite runs automatically, unconditionally, as step 1 of every invocation.

.PARAMETER SelfTest
 Run only the scanner's own self-test suite and exit -- skips the real census.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\instruction-surface-gate.ps1

.EXAMPLE
 .\instruction-surface-gate.ps1 -SelfTest
#>

[CmdletBinding()]
param(
    [switch]$SelfTest,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\instruction_surface.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $PythonExe = Join-Path $venvPath "Scripts\python.exe"

    if (-not (Test-Path $PythonScript)) {
        Write-Error "Python script not found: $PythonScript"
        exit 2
    }

    $pythonArgs = @($PythonScript)
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($Dbg) { $pythonArgs += "--debug" }

    & $PythonExe @pythonArgs
    exit $LASTEXITCODE
} catch {
    Write-Error "Error: $_"
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
