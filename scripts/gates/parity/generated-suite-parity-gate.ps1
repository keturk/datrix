#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language generated-suite parity gate.

.DESCRIPTION
 Every registered language's generated project carries its own emitted test
 suite. For every (example, runtime, provider) unit-tested in >= 2 registered
 languages under the generate.ps1 output base
 (<workspace>/.generated/<language>/<runtime>/<provider>/<example>/), compares
 the structured result index run-complete.ps1 wrote for each language's latest
 unit-test run
 (<project>/.test_results/unit-tests-<stamp>/index.json) and reports:

   ROLE GAP       a test present in one language's suite and absent from
                  another's -- a language silently emitting nothing for
                  behaviour another language tests;
   BEHAVIOUR GAP  a test present in several languages' suites that passes in
                  one and fails (or errors) in another;
   SKIP GAP       a test one language skips and another runs -- its own
                  category, a skip is neither a pass nor a fail;
   UNIDENTIFIED   a test that carries no language-neutral case id, so it can
                  match no other language's test.

 A test is identified by its service and its language-neutral case id, which
 the index records beside the framework-reported name (from the JUnit property
 a generated pytest suite writes, or the Jest test's own title). The same test
 of the same item carries the same case id in every language, so module
 paths, describe titles and wording never decide whether two languages test
 the same thing.

 Generates NOTHING and runs NOTHING -- reads existing index.json files only.
 There is no committed baseline: the gate is exactly as current as the local
 corpus, prints every language's oldest and newest index timestamp, and REFUSES
 to run (exit 2) when the evidence is incomplete: a registered language with no
 unit-tests index for an example another language has one for (and no entry in
 scripts/config/parity-known-nongenerating.json), an index written before
 per-test records existed, a service whose per-test records do not account for
 its counts, a service whose spec files never ran, or fewer than two registered
 languages. Run each language's unit tests for the full corpus first (Jon runs
 this -- the gate never runs a suite itself):

   .\test\run-complete.ps1 -All -L <language> -Skip4

 Only unit-test runs are compared; a deploy-test index records the docker
 lifecycle phases of a live stack, not a flat per-test suite.

 Runs a built-in non-vacuity self-test on every invocation. Fails loud
 (exit 2) if no (example, runtime, provider) is unit-tested in >= 2 languages.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER GeneratedRoot
 The generate.ps1 output base to read. Default: <workspace>/.generated
 (generate.ps1's own default -OutputBase).

.PARAMETER ListLimit
 Gaps listed per (example group, gap kind) before the report summarizes the
 rest. Default: 10.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\generated-suite-parity-gate.ps1
 Run the gate over every multi-language group under <workspace>/.generated.

.EXAMPLE
 .\generated-suite-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated -ListLimit 50
 Same, with the output base named explicitly and up to 50 gaps listed per kind.

.EXAMPLE
 .\generated-suite-parity-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$GeneratedRoot,

    [Parameter()]
    [Nullable[int]]$ListLimit,

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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.parity.generated_suite_parity_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
