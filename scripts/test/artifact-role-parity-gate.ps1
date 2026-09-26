#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language artifact-role parity gate.

.DESCRIPTION
 For every (example, runtime, provider) generated in >= 2 registered
 languages under the generate.ps1 output base
 (<workspace>/.generated/<language>/<runtime>/<provider>/<example>/),
 classifies each language's generated paths by domain role (via each
 language's own derived DomainDeclaration.structural_pattern) and asserts
 the set of roles with >= 1 matching file is identical across those
 languages.

 Generates NOTHING and stores NOTHING -- it reads the generation pipeline's
 own per-target manifests (.datrix/manifests/<target>.json: the files each
 target wrote, plus a generated_at stamp) from the trees generate.ps1 already
 wrote. There is no committed baseline and no re-recording step: the gate is
 exactly as current as the local corpus, prints every language's oldest and
 newest generated_at stamp, and REFUSES to run (exit 2) when any registered
 language's corpus is incomplete -- a registered example with no generated
 tree and no entry in scripts/config/parity-known-nongenerating.json -- naming
 every missing (example, language) pair. Generate the full corpus first, once
 per registered language:

   .\dev\generate.ps1 -All -L <language>

 A parked example that DOES have a generated tree is a stale park entry and
 also fails the gate: the recorded defect is fixed and the entry must go.

 Runs a built-in non-vacuity self-test on every invocation. Fails loud
 (exit 2) if zero groups are generated in >= 2 languages.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER GeneratedRoot
 The generate.ps1 output base to read. Default: <workspace>/.generated
 (generate.ps1's own default -OutputBase).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.PARAMETER Census
 Print every (language, domain) the generated corpus exercises nowhere, with
 its reviewed status from corpus-vacuity-records.json (or UNRECORDED), and
 exit 0. A measurement, not a verdict -- the gate's own verdict on the same
 data runs as part of a normal invocation. Requires a complete corpus for
 the same reason the gate does.

.EXAMPLE
 .\artifact-role-parity-gate.ps1
 Run the gate over every multi-language group under <workspace>/.generated.

.EXAMPLE
 .\artifact-role-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated
 Same, with the output base named explicitly.

.EXAMPLE
 .\artifact-role-parity-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\artifact-role-parity-gate.ps1 -Census
 Report the corpus-vacuity census against the reviewed records.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$GeneratedRoot,

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Census
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\artifact_role_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: artifact_role_parity.py not found at: $runnerScript"
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
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($Census) { $pythonArgs += "--census" }

    Write-Host "Running artifact-role parity gate (D7, over the local generated corpus)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Artifact-role parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Artifact-role parity gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
