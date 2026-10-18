#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: every framework repo normalizes text to LF and commits no CRLF line.

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\line_endings.py, which checks
 the datrix showcase repo and every datrix-* git checkout in the workspace (discovered
 at runtime) for two facts, both read from git:

   policy          -- 'git check-attr text eol' on a path no per-extension rule names
                      resolves to text=auto, eol=lf: the catch-all '* text=auto eol=lf'
                      rule is in force, so a CRLF working-tree file is staged as LF.
   committed-crlf  -- 'git ls-files --eol' reports no tracked file whose index blob is
                      i/crlf or i/mixed.

 WHY IT EXISTS: with core.autocrlf=false and no attribute rule, a file a bulk edit
 rewrote with CRLF is committed as CRLF, and every line of it shows as changed. A
 package once had forty-two modified files switched to CRLF in its working tree, one
 commit away from rewriting all of them.

 The non-vacuity self-test runs before every scan: a scratch repo with no attributes
 must report both facts, and the same files staged under the catch-all rule nothing.

 Exit codes:
   0 = every scanned repo holds both facts (or the self-test passed, with -SelfTest)
   1 = at least one violation, or the self-test failed
   2 = usage error (unknown -Repo name, no framework repo found) or a failing git command

.PARAMETER Repo
 Limit the scan to these repo names. Default: every framework repo in the workspace.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Dbg
 Enable DEBUG logging and print the python invocation before running.

.EXAMPLE
 .\line-ending-gate.ps1
 Check every framework repo in the workspace.

.EXAMPLE
 .\line-ending-gate.ps1 -Repo datrix-codegen-flutter
 Check only the named repo(s).

.EXAMPLE
 .\line-ending-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
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

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Repo = @($Repo | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($name in $Repo) { $pythonArgs += @("--repo", $name) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\line_endings.py") -Arguments $pythonArgs -Gate "line-ending" -ShowCommand:$Dbg)
