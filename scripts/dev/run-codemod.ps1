#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run a Bowler codemod on the Datrix codebase.

.DESCRIPTION
 Activates the Datrix virtual environment and runs the specified codemod script
 from scripts/dev/codemods. All arguments after the codemod name are passed
 through to the codemod (e.g. OLD_NAME NEW_NAME, or path list).
 Requires bowler to be installed in the venv (pip install bowler).

.PARAMETER CodemodName
 Name of the codemod script without .py (e.g. 01_rename_function, 02_rename_class).
 Positional.

.PARAMETER CodemodArgs
 Remaining arguments passed to the codemod (e.g. old name, new name, paths).
 ValueFromRemainingArguments.

.EXAMPLE
 .\run-codemod.ps1 01_rename_function parse_file parse_path
 Preview: rename function parse_file to parse_path (diff only).

.EXAMPLE
 .\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src
 Preview: rename class in given path.

.EXAMPLE
 .\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src
 Update imports when a module is renamed.
#>

[CmdletBinding()]
param(
 [Parameter(Mandatory = $true, Position = 0)]
 [string]$CodemodName,

 [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
 [string[]]$CodemodArgs = @()
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$commonDir = Join-Path $scriptsDir "common"
$libraryDir = Join-Path $scriptsDir "library"
$pythonScript = Join-Path $libraryDir "dev\run_codemod.py"

if (-not (Test-Path $pythonScript)) {
 Write-Error "run_codemod.py not found: $pythonScript"
 exit 1
}

. (Join-Path $commonDir "venv.ps1")

function Invoke-Cleanup {
 Disable-DatrixVenv
}
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null
trap {
 Invoke-Cleanup
 exit 130
}

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
 Write-Error "Failed to activate virtual environment"
 exit 1
}

$venvPath = Get-DatrixVenvPath
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
 $pythonExe = Join-Path $venvPath "bin\python"
}

$pythonArgs = @($pythonScript, $CodemodName) + $CodemodArgs
& $pythonExe @pythonArgs
exit $LASTEXITCODE
