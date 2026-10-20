#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: every framework repo normalizes text to LF and commits no CRLF line.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.line_ending_gate in the shared venv. It checks the datrix
 showcase repo and every datrix-* git checkout in the workspace (discovered at runtime) for two
 facts, both read from git:

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
 Limit the scan to these repo names (an array or one comma-separated value). Default: every
 framework repo in the workspace.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and the wrapper seam checks, and skip the real scan.

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
 [string[]]$Repo, [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.line_ending_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
