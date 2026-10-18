#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rename feature tags across every tag carrier of the package test trees, from a mapping file.

.DESCRIPTION
 Runs lib\retag.py in the shared venv. Carriers: pytest tag(...) calls (located with ast and
 rewritten at the exact literal) and fixture "@tags" header lines (.dtrx, .dcfg, .dseed).
 A rule may be scoped to named files; a tag with only scoped rules must name every file it is
 used in, or the run is refused. When the new tag is already present in the same call or header
 line, the old one is removed instead of duplicated. Preview by default (a unified diff is
 written to <workspace>\.tmp\retag\retag.diff); -Apply writes. A self-test runs first.

.PARAMETER Mapping
 The mapping JSON: {"retags": [{"from": "...", "to": "...", "paths": ["datrix-x/tests/a.py"]}]}.

.PARAMETER Apply
 Write the files. Without it, only preview.

.PARAMETER SelfTest
 Run only the self-test.

.EXAMPLE
 .\retag.ps1 -Mapping D:\datrix\.tmp\retags.json

.EXAMPLE
 .\retag.ps1 -Mapping D:\datrix\.tmp\retags.json -Apply
#>

[CmdletBinding()]
param(
 [string]$Mapping,
 [switch]$Apply,
 [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Mapping) { $pythonArgs += @("--mapping", $Mapping) }
if ($Apply) { $pythonArgs += "--apply" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\retag.py") -Arguments $pythonArgs)
