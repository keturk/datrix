#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: no retired internal-DSL name appears in a Datrix framework repo.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.retired_dsl_names_gate in the shared venv, which scans
 every publishable file (tracked plus untracked-but-not-ignored) of every framework repo in
 the workspace (datrix plus every datrix-* clone, discovered from disk) -- file content,
 file names and directory names -- for the retired spellings listed in
 scripts\config\retired-dsl-names.json, and fails listing path:line per hit.

 WHY IT EXISTS: when an internal language is renamed or replaced, its old name must leave
 every identifier, module, package, entry-point group, feature tag, script, resource file
 and document. A rename that leaves stragglers keeps two names for one thing alive; this is
 the check that holds the terminal state at zero.

 The spellings file is the only path skipped. Its self-test plants every sample in a
 scratch git repo under D:\datrix\.tmp\ (content, a file name, a directory name, plus a
 git-ignored copy that must not be reported) and runs before every scan: a detector that
 stopped detecting reports a clean tree, which is indistinguishable from a clean tree.

 Exit codes:
   0 = no retired name found (or the self-test passed, with -SelfTest)
   1 = at least one retired name, or the self-test failed
   2 = usage error, a malformed spellings file, a repo git cannot list, or a file that
       cannot be read

.PARAMETER Repo
 Limit the scan to these repo names. Default: every framework repo in the workspace.

.PARAMETER SelfTest
 Run only the self-test and skip the real scan.

.PARAMETER Dbg
 Print the interpreter and arguments before running, and log at DEBUG level.

.EXAMPLE
 .\retired-dsl-names-gate.ps1
 Scan every publishable file in every framework repo.

.EXAMPLE
 .\retired-dsl-names-gate.ps1 -Repo datrix-common
 Scan only the named repo.

.EXAMPLE
 .\retired-dsl-names-gate.ps1 -SelfTest
 Run only the self-test.
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
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.retired_dsl_names_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
