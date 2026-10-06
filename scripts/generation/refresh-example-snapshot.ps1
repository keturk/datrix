#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Refresh one committed example snapshot with one command.

.DESCRIPTION
 Generates ONE example in ONE registered language (single-project generate.ps1;
 never -All, -Domains or -TestSet) into
 D:\datrix\.tmp\example-snapshots\<example>\<language>-<platform>\, then replaces
 <example>\generated\<language>-<platform>\ with that output minus every path git
 ignores there (the repository's .datrix\ rule and the generated project's own
 .gitignore: build output, per-service secrets\). The ignore set is asked of git,
 never restated.

 <platform> is a registered datrix.platforms name taken from the example's
 resolved deployment (default profile 'test'): the provider-owned platform when
 the provider owns one (aws), otherwise the platform that emits the runtime's
 container scaffolding (docker for docker-compose). -Platform overrides it.

 Exit 2 for a refused request: a language or platform that is not registered, a
 missing source, or a deployment that resolves to no single platform.

.PARAMETER Source
 Path to the example's system.dtrx.

.PARAMETER Language
 A registered datrix.languages name.

.PARAMETER Platform
 Optional registered datrix.platforms name overriding the derived one.

.PARAMETER ConfigProfile
 Config profile that selects the deployment (default: test).

.PARAMETER SelfTest
 Run only the fixture self-test (a project with secrets\ and .datrix\ copies neither).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\refresh-example-snapshot.ps1 -Source d:\datrix\datrix\examples\03-domains\ecommerce\system.dtrx -Language python
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Source,

    [Parameter()]
    [string]$Language,

    [Parameter()]
    [string]$Platform,

    [Parameter()]
    [string]$ConfigProfile = "test",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = Join-Path $scriptDir "lib\refresh_example_snapshot.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: refresh_example_snapshot.py not found at: $runnerScript"
    exit 1
}

if (-not $SelfTest -and (-not $Source -or -not $Language)) {
    Write-Error "-Source and -Language are required unless -SelfTest is given."
    exit 2
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
    if ($SelfTest) {
        $pythonArgs += "--self-test"
    } else {
        $pythonArgs += @("--source", $Source, "--language", $Language, "--profile", $ConfigProfile)
        if ($Platform) { $pythonArgs += @("--platform", $Platform) }
    }
    if ($Dbg) { $pythonArgs += "--debug" }

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Snapshot refresh failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }
    exit 0
} finally {
    Invoke-Cleanup
}
