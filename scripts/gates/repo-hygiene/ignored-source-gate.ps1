#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: a .gitignore rule may never shadow a publishable file.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.ignored_source_gate in the shared venv, over
 the shared scan datrix_scripts.ignored_source, which computes -- for the datrix
 showcase repo and every datrix-* clone in the workspace, discovered at
 runtime -- the set difference between the working tree and what a
 'git add -A' would stage. Every element of that difference must be a
 reviewed, scoped entry in scripts/config/ignored-source-exemptions.json;
 anything else is a source file a .gitignore rule is silently deleting from
 every clone.

 WHY IT EXISTS: a package once carried the stock Python .gitignore's
 UNANCHORED `MANIFEST` line. Git matches an unanchored pattern at ANY depth,
 and core.ignorecase=true on this platform makes it case-insensitive, so it
 matched a templates/manifest/ directory and swallowed the Jinja2 templates
 inside it. Nothing was visible locally -- the files were on disk, the tests
 passed, the emitted output compiled. The loss only appears after a clone or
 a wheel install, as a package that cannot generate. It was found by hand,
 by comparing a file count against a `git add -A --dry-run` count. This is
 that comparison, living in code.

 GIT IS THE ORACLE: ignore matching is never re-implemented here.
 `git ls-files -o -i --exclude-standard` produces the difference and
 `git check-ignore -v` names the .gitignore file, line number and pattern
 responsible, so a finding points at the line to fix rather than starting a
 hunt. Anchoring, negation (`!`), nested .gitignore files and
 core.ignorecase interact in ways a hand-rolled matcher gets wrong, and a
 wrong matcher returns a confident "clean" that will be believed.

 EXEMPTIONS ARE SCOPED: each entry excuses one rule over one path scope and
 carries a written reason. An entry for the root build/ tree does not excuse
 the same unanchored rule swallowing a templates/build/ directory of source.

 The non-vacuity self-test runs before every scan: a scanner that stopped
 scanning reports a clean tree, which is indistinguishable from a clean tree.

 Exit codes:
   0 = every unstaged working-tree path is a reviewed exemption
   1 = at least one publishable file is shadowed, or the self-test failed
   2 = usage error, or a missing/malformed/miscounted exemption file

.PARAMETER Repo
 Limit the scan to these repo names. Default: every framework repo in the workspace.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER ShowExempt
 Also print every reviewed exemption entry and its written reason.

.PARAMETER Dbg
 Enable DEBUG logging and print the python invocation before running.

.EXAMPLE
 .\ignored-source-gate.ps1
 Scan every framework repo in the workspace.

.EXAMPLE
 .\ignored-source-gate.ps1 -Repo datrix-language
 Scan only the named repo(s).

.EXAMPLE
 .\ignored-source-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\ignored-source-gate.ps1 -ShowExempt
 Print the reviewed exemption entries with their reasons, then scan.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Repo,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowExempt,

    [Parameter()]
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.ignored_source_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
