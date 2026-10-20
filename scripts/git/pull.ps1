#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Pull every Datrix repository, then summarize which pulled and which did not.

.DESCRIPTION
 The behaviour is datrix_scripts.git.pull. Pulls each git repository directly under the
 workspace root in turn, printing git's output under its name, then prints one summary
 grouping every repository by outcome:
   Updated                    new commits pulled (old..new, commit count)
   Up to date                 nothing to pull
   Conflict                   the pull stopped with unmerged paths (listed)
   Blocked by local changes   the pull would overwrite local changes or untracked
                              files (listed); nothing merged -- run /resolve-conflicts
   Failed                     anything else (no upstream, network, auth); git's error shown

 Exit codes:
   0 = every repository updated or up to date (or a passing -SelfTest)
   1 = at least one repository conflicted, was blocked, or failed (or a self-test check failed)
   2 = the run could not start

.PARAMETER SelfTest
 Pull real repositories in a temporary directory (updated, blocked, no upstream), run the census
 that no git script runs stash/reset/checkout/revert/restore, and the wrapper seam checks.

.EXAMPLE
 .\git\pull.ps1
#>
[CmdletBinding()]
param(
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.pull" -Parameters $PSBoundParameters
exit $LASTEXITCODE
