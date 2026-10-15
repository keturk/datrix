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

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($name in $Repo) { $pythonArgs += @("--repo", $name) }
if ($DryRun) { $pythonArgs += "--dry-run" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\fix_line_endings.py") -Arguments $pythonArgs)
