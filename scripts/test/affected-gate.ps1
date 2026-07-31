#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run the affected set of Datrix package suites concurrently and return one verdict.

.DESCRIPTION
 Activates the Datrix virtual environment and runs affected_gate.py. Derives
 the affected set (changed packages union their reverse-dependency closure),
 schedules `test.ps1 <pkg>` child processes longest-first under a
 PYTEST_XDIST_AUTO_NUM_WORKERS budget so concurrently running children never
 oversubscribe the machine, and aggregates one GREEN/RED verdict by reusing
 gate-verdict's own per-project evaluation. Writes affected-gate.json to
 <workspace>\.tmp\test\ by default. A plain-Python self-test suite runs
 automatically, unconditionally, as step 1 of every invocation.

.PARAMETER Projects
 One or more CHANGED package names (comma-separated or space-separated).

.PARAMETER All
 Treat every discovered package as changed.

.PARAMETER MaxConcurrent
 Max concurrent package suites (default 4).

.PARAMETER WorkersPerChild
 Override PYTEST_XDIST_AUTO_NUM_WORKERS per child (default floor(logical
 cores / MaxConcurrent)).

.PARAMETER Mypy
 Also run mypy.ps1 for the CHANGED packages only, inside the same budget.

.PARAMETER Force
 Start even if a requested package's newest run looks in-progress.

.PARAMETER Output
 Output JSON path (default <workspace>\.tmp\test\affected-gate.json).

.PARAMETER SelfTest
 Run only the scheduler's own self-test suite and exit -- skips real
 scheduling. The same self-test also runs automatically, unconditionally, as
 step 1 of every normal invocation.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\affected-gate.ps1 -Projects datrix-common

.EXAMPLE
 .\affected-gate.ps1 -All -MaxConcurrent 4 -Mypy
#>

[CmdletBinding()]
param(
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$Projects,

    [switch]$All,

    [int]$MaxConcurrent,

    [int]$WorkersPerChild,

    [switch]$Mypy,

    [switch]$Force,

    [string]$Output,

    [switch]$SelfTest,

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\affected_gate.py"

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
    if ($MaxConcurrent) { $pythonArgs += @("--max-concurrent", $MaxConcurrent) }
    if ($WorkersPerChild) { $pythonArgs += @("--workers-per-child", $WorkersPerChild) }
    if ($Mypy) { $pythonArgs += "--mypy" }
    if ($Force) { $pythonArgs += "--force" }
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
