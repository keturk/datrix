#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Give each modified file back the line endings its index copy has.

.DESCRIPTION
    Wraps scripts\git\lib\fix_line_endings.py. A tool that writes a file back with the other
    line-ending style turns a small edit into a whole-file rewrite and hides the real change.
    For every file with unstaged modifications, this reads the file's own index blob
    (git show :<path>, read-only) and rewrites ONLY the working copy's line terminators to
    match it. Content is never changed; nothing is reverted, staged or checked out.

    Skipped: binary files and files already matching. A file whose index copy itself mixes
    CRLF and LF is named and left as is.

    Exit codes: 0 = done (or a clean -DryRun), 2 = a git command failed or a bad argument.

.PARAMETER Repo
    Repository directory names (e.g. datrix-codegen-python). Default: every framework repo.

.PARAMETER DryRun
    List the files that would be rewritten; write nothing.

.EXAMPLE
    .\git\fix-line-endings.ps1 -DryRun
    Which modified files have line endings that differ from their index copy?

.EXAMPLE
    .\git\fix-line-endings.ps1 -Repo datrix-codegen-python
    Restore them in one repository.
#>

[CmdletBinding()]
param(
    [string[]]$Repo = @(),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Repo = @($Repo | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent $scriptDir) "common"
. (Join-Path $commonDir "venv.ps1")

$pythonScript = Join-Path $scriptDir "lib\fix_line_endings.py"
if (-not (Test-Path $pythonScript)) {
    Write-Error "fix_line_endings.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
    if (-not (Ensure-DatrixVenv)) {
        Write-Error "Failed to activate the Datrix virtual environment"
        exit 2
    }

    $pythonArgs = @($pythonScript)
    foreach ($name in $Repo) { $pythonArgs += "--repo"; $pythonArgs += $name }
    if ($DryRun) { $pythonArgs += "--dry-run" }

    & python @pythonArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
} finally {
    Invoke-Cleanup
}
