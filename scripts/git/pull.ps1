#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pull every Datrix repository, then summarize which pulled and which did not.

.DESCRIPTION
    Wraps scripts\library\git\pull.py. Pulls each git repository directly under the
    workspace root in turn, printing git's output under its name, then prints one summary
    grouping every repository by outcome:
      Updated                    new commits pulled (old..new, commit count)
      Up to date                 nothing to pull
      Conflict                   the pull stopped with unmerged paths (listed)
      Blocked by local changes   the pull would overwrite local changes or untracked
                                 files (listed); nothing merged -- run /resolve-conflicts
      Failed                     anything else (no upstream, network, auth); git's error shown

    Exit codes:
      0 = every repository updated or up to date
      1 = at least one repository conflicted, was blocked, or failed
      2 = the run could not start

.EXAMPLE
    .\pull.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$pythonScript = Join-Path $scriptsDir "library\git\pull.py"
$commonDir = Join-Path $scriptsDir "common"
. (Join-Path $commonDir "venv.ps1")

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
        exit 2
    }
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    & $pythonExe $pythonScript
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 2
}
finally {
    Invoke-Cleanup
}
