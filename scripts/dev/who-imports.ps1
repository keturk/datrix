#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Show which runtime import chain first loads a module.

.DESCRIPTION
 Wraps dev\lib\who_imports.py. Imports each -Root module in a fresh interpreter with an
 observer on sys.meta_path; the first time a -Target module (or any submodule of a target
 package) is looked up, it prints the chain of workspace frames that led there -- the
 import statement, function-level ones included, that pulled the target in. The observer
 resolves nothing itself, so imports behave as without it.

 scan\check-import-boundaries.ps1 reports that a forbidden edge exists (statically); this
 shows which chain realizes it at runtime.

 Exit codes: 0 = every root imported (a target that never loaded is listed as such),
 2 = a root failed to import (its error is printed).

.PARAMETER Root
 Modules to import (required, one or more).

.PARAMETER Target
 Modules or packages to watch (required, one or more).

.EXAMPLE
 .\dev\who-imports.ps1 -Root datrix_codegen_kernel.gendsl -Target datrix_codegen_common
 Does the kernel's genDSL load the language layer, and through which import?
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Root,
    [Parameter(Mandatory = $true)]
    [string[]]$Target
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Root = @($Root | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Target = @($Target | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$pythonScript = Join-Path $scriptDir "lib\who_imports.py"
if (-not (Test-Path $pythonScript)) {
    Write-Error "who_imports.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
    if (-not (Ensure-DatrixVenv)) {
        Write-Error "Failed to activate the Datrix virtual environment"
        exit 2
    }
    if (-not (Ensure-DatrixPackagesInstalled -SkipIfInstalled)) {
        Write-Error "Failed to ensure the Datrix packages are installed"
        exit 2
    }

    $pythonArgs = @($pythonScript)
    foreach ($item in $Root) { $pythonArgs += "--root"; $pythonArgs += $item }
    foreach ($item in $Target) { $pythonArgs += "--target"; $pythonArgs += $item }

    & python @pythonArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
} finally {
    Invoke-Cleanup
}
