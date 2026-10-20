#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Response-body transform census gate.

.DESCRIPTION
 The response-bodies parity rows prove every registered language's response classes
 emit camelCase wire keys; a framework-level transform applied AFTER serialization
 (a global interceptor, a response-model setting) is invisible to them. Each
 registered language declares the code idioms that spell such a transform in its
 framework (LanguageCapabilityDeclaration.response_body_transform_idioms: parsed facts,
 never regular expressions). This gate generates the shared CQRS example once per
 registered language, reads the emitted source files for them through the language's
 own conformance probes (a parse-tree reading: a string literal or a comment neither
 hides nor fakes a hit, and a file that does not parse fails the run), and requires
 every hit to be a typed `transform_exemptions`
 entry of datrix/scripts/config/response-body-transform-exemptions.json (language,
 path suffix, matched text, reason). An unreviewed hit, a stale entry and a language
 with no declaration each fail by name; the review file is refused if it carries any
 key other than _comment and transform_exemptions.

 The gate holds no pattern over code. Derives its language set from the installed
 `datrix.languages` entry points -- never a hardcoded literal.

 Runs a self-test on every invocation: the gate names no target, a planted reading is
 reported at its coordinates and the reading is asked for exactly the declared idioms,
 an exemption covers it, a stale exemption and a language with no declaration are
 reported, every registered language supplies a probe reading, the review file refuses a set-aside list,
 a non-object entry and a blank reason, and fewer than two languages refuse the run.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the self-test and skip generation.

.EXAMPLE
 .\response-body-transform-census-gate.ps1
 Census every registered language.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.parity.response_body_transform_census_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
