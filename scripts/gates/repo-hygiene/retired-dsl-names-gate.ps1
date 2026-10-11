#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: no retired internal-DSL name appears in a Datrix framework repo.

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\retired_dsl_names.py, which scans
 every publishable file (tracked plus untracked-but-not-ignored) of every framework repo in
 the workspace (datrix plus every datrix-* clone, discovered from disk) -- file content,
 file names and directory names -- for the retired spellings listed in
 lib\retired_dsl_names.json, and fails listing path:line per hit.

 WHY IT EXISTS: when an internal language is renamed or replaced, its old name must leave
 every identifier, module, package, entry-point group, feature tag, script, resource file
 and document. A rename that leaves stragglers keeps two names for one thing alive; this is
 the check that holds the terminal state at zero.

 The spellings file is the only path skipped. Its self-test plants every sample in a
 scratch git repo under D:\datrix\.tmp\ (content, a file name, a directory name, plus a
 git-ignored copy that must not be reported) and runs before every scan: a detector that
 stopped detecting reports a clean tree, which is indistinguishable from a clean tree.

 Exit codes:
   0 = no retired name found (or the self-test passed, with -SelfTest)
   1 = at least one retired name, or the self-test failed
   2 = usage error, a malformed spellings file, a repo git cannot list, or a file that
       cannot be read

.PARAMETER Repo
 Limit the scan to these repo names. Default: every framework repo in the workspace.

.PARAMETER SelfTest
 Run only the self-test and skip the real scan.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\retired-dsl-names-gate.ps1
 Scan every publishable file in every framework repo.

.EXAMPLE
 .\retired-dsl-names-gate.ps1 -Repo datrix-common
 Scan only the named repo.

.EXAMPLE
 .\retired-dsl-names-gate.ps1 -SelfTest
 Run only the self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Repo,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\retired_dsl_names.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: retired_dsl_names.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

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
    foreach ($name in $Repo) { $pythonArgs += @("--repo", $name) }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
        Write-Host ""
    }

    & $pythonExe @pythonArgs
    exit $LASTEXITCODE

} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
