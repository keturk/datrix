#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: no file under a generator package's src/ holds a code point a reader cannot see.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.hidden_code_point_gate in the shared venv. It reads every
 file a commit could publish under src/ of every datrix-codegen-* git checkout in the workspace
 (discovered at runtime) as UTF-8 and reports, as <repo>/<path>:<line>:<column>: U+HHHH, every
 code point datrix_common.utils.hidden_text.hidden_in_source flags other than TAB, LF and CR:
 controls, bidi controls, zero-width characters, non-ASCII spaces, Default_Ignorable code points
 and U+2800. A file that is not UTF-8 text is reported too.

 WHY IT EXISTS: a generator's sources are what every generated project is built from. A code
 point that renders as nothing makes the source a reviewer reads differ from the source a
 compiler reads (Trojan Source, CVE-2021-42574), in the framework and in every project it emits.

 The non-vacuity self-test runs before every scan: every row of the shared hidden-text corpus
 must be reported at its line and column, TAB, LF and CR must pass, and planted files must
 report exactly their defects.

 Exit codes:
   0 = no hidden code point (or the self-test passed, with -SelfTest)
   1 = a hidden code point, a file that is not UTF-8, a failed self-test, or stale package installs
   2 = usage error (unknown -Repo name, no generator repo found) or a failing git command or read

.PARAMETER Repo
 Limit the scan to these generator repo names (an array or one comma-separated value). Default:
 every datrix-codegen-* repo in the workspace.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and the wrapper seam checks, and skip the real scan.

.PARAMETER Dbg
 Enable DEBUG logging and print the python invocation before running.

.EXAMPLE
 .\hidden-code-point-gate.ps1
 Check every generator repo in the workspace.

.EXAMPLE
 .\hidden-code-point-gate.ps1 -Repo datrix-codegen-angular
 Check only the named repo(s).

.EXAMPLE
 .\hidden-code-point-gate.ps1 -SelfTest
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.hidden_code_point_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
