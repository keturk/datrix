#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Derive the reverse-dependency closure of Datrix packages from actual imports.

.DESCRIPTION
 Activates the Datrix virtual environment and runs affected_set.py. Discovers
 every datrix-* package from disk (no hardcoded package list), builds the
 import graph from each package's src/, tests/, and root-level conftest.py
 plus declared pyproject.toml dependencies, and prints each requested
 package's transitive reverse-dependency closure (the packages that must
 also be tested when it changes). Writes affected-set.json to
 <workspace>\.tmp\test\ by default. A plain-Python self-test suite runs
 automatically, unconditionally, as step 1 of every invocation.

.PARAMETER Projects
 One or more package names (comma-separated or space-separated) to report
 closures for.

.PARAMETER All
 Report every discovered package's closure.

.PARAMETER Output
 Output JSON path (default <workspace>\.tmp\test\affected-set.json).

.PARAMETER SelfTest
 Run only the scanner's own self-test suite and exit -- skips the real
 derivation. The same self-test also runs automatically, unconditionally, as
 step 1 of every normal invocation.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\affected-set.ps1 -Projects datrix-language

.EXAMPLE
 .\affected-set.ps1 -All

.EXAMPLE
 .\affected-set.ps1 -SelfTest
#>

[CmdletBinding()]
param(
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$Projects,

    [switch]$All,

    [string]$Output,

    [switch]$SelfTest,

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\affected_set.py"

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
    foreach ($project in $Projects) {
        if ($project) { $pythonArgs += @("--projects", $project) }
    }
    if ($All) { $pythonArgs += "--all" }
    if ($Output) { $pythonArgs += @("--output", $Output) }
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
