#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Zero-environment runtime census gate -- every registered language is
 obligated to bake deployment-static values at generation time, and its
 baseline entry kind decides how its environment reads are held.

.DESCRIPTION
 The zero-environment runtime architecture bakes every deployment-static value
 into literal constants at generation time; the running service consults no
 environment variable. Every registered language is obligated to it. Each
 language plugin states, on its LanguageCapabilityDeclaration
 (zero_environment_runtime), the code idioms that spell an environment read in
 the code it emits (parsed facts such as a member access or an import, never
 regular expressions). This gate generates the registered `serverless` example
 for each registered language, reads every emitted source file through the
 language's own conformance probes (a parse-tree reading: a string literal or a
 comment neither hides nor fakes a read, and a file that does not parse fails
 the run), and holds each language to the rule the KIND of its entry in
 scripts/config/zero-environment-runtime-baseline.json selects:

   * reviewed_exemptions -- every emitted file that reads the environment is
     listed by its path relative to the generated root, with a written reason;
     an unlisted read and a stale entry are both violations, and the live
     census must read at least one listed file. A language with no entry is
     held to this kind with an empty list;
   * pinned_count -- a decrease-only count of environment-reading emitted files,
     for a language that delivers runtime facts through the environment by
     design; it may fall and may never rise;
   * a registered language that states no idioms fails, named, and a baseline
     entry naming an unregistered language is stale and fails.

 Language set from the installed datrix.languages entry points at runtime;
 idioms from each language's own declaration -- never a table here. Runs a
 built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (lists every environment read in the emitted files).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.PARAMETER UpdateBaseline
 Lower every pinned_count entry to its live census (the only writer of
 pinned_count values; it refuses to raise one). reviewed_exemptions entries are
 hand-authored and left untouched.

.EXAMPLE
 .\zero-environment-runtime-gate.ps1

.EXAMPLE
 .\zero-environment-runtime-gate.ps1 -UpdateBaseline
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$UpdateBaseline
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.realization.zero_environment_runtime_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
