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
                  category, a skip is neither a pass nor a fail.

 A test is identified by its service and the framework-reported full test name
 exactly as the index records it, so two languages agree on a test only when
 they emit the same name for it.

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

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = Join-Path $scriptDir "lib\generated_suite_parity.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: generated_suite_parity.py not found at: $runnerScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

trap {
    Invoke-Cleanup
    break
}

Ensure-DatrixVenv

try {
    Ensure-DatrixPackagesInstalled

    $pythonArgs = @($runnerScript)
    if ($GeneratedRoot) { $pythonArgs += @("--generated-root", $GeneratedRoot) }
    if ($null -ne $ListLimit) { $pythonArgs += @("--list-limit", "$ListLimit") }
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    Write-Host "Running generated-suite parity gate (over the local unit-test indices)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Generated-suite parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Generated-suite parity gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
