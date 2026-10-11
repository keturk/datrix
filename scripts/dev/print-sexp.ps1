#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Print the tree-sitter parse tree of Datrix source as a corpus-style S-expression.

.DESCRIPTION
 Wraps dev\lib\print_sexp.py. Parses with the built Datrix grammar (the same compiled parser
 datrix-language loads; the native tree-sitter CLI cannot load that library on every host)
 and prints the tree in tree-sitter corpus layout -- two-space indent, closing parentheses on
 the last child's line -- ready to paste into a corpus test as the expected tree.

 Named nodes only by default; -All also prints anonymous nodes (keywords, punctuation) as
 quoted text. MISSING nodes print as (MISSING <type>).

 Exit codes: 0 = no error in the tree, 1 = ERROR or MISSING nodes present (tree still
 printed), 2 = the input could not be read.

.PARAMETER Path
 A .dtrx file.

.PARAMETER Text
 Datrix source given inline instead of a file.

.PARAMETER All
 Also print anonymous nodes.

.EXAMPLE
 .\dev\print-sexp.ps1 examples\01-foundation\system.dtrx

.EXAMPLE
 .\dev\print-sexp.ps1 -Text 'enum Status { Active, Inactive }' -All
#>

[CmdletBinding(DefaultParameterSetName = "File")]
param(
    [Parameter(ParameterSetName = "File", Position = 0, Mandatory = $true)]
    [string]$Path,
    [Parameter(ParameterSetName = "Text", Mandatory = $true)]
    [string]$Text,
    [switch]$All
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$pythonScript = Join-Path $scriptDir "lib\print_sexp.py"
if (-not (Test-Path $pythonScript)) {
    Write-Error "print_sexp.py not found at: $pythonScript"
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

    if ($PSCmdlet.ParameterSetName -eq "Text") {
        $pythonArgs = @($pythonScript, "--text", $Text)
    } else {
        $pythonArgs = @($pythonScript, $Path)
    }
    if ($All) { $pythonArgs += "--all" }

    & python @pythonArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
} finally {
    Invoke-Cleanup
}
