#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Declarative design-acceptance assertion runner over a file tree.

.DESCRIPTION
 PowerShell wrapper for conformance_gate.py. Evaluates a JSON spec of
 must_contain / must_not_contain / file_exists / file_absent / count_equals
 assertions (regex patterns, text files only) over a target tree and writes a
 per-assertion PASS/FAIL ledger to
 <workspace>\.test-output\conformance\<spec-stem>-ledger.json.
 must_not_contain supports a negative_control tree: the pattern MUST appear
 there or the assertion fails as vacuous. A built-in self-test proving every
 assertion type both detects a violation and passes a satisfied case runs as
 step 1 of every invocation (self-test failure aborts with exit 2).

.PARAMETER Spec
 Path to the conformance spec JSON.

.PARAMETER SelfTest
 Run only the built-in self-test and exit.

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\conformance-gate.ps1 my-spec.json

.EXAMPLE
 .\conformance-gate.ps1 -SelfTest
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Spec,

 [Parameter()]
 [switch]$SelfTest,

 [Parameter()]
 [string]$Output,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Spec) { $pythonArgs += @("--spec", $Spec) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\conformance_gate.py") -Arguments $pythonArgs -Gate "conformance")
