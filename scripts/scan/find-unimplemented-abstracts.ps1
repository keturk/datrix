#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Find classes that inherit abstract methods they never implement.

.DESCRIPTION
 Wraps scan\lib\find_unimplemented_abstracts.py. Imports every module of the selected
 packages (default: every datrix-* package with a src/ tree) and lists every class whose
 __abstractmethods__ is non-empty. A class that subclasses abc.ABC directly, declares an
 abstract method itself, is a typing.Protocol, or is itself subclassed is an intended
 abstract base; every other such class (a leaf meant to be concrete) is INCOMPLETE -- it
 cannot be instantiated, and nothing says so until something tries. Each missing method is printed with the base that declares it abstract.

 Exit codes: 0 = no incomplete class, 1 = incomplete class(es) found,
 2 = a module failed to import (each failure is listed) or a bad argument.

.PARAMETER Package
 Import names to scan (e.g. datrix_codegen_python). Default: every datrix-* package.

.PARAMETER ShowBases
 Also list the intended abstract bases.

.PARAMETER Dbg
 Debug logging (per-package module and class counts).

.EXAMPLE
 .\scan\find-unimplemented-abstracts.ps1
 Every incomplete class in every package.

.EXAMPLE
 .\scan\find-unimplemented-abstracts.ps1 -Package datrix_codegen_python -ShowBases
 One package, with its abstract bases.
#>

[CmdletBinding()]
param(
    [string[]]$Package = @(),
    [switch]$ShowBases,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Package = @($Package | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$pythonScript = Join-Path $scriptDir "lib\find_unimplemented_abstracts.py"
if (-not (Test-Path $pythonScript)) {
    Write-Error "find_unimplemented_abstracts.py not found at: $pythonScript"
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
    foreach ($name in $Package) { $pythonArgs += "--package"; $pythonArgs += $name }
    if ($ShowBases) { $pythonArgs += "--show-bases" }
    if ($Dbg) { $pythonArgs += "--debug" }

    & python @pythonArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
} finally {
    Invoke-Cleanup
}
