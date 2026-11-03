#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Every declared field and relationship modifier has a reader in framework source.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.modifier_vocabulary_gate in the shared venv. The closed
 modifier vocabularies (datrix_common.datrix_model.modifier_vocabulary) are what semantic
 analysis accepts after a field's or relationship's ':'; the Field and Relationship readers
 refuse an undeclared word. This gate proves the other direction: every declared word is read
 somewhere, so analysis never accepts a word every target drops.

 It AST-scans every datrix package's src/ tree (the vocabulary module excepted) for two shapes:

   A. a reference to a vocabulary constant naming the word
   B. the word as a literal passed to has_modifier()/get_modifier(), or compared with <x>.name

 The scanner's self-test runs first on every invocation -- a planted unread word must be
 reported and its fully read twin must pass -- so a scanner that can only return zero fails.

 Exit codes:
   0 = every declared word is read, or a successful -SelfTest run
   1 = a declared word has no reader
   2 = usage error, no packages discovered, a stale install, or the self-test failed

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the scanner's self-test and exit, skipping the real scan.

.PARAMETER ShowFiles
 Print each file as it is scanned.

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\modifier-vocabulary-gate.ps1
 Scan every package, fail on any declared word without a reader.

.EXAMPLE
 .\modifier-vocabulary-gate.ps1 -SelfTest
 Prove the scanner reports an unread word, without scanning the tree.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.modifier_vocabulary_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
