#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Keep each duplicated test fixture once: list the plan, prove it, write it and record it.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.fixture_dedupe.cli. Over every datrix-* package's tests/ and the
 shared datrix-testing fixture set it finds the groups of one fixture: files of equal normalized content
 whose references (include, config path, .dcfg import, .dseed file) resolve to files that are one,
 recursively; and inline literals assigned to one name with equal normalized text. Each group's copy is
 placed under the corpus's shared/ directory (shared/<package>/<path>, shared/inline/<module>/<NAME>.<kind>).
 A copy stays where a test or a case collector reads its directory whole, where it is already in the shared
 set, where its bytes differ from the copy that moves, or, for a .dcfg, where the model-contract capture's
 secret screen flags it in the would-be corpus. Without -DryRun the write is proven over the planned tree
 (moved bytes, references, rewritten test sites), written, proven again on disk with every semantic
 baseline's drift, and recorded under <workspace>\.tmp\fixture-dedupe\; a failure once written puts every
 file back. Runs no git command.

 Exit codes: 0 = listed (and written and proven), 1 = a walk site or reference the plan cannot prove, or a
 failed proof (nothing written, or everything put back), 2 = usage error, an unreadable or unparsable file,
 a missing corpus, a capture that cannot run, or a semantic-baseline entry that cannot be analyzed.

.PARAMETER DryRun
 List the groups, their placements, the kept copies and the refused sites, and write nothing.

.PARAMETER BaseDir
 Workspace root (default: the workspace).

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the self-test: the dedupe rules over a planted workspace, and the wrapper seam.

.EXAMPLE
 .\dev\fixture-dedupe.ps1 -DryRun
 List the plan over the workspace.

.EXAMPLE
 .\dev\fixture-dedupe.ps1
 List, prove, write and record the plan over the workspace.

.EXAMPLE
 .\dev\fixture-dedupe.ps1 -SelfTest
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][switch]$DryRun,
 [Parameter(ParameterSetName = "Run")][string]$BaseDir,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.fixture_dedupe.cli" -Parameters $PSBoundParameters
exit $LASTEXITCODE
