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
                              files (listed); nothing merged
   Failed                     anything else (no upstream, network, auth); git's error shown

 A repository left Conflict or Blocked is handed to a Claude agent (Sonnet 5.5, medium effort)
 whose whole prompt is /resolve-conflicts <repo>, as if typed: it merges the overlap by hand and
 finishes through resolve-pull. This script then pulls the repository again and reports the new
 outcome. One repository's trouble never stops the others.

 Exit codes:
   0 = every repository updated or up to date (or a passing -SelfTest)
   1 = at least one repository conflicted, was blocked, or failed (or a self-test check failed)
   2 = the run could not start

.PARAMETER ConflictRepairAttempts
 How many times a Conflict or Blocked repository is handed to the agent before the repository is
 reported as it stands; it is pulled again after each run. Default 2; 0 reports it without an agent.

.PARAMETER ConflictRepairModel
 Claude model of the conflict agent. Default: claude-sonnet-5-5

.PARAMETER ConflictRepairEffort
 Effort level of the conflict agent: low, medium, high, xhigh or max. Default: medium. The skill's
 own frontmatter names an effort too, which may take precedence while the skill runs.

.PARAMETER ConflictRepairTimeoutMs
 Timeout (ms) for each conflict agent run. Default 3600000.

.PARAMETER SelfTest
 Pull real repositories in a temporary directory (updated, blocked, no upstream), run the census
 that no git script runs stash/reset/checkout/revert/restore, and the wrapper seam checks.

.EXAMPLE
 .\git\pull.ps1
#>
[CmdletBinding()]
param(
 [ValidateRange(0, [int]::MaxValue)]
 [int]$ConflictRepairAttempts,
 [string]$ConflictRepairModel,
 [ValidateSet('low', 'medium', 'high', 'xhigh', 'max')]
 [string]$ConflictRepairEffort,
 [int]$ConflictRepairTimeoutMs,
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
