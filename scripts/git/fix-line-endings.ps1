#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Give each modified file back the line endings its index copy has.

.DESCRIPTION
 The behaviour is datrix_scripts.git.fix_line_endings. A tool that writes a file back with the
 other line-ending style turns a small edit into a whole-file rewrite and hides the real change.
 For every file with unstaged modifications, this reads the file's own index blob
 (git show :<path>, read-only) and rewrites ONLY the working copy's line terminators to
 match it. Content is never changed; nothing is reverted, staged or checked out.

 Skipped: binary files and files already matching. A file whose index copy itself mixes
 CRLF and LF is named and left as is.

 Exit codes: 0 = done (or a clean -DryRun, or a passing -SelfTest), 1 = a self-test check failed,
 2 = a git command failed or a bad argument.

.PARAMETER Repo
 Repository directory names (e.g. datrix-codegen-python), as an array or comma-separated.
 Default: every framework repo.

.PARAMETER DryRun
 List the files that would be rewritten; write nothing.

.PARAMETER SelfTest
 Restore the endings in a real repository in a temporary directory, run the census that no git
 script runs stash/reset/checkout/revert/restore, and the wrapper seam checks.

.EXAMPLE
 .\git\fix-line-endings.ps1 -DryRun
 Which modified files have line endings that differ from their index copy?

.EXAMPLE
 .\git\fix-line-endings.ps1 -Repo datrix-codegen-python
 Restore them in one repository.
#>
[CmdletBinding()]
param(
 [string[]]$Repo,
 [switch]$DryRun,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.fix_line_endings" -Parameters $PSBoundParameters
exit $LASTEXITCODE
