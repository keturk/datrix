#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Example config load gate: every declared profile of every example .dcfg loads,
 and every example analyzes under every leaf profile of its system config.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.example_config_load_gate in the shared venv.

 Every model a config document validates into rejects unknown keys, so a
 key the model does not declare is an error at load time rather than a value
 silently dropped. This gate loads every declared profile of every .dcfg
 under datrix/examples through the real loaders (service, shared, system,
 identity, app, strings, extern) and fails on any error, so a misspelled or
 retired key in the corpus is found here.

 Every example whose configs all load is then parsed, config-resolved and
 semantically analyzed (the front half of a generation run) under every leaf
 profile of its system config -- a profile no other profile extends -- and
 fails on any error diagnostic, so a config that loads but breaks a semantic
 rule on a profile nobody generates by default is found here too.

 Runs a built-in non-vacuity self-test on every invocation: a planted temp
 .dcfg carrying an unknown nested key must be reported (key named, value not
 echoed) and its clean twin must load; a planted project whose pooled
 messaging block sizes itself must be reported with POOL002 under its leaf
 profile only, and its clean twin must analyze clean. Fails loud (exit 2) if
 zero .dcfg or system.dtrx files exist on disk.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable DEBUG logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real check.

.EXAMPLE
 .\example-config-load-gate.ps1
 Load every declared profile of every example .dcfg and analyze every example
 under every leaf profile.

.EXAMPLE
 .\example-config-load-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.example_config_load_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
