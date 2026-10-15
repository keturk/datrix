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
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

if (-not $SelfTest -and (-not $Source -or -not $Language)) {
    Write-Host "Error: -Source and -Language are required unless -SelfTest is given." -ForegroundColor Red
    exit 2
}

$pythonArgs = @()
if ($SelfTest) {
    $pythonArgs += "--self-test"
} else {
    $pythonArgs += @("--source", $Source, "--language", $Language, "--profile", $ConfigProfile)
    if ($Platform) { $pythonArgs += @("--platform", $Platform) }
}
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\refresh_example_snapshot.py") -Arguments $pythonArgs -RequirePackages)
